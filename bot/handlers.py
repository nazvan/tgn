from telegram import Update, ParseMode
from telegram.ext import CallbackContext, ConversationHandler
from sqlalchemy.orm import Session

from database.models import SessionLocal
from database.operations import (
    create_worker, get_all_workers, get_worker, update_worker_status,
    create_account, get_worker_accounts, get_account, update_account_status
)
from celery_app.tasks import (
    register_worker, check_worker_status, add_account_to_worker,
    start_account, stop_account, check_account_status, list_active_workers
)
from .keyboards import (
    get_main_menu, get_workers_menu, get_accounts_menu,
    get_worker_control_keyboard, get_account_control_keyboard,
    get_worker_selection_keyboard, get_account_selection_keyboard
)

# Состояния для ConversationHandler
(
    MAIN_MENU, WORKERS_MENU, ACCOUNTS_MENU,
    ADD_ACCOUNT_PHONE, ADD_ACCOUNT_API_ID, ADD_ACCOUNT_API_HASH, ADD_ACCOUNT_WORKER
) = range(7)

# Функция для получения сессии базы данных
def get_db():
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()

# Обработчики команд

def start(update: Update, context: CallbackContext) -> int:
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    
    update.message.reply_text(
        "👋 Добро пожаловать в бота для управления воркерами и аккаунтами Telethon!\n\n"
        "Используйте меню для навигации:",
        reply_markup=get_main_menu()
    )
    
    return MAIN_MENU

def main_menu(update: Update, context: CallbackContext) -> int:
    """Обработчик главного меню"""
    text = update.message.text
    
    if text == "👥 Воркеры":
        update.message.reply_text(
            "Меню управления воркерами:",
            reply_markup=get_workers_menu()
        )
        return WORKERS_MENU
    
    elif text == "👤 Аккаунты":
        update.message.reply_text(
            "Меню управления аккаунтами:",
            reply_markup=get_accounts_menu()
        )
        return ACCOUNTS_MENU
    
    elif text == "📊 Статистика":
        # Здесь будет логика отображения статистики
        update.message.reply_text(
            "Статистика пока недоступна.",
            reply_markup=get_main_menu()
        )
        return MAIN_MENU
    
    elif text == "⚙️ Настройки":
        # Здесь будет логика настроек
        update.message.reply_text(
            "Настройки пока недоступны.",
            reply_markup=get_main_menu()
        )
        return MAIN_MENU
    
    else:
        update.message.reply_text(
            "Пожалуйста, используйте меню для навигации.",
            reply_markup=get_main_menu()
        )
        return MAIN_MENU

# Обработчики для воркеров

def workers_menu(update: Update, context: CallbackContext) -> int:
    """Обработчик меню воркеров"""
    text = update.message.text
    
    if text == "📋 Список воркеров":
        # Отправляем сообщение о загрузке, так как проверка может занять время
        loading_message = update.message.reply_text(
            "Загрузка списка воркеров... ⏳"
        )
        
        db = get_db()
        # Получаем всех воркеров из базы данных
        db_workers = get_all_workers(db)
        
        if not db_workers:
            # Используем reply вместо edit_text, чтобы избежать проблем с клавиатурой
            update.message.reply_text(
                "Список воркеров пуст. Запустите воркер, чтобы он появился в списке.",
                reply_markup=get_workers_menu()
            )
            return WORKERS_MENU
        
        # Получаем активные воркеры через Redis/Celery
        try:
            # Запрашиваем список активных воркеров через Celery
            active_workers_result = list_active_workers.delay()
            active_workers_data = active_workers_result.get(timeout=10)
            
            active_worker_names = set()
            if active_workers_data and active_workers_data.get('status') == 'success':
                workers_list = active_workers_data.get('workers', [])
                active_worker_names = {worker.get('name') for worker in workers_list}
            
            # Обновляем статусы воркеров в базе данных на основе данных из Redis
            for worker in db_workers:
                is_active = worker.name in active_worker_names
                if worker.is_active != is_active:
                    update_worker_status(db, worker.id, is_active)
                    # Обновляем объект локально, так как база уже обновлена
                    worker.is_active = is_active
            
            # Получаем обновленный список воркеров
            updated_workers = get_all_workers(db)
            
            if not updated_workers:
                # Используем reply вместо edit_text
                update.message.reply_text(
                    "Список воркеров пуст. Запустите воркер, чтобы он появился в списке.",
                    reply_markup=get_workers_menu()
                )
            else:
                # Добавляем информацию о реальном статусе воркеров через Redis
                text = "Список воркеров:\n\n"
                for i, worker in enumerate(updated_workers, 1):
                    online_status = "🟢 Онлайн" if worker.is_active else "🔴 Оффлайн"
                    text += f"{i}. {worker.name} - {online_status}\n   Сервер: {worker.server_address}\n\n"
                
                # Используем reply вместо edit_text
                update.message.reply_text(
                    text,
                    reply_markup=get_workers_menu()
                )
        except Exception as e:
            # В случае ошибки при взаимодействии с Celery/Redis показываем данные только из БД
            text = "Невозможно получить реальные статусы воркеров. Отображаются данные из базы:\n\n"
            for i, worker in enumerate(db_workers, 1):
                status = "✅ Активен" if worker.is_active else "❌ Неактивен"
                text += f"{i}. {worker.name} - {status}\n   Сервер: {worker.server_address}\n\n"
            
            # Используем reply вместо edit_text
            update.message.reply_text(
                text,
                reply_markup=get_workers_menu()
            )
        
        return WORKERS_MENU
    
    elif text == "🔙 Назад":
        update.message.reply_text(
            "Главное меню:",
            reply_markup=get_main_menu()
        )
        return MAIN_MENU
    
    else:
        update.message.reply_text(
            "Пожалуйста, используйте меню для навигации.",
            reply_markup=get_workers_menu()
        )
        return WORKERS_MENU

def worker_callback(update: Update, context: CallbackContext) -> int:
    """Обработчик callback-запросов для воркеров"""
    query = update.callback_query
    query.answer()
    
    data = query.data.split(':')
    action = data[0]
    worker_id = int(data[1]) if len(data) > 1 else None
    
    db = get_db()
    
    if action == "select_worker":
        worker = get_worker(db, worker_id)
        
        if worker:
            # Перед отображением информации о воркере проверим его статус через Celery
            try:
                status_result = check_worker_status.delay(worker.name)
                status_data = status_result.get(timeout=5)
                worker_status = status_data.get('status', 'неизвестен')
                
                # Обновляем статус воркера в базе данных
                is_active = worker_status == 'online'
                if worker.is_active != is_active:
                    update_worker_status(db, worker_id, is_active)
                    worker.is_active = is_active
                
                status_emoji = "🟢 Онлайн" if is_active else "🔴 Оффлайн"
            except Exception:
                worker_status = "не удалось определить"
                status_emoji = "❓ Статус неизвестен"
            
            query.edit_message_text(
                f"Воркер: {worker.name}\n"
                f"Адрес: {worker.server_address}\n"
                f"Статус: {status_emoji}\n"
                f"Аккаунтов: {len(worker.accounts)}",
                reply_markup=get_worker_control_keyboard(worker_id)
            )
        else:
            query.edit_message_text(
                "Воркер не найден.",
                reply_markup=None
            )
    
    elif action == "worker_accounts":
        worker = get_worker(db, worker_id)
        accounts = get_worker_accounts(db, worker_id)
        
        if accounts:
            text = f"Аккаунты воркера {worker.name}:\n\n"
            for i, account in enumerate(accounts, 1):
                text += f"{i}. {account.phone} - {'Активен' if account.is_active else 'Неактивен'}\n"
            
            query.edit_message_text(
                text,
                reply_markup=get_account_selection_keyboard(accounts)
            )
        else:
            query.edit_message_text(
                f"У воркера {worker.name} нет аккаунтов.",
                reply_markup=get_worker_control_keyboard(worker_id)
            )
    
    elif action == "worker_status":
        worker = get_worker(db, worker_id)
        
        # Отправка задачи для проверки статуса воркера
        try:
            result = check_worker_status.delay(worker.name)
            status = result.get(timeout=5)  # Ожидание результата с таймаутом
            
            status_text = status.get('status', 'неизвестен')
            status_emoji = "🟢 Онлайн" if status_text == 'online' else "🔴 Оффлайн"
            
            query.edit_message_text(
                f"Статус воркера {worker.name}:\n\n"
                f"Статус: {status_emoji}\n",
                reply_markup=get_worker_control_keyboard(worker_id)
            )
            
            # Обновляем статус воркера в базе данных
            is_active = status_text == 'online'
            if worker.is_active != is_active:
                update_worker_status(db, worker_id, is_active)
        except Exception as e:
            query.edit_message_text(
                f"Ошибка при проверке статуса воркера {worker.name}:\n"
                f"{str(e)}",
                reply_markup=get_worker_control_keyboard(worker_id)
            )
    
    elif action == "worker_activate":
        worker = update_worker_status(db, worker_id, True)
        
        query.edit_message_text(
            f"✅ Воркер {worker.name} активирован в базе данных.\n"
            f"Реальный статус может отличаться.",
            reply_markup=get_worker_control_keyboard(worker_id)
        )
    
    elif action == "worker_deactivate":
        worker = update_worker_status(db, worker_id, False)
        
        query.edit_message_text(
            f"❌ Воркер {worker.name} деактивирован в базе данных.",
            reply_markup=get_worker_control_keyboard(worker_id)
        )
    
    elif action == "back_to_main":
        query.edit_message_text(
            "Выберите действие в меню:",
            reply_markup=None
        )
    
    return WORKERS_MENU

# Обработчики для аккаунтов

def accounts_menu(update: Update, context: CallbackContext) -> int:
    """Обработчик меню аккаунтов"""
    text = update.message.text
    
    if text == "➕ Добавить аккаунт":
        update.message.reply_text(
            "Введите номер телефона аккаунта в международном формате (например, +79123456789):"
        )
        return ADD_ACCOUNT_PHONE
    
    elif text == "📋 Список аккаунтов":
        db = get_db()
        # Получаем всех воркеров и их аккаунты
        workers = get_all_workers(db, active_only=True)
        
        if not workers:
            update.message.reply_text(
                "Нет активных воркеров. Сначала добавьте и активируйте воркера.",
                reply_markup=get_accounts_menu()
            )
        else:
            text = "Список аккаунтов по воркерам:\n\n"
            
            for worker in workers:
                text += f"Воркер: {worker.name}\n"
                accounts = get_worker_accounts(db, worker.id)
                
                if accounts:
                    for i, account in enumerate(accounts, 1):
                        text += f"  {i}. {account.phone} - {'Активен' if account.is_active else 'Неактивен'}\n"
                else:
                    text += "  Нет аккаунтов\n"
                
                text += "\n"
            
            update.message.reply_text(
                text,
                reply_markup=get_accounts_menu()
            )
        
        return ACCOUNTS_MENU
    
    elif text == "🔙 Назад":
        update.message.reply_text(
            "Главное меню:",
            reply_markup=get_main_menu()
        )
        return MAIN_MENU
    
    else:
        update.message.reply_text(
            "Пожалуйста, используйте меню для навигации.",
            reply_markup=get_accounts_menu()
        )
        return ACCOUNTS_MENU

def add_account_phone(update: Update, context: CallbackContext) -> int:
    """Обработчик ввода номера телефона аккаунта"""
    phone = update.message.text
    context.user_data['account_phone'] = phone
    
    update.message.reply_text(
        f"Номер телефона: {phone}\n\n"
        "Теперь введите API ID аккаунта:"
    )
    
    return ADD_ACCOUNT_API_ID

def add_account_api_id(update: Update, context: CallbackContext) -> int:
    """Обработчик ввода API ID аккаунта"""
    api_id = update.message.text
    context.user_data['account_api_id'] = api_id
    
    update.message.reply_text(
        f"API ID: {api_id}\n\n"
        "Теперь введите API Hash аккаунта:"
    )
    
    return ADD_ACCOUNT_API_HASH

def add_account_api_hash(update: Update, context: CallbackContext) -> int:
    """Обработчик ввода API Hash аккаунта"""
    api_hash = update.message.text
    context.user_data['account_api_hash'] = api_hash
    
    db = get_db()
    workers = get_all_workers(db, active_only=True)
    
    if not workers:
        update.message.reply_text(
            "Нет активных воркеров. Сначала добавьте и активируйте воркера.",
            reply_markup=get_accounts_menu()
        )
        return ACCOUNTS_MENU
    
    keyboard = get_worker_selection_keyboard(workers)
    
    update.message.reply_text(
        "Выберите воркера для этого аккаунта:",
        reply_markup=keyboard
    )
    
    return ADD_ACCOUNT_WORKER

def add_account_worker(update: Update, context: CallbackContext) -> int:
    """Обработчик выбора воркера для аккаунта"""
    query = update.callback_query
    query.answer()
    
    data = query.data.split(':')
    action = data[0]
    worker_id = int(data[1]) if len(data) > 1 else None
    
    if action != "select_worker":
        query.edit_message_text(
            "Пожалуйста, выберите воркера из списка.",
            reply_markup=None
        )
        return ACCOUNTS_MENU
    
    phone = context.user_data.get('account_phone')
    api_id = context.user_data.get('account_api_id')
    api_hash = context.user_data.get('account_api_hash')
    
    db = get_db()
    worker = get_worker(db, worker_id)
    
    # Создание аккаунта в базе данных
    account = create_account(db, phone, api_id, api_hash, worker_id)
    
    # Отправка задачи для добавления аккаунта к воркеру
    account_data = {
        'id': account.id,
        'phone': phone,
        'api_id': api_id,
        'api_hash': api_hash
    }
    add_account_to_worker.delay(worker.name, account_data)
    
    query.edit_message_text(
        f"✅ Аккаунт {phone} успешно добавлен к воркеру {worker.name}!",
        reply_markup=None
    )
    
    # Очистка данных пользователя
    context.user_data.clear()
    
    return ACCOUNTS_MENU

def account_callback(update: Update, context: CallbackContext) -> int:
    """Обработчик callback-запросов для аккаунтов"""
    query = update.callback_query
    query.answer()
    
    data = query.data.split(':')
    action = data[0]
    account_id = int(data[1]) if len(data) > 1 else None
    
    db = get_db()
    
    if action == "select_account":
        account = get_account(db, account_id)
        worker = get_worker(db, account.worker_id)
        
        if account:
            query.edit_message_text(
                f"Аккаунт: {account.phone}\n"
                f"Воркер: {worker.name}\n"
                f"Статус: {'Активен' if account.is_active else 'Неактивен'}",
                reply_markup=get_account_control_keyboard(account_id)
            )
        else:
            query.edit_message_text(
                "Аккаунт не найден.",
                reply_markup=None
            )
    
    elif action == "account_start":
        account = get_account(db, account_id)
        worker = get_worker(db, account.worker_id)
        
        # Отправка задачи для запуска аккаунта
        result = start_account.delay(worker.name, account_id)
        response = result.get(timeout=5)  # Ожидание результата с таймаутом
        
        if response.get('status') == 'success':
            # Обновление статуса аккаунта в базе данных
            update_account_status(db, account_id, True)
            
            query.edit_message_text(
                f"✅ Аккаунт {account.phone} запущен на воркере {worker.name}.",
                reply_markup=get_account_control_keyboard(account_id)
            )
        else:
            query.edit_message_text(
                f"❌ Не удалось запустить аккаунт {account.phone}: {response.get('message')}",
                reply_markup=get_account_control_keyboard(account_id)
            )
    
    elif action == "account_stop":
        account = get_account(db, account_id)
        worker = get_worker(db, account.worker_id)
        
        # Отправка задачи для остановки аккаунта
        result = stop_account.delay(worker.name, account_id)
        response = result.get(timeout=5)  # Ожидание результата с таймаутом
        
        if response.get('status') == 'success':
            # Обновление статуса аккаунта в базе данных
            update_account_status(db, account_id, False)
            
            query.edit_message_text(
                f"⏹️ Аккаунт {account.phone} остановлен на воркере {worker.name}.",
                reply_markup=get_account_control_keyboard(account_id)
            )
        else:
            query.edit_message_text(
                f"❌ Не удалось остановить аккаунт {account.phone}: {response.get('message')}",
                reply_markup=get_account_control_keyboard(account_id)
            )
    
    elif action == "account_status":
        account = get_account(db, account_id)
        worker = get_worker(db, account.worker_id)
        
        # Отправка задачи для проверки статуса аккаунта
        result = check_account_status.delay(worker.name, account_id)
        status = result.get(timeout=5)  # Ожидание результата с таймаутом
        
        query.edit_message_text(
            f"Статус аккаунта {account.phone}:\n\n"
            f"Статус: {status.get('status', 'Неизвестно')}\n",
            reply_markup=get_account_control_keyboard(account_id)
        )
    
    elif action == "account_delete":
        # Здесь будет логика удаления аккаунта
        query.edit_message_text(
            "Функция удаления аккаунта пока не реализована.",
            reply_markup=None
        )
    
    return ACCOUNTS_MENU 