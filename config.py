import os
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Настройки Telegram бота
TG_BOT_TOKEN = os.getenv('TG_BOT_TOKEN')
ADMIN_IDS = list(map(int, os.getenv('ADMIN_IDS', '').split(',')))

# Настройки базы данных
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///tg_bot.db')

# Настройки Redis и Celery
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL 