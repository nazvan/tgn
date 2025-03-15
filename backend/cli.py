#!/usr/bin/env python
"""
Командная утилита для управления воркерами через базу данных и Redis
"""
import argparse
import json
import logging
import redis
from tabulate import tabulate
from database.models import SessionLocal
from database.operations import (
    get_all_workers, get_worker_by_name, update_worker_status
)
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

# Инициализация клиента Redis
redis_client = redis.from_url(REDIS_URL)

def get_db():
    """Функция для получения сессии базы данных"""
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()

def list_workers(args):
    """Вывод списка всех воркеров из базы данных"""
    db = get_db()
    workers = get_all_workers(db, active_only=args.active_only)
    
    if not workers:
        print("Список воркеров пуст")
        return
    
    # Подготовка данных для таблицы
    table_data = []
    for worker in workers:
        # Получаем данные из Redis, если есть
        redis_status = "Неизвестно"
        worker_key = f"{WORKER_STATUS_KEY_PREFIX}{worker.name}"
        worker_data_raw = redis_client.get(worker_key)
        
        if worker_data_raw:
            try:
                worker_data = json.loads(worker_data_raw)
                redis_status = worker_data.get('status', 'Неизвестно')
            except json.JSONDecodeError:
                redis_status = "Ошибка данных"
        
        table_data.append([
            worker.id,
            worker.name,
            worker.server_address,
            "Активен" if worker.is_active else "Неактивен",
            redis_status,
            worker.created_at.strftime("%Y-%m-%d %H:%M:%S") if worker.created_at else "Неизвестно"
        ])
    
    # Вывод таблицы
    headers = ["ID", "Имя", "Сервер", "Статус в БД", "Статус в Redis", "Создан"]
    print(tabulate(table_data, headers=headers, tablefmt="grid"))

def show_worker(args):
    """Вывод информации о конкретном воркере"""
    db = get_db()
    worker = get_worker_by_name(db, args.name)
    
    if not worker:
        print(f"Воркер {args.name} не найден")
        return
    
    # Получаем данные из Redis, если есть
    redis_status = "Неизвестно"
    redis_data = "Нет данных"
    worker_key = f"{WORKER_STATUS_KEY_PREFIX}{worker.name}"
    worker_data_raw = redis_client.get(worker_key)
    
    if worker_data_raw:
        try:
            worker_data = json.loads(worker_data_raw)
            redis_status = worker_data.get('status', 'Неизвестно')
            redis_data = json.dumps(worker_data, indent=2)
        except json.JSONDecodeError:
            redis_status = "Ошибка данных"
    
    # Вывод информации о воркере
    print(f"ID: {worker.id}")
    print(f"Имя: {worker.name}")
    print(f"Сервер: {worker.server_address}")
    print(f"Статус в БД: {'Активен' if worker.is_active else 'Неактивен'}")
    print(f"Статус в Redis: {redis_status}")
    print(f"Создан: {worker.created_at.strftime('%Y-%m-%d %H:%M:%S') if worker.created_at else 'Неизвестно'}")
    print("\nДанные воркера в Redis:")
    print(redis_data)

def activate_worker(args):
    """Активация воркера в базе данных"""
    db = get_db()
    worker = get_worker_by_name(db, args.name)
    
    if not worker:
        print(f"Воркер {args.name} не найден")
        return
    
    worker = update_worker_status(db, worker.id, True)
    print(f"Воркер {worker.name} активирован в базе данных")

def deactivate_worker(args):
    """Деактивация воркера в базе данных"""
    db = get_db()
    worker = get_worker_by_name(db, args.name)
    
    if not worker:
        print(f"Воркер {args.name} не найден")
        return
    
    worker = update_worker_status(db, worker.id, False)
    print(f"Воркер {worker.name} деактивирован в базе данных")

def main():
    # Создание парсера аргументов командной строки
    parser = argparse.ArgumentParser(description="Управление воркерами в системе Telegram-бота")
    subparsers = parser.add_subparsers(dest="command", help="Команды")
    
    # Команда list
    list_parser = subparsers.add_parser("list", help="Вывод списка всех воркеров")
    list_parser.add_argument("--active-only", action="store_true", help="Показать только активные воркеры")
    list_parser.set_defaults(func=list_workers)
    
    # Команда show
    show_parser = subparsers.add_parser("show", help="Вывод информации о конкретном воркере")
    show_parser.add_argument("name", help="Имя воркера")
    show_parser.set_defaults(func=show_worker)
    
    # Команда activate
    activate_parser = subparsers.add_parser("activate", help="Активация воркера в базе данных")
    activate_parser.add_argument("name", help="Имя воркера")
    activate_parser.set_defaults(func=activate_worker)
    
    # Команда deactivate
    deactivate_parser = subparsers.add_parser("deactivate", help="Деактивация воркера в базе данных")
    deactivate_parser.add_argument("name", help="Имя воркера")
    deactivate_parser.set_defaults(func=deactivate_worker)
    
    # Парсинг аргументов
    args = parser.parse_args()
    
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main() 