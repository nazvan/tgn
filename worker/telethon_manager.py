import asyncio
import threading
import logging
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class TelethonAccount:
    """Класс для управления аккаунтом Telethon"""
    
    def __init__(self, account_id, phone, api_id, api_hash, session_string=None):
        self.account_id = account_id
        self.phone = phone
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_string = session_string
        self.client = None
        self.is_running = False
        self.is_connected = False
        self.thread = None
        self.loop = None
        self.messages_count = 0  # Счетчик полученных сообщений
    
    async def _message_handler(self, event):
        """Обработчик входящих сообщений"""
        self.messages_count += 1
        sender = await event.get_sender()
        
        logger.info(f"Аккаунт {self.phone} получил сообщение от {sender.username if hasattr(sender, 'username') else sender.id}: {event.text[:50]}...")
        
        # Здесь можно добавить логику обработки сообщений
        # Например, сохранение в базу данных, пересылка и т.д.
    
    async def _run_client(self):
        """Запуск клиента Telethon"""
        try:
            # Создание клиента с использованием StringSession
            session = StringSession(self.session_string) if self.session_string else StringSession()
            self.client = TelegramClient(session, self.api_id, self.api_hash)
            
            # Регистрация обработчика сообщений
            self.client.add_event_handler(
                self._message_handler,
                events.NewMessage(incoming=True)
            )
            
            # Подключение к Telegram
            await self.client.connect()
            self.is_connected = self.client.is_connected()
            
            # Если не авторизован, выполнить авторизацию
            if not await self.client.is_user_authorized():
                logger.warning(f"Аккаунт {self.phone} не авторизован. Требуется выполнить вход.")
                # В реальном приложении здесь будет логика авторизации
                # Например, запрос кода подтверждения и т.д.
                return False
            
            # Сохранение строки сессии, если она не была предоставлена
            if not self.session_string:
                self.session_string = self.client.session.save()
                logger.info(f"Создана новая сессия для аккаунта {self.phone}")
            
            logger.info(f"Аккаунт {self.phone} успешно запущен и подключен")
            
            # Запускаем обработку событий
            while self.is_running:
                await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Ошибка при запуске аккаунта {self.phone}: {str(e)}")
            self.is_connected = False
            return False
        finally:
            # Отключаемся при выходе из цикла
            if self.client and self.client.is_connected():
                await self.client.disconnect()
                self.is_connected = False
    
    def _thread_function(self):
        """Функция для запуска клиента в отдельном потоке"""
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self._run_client())
        except Exception as e:
            logger.error(f"Ошибка в потоке аккаунта {self.phone}: {str(e)}")
        finally:
            if self.loop:
                self.loop.close()
            self.is_running = False
            self.is_connected = False
            logger.info(f"Поток аккаунта {self.phone} завершен")
    
    def start(self):
        """Запуск аккаунта в отдельном потоке"""
        if not self.is_running:
            try:
                self.is_running = True
                self.thread = threading.Thread(target=self._thread_function)
                self.thread.daemon = True
                self.thread.start()
                logger.info(f"Аккаунт {self.phone} запускается...")
                return True
            except Exception as e:
                logger.error(f"Не удалось запустить аккаунт {self.phone}: {str(e)}")
                self.is_running = False
                return False
        else:
            logger.warning(f"Аккаунт {self.phone} уже запущен")
        return False
    
    def stop(self):
        """Остановка аккаунта"""
        if self.is_running:
            try:
                logger.info(f"Остановка аккаунта {self.phone}...")
                self.is_running = False
                
                if self.client and self.client.is_connected():
                    # Используем loop для выполнения корутины disconnect
                    if self.loop:
                        asyncio.run_coroutine_threadsafe(self.client.disconnect(), self.loop)
                
                # Ожидание завершения потока
                if self.thread and self.thread.is_alive():
                    self.thread.join(timeout=5)
                
                self.is_connected = False
                logger.info(f"Аккаунт {self.phone} успешно остановлен")
                return True
            except Exception as e:
                logger.error(f"Ошибка при остановке аккаунта {self.phone}: {str(e)}")
                return False
        else:
            logger.warning(f"Аккаунт {self.phone} не запущен")
        return False
    
    def get_status(self):
        """Получение статуса аккаунта"""
        return {
            'account_id': self.account_id,
            'phone': self.phone,
            'is_running': self.is_running,
            'is_connected': self.is_connected if self.client else False,
            'messages_count': self.messages_count,
            'has_session': bool(self.session_string)
        }


class TelethonManager:
    """Класс для управления несколькими аккаунтами Telethon"""
    
    def __init__(self):
        self.accounts = {}  # словарь аккаунтов: account_id -> TelethonAccount
    
    def add_account(self, account_id, phone, api_id, api_hash, session_string=None):
        """Добавление нового аккаунта"""
        if account_id not in self.accounts:
            account = TelethonAccount(account_id, phone, api_id, api_hash, session_string)
            self.accounts[account_id] = account
            return True
        return False
    
    def remove_account(self, account_id):
        """Удаление аккаунта"""
        if account_id in self.accounts:
            account = self.accounts[account_id]
            if account.is_running:
                account.stop()
            del self.accounts[account_id]
            return True
        return False
    
    def start_account(self, account_id):
        """Запуск аккаунта"""
        if account_id in self.accounts:
            return self.accounts[account_id].start()
        return False
    
    def stop_account(self, account_id):
        """Остановка аккаунта"""
        if account_id in self.accounts:
            return self.accounts[account_id].stop()
        return False
    
    def get_account_status(self, account_id):
        """Получение статуса аккаунта"""
        if account_id in self.accounts:
            return self.accounts[account_id].get_status()
        return None
    
    def get_all_accounts_status(self):
        """Получение статуса всех аккаунтов"""
        return {account_id: account.get_status() for account_id, account in self.accounts.items()}
    
    def stop_all_accounts(self):
        """Остановка всех аккаунтов"""
        for account_id in list(self.accounts.keys()):
            self.stop_account(account_id)
        return True 