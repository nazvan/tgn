import asyncio
import logging
import sys
import os
from multiprocessing import Process
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from config import API_ID, API_HASH, PHONE_NUMBER

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


async def authenticate_telethon():
    """
    Выполняет аутентификацию в Telegram с запросом кода и пароля если необходимо.
    Это позволяет создать сессии для парсера новостей.
    """
    logger.info("Начинаю процесс аутентификации в Telegram для парсера...")
    
    # Создаем клиент для парсера
    parser_client = TelegramClient('parser_session', API_ID, API_HASH)
    await parser_client.connect()
    
    # Если еще не авторизован, запрашиваем авторизацию
    if not await parser_client.is_user_authorized():
        logger.info(f"Отправка кода авторизации на номер {PHONE_NUMBER}")
        await parser_client.send_code_request(PHONE_NUMBER)
        
        try:
            print("\nВнимание! Вам отправлен код авторизации в Telegram.")
            code = input("Введите полученный код: ")
            await parser_client.sign_in(PHONE_NUMBER, code)
            
        except SessionPasswordNeededError:
            # Если включена двухфакторная аутентификация
            password = input("Введите пароль двухфакторной аутентификации: ")
            await parser_client.sign_in(password=password)
    
    logger.info("Аутентификация парсера успешно выполнена.")
    
    # Закрываем соединения, они будут восстановлены в соответствующем процессе
    await parser_client.disconnect()


def run_parser():
    """Запускает парсер новостей"""
    from parser import run_parser
    asyncio.run(run_parser())


def run_bot():
    """Запускает бота модерации"""
    from bot import main
    asyncio.run(main())


if __name__ == "__main__":
    logger.info("Запуск приложения...")
    
    # Выполняем авторизацию парсера перед запуском процессов
    try:
        asyncio.run(authenticate_telethon())
    except Exception as e:
        logger.error(f"Ошибка при аутентификации: {e}")
        sys.exit(1)
    
    # Создаем процесс для парсера
    parser_process = Process(target=run_parser)
    parser_process.start()
    logger.info("Парсер новостей запущен")
    
    # Создаем процесс для бота
    bot_process = Process(target=run_bot)
    bot_process.start()
    logger.info("Бот модерации запущен")
    
    try:
        # Ожидаем завершения процессов
        parser_process.join()
        bot_process.join()
    except KeyboardInterrupt:
        logger.info("Получен сигнал завершения, останавливаем приложение...")
        parser_process.terminate()
        bot_process.terminate()
        parser_process.join()
        bot_process.join()
        logger.info("Приложение остановлено")
    except Exception as e:
        logger.error(f"Произошла ошибка: {e}")
        parser_process.terminate()
        bot_process.terminate()
        parser_process.join()
        bot_process.join()
        sys.exit(1) 