#!/usr/bin/env python
"""
Скрипт для запуска бэкенд-сервиса, который отслеживает появление новых воркеров в Redis
и автоматически добавляет их в базу данных.
"""
import sys
import logging
from database.models import create_tables
from backend.listener import run_listener

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main():
    # Создаем таблицы в базе данных, если они не существуют
    create_tables()
    
    # Проверяем, был ли указан интервал сканирования
    interval = 10  # По умолчанию 10 секунд
    if len(sys.argv) > 1:
        try:
            interval = int(sys.argv[1])
        except ValueError:
            logger.error(f"Неверный формат интервала: {sys.argv[1]}. Используется значение по умолчанию: {interval}")
    
    # Запускаем прослушивание Redis
    run_listener(interval)

if __name__ == "__main__":
    main() 