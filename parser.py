import os
import asyncio
import json
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument, MessageMediaWebPage
import logging
from datetime import datetime
import aiohttp
import mimetypes

from config import API_ID, API_HASH, PHONE_NUMBER, SOURCE_CHANNELS, BOT_TOKEN, MODERATOR_IDS
from database import get_session, News, init_db

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Директория для сохранения медиа
MEDIA_DIR = os.path.join(os.getcwd(), 'media')
os.makedirs(MEDIA_DIR, exist_ok=True)


class NewsParser:
    def __init__(self):
        self.client = None
        self.session = get_session()

    async def start(self):
        # Инициализация клиента Telethon, используя существующую сессию
        self.client = TelegramClient('parser_session', API_ID, API_HASH)
        
        # Подключаемся без запроса кода (использует существующую сессию)
        await self.client.connect()
        
        # Проверяем, что пользователь авторизован
        if not await self.client.is_user_authorized():
            logger.error("Парсер не авторизован. Запустите main.py для авторизации.")
            return
        
        logger.info("Парсер запущен и авторизован")

        # Подписка на новые сообщения в указанных каналах
        @self.client.on(events.NewMessage(chats=SOURCE_CHANNELS))
        async def new_message_handler(event):
            await self.process_message(event)

        # Бесконечный цикл для поддержания работы клиента
        await self.client.run_until_disconnected()

    async def process_message(self, event):
        """Обрабатывает новое сообщение из канала"""
        message = event.message
        chat = await event.get_chat()
        
        # Получаем содержимое сообщения
        content = message.text or message.message or ""
        logger.info(f"Получено новое сообщение от {chat.username or chat.id}: {content[:50]}...")
        
        # Проверяем, есть ли медиа в сообщении
        has_media = message.media is not None
        media_path = None
        media_type = None
        
        if has_media:
            logger.info(f"Сообщение содержит медиа типа: {type(message.media).__name__}")
            
            # Обрабатываем медиа
            if isinstance(message.media, MessageMediaPhoto):
                media_type = 'photo'
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                media_path = os.path.join(MEDIA_DIR, f'photo_{message.id}_{timestamp}.jpg')
                try:
                    await self.client.download_media(message, media_path)
                    logger.info(f"Фото успешно сохранено: {media_path}")
                    
                    # Проверяем, существует ли файл и его размер
                    if os.path.exists(media_path):
                        file_size = os.path.getsize(media_path)
                        logger.info(f"Размер файла: {file_size} байт")
                    else:
                        logger.error(f"Файл не найден после сохранения: {media_path}")
                except Exception as e:
                    logger.error(f"Ошибка при скачивании фото: {e}")
                    media_path = None
            
            elif isinstance(message.media, MessageMediaDocument):
                # Определяем тип документа
                document = message.media.document
                mime_type = document.mime_type
                file_name = None
                
                # Пытаемся получить оригинальное имя файла
                for attribute in document.attributes:
                    if hasattr(attribute, 'file_name') and attribute.file_name:
                        file_name = attribute.file_name
                        break
                
                if not file_name:
                    # Если имя не найдено, создаем на основе mime-типа
                    ext = mimetypes.guess_extension(mime_type) or '.dat'
                    file_name = f'doc_{message.id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}{ext}'
                
                # Сохраняем документ
                media_type = 'document'
                media_path = os.path.join(MEDIA_DIR, file_name)
                try:
                    await self.client.download_media(message, media_path)
                    logger.info(f"Документ успешно сохранен: {media_path}, MIME: {mime_type}")
                    
                    # Проверяем, существует ли файл и его размер
                    if os.path.exists(media_path):
                        file_size = os.path.getsize(media_path)
                        logger.info(f"Размер файла: {file_size} байт")
                    else:
                        logger.error(f"Файл не найден после сохранения: {media_path}")
                except Exception as e:
                    logger.error(f"Ошибка при скачивании документа: {e}")
                    media_path = None
            
            elif isinstance(message.media, MessageMediaWebPage):
                # Для веб-страниц просто извлекаем информацию, но не скачиваем
                logger.info("Сообщение содержит веб-страницу, медиафайл не будет скачан")
                has_media = False
            
            else:
                logger.warning(f"Неизвестный тип медиа: {type(message.media).__name__}, скачивание будет пропущено")
                has_media = False
        
        # Если сообщение полностью пустое (нет текста и медиа), пропускаем его
        if not content and not has_media:
            logger.info("Пустое сообщение без медиа, пропускаем")
            return
        
        # Создаем запись в базе данных
        news = News(
            source_channel=chat.username or str(chat.id),
            message_id=message.id,
            content=content,
            has_media=has_media,
            media_type=media_type,
            media_path=media_path
        )
        
        self.session.add(news)
        self.session.commit()
        
        logger.info(f"Новая новость сохранена из канала {chat.username or chat.id}, ID: {news.id}, has_media: {has_media}, media_path: {media_path}")
        
        # Отправляем уведомление о новой новости всем модераторам через нашего бота
        await self.notify_moderators_about_new_news(news)

    async def notify_moderators_about_new_news(self, news):
        """Отправляет уведомление модераторам о новой новости"""
        try:
            # Отправляем уведомление каждому модератору через бота
            for moderator_id in MODERATOR_IDS:
                # Создаем inline кнопки для действий
                inline_keyboard = {
                    "inline_keyboard": [
                        [
                            {"text": "✅ Одобрить и опубликовать", "callback_data": f"approve_{news.id}"},
                            {"text": "✏️ Редактировать", "callback_data": f"edit_{news.id}"}
                        ]
                    ]
                }
                
                # Формируем сообщение
                message_text = f"📢 <b>Новая новость №{news.id}</b> из канала <b>{news.source_channel}</b>:\n\n{news.content}"
                
                # Если есть медиа, отправляем с медиа
                if news.has_media and news.media_path and os.path.exists(news.media_path):
                    logger.info(f"Отправка новости {news.id} с медиа {news.media_path} модератору {moderator_id}")
                    await self.send_media_to_moderator(moderator_id, news, message_text, inline_keyboard)
                else:
                    # Иначе отправляем просто текст
                    logger.info(f"Отправка текстовой новости {news.id} модератору {moderator_id}")
                    await self.send_text_to_moderator(moderator_id, message_text, inline_keyboard)
                
                logger.info(f"Уведомление о новой новости {news.id} отправлено модератору {moderator_id}")
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления о новой новости: {e}")

    async def send_text_to_moderator(self, moderator_id, text, inline_keyboard):
        """Отправляет текстовое сообщение модератору через бота"""
        bot_api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        
        payload = {
            "chat_id": moderator_id,
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": json.dumps(inline_keyboard)
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(bot_api_url, json=payload) as response:
                    if response.status != 200:
                        response_text = await response.text()
                        logger.error(f"Ошибка при отправке сообщения: {response_text}")
                    else:
                        logger.info(f"Текстовое сообщение успешно отправлено модератору {moderator_id}")
            except Exception as e:
                logger.error(f"Исключение при отправке текстового сообщения: {e}")

    async def send_media_to_moderator(self, moderator_id, news, caption, inline_keyboard):
        """Отправляет медиа сообщение модератору через бота"""
        if news.media_type == 'photo':
            bot_api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
            file_param = "photo"
        else:  # document
            bot_api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
            file_param = "document"
        
        # Проверяем существование файла перед отправкой
        if not os.path.exists(news.media_path):
            logger.error(f"Файл не найден перед отправкой: {news.media_path}")
            # Если файл не найден, отправляем только текст
            await self.send_text_to_moderator(
                moderator_id, 
                f"{caption}\n\n⚠️ <i>Медиафайл не найден, показан только текст</i>", 
                inline_keyboard
            )
            return
        
        try:
            # Сначала читаем файл в память
            with open(news.media_path, 'rb') as file:
                file_content = file.read()
                
            filename = os.path.basename(news.media_path)
            content_type = mimetypes.guess_type(news.media_path)[0] or 'application/octet-stream'
            logger.info(f"Подготовлен файл для отправки: {filename}, тип: {content_type}, размер: {len(file_content)} байт")
            
            # Создаем данные формы с уже прочитанным содержимым файла
            data = aiohttp.FormData()
            data.add_field('chat_id', str(moderator_id))
            data.add_field('caption', caption)
            data.add_field('parse_mode', 'HTML')
            data.add_field('reply_markup', json.dumps(inline_keyboard))
            data.add_field(
                file_param, 
                file_content, 
                filename=filename,
                content_type=content_type
            )
            
            # Отправляем запрос
            async with aiohttp.ClientSession() as session:
                async with session.post(bot_api_url, data=data) as response:
                    if response.status != 200:
                        response_text = await response.text()
                        logger.error(f"Ошибка при отправке медиа: {response_text}")
                        
                        # Если не удалось отправить медиа, пробуем отправить хотя бы текст
                        await self.send_text_to_moderator(
                            moderator_id, 
                            f"{caption}\n\n⚠️ <i>Не удалось отправить медиафайл: {response_text}</i>", 
                            inline_keyboard
                        )
                    else:
                        logger.info(f"Медиафайл успешно отправлен модератору {moderator_id}")
        except Exception as e:
            logger.error(f"Исключение при отправке медиафайла: {e}")
            # При любой ошибке отправляем хотя бы текст
            await self.send_text_to_moderator(
                moderator_id, 
                f"{caption}\n\n⚠️ <i>Ошибка при отправке медиафайла: {str(e)}</i>", 
                inline_keyboard
            )


async def run_parser():
    # Инициализация базы данных
    init_db()
    
    # Запуск парсера
    parser = NewsParser()
    await parser.start()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(run_parser())
    except KeyboardInterrupt:
        print("Парсер остановлен.")
    finally:
        loop.close() 