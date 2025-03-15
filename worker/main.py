import os
import time
import threading
import json
from celery import Celery
from celery.signals import worker_ready, worker_shutting_down
from celery.schedules import crontab
from .telethon_manager import TelethonManager
import redis
import pathlib
from dotenv import load_dotenv, set_key

# Путь к .env файлу в директории worker
ENV_FILE_PATH = pathlib.Path(__file__).parent / '.env'

# Загружаем переменные из .env файла, если он существует
if ENV_FILE_PATH.exists():
    load_dotenv(ENV_FILE_PATH)

# Получение имени воркера из переменной окружения или создание нового
WORKER_NAME = os.getenv('WORKER_NAME')
if not WORKER_NAME:
    # Если имя воркера не задано, создаем новое и сохраняем его в .env файл
    WORKER_NAME = 'worker_' + str(int(time.time()))
    # Создаем .env файл, если его нет
    if not ENV_FILE_PATH.exists():
        with open(ENV_FILE_PATH, 'w') as f:
            f.write(f'WORKER_NAME={WORKER_NAME}\n')
    else:
        # Обновляем существующий .env файл
        set_key(ENV_FILE_PATH, 'WORKER_NAME', WORKER_NAME)
    
    print(f"Создан новый ID воркера: {WORKER_NAME}, сохранен в {ENV_FILE_PATH}")
else:
    print(f"Загружен существующий ID воркера: {WORKER_NAME}")

SERVER_ADDRESS = os.getenv('SERVER_ADDRESS', 'localhost')

# Настройка Celery и Redis
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
worker_app = Celery(
    'worker',
    broker=REDIS_URL,
    backend=REDIS_URL
)

# Настройка Celery
worker_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)

# Импортируем все задачи из celery_app.tasks, чтобы воркер мог их обрабатывать
import celery_app.tasks
# Импортируем конкретные задачи, которые будем использовать напрямую
# worker_heartbeat используется в периодических задачах для обновления статуса воркера
from celery_app.tasks import register_worker, check_worker_status, ping_worker, worker_heartbeat

# Настройка периодических задач для обновления статуса
worker_app.conf.beat_schedule = {
    'update-worker-status-every-30-seconds': {
        'task': 'worker.heartbeat',
        'schedule': 30.0,  # Каждые 30 секунд
        'args': (WORKER_NAME, SERVER_ADDRESS)
    },
}

# Инициализация Redis для хранения статусов воркеров
redis_client = redis.from_url(REDIS_URL)
WORKER_STATUS_KEY_PREFIX = "worker_status:"
WORKER_LAST_SEEN_KEY_PREFIX = "worker_last_seen:"

# Создание менеджера аккаунтов Telethon
telethon_manager = TelethonManager()

def update_worker_status():
    """Обновление статуса воркера в Redis"""
    worker_key = f"{WORKER_STATUS_KEY_PREFIX}{WORKER_NAME}"
    worker_last_seen_key = f"{WORKER_LAST_SEEN_KEY_PREFIX}{WORKER_NAME}"
    
    worker_data = {
        'name': WORKER_NAME,
        'server_address': SERVER_ADDRESS,
        'status': 'online'
    }
    
    redis_client.set(worker_key, json.dumps(worker_data))
    redis_client.set(worker_last_seen_key, int(time.time()))
    
    print(f"Статус воркера {WORKER_NAME} обновлен в Redis")

@worker_ready.connect
def worker_ready_handler(**kwargs):
    """Регистрация воркера при запуске"""
    # Обновление статуса в Redis
    update_worker_status()
    
    # Вызываем задачу для регистрации воркера напрямую вместо отправки через send_task
    register_worker.delay(WORKER_NAME, SERVER_ADDRESS)
    
    print(f"Воркер {WORKER_NAME} зарегистрирован на сервере {SERVER_ADDRESS}")

@worker_shutting_down.connect
def worker_shutdown(**kwargs):
    """Обработка выключения воркера"""
    # Остановка всех аккаунтов
    telethon_manager.stop_all_accounts()
    
    # Обновление статуса в Redis
    worker_key = f"{WORKER_STATUS_KEY_PREFIX}{WORKER_NAME}"
    worker_data = redis_client.get(worker_key)
    
    if worker_data:
        worker_json = json.loads(worker_data)
        worker_json['status'] = 'offline'
        redis_client.set(worker_key, json.dumps(worker_json))
    
    print(f"Воркер {WORKER_NAME} завершает работу, все аккаунты остановлены")

@worker_app.task(name='worker.ping')
def ping_worker():
    """Задача для проверки доступности воркера"""
    # Обновляем статус в Redis
    update_worker_status()
    
    return {'status': 'pong', 'worker': WORKER_NAME, 'time': int(time.time())}

@worker_app.task(name='worker.add_account')
def add_account(account_data):
    """Задача для добавления аккаунта к воркеру"""
    account_id = account_data.get('id')
    phone = account_data.get('phone')
    api_id = account_data.get('api_id')
    api_hash = account_data.get('api_hash')
    session_string = account_data.get('session_string')
    
    result = telethon_manager.add_account(
        account_id, phone, api_id, api_hash, session_string
    )
    
    return {
        'status': 'success' if result else 'error',
        'message': f'Аккаунт {phone} {"добавлен" if result else "не удалось добавить"}'
    }

@worker_app.task(name='worker.remove_account')
def remove_account(account_id):
    """Задача для удаления аккаунта из воркера"""
    result = telethon_manager.remove_account(account_id)
    
    return {
        'status': 'success' if result else 'error',
        'message': f'Аккаунт {account_id} {"удален" if result else "не удалось удалить"}'
    }

@worker_app.task(name='worker.start_account')
def start_account(account_id):
    """Задача для запуска аккаунта"""
    result = telethon_manager.start_account(account_id)
    
    return {
        'status': 'success' if result else 'error',
        'message': f'Аккаунт {account_id} {"запущен" if result else "не удалось запустить"}'
    }

@worker_app.task(name='worker.stop_account')
def stop_account(account_id):
    """Задача для остановки аккаунта"""
    result = telethon_manager.stop_account(account_id)
    
    return {
        'status': 'success' if result else 'error',
        'message': f'Аккаунт {account_id} {"остановлен" if result else "не удалось остановить"}'
    }

@worker_app.task(name='worker.get_account_status')
def get_account_status(account_id):
    """Задача для получения статуса аккаунта"""
    status = telethon_manager.get_account_status(account_id)
    
    if status:
        return {
            'status': 'success',
            'data': status
        }
    else:
        return {
            'status': 'error',
            'message': f'Аккаунт {account_id} не найден'
        }

@worker_app.task(name='worker.get_all_accounts_status')
def get_all_accounts_status():
    """Задача для получения статуса всех аккаунтов"""
    status = telethon_manager.get_all_accounts_status()
    
    return {
        'status': 'success',
        'data': status
    }

@worker_app.task(name='worker.stop_all_accounts')
def stop_all_accounts():
    """Задача для остановки всех аккаунтов"""
    result = telethon_manager.stop_all_accounts()
    
    return {
        'status': 'success' if result else 'error',
        'message': 'Все аккаунты остановлены' if result else 'Не удалось остановить все аккаунты'
    }

if __name__ == '__main__':
    # Обновление статуса перед запуском
    update_worker_status()
    
    # Запуск воркера Celery
    argv = [
        'worker',
        '--loglevel=info',
        f'--hostname={WORKER_NAME}@%h',
        f'--queues={WORKER_NAME},control',  # Слушаем очередь с именем воркера и общую очередь control
        '--beat',  # Включаем встроенный scheduler для периодических задач
    ]
    worker_app.worker_main(argv) 