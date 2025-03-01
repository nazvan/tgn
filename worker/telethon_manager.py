import asyncio
import threading
from telethon import TelegramClient
from telethon.sessions import StringSession

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
        self.thread = None
        self.loop = None
    
    async def _run_client(self):
        """Запуск клиента Telethon"""
        # Создание клиента с использованием StringSession
        session = StringSession(self.session_string) if self.session_string else StringSession()
        self.client = TelegramClient(session, self.api_id, self.api_hash)
        
        # Подключение к Telegram
        await self.client.connect()
        
        # Если не авторизован, выполнить авторизацию
        if not await self.client.is_user_authorized():
            # В реальном приложении здесь будет логика авторизации
            # Например, запрос кода подтверждения и т.д.
            pass
        
        # Сохранение строки сессии, если она не была предоставлена
        if not self.session_string:
            self.session_string = self.client.session.save()
        
        # Здесь будет основная логика работы клиента
        # Например, мониторинг сообщений, отправка сообщений и т.д.
        while self.is_running:
            # Пример: просто ожидание, чтобы клиент оставался активным
            await asyncio.sleep(1)
    
    def _thread_function(self):
        """Функция для запуска клиента в отдельном потоке"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._run_client())
    
    def start(self):
        """Запуск аккаунта в отдельном потоке"""
        if not self.is_running:
            self.is_running = True
            self.thread = threading.Thread(target=self._thread_function)
            self.thread.daemon = True
            self.thread.start()
            return True
        return False
    
    def stop(self):
        """Остановка аккаунта"""
        if self.is_running:
            self.is_running = False
            if self.client and self.client.is_connected():
                # Используем loop для выполнения корутины disconnect
                if self.loop:
                    asyncio.run_coroutine_threadsafe(self.client.disconnect(), self.loop)
            # Ожидание завершения потока
            if self.thread and self.thread.is_alive():
                self.thread.join(timeout=5)
            return True
        return False
    
    def get_status(self):
        """Получение статуса аккаунта"""
        return {
            'account_id': self.account_id,
            'phone': self.phone,
            'is_running': self.is_running,
            'is_connected': self.client.is_connected() if self.client else False
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