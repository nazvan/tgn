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
        "Вы сможете сразу одобрить или отклонить их."
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
        "❌ <i>Отклонить</i> - Новость не будет опубликована\n"
        "🗑️ <i>Удалить</i> - Удалить опубликованную новость из целевого канала\n\n"
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
    reviewed_news = session.query(News).filter(News.is_reviewed == True).count()
    approved_news = session.query(News).filter(News.is_approved == True).count()
    rejected_news = session.query(News).filter(News.is_reviewed == True, News.is_approved == False).count()
    pending_news = session.query(News).filter(News.is_reviewed == False).count()
    published_news = session.query(News).filter(News.is_published == True).count()
    
    # Формируем сообщение со статистикой
    stats_message = (
        "📊 <b>Статистика модерации</b>\n\n"
        f"Всего новостей: <b>{total_news}</b>\n"
        f"Просмотрено: <b>{reviewed_news}</b>\n"
        f"Одобрено: <b>{approved_news}</b>\n"
        f"Отклонено: <b>{rejected_news}</b>\n"
        f"Ожидает проверки: <b>{pending_news}</b>\n"
        f"Опубликовано: <b>{published_news}</b>"
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
    news_id = int(callback_query.data.split('_')[1])
    
    session = get_session()
    news = session.query(News).filter(News.id == news_id).first()
    
    if not news:
        await bot.answer_callback_query(callback_query.id, "Новость не найдена.")
        return
    
    # Если новость уже опубликована, нельзя редактировать
    if news.is_published:
        await bot.answer_callback_query(callback_query.id, "Нельзя редактировать опубликованную новость.")
        return
    
    # Сохраняем ID новости в состоянии
    await state.update_data(news_id=news_id)
    
    # Переходим в состояние ожидания нового текста
    await ReviewStates.waiting_for_edit_text.set()
    
    # Отвечаем на callback
    await bot.answer_callback_query(callback_query.id)
    
    # Отправляем сообщение с просьбой ввести новый текст
    await bot.send_message(
        callback_query.from_user.id,
        f"Отправьте новый текст для новости №{news_id}.\n\nТекущий текст:\n\n{news.content}",
        parse_mode="HTML"
    )


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
    
    # Отправляем сообщение об успешном обновлении
    await message.reply(
        f"✅ Текст новости №{news_id} успешно обновлен.\n\n"
        f"<b>Было:</b>\n{old_content}\n\n"
        f"<b>Стало:</b>\n{news.content}",
        parse_mode="HTML"
    )
    
    # Отправляем новую клавиатуру с кнопками для одобрения/отклонения
    markup = InlineKeyboardMarkup(row_width=3)
    markup.add(
        InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{news_id}"),
        InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit_{news_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{news_id}")
    )
    
    # Формируем новое сообщение с обновленным текстом
    message_text = f"📢 <b>Новость №{news.id}</b> из канала <b>{news.source_channel}</b> (отредактирована):\n\n{news.content}"
    
    try:
        # Если у новости есть медиа, отправляем с медиа
        if news.has_media and news.media_path and os.path.exists(news.media_path):
            logger.info(f"Отправка отредактированной новости {news.id} с медиа {news.media_path}")
            
            if news.media_type == 'photo':
                try:
                    # Сначала читаем файл в память
                    with open(news.media_path, 'rb') as file:
                        file_content = file.read()
                    
                    logger.info(f"Файл {news.media_path} прочитан в память, размер: {len(file_content)} байт")
                    
                    # Отправляем фото из памяти
                    await message.answer_photo(
                        photo=file_content,
                        caption=message_text,
                        reply_markup=markup,
                        parse_mode="HTML"
                    )
                    logger.info(f"Фото для новости {news.id} успешно отправлено после редактирования")
                except Exception as e:
                    logger.error(f"Ошибка при отправке фото после редактирования: {e}")
                    # Отправляем текст без фото при ошибке
                    await message.answer(
                        f"{message_text}\n\n⚠️ <i>Не удалось отобразить фото: {str(e)}</i>", 
                        reply_markup=markup, 
                        parse_mode="HTML"
                    )
            elif news.media_type == 'document':
                try:
                    # Сначала читаем файл в память
                    with open(news.media_path, 'rb') as file:
                        file_content = file.read()
                    
                    # Определяем тип файла для корректного отображения
                    mime_type = mimetypes.guess_type(news.media_path)[0]
                    filename = os.path.basename(news.media_path)
                    
                    logger.info(f"Документ {filename} прочитан в память, размер: {len(file_content)} байт, тип: {mime_type}")
                    
                    if mime_type and mime_type.startswith('image/'):
                        # Если это изображение, отправляем как фото для лучшего отображения
                        await message.answer_photo(
                            photo=file_content, 
                            caption=message_text, 
                            reply_markup=markup, 
                            parse_mode="HTML"
                        )
                    else:
                        # Иначе отправляем как документ
                        await message.answer_document(
                            document=file_content, 
                            caption=message_text, 
                            reply_markup=markup, 
                            parse_mode="HTML"
                        )
                    logger.info(f"Документ для новости {news.id} успешно отправлен после редактирования")
                except Exception as e:
                    logger.error(f"Ошибка при отправке документа после редактирования: {e}")
                    # Отправляем текст без документа при ошибке
                    await message.answer(
                        f"{message_text}\n\n⚠️ <i>Не удалось отобразить документ: {str(e)}</i>", 
                        reply_markup=markup, 
                        parse_mode="HTML"
                    )
        else:
            # Иначе отправляем просто текст
            logger.info(f"Отправка отредактированной новости {news.id} без медиа")
            await message.answer(message_text, reply_markup=markup, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Общая ошибка при отправке отредактированной новости {news.id}: {e}")
        # Гарантированно отправляем сообщение в случае ошибки
        await message.answer(
            f"📢 <b>Новость №{news.id}</b> из канала <b>{news.source_channel}</b> (отредактирована):\n\n"
            f"{news.content}\n\n⚠️ <i>Произошла ошибка при отображении: {str(e)}</i>",
            reply_markup=markup,
            parse_mode="HTML"
        )


@dp.callback_query_handler(lambda c: c.data.startswith(('approve_', 'reject_', 'delete_', 'dummy_')))
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
                    InlineKeyboardButton("✅ Опубликовано", callback_data=f"dummy_{news.id}"),
                    InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_{news.id}")
                )
                
                # Обновляем сообщение с новой клавиатурой
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
            
    elif action == 'reject':
        # Отклоняем новость
        news.is_reviewed = True
        news.is_approved = False
        session.commit()
        
        await bot.answer_callback_query(callback_query.id, "Новость отклонена.")
        
        # Обновляем клавиатуру
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("❌ Отклонено", callback_data=f"dummy_{news.id}"))
        
        await bot.edit_message_reply_markup(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            reply_markup=markup
        )
        
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
                
                # Обновляем статус в базе данных
                news.is_published = False
                news.published_message_id = None
                session.commit()
                
                await bot.answer_callback_query(callback_query.id, "Новость удалена из канала.")
                
                # Обновляем клавиатуру
                markup = InlineKeyboardMarkup()
                markup.add(
                    InlineKeyboardButton("✅ Одобрено, публикация удалена", callback_data=f"dummy_{news.id}")
                )
                
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