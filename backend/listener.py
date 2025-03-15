#!/usr/bin/env python
import time
import json
import redis
import logging
from database.models import SessionLocal
from database.operations import create_worker, get_worker_by_name, update_worker_status
from config import REDIS_URL

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Константы для работы с Redis
WORKER_STATUS_KEY_PREFIX = "worker_status:"
WORKER_LAST_SEEN_KEY_PREFIX = "worker_last_seen:"
WORKER_ONLINE_TIMEOUT = 60  # секунд, после которых воркер считается неактивным

# Инициализация клиента Redis
redis_client = redis.from_url(REDIS_URL)

def get_db():
    """Функция для получения сессии базы данных"""
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()

def scan_workers():
    """
    Сканирование всех воркеров в Redis и обновление их статуса в базе данных
    """
    # Получаем все ключи с префиксом WORKER_STATUS_KEY_PREFIX
    cursor = 0
    worker_keys = []
    while True:
        cursor, keys = redis_client.scan(cursor, f"{WORKER_STATUS_KEY_PREFIX}*", 100)
        worker_keys.extend(keys)
        if cursor == 0:
            break
    
    db = get_db()
    current_time = int(time.time())
    
    for key in worker_keys:
        worker_name = key.decode('utf-8').replace(WORKER_STATUS_KEY_PREFIX, "")
        worker_data_raw = redis_client.get(key)
        
        if worker_data_raw:
            try:
                worker_data = json.loads(worker_data_raw)
                server_address = worker_data.get('server_address', 'unknown')
                
                # Проверяем, существует ли воркер в базе данных
                worker = get_worker_by_name(db, worker_name)
                
                # Получаем время последнего обновления статуса
                last_seen_key = f"{WORKER_LAST_SEEN_KEY_PREFIX}{worker_name}"
                last_seen_raw = redis_client.get(last_seen_key)
                last_seen = int(last_seen_raw) if last_seen_raw else 0
                
                # Определяем, онлайн ли воркер
                # Воркер активен, если обновлял статус недавно и не отмечен явно как offline
                is_active = False
                if worker_data and (current_time - last_seen) < WORKER_ONLINE_TIMEOUT and worker_data.get('status') != 'offline':
                    is_active = True
                
                if not worker:
                    # Если воркера нет в базе данных, создаем его
                    logger.info(f"Обнаружен новый воркер: {worker_name}, добавляю в базу данных")
                    worker = create_worker(db, worker_name, server_address)
                    logger.info(f"Воркер {worker_name} добавлен в базу данных")
                else:
                    # Обновляем статус существующего воркера
                    if worker.is_active != is_active:
                        logger.info(f"Обновляю статус воркера {worker_name} на {'активен' if is_active else 'неактивен'}")
                        update_worker_status(db, worker.id, is_active)
            except Exception as e:
                logger.error(f"Ошибка при обработке воркера {worker_name}: {str(e)}")

def run_listener(interval=10):
    """
    Запуск прослушивания Redis с указанным интервалом
    
    Args:
        interval (int): Интервал сканирования в секундах
    """
    logger.info(f"Запуск бэкенд-сервиса прослушивания Redis с интервалом {interval} секунд")
    
    while True:
        try:
            scan_workers()
        except Exception as e:
            logger.error(f"Ошибка при сканировании воркеров: {str(e)}")
        
        time.sleep(interval)

if __name__ == "__main__":
    run_listener() 