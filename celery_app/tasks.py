from celery import Celery
from config import CELERY_BROKER_URL, CELERY_RESULT_BACKEND
from celery.result import AsyncResult
import redis
import json
import time

# Инициализация приложения Celery
celery_app = Celery(
    'tg_bot',
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND
)

# Инициализация Redis для хранения статусов воркеров
redis_client = redis.from_url(CELERY_RESULT_BACKEND)
WORKER_STATUS_KEY_PREFIX = "worker_status:"
WORKER_LAST_SEEN_KEY_PREFIX = "worker_last_seen:"
WORKER_ONLINE_TIMEOUT = 60  # секунд, после которых воркер считается неактивным

# Задачи для управления воркерами

@celery_app.task(name='worker.register')
def register_worker(worker_name, server_address):
    """Задача для регистрации нового воркера"""
    # Сохранение статуса воркера в Redis
    worker_key = f"{WORKER_STATUS_KEY_PREFIX}{worker_name}"
    worker_last_seen_key = f"{WORKER_LAST_SEEN_KEY_PREFIX}{worker_name}"
    
    worker_data = {
        'name': worker_name,
        'server_address': server_address,
        'status': 'online'
    }
    
    redis_client.set(worker_key, json.dumps(worker_data))
    redis_client.set(worker_last_seen_key, int(time.time()))
    
    return {'status': 'success', 'message': f'Воркер {worker_name} зарегистрирован'}

@celery_app.task(name='worker.status')
def check_worker_status(worker_name):
    """Задача для проверки статуса воркера"""
    # Проверка статуса воркера в Redis
    worker_key = f"{WORKER_STATUS_KEY_PREFIX}{worker_name}"
    worker_last_seen_key = f"{WORKER_LAST_SEEN_KEY_PREFIX}{worker_name}"
    
    worker_data = redis_client.get(worker_key)
    last_seen = redis_client.get(worker_last_seen_key)
    
    if not worker_data or not last_seen:
        return {'status': 'offline', 'worker': worker_name}
    
    # Проверка, не устарел ли статус
    last_seen_time = int(last_seen)
    current_time = int(time.time())
    
    if current_time - last_seen_time > WORKER_ONLINE_TIMEOUT:
        status = 'offline'
    else:
        status = 'online'
        
    # Проверка через Celery, жив ли воркер
    # Отправляем ping и ждем ответ не более 5 секунд
    try:
        ping_task = celery_app.send_task(
            'worker.ping',
            args=[],
            kwargs={},
            queue=worker_name,
            expires=5
        )
        ping_result = ping_task.get(timeout=5)
        
        if ping_result and ping_result.get('status') == 'pong':
            status = 'online'
            # Обновляем время последнего ответа
            redis_client.set(worker_last_seen_key, int(time.time()))
    except Exception:
        status = 'offline'
    
    result = {'status': status, 'worker': worker_name}
    
    # Обновляем статус в Redis
    if worker_data:
        worker_json = json.loads(worker_data)
        worker_json['status'] = status
        redis_client.set(worker_key, json.dumps(worker_json))
    
    return result

@celery_app.task(name='worker.ping')
def ping_worker():
    """Задача для проверки доступности воркера"""
    return {'status': 'pong', 'time': int(time.time())}

@celery_app.task(name='worker.heartbeat')
def worker_heartbeat(worker_name, server_address):
    """Периодическая задача для обновления статуса воркера"""
    # Обновление статуса воркера в Redis
    worker_key = f"{WORKER_STATUS_KEY_PREFIX}{worker_name}"
    worker_last_seen_key = f"{WORKER_LAST_SEEN_KEY_PREFIX}{worker_name}"
    
    worker_data = {
        'name': worker_name,
        'server_address': server_address,
        'status': 'online'
    }
    
    redis_client.set(worker_key, json.dumps(worker_data))
    redis_client.set(worker_last_seen_key, int(time.time()))
    
    return {
        'status': 'online', 
        'worker': worker_name,
        'time': int(time.time())
    }

@celery_app.task(name='worker.list_active')
def list_active_workers():
    """Задача для получения списка активных воркеров"""
    # Получение всех ключей со статусами воркеров
    worker_keys = redis_client.keys(f"{WORKER_STATUS_KEY_PREFIX}*")
    active_workers = []
    
    for key in worker_keys:
        worker_data = redis_client.get(key)
        if worker_data:
            worker_json = json.loads(worker_data)
            worker_name = worker_json.get('name')
            
            # Проверка, не устарел ли статус
            last_seen_key = f"{WORKER_LAST_SEEN_KEY_PREFIX}{worker_name}"
            last_seen = redis_client.get(last_seen_key)
            
            if last_seen:
                last_seen_time = int(last_seen)
                current_time = int(time.time())
                
                if current_time - last_seen_time <= WORKER_ONLINE_TIMEOUT:
                    active_workers.append(worker_json)
    
    return {
        'status': 'success',
        'workers': active_workers
    }

# Задачи для управления аккаунтами Telethon

@celery_app.task(name='account.add')
def add_account_to_worker(worker_name, account_data):
    """Задача для добавления аккаунта к воркеру"""
    # В реальном приложении здесь будет логика добавления аккаунта
    return {
        'status': 'success',
        'message': f'Аккаунт {account_data["phone"]} добавлен к воркеру {worker_name}'
    }

@celery_app.task(name='account.start')
def start_account(worker_name, account_id):
    """Задача для запуска аккаунта на воркере"""
    # В реальном приложении здесь будет логика запуска аккаунта
    return {
        'status': 'success',
        'message': f'Аккаунт {account_id} запущен на воркере {worker_name}'
    }

@celery_app.task(name='account.stop')
def stop_account(worker_name, account_id):
    """Задача для остановки аккаунта на воркере"""
    # В реальном приложении здесь будет логика остановки аккаунта
    return {
        'status': 'success',
        'message': f'Аккаунт {account_id} остановлен на воркере {worker_name}'
    }

@celery_app.task(name='account.status')
def check_account_status(worker_name, account_id):
    """Задача для проверки статуса аккаунта на воркере"""
    # В реальном приложении здесь будет логика проверки статуса аккаунта
    return {
        'status': 'running',
        'worker': worker_name,
        'account_id': account_id
    } 