import os
import asyncio
import logging
import mimetypes
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import BOT_TOKEN, MODERATOR_IDS, TARGET_CHANNEL
from database import get_session, News, init_db

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)


class ReviewStates(StatesGroup):
    waiting_for_review = State()
    waiting_for_edit_text = State()


@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    if message.from_user.id not in MODERATOR_IDS:
        await message.reply("У вас нет доступа к этому боту.")
        return
    
    await message.reply(
        "Привет! Я бот для модерации новостей из телеграм-каналов.\n\n"
        "Я буду автоматически присылать вам новости, как только они появятся в отслеживаемых каналах. "
        "Вы сможете сразу одобрить или отредактировать их."
    )


@dp.message_handler(commands=['help'])
async def cmd_help(message: types.Message):
    """Обработчик команды /help"""
    if message.from_user.id not in MODERATOR_IDS:
        await message.reply("У вас нет доступа к этому боту.")
        return
    
    await message.reply(
        "🤖 <b>Помощь по использованию бота</b>\n\n"
        "Я автоматически присылаю вам новости из отслеживаемых каналов.\n\n"
        "<b>Доступные команды:</b>\n"
        "/start - Запуск бота\n"
        "/help - Показать справку\n"
        "/stats - Статистика модерации\n\n"
        "<b>Действия с новостями:</b>\n"
        "✅ <i>Одобрить</i> - Новость будет опубликована в целевой канал\n"
        "✏️ <i>Редактировать</i> - Изменить текст новости перед публикацией\n"
        "✏️ <i>Редактировать (опубликованную)</i> - Изменить текст уже опубликованной новости\n"
        "🔄 <i>Восстановить оригинал</i> - Вернуть текст новости к исходному состоянию\n"
        "🗑️ <i>Удалить</i> - Удалить опубликованную новость из канала (она вернется в очередь на публикацию)\n\n"
        "Новости публикуются в канал <b>{}</b>".format(TARGET_CHANNEL),
        parse_mode="HTML"
    )


@dp.message_handler(commands=['stats'])
async def cmd_stats(message: types.Message):
    """Показывает статистику модерации"""
    if message.from_user.id not in MODERATOR_IDS:
        await message.reply("У вас нет доступа к этому боту.")
        return
    
    session = get_session()
    
    # Получаем статистику
    total_news = session.query(News).count()
    published_news = session.query(News).filter(News.is_published == True).count()
    pending_news = session.query(News).filter(News.is_published == False).count()
    
    # Формируем сообщение со статистикой
    stats_message = (
        "📊 <b>Статистика модерации</b>\n\n"
        f"Всего новостей: <b>{total_news}</b>\n"
        f"Опубликовано: <b>{published_news}</b>\n"
        f"Ожидает публикации: <b>{pending_news}</b>\n"
    )
    
    await message.reply(stats_message, parse_mode="HTML")


@dp.callback_query_handler(lambda c: c.data.startswith('edit_'))
async def process_edit_callback(callback_query: types.CallbackQuery, state: FSMContext):
    """Обрабатывает запрос на редактирование новости"""
    user_id = callback_query.from_user.id
    if user_id not in MODERATOR_IDS:
        await bot.answer_callback_query(callback_query.id, "У вас нет доступа.")
        return
    
    # Получаем ID новости из callback_data
    callback_data = callback_query.data
    
    # Проверяем, это редактирование опубликованной новости или еще не опубликованной
    is_published_edit = False
    if callback_data.startswith('edit_published_'):
        news_id = int(callback_data.split('_')[2])
        is_published_edit = True
    else:
        news_id = int(callback_data.split('_')[1])
    
    session = get_session()
    news = session.query(News).filter(News.id == news_id).first()
    
    if not news:
        await bot.answer_callback_query(callback_query.id, "Новость не найдена.")
        return
    
    # Сохраняем ID новости, флаг опубликованной новости и ID сообщения в состоянии
    await state.update_data(
        news_id=news_id, 
        is_published_edit=is_published_edit,
        original_message_id=callback_query.message.message_id,
        original_chat_id=callback_query.message.chat.id
    )
    
    # Переходим в состояние ожидания нового текста
    await ReviewStates.waiting_for_edit_text.set()
    
    # Отвечаем на callback
    await bot.answer_callback_query(callback_query.id)
    
    # Отправляем сообщение с просьбой ввести новый текст
    edit_type = "опубликованной " if is_published_edit else ""
    request_msg = await bot.send_message(
        callback_query.from_user.id,
        f"Отправьте новый текст для {edit_type}новости №{news_id}.\n\nТекущий текст:\n\n{news.content}",
        parse_mode="HTML"
    )
    
    # Сохраняем ID сообщения с запросом для последующего удаления
    await state.update_data(request_message_id=request_msg.message_id)


@dp.callback_query_handler(lambda c: c.data.startswith('restore_original_'))
async def process_restore_original(callback_query: types.CallbackQuery):
    """Обрабатывает запрос на восстановление оригинального текста новости"""
    user_id = callback_query.from_user.id
    if user_id not in MODERATOR_IDS:
        await bot.answer_callback_query(callback_query.id, "У вас нет доступа.")
        return
    
    # Получаем ID новости из callback_data
    news_id = int(callback_query.data.split('_')[2])
    
    session = get_session()
    news = session.query(News).filter(News.id == news_id).first()
    
    if not news:
        await bot.answer_callback_query(callback_query.id, "Новость не найдена.")
        return
    
    if not news.original_content:
        await bot.answer_callback_query(callback_query.id, "Оригинальный текст не найден.")
        return
    
    # Получаем оригинальный текст и текущий текст для информирования
    old_content = news.content
    original_content = news.original_content
    
    # Восстанавливаем оригинальный текст
    news.content = original_content
    session.commit()
    
    await bot.answer_callback_query(callback_query.id, "Текст восстановлен до оригинального.")
    
    # Определяем тип сообщения (опубликованное или нет)
    is_published = news.is_published and news.published_message_id
    
    # Обновляем текст в целевом канале, если новость была опубликована
    if is_published:
        try:
            # Создаем правильный формат имени канала
            target_channel = TARGET_CHANNEL
            if target_channel and not target_channel.startswith('@') and not target_channel.startswith('-'):
                if not target_channel.isdigit():  # Если это не числовой ID
                    target_channel = f'@{target_channel}'  # Добавляем @ если это username без @
            
            # Обновляем сообщение в канале
            if news.has_media and news.media_path and os.path.exists(news.media_path):
                # Читаем файл в память
                with open(news.media_path, 'rb') as file:
                    file_content = file.read()
                
                # Обработка разных типов медиа
                if news.media_type == 'photo':
                    await bot.edit_message_media(
                        chat_id=target_channel,
                        message_id=news.published_message_id,
                        media=types.InputMediaPhoto(
                            media=file_content,
                            caption=news.content
                        )
                    )
                else:  # document
                    # Определяем тип файла
                    mime_type = mimetypes.guess_type(news.media_path)[0]
                    
                    # Если это изображение, отправляем как фото для лучшего отображения
                    if mime_type and mime_type.startswith('image/'):
                        await bot.edit_message_media(
                            chat_id=target_channel,
                            message_id=news.published_message_id,
                            media=types.InputMediaPhoto(
                                media=file_content,
                                caption=news.content
                            )
                        )
                    else:
                        await bot.edit_message_media(
                            chat_id=target_channel,
                            message_id=news.published_message_id,
                            media=types.InputMediaDocument(
                                media=file_content,
                                caption=news.content
                            )
                        )
            else:
                # Обновляем только текст
                await bot.edit_message_text(
                    chat_id=target_channel,
                    message_id=news.published_message_id,
                    text=news.content
                )
        except Exception as e:
            logger.error(f"Ошибка при обновлении опубликованной новости: {e}")
    
    # Формируем сообщение об успешном обновлении
    success_message = f"✅ Текст новости №{news_id} восстановлен до оригинального{' и обновлен в канале' if is_published else ''}."
    
    # Формируем новую клавиатуру в зависимости от статуса новости
    if is_published:
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("Опубликовано", callback_data=f"dummy_{news_id}"),
            InlineKeyboardButton("Редактировать", callback_data=f"edit_published_{news_id}"),
            InlineKeyboardButton("Удалить", callback_data=f"delete_{news_id}")
        )
    else:
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("Опубликовать", callback_data=f"approve_{news_id}"),
            InlineKeyboardButton("Редактировать", callback_data=f"edit_{news_id}")
        )
    
    # Добавляем кнопку восстановления оригинала, если текущий текст отличается от оригинального
    if news.content != news.original_content:
        markup.add(InlineKeyboardButton("Восстановить оригинал", callback_data=f"restore_original_{news_id}"))
    
    # Формируем новое сообщение с обновленным текстом
    message_text = (
        f"📢 <b>Новость №{news.id}</b> из канала <b>{news.source_channel}</b> "
        f"(восстановлен оригинал):\n\n{news.content}\n\n{success_message}"
    )
    
    # Обновляем сообщение с новостью у модератора
    try:
        # Обновляем оригинальное сообщение
        if news.has_media and news.media_path and os.path.exists(news.media_path):
            # Читаем файл в память
            with open(news.media_path, 'rb') as file:
                file_content = file.read()
            
            mime_type = mimetypes.guess_type(news.media_path)[0]
            
            # Если это фото или документ-изображение, обновляем как фото
            if news.media_type == 'photo' or (mime_type and mime_type.startswith('image/')):
                await bot.edit_message_media(
                    chat_id=callback_query.message.chat.id,
                    message_id=callback_query.message.message_id,
                    media=types.InputMediaPhoto(
                        media=file_content,
                        caption=message_text,
                        parse_mode="HTML"
                    ),
                    reply_markup=markup
                )
            else:
                # Иначе обновляем как документ
                await bot.edit_message_media(
                    chat_id=callback_query.message.chat.id,
                    message_id=callback_query.message.message_id,
                    media=types.InputMediaDocument(
                        media=file_content,
                        caption=message_text,
                        parse_mode="HTML"
                    ),
                    reply_markup=markup
                )
        else:
            # Обновляем только текст оригинального сообщения
            await bot.edit_message_text(
                chat_id=callback_query.message.chat.id,
                message_id=callback_query.message.message_id,
                text=message_text,
                parse_mode="HTML",
                reply_markup=markup
            )
    except Exception as e:
        logger.error(f"Ошибка при обновлении сообщения с новостью после восстановления: {e}")
        # В случае ошибки пытаемся хотя бы обновить кнопки
        try:
            await bot.edit_message_reply_markup(
                chat_id=callback_query.message.chat.id,
                message_id=callback_query.message.message_id,
                reply_markup=markup
            )
        except Exception as e2:
            logger.error(f"Дополнительная ошибка при обновлении кнопок: {e2}")


@dp.message_handler(state=ReviewStates.waiting_for_edit_text)
async def process_edit_text(message: types.Message, state: FSMContext):
    """Обрабатывает ввод нового текста для новости"""
    user_id = message.from_user.id
    if user_id not in MODERATOR_IDS:
        await message.reply("У вас нет доступа к этому боту.")
        return
    
    # Получаем данные из состояния
    data = await state.get_data()
    news_id = data.get('news_id')
    is_published_edit = data.get('is_published_edit', False)
    original_message_id = data.get('original_message_id')
    original_chat_id = data.get('original_chat_id')
    request_message_id = data.get('request_message_id')
    
    # Получаем новость из базы данных
    session = get_session()
    news = session.query(News).filter(News.id == news_id).first()
    
    if not news:
        await message.reply("Новость не найдена.")
        await state.finish()
        return
    
    # Обновляем текст новости
    old_content = news.content
    news.content = message.text
    session.commit()
    
    # Сбрасываем состояние
    await state.finish()
    
    # Формируем сообщение об успешном обновлении
    success_message = (
        f"✅ Текст {'опубликованной ' if is_published_edit else ''}новости №{news_id} "
        f"успешно обновлен{' в канале' if is_published_edit and news.is_published else ''}."
    )
    
    # Если это было редактирование опубликованной новости
    if is_published_edit and news.is_published and news.published_message_id:
        try:
            # Создаем правильный формат имени канала
            target_channel = TARGET_CHANNEL
            if target_channel and not target_channel.startswith('@') and not target_channel.startswith('-'):
                if not target_channel.isdigit():  # Если это не числовой ID
                    target_channel = f'@{target_channel}'  # Добавляем @ если это username без @
            
            # Обновляем сообщение в канале
            if news.has_media and news.media_path and os.path.exists(news.media_path):
                logger.info(f"Обновление опубликованной новости {news.id} с медиа")
                
                # Читаем файл в память
                with open(news.media_path, 'rb') as file:
                    file_content = file.read()
                
                # Обработка разных типов медиа
                if news.media_type == 'photo':
                    await bot.edit_message_media(
                        chat_id=target_channel,
                        message_id=news.published_message_id,
                        media=types.InputMediaPhoto(
                            media=file_content,
                            caption=news.content
                        )
                    )
                else:  # document
                    # Определяем тип файла
                    mime_type = mimetypes.guess_type(news.media_path)[0]
                    
                    # Если это изображение, отправляем как фото для лучшего отображения
                    if mime_type and mime_type.startswith('image/'):
                        await bot.edit_message_media(
                            chat_id=target_channel,
                            message_id=news.published_message_id,
                            media=types.InputMediaPhoto(
                                media=file_content,
                                caption=news.content
                            )
                        )
                    else:
                        await bot.edit_message_media(
                            chat_id=target_channel,
                            message_id=news.published_message_id,
                            media=types.InputMediaDocument(
                                media=file_content,
                                caption=news.content
                            )
                        )
            else:
                # Обновляем только текст
                await bot.edit_message_text(
                    chat_id=target_channel,
                    message_id=news.published_message_id,
                    text=news.content
                )
            
            # Клавиатура для опубликованной новости
            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(
                InlineKeyboardButton("Опубликовано", callback_data=f"dummy_{news_id}"),
                InlineKeyboardButton("Редактировать", callback_data=f"edit_published_{news_id}"),
                InlineKeyboardButton("Удалить", callback_data=f"delete_{news_id}")
            )
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении опубликованной новости: {e}")
            success_message = f"❌ Ошибка при обновлении опубликованной новости: {e}"
            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(
                InlineKeyboardButton("Опубликовано", callback_data=f"dummy_{news_id}"),
                InlineKeyboardButton("Редактировать", callback_data=f"edit_published_{news_id}"),
                InlineKeyboardButton("Удалить", callback_data=f"delete_{news_id}")
            )
    else:
        # Клавиатура для неопубликованной новости
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("Опубликовать", callback_data=f"approve_{news_id}"),
            InlineKeyboardButton("Редактировать", callback_data=f"edit_{news_id}")
        )
    
    # Добавляем кнопку восстановления оригинала, если текущий текст отличается от оригинального
    if news.content != news.original_content:
        markup.add(InlineKeyboardButton("Восстановить оригинал", callback_data=f"restore_original_{news_id}"))
    
    # Формируем новое сообщение с обновленным текстом и информацией об обновлении
    message_text = (
        f"📢 <b>Новость №{news.id}</b> из канала <b>{news.source_channel}</b> (отредактирована):\n\n"
        f"{news.content}\n\n"
        f"{success_message}"
    )
    
    try:
        # Обновляем оригинальное сообщение
        if news.has_media and news.media_path and os.path.exists(news.media_path):
            logger.info(f"Обновление сообщения новости {news.id} с медиа")
            
            # Читаем файл в память
            with open(news.media_path, 'rb') as file:
                file_content = file.read()
            
            mime_type = mimetypes.guess_type(news.media_path)[0]
            
            # Если это фото или документ-изображение, обновляем как фото
            if news.media_type == 'photo' or (mime_type and mime_type.startswith('image/')):
                await bot.edit_message_media(
                    chat_id=original_chat_id,
                    message_id=original_message_id,
                    media=types.InputMediaPhoto(
                        media=file_content,
                        caption=message_text,
                        parse_mode="HTML"
                    ),
                    reply_markup=markup
                )
            else:
                # Иначе обновляем как документ
                await bot.edit_message_media(
                    chat_id=original_chat_id,
                    message_id=original_message_id,
                    media=types.InputMediaDocument(
                        media=file_content,
                        caption=message_text,
                        parse_mode="HTML"
                    ),
                    reply_markup=markup
                )
        else:
            # Обновляем только текст оригинального сообщения
            await bot.edit_message_text(
                chat_id=original_chat_id,
                message_id=original_message_id,
                text=message_text,
                parse_mode="HTML",
                reply_markup=markup
            )
    except Exception as e:
        logger.error(f"Ошибка при обновлении сообщения с новостью: {e}")
        # В случае ошибки пытаемся хотя бы обновить кнопки
        try:
            await bot.edit_message_reply_markup(
                chat_id=original_chat_id,
                message_id=original_message_id,
                reply_markup=markup
            )
        except Exception as e2:
            logger.error(f"Дополнительная ошибка при обновлении кнопок: {e2}")
    
    # Удаляем сообщение пользователя с новым текстом
    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    except Exception as e:
        logger.error(f"Не удалось удалить сообщение пользователя: {e}")
    
    # Удаляем сообщение-запрос от бота
    if request_message_id:
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=request_message_id)
        except Exception as e:
            logger.error(f"Не удалось удалить сообщение-запрос: {e}")


@dp.callback_query_handler(lambda c: c.data.startswith(('approve_', 'delete_', 'dummy_')))
async def process_review_callback(callback_query: types.CallbackQuery):
    """Обрабатывает результаты рецензирования и удаления"""
    user_id = callback_query.from_user.id
    if user_id not in MODERATOR_IDS:
        await bot.answer_callback_query(callback_query.id, "У вас нет доступа.")
        return
    
    parts = callback_query.data.split('_')
    action = parts[0]
    news_id = int(parts[1])
    
    session = get_session()
    news = session.query(News).filter(News.id == news_id).first()
    
    if not news:
        await bot.answer_callback_query(callback_query.id, "Новость не найдена.")
        return
    
    if action == 'approve':
        # Одобряем и публикуем новость
        news.is_reviewed = True
        news.is_approved = True
        session.commit()
        
        await bot.answer_callback_query(callback_query.id, "Новость одобрена и публикуется...")
        
        # Публикуем новость
        try:
            published_msg = await publish_news(news)
            if published_msg:
                news.is_published = True
                news.published_message_id = published_msg.message_id
                session.commit()
                
                # Обновляем клавиатуру с кнопками
                markup = InlineKeyboardMarkup(row_width=2)
                markup.add(
                    InlineKeyboardButton("Опубликовано", callback_data=f"dummy_{news.id}"),
                    InlineKeyboardButton("Редактировать", callback_data=f"edit_published_{news.id}"),
                    InlineKeyboardButton("Удалить", callback_data=f"delete_{news.id}")
                )
                
                # Добавляем кнопку восстановления оригинала, если текущий текст отличается от оригинального
                if news.content != news.original_content:
                    markup.add(InlineKeyboardButton("Восстановить оригинал", callback_data=f"restore_original_{news.id}"))
                
                await bot.edit_message_reply_markup(
                    chat_id=callback_query.message.chat.id,
                    message_id=callback_query.message.message_id,
                    reply_markup=markup
                )
                
        except Exception as e:
            logger.error(f"Ошибка при публикации новости {news.id}: {e}")
            await bot.answer_callback_query(callback_query.id, f"Ошибка при публикации: {e}")
            # Возвращаем статус новости
            news.is_reviewed = False
            news.is_approved = False
            session.commit()
            
    elif action == 'delete':
        # Удаляем опубликованную новость из целевого канала
        if news.is_published and news.published_message_id:
            try:
                # Создаем правильный формат имени канала
                target_channel = TARGET_CHANNEL
                if target_channel and not target_channel.startswith('@') and not target_channel.startswith('-'):
                    if not target_channel.isdigit():  # Если это не числовой ID
                        target_channel = f'@{target_channel}'  # Добавляем @ если это username без @
                
                # Удаляем сообщение из канала
                await bot.delete_message(
                    chat_id=target_channel,
                    message_id=news.published_message_id
                )
                
                # Обновляем статус в базе данных - возвращаем новость в исходное состояние
                news.is_published = False
                news.published_message_id = None
                news.is_reviewed = False
                news.is_approved = False
                session.commit()
                
                await bot.answer_callback_query(callback_query.id, "Новость удалена из канала и возвращена в очередь на публикацию.")
                
                # Обновляем клавиатуру для возможности редактирования и повторной публикации
                markup = InlineKeyboardMarkup(row_width=2)
                markup.add(
                    InlineKeyboardButton("Опубликовать", callback_data=f"approve_{news.id}"),
                    InlineKeyboardButton("Редактировать", callback_data=f"edit_{news.id}")
                )
                
                # Добавляем кнопку восстановления оригинала, если текущий текст отличается от оригинального
                if news.content != news.original_content:
                    markup.add(InlineKeyboardButton("Восстановить оригинал", callback_data=f"restore_original_{news.id}"))
                
                await bot.edit_message_reply_markup(
                    chat_id=callback_query.message.chat.id,
                    message_id=callback_query.message.message_id,
                    reply_markup=markup
                )
                
            except Exception as e:
                logger.error(f"Ошибка при удалении новости из канала: {e}")
                await bot.answer_callback_query(callback_query.id, f"Ошибка при удалении: {e}")
        else:
            await bot.answer_callback_query(callback_query.id, "Эта новость не была опубликована.")
    
    elif action == 'dummy':
        # Для неактивных кнопок, просто закрываем запрос
        await bot.answer_callback_query(callback_query.id)


@dp.callback_query_handler(lambda c: c.data.startswith('dummy_'))
async def process_dummy_callback(callback_query: types.CallbackQuery):
    """Обрабатывает нажатия на неактивные кнопки"""
    await bot.answer_callback_query(callback_query.id, "Действие уже выполнено.")


async def publish_news(news):
    """Публикует новость в целевой канал через бота"""
    try:
        # Создаем правильный формат имени канала, если это username
        target_channel = TARGET_CHANNEL
        if target_channel and not target_channel.startswith('@') and not target_channel.startswith('-'):
            if not target_channel.isdigit():  # Если это не числовой ID
                target_channel = f'@{target_channel}'  # Добавляем @ если это username без @
        
        if news.has_media and news.media_path and os.path.exists(news.media_path):
            logger.info(f"Публикация новости {news.id} с медиафайлом {news.media_path} в канал {target_channel}")
            
            # Читаем файл в память перед отправкой
            with open(news.media_path, 'rb') as file:
                file_content = file.read()
            
            logger.info(f"Файл {news.media_path} прочитан в память для публикации, размер: {len(file_content)} байт")
            
            # Отправляем сообщение с медиа через бота
            if news.media_type == 'photo':
                return await bot.send_photo(
                    chat_id=target_channel,
                    photo=file_content,
                    caption=news.content
                )
            elif news.media_type == 'document':
                # Определяем тип файла
                mime_type = mimetypes.guess_type(news.media_path)[0]
                
                # Если это изображение, отправляем как фото для лучшего отображения
                if mime_type and mime_type.startswith('image/'):
                    return await bot.send_photo(
                        chat_id=target_channel,
                        photo=file_content,
                        caption=news.content
                    )
                else:
                    return await bot.send_document(
                        chat_id=target_channel,
                        document=file_content,
                        caption=news.content
                    )
        else:
            # Отправляем текстовое сообщение через бота
            logger.info(f"Публикация текстовой новости {news.id} в канал {target_channel}")
            return await bot.send_message(
                chat_id=target_channel,
                text=news.content
            )
    except Exception as e:
        logger.error(f"Ошибка при публикации новости {news.id}: {e}")
        raise


async def main():
    """Основная функция запуска бота"""
    # Инициализация базы данных
    init_db()
    
    # Проверяем, может ли бот публиковать в целевой канал
    try:
        # Создаем правильный формат имени канала, если это username
        target_channel = TARGET_CHANNEL
        if target_channel and not target_channel.startswith('@') and not target_channel.startswith('-'):
            if not target_channel.isdigit():  # Если это не числовой ID
                target_channel = f'@{target_channel}'  # Добавляем @ если это username без @
        
        chat_info = await bot.get_chat(target_channel)
        logger.info(f"Бот подключен к каналу: {chat_info.title}")
        
        # Проверяем права бота в канале
        bot_member = await bot.get_chat_member(target_channel, (await bot.get_me()).id)
        if bot_member.is_chat_admin():
            logger.info("Бот имеет права администратора в канале для публикации.")
        else:
            logger.warning("Бот не имеет прав администратора в канале! Добавьте бота как администратора канала.")
    except Exception as e:
        logger.error(f"Ошибка при проверке доступа к каналу: {e}")
        logger.warning("Убедитесь, что бот добавлен в канал и имеет необходимые права.")
    
    # Запуск бота
    await dp.start_polling()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("Бот остановлен.")
    finally:
        loop.close() 