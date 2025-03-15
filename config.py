# Конфигурационный файл

import os
from dotenv import load_dotenv
from typing import List

# Загружаем переменные окружения из файла .env
load_dotenv()

# Данные для Telethon
API_ID = os.getenv('API_ID')  # Получите от https://my.telegram.org/
API_HASH = os.getenv('API_HASH')  # Получите от https://my.telegram.org/
PHONE_NUMBER = os.getenv('PHONE_NUMBER')  # Ваш номер телефона в формате +79123456789

# Данные для бота TelegramBotAPI
BOT_TOKEN = os.getenv('BOT_TOKEN')  # Получите от @BotFather

# Каналы для парсинга (usernames без @)
SOURCE_CHANNELS = os.getenv('SOURCE_CHANNELS', '').split(',')

# Канал для публикации новостей
TARGET_CHANNEL = os.getenv('TARGET_CHANNEL')  # Укажите username канала без @ или ID канала

# ID пользователей, которые могут модерировать новости
MODERATOR_IDS = [int(id) for id in os.getenv('MODERATOR_IDS', '').split(',') if id]

# Настройки базы данных
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///telegram_news.db') 