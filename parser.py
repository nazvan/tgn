import os
import asyncio
import json
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
import logging
from datetime import datetime
import aiohttp

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
        if not content and not message.media:
            return  # Пропускаем пустые сообщения без медиа
        
        # Проверяем, есть ли медиа в сообщении
        has_media = message.media is not None
        media_path = None
        media_type = None
        
        if has_media:
            # Обрабатываем медиа
            if isinstance(message.media, MessageMediaPhoto):
                media_type = 'photo'
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                media_path = os.path.join(MEDIA_DIR, f'photo_{message.id}_{timestamp}.jpg')
                await self.client.download_media(message, media_path)
            elif isinstance(message.media, MessageMediaDocument):
                media_type = 'document'
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                media_path = os.path.join(MEDIA_DIR, f'doc_{message.id}_{timestamp}')
                await self.client.download_media(message, media_path)
        
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
        
        logger.info(f"Новая новость сохранена из канала {chat.username or chat.id}, ID: {news.id}")
        
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
                            {"text": "✏️ Редактировать", "callback_data": f"edit_{news.id}"},
                            {"text": "❌ Отклонить", "callback_data": f"reject_{news.id}"}
                        ]
                    ]
                }
                
                # Формируем сообщение
                message_text = f"📢 <b>Новая новость №{news.id}</b> из канала <b>{news.source_channel}</b>:\n\n{news.content}"
                
                # Если есть медиа, отправляем с медиа
                if news.has_media and news.media_path and os.path.exists(news.media_path):
                    await self.send_media_to_moderator(moderator_id, news, message_text, inline_keyboard)
                else:
                    # Иначе отправляем просто текст
                    await self.send_text_to_moderator(moderator_id, message_text, inline_keyboard)
                
                logger.info(f"Уведомление о новой новости отправлено модератору {moderator_id}")
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
            async with session.post(bot_api_url, json=payload) as response:
                if response.status != 200:
                    logger.error(f"Ошибка при отправке сообщения: {await response.text()}")

    async def send_media_to_moderator(self, moderator_id, news, caption, inline_keyboard):
        """Отправляет медиа сообщение модератору через бота"""
        if news.media_type == 'photo':
            bot_api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
            file_param = "photo"
        else:  # document
            bot_api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
            file_param = "document"
        
        # Подготавливаем данные формы
        data = aiohttp.FormData()
        data.add_field('chat_id', str(moderator_id))
        data.add_field('caption', caption)
        data.add_field('parse_mode', 'HTML')
        data.add_field('reply_markup', json.dumps(inline_keyboard))
        
        # Добавляем файл
        with open(news.media_path, 'rb') as file:
            data.add_field(file_param, file, 
                          filename=os.path.basename(news.media_path),
                          content_type='application/octet-stream')
        
        # Отправляем запрос
        async with aiohttp.ClientSession() as session:
            async with session.post(bot_api_url, data=data) as response:
                if response.status != 200:
                    logger.error(f"Ошибка при отправке медиа: {await response.text()}")


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