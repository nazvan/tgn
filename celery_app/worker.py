from celery import Celery
from config import CELERY_BROKER_URL, CELERY_RESULT_BACKEND

# Инициализация воркера Celery
celery_worker = Celery(
    'worker',
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND
)

# Настройка Celery
celery_worker.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)

# Импорт задач
import celery_app.tasks 