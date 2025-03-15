from telegram import Update, ParseMode, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler
from sqlalchemy.orm import Session
import redis
import json
import time
import logging

from database.models import SessionLocal
from database.operations import (
    create_worker, get_all_workers, get_worker, update_worker_status,
    create_account, get_worker_accounts, get_account, update_account_status,
    get_account_by_phone, delete_worker, get_all_accounts
)
from celery_app.tasks import (
    celery_app, register_worker, check_worker_status, add_account_to_worker,
    start_account, stop_account, check_account_status
)
from .keyboards import (
    get_main_menu, get_workers_menu, get_accounts_menu,
    get_worker_control_keyboard, get_account_control_keyboard,
    get_worker_selection_keyboard, get_account_selection_keyboard,
    get_telethon_account_keyboard, get_worker_selection_keyboard_for_accounts
)
from config import REDIS_URL, WORKER_STATUS_KEY_PREFIX, WORKER_LAST_SEEN_KEY_PREFIX, WORKER_ONLINE_TIMEOUT

# Состояния диалога
MAIN_MENU, WORKERS_MENU, ACCOUNTS_MENU = range(3)
ADD_ACCOUNT_PHONE, ADD_ACCOUNT_API_ID, ADD_ACCOUNT_API_HASH, ADD_ACCOUNT_CONFIRM = range(3, 7)

# Инициализация Redis-клиента
redis_client = redis.Redis.from_url(REDIS_URL)

# Логгер
logger = logging.getLogger(__name__)

# Генератор сессий с базой данных
def get_db():
    """Функция-генератор сессий для работы с базой данных"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Обработчики команд

def start(update: Update, context: CallbackContext) -> int:
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    
    update.message.reply_text(
        "👋 Добро пожаловать в бота для управления воркерами!\n\n"
        "Нажмите кнопку для просмотра списка воркеров:",
        reply_markup=get_main_menu()
    )
    
    return MAIN_MENU

def main_menu_callback(update: Update, context: CallbackContext) -> int:
    """Обработчик callback-запросов для главного меню"""
    query = update.callback_query
    query.answer()
    
    action = query.data
    
    if action == "main_workers":
        return workers_menu(update, context)
    elif action == "main_accounts":
        return accounts_menu(update, context)
    elif action == "back_to_main":
        query.edit_message_text(
            "Главное меню:",
            reply_markup=get_main_menu()
        )
        return MAIN_MENU
    
    return MAIN_MENU

def main_menu(update: Update, context: CallbackContext) -> int:
    """Обработчик сообщений в главном меню (оставлен для обратной совместимости)"""
    # Отправляем новое меню с инлайн-кнопками
    update.message.reply_text(
        "Используйте кнопку для просмотра списка воркеров:",
        reply_markup=get_main_menu()
    )
    return MAIN_MENU

# Обработчики для воркеров

def workers_menu(update: Update, context: CallbackContext) -> int:
    """Обработчик сообщений в меню воркеров (оставлен для обратной совместимости)"""
    # Отправляем новое меню с инлайн-кнопками
    update.message.reply_text(
        "Меню управления воркерами:",
        reply_markup=get_workers_menu()
    )
    return WORKERS_MENU

def workers_menu_callback(update: Update, context: CallbackContext) -> int:
    """Обработчик callback-запросов для меню воркеров"""
    query = update.callback_query
    query.answer()
    
    data = query.data
    
    if data == "workers_list":
        # Получаем список всех воркеров напрямую
        db = next(get_db())
        workers = get_all_workers(db)
        
        if not workers:
            query.edit_message_text(
                "Список воркеров пуст. Запустите воркер, чтобы он появился в списке.",
                reply_markup=get_main_menu()
            )
            return MAIN_MENU
        
        # Получаем статусы воркеров из Redis
        try:
            # Получаем текущее время
            current_time = int(time.time())
            
            # Получаем все ключи со статусами воркеров
            worker_keys = redis_client.keys(f"{WORKER_STATUS_KEY_PREFIX}*")
            active_worker_names = set()
            
            # Проверяем статус каждого воркера в Redis
            for key in worker_keys:
                worker_name = key.decode('utf-8').replace(WORKER_STATUS_KEY_PREFIX, "")
                
                # Получаем данные воркера
                worker_data_raw = redis_client.get(key)
                worker_data = json.loads(worker_data_raw) if worker_data_raw else None
                
                # Получаем время последнего обновления статуса
                last_seen_key = f"{WORKER_LAST_SEEN_KEY_PREFIX}{worker_name}"
                last_seen_raw = redis_client.get(last_seen_key)
                last_seen = int(last_seen_raw) if last_seen_raw else 0
                
                # Воркер активен, если обновлял статус недавно и не отмечен явно как offline
                if worker_data and (current_time - last_seen <= WORKER_ONLINE_TIMEOUT) and worker_data.get('status') != 'offline':
                    active_worker_names.add(worker_name)
            
            # Обновляем статус воркеров в базе данных
            for worker in workers:
                is_active = worker.name in active_worker_names
                # Обновляем статус в БД только если он изменился
                if worker.is_active != is_active:
                    update_worker_status(db, worker.id, is_active)
                    worker.is_active = is_active
            
            # Формируем сообщение со списком всех воркеров
            message = f"Все воркеры ({len(workers)}):\n\n"
            
            for worker in workers:
                status_emoji = "🟢" if worker.is_active else "🔴"
                message += f"{status_emoji} {worker.name} - {worker.server_address}\n"
            
            # Отправляем список воркеров с клавиатурой для выбора
            query.edit_message_text(
                message,
                reply_markup=get_worker_selection_keyboard(workers)
            )
        except Exception as e:
            # В случае ошибки показываем данные из базы данных
            message = "Не удалось получить актуальные статусы воркеров. Показаны данные из базы данных:\n\n"
            
            for worker in workers:
                status_emoji = "🟢" if worker.is_active else "🔴"
                message += f"{status_emoji} {worker.name} - {worker.server_address}\n"
            
            query.edit_message_text(
                message,
                reply_markup=get_worker_selection_keyboard(workers)
            )
        
        return WORKERS_MENU
    
    elif data == "back_to_main":
        query.edit_message_text(
            "Главное меню:",
            reply_markup=get_main_menu()
        )
        return MAIN_MENU
    
    return WORKERS_MENU

def worker_callback(update: Update, context: CallbackContext) -> int:
    """Обработчик callback-запросов для воркеров"""
    query = update.callback_query
    query.answer()
    
    data = query.data.split(':')
    action = data[0]
    worker_id = int(data[1]) if len(data) > 1 else None
    
    db = next(get_db())
    
    # Обработчик для кнопки "Назад"
    if action == "back_to_workers":
        try:
            # Возвращаемся к списку воркеров
            workers = get_all_workers(db)
            
            # Формируем сообщение со списком всех воркеров
            message = f"Все воркеры ({len(workers)}):\n\n"
            
            # Получаем статусы воркеров из Redis
            current_time = int(time.time())
            active_worker_names = set()
            
            try:
                # Получаем все ключи со статусами воркеров
                worker_keys = redis_client.keys(f"{WORKER_STATUS_KEY_PREFIX}*")
                
                # Проверяем статус каждого воркера в Redis
                for key in worker_keys:
                    worker_name = key.decode('utf-8').replace(WORKER_STATUS_KEY_PREFIX, "")
                    
                    # Получаем данные воркера
                    worker_data_raw = redis_client.get(key)
                    worker_data = json.loads(worker_data_raw) if worker_data_raw else None
                    
                    # Получаем время последнего обновления статуса
                    last_seen_key = f"{WORKER_LAST_SEEN_KEY_PREFIX}{worker_name}"
                    last_seen_raw = redis_client.get(last_seen_key)
                    last_seen = int(last_seen_raw) if last_seen_raw else 0
                    
                    # Воркер активен, если обновлял статус недавно и не отмечен явно как offline
                    if worker_data and (current_time - last_seen <= WORKER_ONLINE_TIMEOUT) and worker_data.get('status') != 'offline':
                        active_worker_names.add(worker_name)
            except Exception as e:
                logger.error(f"Ошибка при получении статусов воркеров из Redis: {str(e)}")
            
            # Формируем список воркеров с актуальными статусами
            for worker in workers:
                is_active = worker.name in active_worker_names
                # Обновляем статус в БД только если он изменился
                if worker.is_active != is_active:
                    update_worker_status(db, worker.id, is_active)
                    worker.is_active = is_active
                
                status_emoji = "🟢" if worker.is_active else "🔴"
                message += f"{status_emoji} {worker.name} - {worker.server_address}\n"
            
            query.edit_message_text(
                message,
                reply_markup=get_worker_selection_keyboard(workers)
            )
        except Exception as e:
            # Обрабатываем возможные ошибки при обновлении сообщения
            logger.error(f"Ошибка при возврате к списку воркеров: {str(e)}")
        return WORKERS_MENU
    
    if action == "select_worker":
        worker = get_worker(db, worker_id)
        
        if worker:
            # Проверяем статус воркера напрямую через Redis
            try:
                # Получаем текущее время
                current_time = int(time.time())
                
                # Проверяем статус воркера в Redis
                worker_key = f"{WORKER_STATUS_KEY_PREFIX}{worker.name}"
                worker_last_seen_key = f"{WORKER_LAST_SEEN_KEY_PREFIX}{worker.name}"
                
                worker_data_raw = redis_client.get(worker_key)
                last_seen_raw = redis_client.get(worker_last_seen_key)
                
                is_active = False
                
                if worker_data_raw and last_seen_raw:
                    worker_data = json.loads(worker_data_raw)
                    last_seen = int(last_seen_raw)
                    
                    # Воркер активен, если обновлял статус недавно и не отмечен явно как offline
                    if (current_time - last_seen <= WORKER_ONLINE_TIMEOUT) and worker_data.get('status') != 'offline':
                        is_active = True
                
                # Обновляем статус воркера в базе данных
                if worker.is_active != is_active:
                    update_worker_status(db, worker_id, is_active)
                    worker.is_active = is_active
                
                status_emoji = "🟢 Онлайн" if is_active else "🔴 Оффлайн"
                
                # Формируем информацию о воркере
                text = f"🤖 <b>Воркер: {worker.name}</b>\n\n"
                text += f"🌐 Сервер: {worker.server_address}\n"
                text += f"🔄 Статус: {status_emoji}\n"
                text += f"⏱ Создан: {worker.created_at.strftime('%d.%m.%Y %H:%M:%S')}\n"
                
                if last_seen_raw:
                    text += f"⏰ Последняя активность: {time.strftime('%d.%m.%Y %H:%M:%S', time.localtime(int(last_seen_raw)))}\n"
            
            except Exception:
                status_emoji = "❓ Статус неизвестен"
                
                # Формируем базовую информацию о воркере
                text = f"🤖 <b>Воркер: {worker.name}</b>\n\n"
                text += f"🌐 Сервер: {worker.server_address}\n"
                text += f"🔄 Статус: {status_emoji}\n"
                text += f"⏱ Создан: {worker.created_at.strftime('%d.%m.%Y %H:%M:%S')}\n"
            
            try:
                query.edit_message_text(
                    text,
                    reply_markup=get_worker_control_keyboard(worker_id),
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logger.error(f"Ошибка при отображении информации о воркере: {str(e)}")
        else:
            query.edit_message_text(
                "Воркер не найден.",
                reply_markup=None
            )
    
    elif action == "worker_status":
        worker = get_worker(db, worker_id)
        
        # Получаем данные о воркере из Redis
        worker_key = f"{WORKER_STATUS_KEY_PREFIX}{worker.name}"
        worker_last_seen_key = f"{WORKER_LAST_SEEN_KEY_PREFIX}{worker.name}"
            
        worker_data_raw = redis_client.get(worker_key)
        worker_data = json.loads(worker_data_raw) if worker_data_raw else None
            
        last_seen_raw = redis_client.get(worker_last_seen_key)
        last_seen = int(last_seen_raw) if last_seen_raw else 0
        
        current_time = int(time.time())
        
        # Определяем статус воркера
        status = "🔴 Оффлайн"
        if worker_data and (current_time - last_seen <= WORKER_ONLINE_TIMEOUT) and worker_data.get('status') != 'offline':
            status = "🟢 Онлайн"
        
        # Формируем сообщение со статусом воркера
        text = f"🤖 <b>Воркер: {worker.name}</b>\n\n"
        text += f"🌐 Сервер: {worker.server_address}\n"
        text += f"🔄 Статус: {status}\n"
        text += f"⏱ Создан: {worker.created_at.strftime('%d.%m.%Y %H:%M:%S')}\n"
        
        if last_seen > 0:
            text += f"⏰ Последняя активность: {time.strftime('%d.%m.%Y %H:%M:%S', time.localtime(last_seen))}\n"
        
        try:
            query.edit_message_text(
                text,
                reply_markup=get_worker_control_keyboard(worker_id),
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Ошибка при обновлении статуса воркера: {str(e)}")
    
    elif action == "worker_delete":
        # Получаем информацию о воркере перед удалением
        worker = get_worker(db, worker_id)
        worker_name = worker.name if worker else "Неизвестный"
        
        # Пытаемся удалить воркер из базы данных
        success = delete_worker(db, worker_id)
        
        if success:
            # Удаляем также информацию из Redis
            try:
                worker_key = f"{WORKER_STATUS_KEY_PREFIX}{worker_name}"
                worker_last_seen_key = f"{WORKER_LAST_SEEN_KEY_PREFIX}{worker_name}"
                
                redis_client.delete(worker_key)
                redis_client.delete(worker_last_seen_key)
            except:
                pass
            
            # Получаем обновленный список воркеров
            workers = get_all_workers(db)
            
            if workers:
                # Формируем сообщение со списком оставшихся воркеров
                message = f"🗑️ Воркер {worker_name} удален.\n\n"
                message += f"Оставшиеся воркеры ({len(workers)}):\n\n"
                
                for w in workers:
                    status_emoji = "🟢" if w.is_active else "🔴"
                    message += f"{status_emoji} {w.name} - {w.server_address}\n"
                
                query.edit_message_text(
                    message,
                    reply_markup=get_worker_selection_keyboard(workers)
                )
            else:
                # Если воркеров не осталось
                query.edit_message_text(
                    f"🗑️ Воркер {worker_name} удален.\n\n"
                    "Список воркеров пуст.",
                    reply_markup=get_main_menu()
                )
                return MAIN_MENU
        else:
            query.edit_message_text(
                f"❌ Не удалось удалить воркер {worker_name}.",
                reply_markup=get_worker_control_keyboard(worker_id)
            )
    
    elif action == "back_to_main":
        # Возвращаемся в главное меню
        try:
            query.edit_message_text(
                "Главное меню бота управления воркерами:",
                reply_markup=get_main_menu()
            )
        except Exception as e:
            logger.error(f"Ошибка при возврате в главное меню: {str(e)}")
        return MAIN_MENU
    
    elif action == "worker_accounts":
        worker = get_worker(db, worker_id)
        accounts = get_worker_accounts(db, worker_id)
        
        if accounts:
            text = f"📱 <b>Аккаунты воркера {worker.name}</b> ({len(accounts)}):\n\n"
            
            for i, account in enumerate(accounts, 1):
                # Проверяем статус аккаунта в Redis
                try:
                    account_status_key = f"account_status:{account.id}"
                    account_status_raw = redis_client.get(account_status_key)
                    
                    if account_status_raw:
                        account_status = json.loads(account_status_raw)
                        is_running = account_status.get('is_running', False)
                        status_emoji = "🟢" if is_running else "🔴"
                    else:
                        status_emoji = "⚪️"
                except:
                    status_emoji = "⚠️"
                
                text += f"{i}. {status_emoji} <b>{account.phone}</b>\n"
            
            # Добавляем кнопки для возврата к воркеру и добавления нового аккаунта
            keyboard = [
                [InlineKeyboardButton("➕ Добавить аккаунт", callback_data=f"worker_add_account:{worker_id}")],
                [InlineKeyboardButton("🔙 К воркеру", callback_data=f"select_worker:{worker_id}")]
            ]
            
            query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.HTML
            )
        else:
            # Если у воркера нет аккаунтов
            text = f"📱 У воркера <b>{worker.name}</b> нет аккаунтов.\n\nДобавьте аккаунт с помощью кнопки ниже."
            
            keyboard = [
                [InlineKeyboardButton("➕ Добавить аккаунт", callback_data=f"worker_add_account:{worker_id}")],
                [InlineKeyboardButton("🔙 К воркеру", callback_data=f"select_worker:{worker_id}")]
            ]
            
            query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.HTML
            )
    
    elif action == "worker_add_account":
        # Сохраняем ID воркера в context.user_data для использования позже
        context.user_data['selected_worker_id'] = worker_id
        
        # Запрашиваем номер телефона для аккаунта
        query.edit_message_text(
            "📱 <b>Добавление нового аккаунта Telethon</b>\n\n"
            "Введите номер телефона в международном формате (например, +79123456789):",
            parse_mode=ParseMode.HTML
        )
        
        return ADD_ACCOUNT_PHONE
    
    return WORKERS_MENU

# Обработчики для аккаунтов

def accounts_menu(update: Update, context: CallbackContext) -> int:
    """Обработчик для меню аккаунтов"""
    text = "Меню управления аккаунтами:\n\n" + \
           "Здесь вы можете добавлять новые аккаунты, просматривать и управлять существующими."
    
    if update.callback_query:
        update.callback_query.edit_message_text(
            text,
            reply_markup=get_accounts_menu()
        )
    else:
        update.message.reply_text(
            text,
            reply_markup=get_accounts_menu()
        )
    
    return ACCOUNTS_MENU

def accounts_menu_callback(update: Update, context: CallbackContext) -> int:
    """Обработчик для обратных вызовов меню аккаунтов"""
    query = update.callback_query
    query.answer()
    
    action = query.data
    
    if action == "accounts_add":
        # Обработчик для добавления нового аккаунта
        query.edit_message_text(
            "Выберите воркер, к которому хотите добавить аккаунт:",
            reply_markup=get_worker_selection_keyboard_for_accounts(next(get_db()))
        )
        return ACCOUNTS_MENU
    
    elif action == "accounts_list":
        # Обработчик для просмотра списка аккаунтов
        db = next(get_db())
        accounts = get_all_accounts(db)
        
        if not accounts:
            query.edit_message_text(
                "🔴 Нет добавленных аккаунтов.\n\n"
                "Вы можете добавить новый аккаунт, нажав на кнопку 'Добавить аккаунт'.",
                reply_markup=get_accounts_menu()
            )
            return ACCOUNTS_MENU
        
        # Группируем аккаунты по воркерам для более удобного отображения
        accounts_by_worker = {}
        for account in accounts:
            worker = get_worker(db, account.worker_id)
            if worker:
                if worker.name not in accounts_by_worker:
                    accounts_by_worker[worker.name] = []
                accounts_by_worker[worker.name].append(account)
        
        # Формируем текст сообщения
        text = "📱 <b>Список всех аккаунтов</b>\n\n"
        
        if not accounts_by_worker:
            text += "Нет доступных аккаунтов."
        else:
            for worker_name, worker_accounts in accounts_by_worker.items():
                text += f"<b>🖥 Воркер {worker_name}</b>\n"
                for account in worker_accounts:
                    status = "🟢 Активен" if account.is_active else "🔴 Неактивен"
                    text += f"  • {account.phone} - {status}\n"
                text += "\n"
        
        query.edit_message_text(
            text,
            reply_markup=get_account_selection_keyboard(accounts),
            parse_mode=ParseMode.HTML
        )
        return ACCOUNTS_MENU
    
    elif action == "back_to_main":
        return main_menu_callback(update, context)
    
    return ACCOUNTS_MENU

def add_account_phone(update: Update, context: CallbackContext) -> int:
    """Обработчик для ввода номера телефона аккаунта"""
    phone = update.message.text.strip()
    
    # Проверяем формат номера телефона
    if not phone.startswith('+') or not phone[1:].isdigit():
        update.message.reply_text(
            "❌ Некорректный формат номера телефона. Пожалуйста, введите номер в международном формате, "
            "начиная с '+' (например, +79123456789):"
        )
        return ADD_ACCOUNT_PHONE
    
    # Сохраняем номер телефона в context.user_data
    context.user_data['account_phone'] = phone
    
    # Запрашиваем API ID
    update.message.reply_text(
        "📱 <b>Добавление аккаунта Telethon</b>\n\n"
        "Введите API ID аккаунта Telegram (например, 12345678):",
        parse_mode=ParseMode.HTML
    )
    
    return ADD_ACCOUNT_API_ID

def add_account_api_id(update: Update, context: CallbackContext) -> int:
    """Обработчик для ввода API ID аккаунта"""
    api_id = update.message.text.strip()
    
    # Проверяем, что API ID - это число
    if not api_id.isdigit():
        update.message.reply_text(
            "❌ Некорректный формат API ID. Пожалуйста, введите числовой API ID:"
        )
        return ADD_ACCOUNT_API_ID
    
    # Сохраняем API ID в context.user_data
    context.user_data['account_api_id'] = api_id
    
    # Запрашиваем API Hash
    update.message.reply_text(
        "📱 <b>Добавление аккаунта Telethon</b>\n\n"
        "Введите API Hash аккаунта Telegram (например, 0123456789abcdef0123456789abcdef):",
        parse_mode=ParseMode.HTML
    )
    
    return ADD_ACCOUNT_API_HASH

def add_account_api_hash(update: Update, context: CallbackContext) -> int:
    """Обработчик для ввода API Hash аккаунта"""
    api_hash = update.message.text.strip()
    
    # Минимальная проверка формата API Hash
    if len(api_hash) < 10:
        update.message.reply_text(
            "❌ Некорректный формат API Hash. Пожалуйста, введите API Hash:"
        )
        return ADD_ACCOUNT_API_HASH
    
    # Сохраняем API Hash в context.user_data
    context.user_data['account_api_hash'] = api_hash
    
    # Выводим сводку данных для подтверждения
    phone = context.user_data.get('account_phone', '')
    api_id = context.user_data.get('account_api_id', '')
    
    # Получаем информацию о воркере
    worker_id = context.user_data.get('selected_worker_id')
    db = next(get_db())
    worker = get_worker(db, worker_id)
    worker_name = worker.name if worker else "Неизвестный воркер"
    
    # Создаем клавиатуру для подтверждения
    keyboard = [
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data="account_confirm"),
            InlineKeyboardButton("❌ Отменить", callback_data=f"select_worker:{worker_id}")
        ]
    ]
    
    # Отправляем сообщение с подтверждением
    update.message.reply_text(
        f"📱 <b>Добавление аккаунта Telethon</b>\n\n"
        f"<b>Воркер:</b> {worker_name}\n"
        f"<b>Телефон:</b> {phone}\n"
        f"<b>API ID:</b> {api_id}\n"
        f"<b>API Hash:</b> {'*' * len(api_hash)}\n\n"
        f"Пожалуйста, проверьте данные и подтвердите добавление аккаунта:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )
    
    return ADD_ACCOUNT_CONFIRM

def add_account_confirm(update: Update, context: CallbackContext) -> int:
    """Обработчик для подтверждения добавления аккаунта"""
    query = update.callback_query
    query.answer()
    
    # Получаем данные аккаунта из context.user_data
    phone = context.user_data.get('account_phone', '')
    api_id = context.user_data.get('account_api_id', '')
    api_hash = context.user_data.get('account_api_hash', '')
    worker_id = context.user_data.get('selected_worker_id')
    
    # Если пользователь подтвердил добавление аккаунта
    if query.data == "account_confirm":
        db = next(get_db())
        
        try:
            # Проверяем, существует ли уже аккаунт с таким номером
            existing_account = get_account_by_phone(db, phone)
            
            if existing_account:
                query.edit_message_text(
                    f"❌ Аккаунт с номером {phone} уже существует.",
                    parse_mode=ParseMode.HTML
                )
                return WORKERS_MENU
            
            # Создаем новый аккаунт в базе данных
            account = create_account(db, phone, api_id, api_hash, worker_id)
            
            # Отправляем задачу для добавления аккаунта на воркер
            worker = get_worker(db, worker_id)
            
            # Создаем данные для отправки на воркер
            account_data = {
                'id': account.id,
                'phone': phone,
                'api_id': api_id,
                'api_hash': api_hash
            }
            
            # Отправляем задачу на воркер через Celery
            try:
                # Отправляем задачу add_account на воркер
                result = celery_app.send_task(
                    'worker.add_account',
                    args=[account_data],
                    kwargs={},
                    queue=worker.name,
                    expires=30
                )
                
                # Ждем результат не более 5 секунд
                task_result = result.get(timeout=5)
                
                if task_result and task_result.get('status') == 'success':
                    query.edit_message_text(
                        f"✅ Аккаунт {phone} успешно добавлен к воркеру {worker.name}.\n\n"
                        f"Статус: {task_result.get('message', 'Добавлен')}",
                        parse_mode=ParseMode.HTML
                    )
                else:
                    query.edit_message_text(
                        f"⚠️ Аккаунт {phone} добавлен в базу данных, но не удалось добавить его к воркеру {worker.name}.\n\n"
                        f"Ошибка: {task_result.get('message', 'Неизвестная ошибка')}",
                        parse_mode=ParseMode.HTML
                    )
            except Exception as e:
                query.edit_message_text(
                    f"⚠️ Аккаунт {phone} добавлен в базу данных, но произошла ошибка при добавлении к воркеру {worker.name}.\n\n"
                    f"Ошибка: {str(e)}",
                    parse_mode=ParseMode.HTML
                )
        except Exception as e:
            # В случае ошибки при создании аккаунта
            query.edit_message_text(
                f"❌ Ошибка при добавлении аккаунта: {str(e)}",
                parse_mode=ParseMode.HTML
            )
    else:
        # Если пользователь отменил добавление аккаунта
        query.edit_message_text(
            "❌ Добавление аккаунта отменено.",
            parse_mode=ParseMode.HTML
        )
    
    # Очищаем данные пользователя
    context.user_data.clear()
    
    return WORKERS_MENU

def account_callback(update: Update, context: CallbackContext) -> int:
    """Обработчик callback-запросов для аккаунтов"""
    query = update.callback_query
    query.answer()
    
    data = query.data.split(':')
    action = data[0]
    account_id = int(data[1]) if len(data) > 1 else None
    
    db = next(get_db())
    account = get_account(db, account_id)
    
    if action == "select_account":
        account = get_account(db, account_id)
        worker = get_worker(db, account.worker_id)
        
        if account:
            # Проверяем статус воркера напрямую через Redis
            try:
                # Получаем текущее время
                current_time = int(time.time())
                
                # Проверяем статус воркера в Redis
                worker_key = f"{WORKER_STATUS_KEY_PREFIX}{worker.name}"
                worker_last_seen_key = f"{WORKER_LAST_SEEN_KEY_PREFIX}{worker.name}"
                
                worker_data_raw = redis_client.get(worker_key)
                last_seen_raw = redis_client.get(worker_last_seen_key)
                
                worker_online = False
                
                if worker_data_raw and last_seen_raw:
                    last_seen = int(last_seen_raw)
                    worker_data = json.loads(worker_data_raw)
                    worker_status = worker_data.get('status', 'offline')
                    
                    # Воркер активен, если:
                    # 1. Обновлял статус недавно (в течение WORKER_ONLINE_TIMEOUT секунд)
                    # 2. И его статус не установлен явно как 'offline'
                    if (current_time - last_seen <= WORKER_ONLINE_TIMEOUT) and worker_status != 'offline':
                        worker_online = True
                
                # Если воркер не в сети, аккаунт тоже не может быть активен
                if not worker_online and account.is_active:
                    update_account_status(db, account_id, False)
                    account.is_active = False
                
                worker_status = "🟢 Онлайн" if worker_online else "🔴 Оффлайн"
                account_status = "✅ Активен" if account.is_active else "❌ Неактивен"
                
                query.edit_message_text(
                    f"Аккаунт: {account.phone}\n"
                    f"Воркер: {worker.name} ({worker_status})\n"
                    f"Статус: {account_status}",
                    reply_markup=get_account_control_keyboard(account_id)
                )
            except Exception as e:
                # В случае ошибки показываем данные только из БД
                query.edit_message_text(
                    f"Аккаунт: {account.phone}\n"
                    f"Воркер: {worker.name}\n"
                    f"Статус: {'Активен' if account.is_active else 'Неактивен'}\n"
                    f"(Ошибка при проверке статуса: {str(e)})",
                    reply_markup=get_account_control_keyboard(account_id)
                )
        else:
            query.edit_message_text(
                "Аккаунт не найден.",
                reply_markup=None
            )
    
    elif action == "account_start":
        # Запуск аккаунта через Celery
        try:
            # Проверяем статус воркера перед запросом
            current_time = int(time.time())
            worker_key = f"{WORKER_STATUS_KEY_PREFIX}{worker.name}"
            worker_last_seen_key = f"{WORKER_LAST_SEEN_KEY_PREFIX}{worker.name}"
            
            worker_data_raw = redis_client.get(worker_key)
            last_seen_raw = redis_client.get(worker_last_seen_key)
            
            worker_online = False
            if worker_data_raw and last_seen_raw:
                last_seen = int(last_seen_raw)
                worker_data = json.loads(worker_data_raw)
                
                if (current_time - last_seen <= WORKER_ONLINE_TIMEOUT) and worker_data.get('status') != 'offline':
                    worker_online = True
            
            if not worker_online:
                query.edit_message_text(
                    f"⚠️ Воркер {worker.name} не в сети. Невозможно запустить аккаунт {account.phone}.",
                    reply_markup=get_telethon_account_keyboard(account_id, worker.id),
                    parse_mode=ParseMode.HTML
                )
                return WORKERS_MENU
                
            # Запускаем аккаунт через Celery
            result = celery_app.send_task(
                'worker.start_account',
                args=[account_id],
                kwargs={},
                queue=worker.name,
                expires=10
            )
            
            # Ждем результат запуска не более 10 секунд
            task_result = result.get(timeout=10)
            
            if task_result and task_result.get('status') == 'success':
                # Обновляем статус аккаунта в базе данных
                update_account_status(db, account_id, True)
                
                # Сохраняем статус в Redis для быстрого доступа
                redis_client.set(
                    f"account_status:{account_id}", 
                    json.dumps({
                        'status': 'active',
                        'is_connected': True,
                        'last_updated': int(time.time())
                    }),
                    ex=300  # Кэшируем на 5 минут
                )
                
                query.edit_message_text(
                    f"✅ Аккаунт {account.phone} успешно запущен!\n\n"
                    f"Статус: 🟢 Активен\n"
                    f"Подключен к Telegram: ✅\n"
                    f"Последнее обновление: {time.strftime('%Y-%m-%d %H:%M:%S')}",
                    reply_markup=get_telethon_account_keyboard(account_id, worker.id),
                    parse_mode=ParseMode.HTML
                )
            else:
                query.edit_message_text(
                    f"⚠️ Не удалось запустить аккаунт {account.phone}.\n\n"
                    f"Ошибка: {task_result.get('message', 'Неизвестная ошибка')}",
                    reply_markup=get_telethon_account_keyboard(account_id, worker.id),
                    parse_mode=ParseMode.HTML
                )
        except Exception as e:
            logger.error(f"Ошибка при запуске аккаунта: {str(e)}")
            query.edit_message_text(
                f"⚠️ Ошибка при запуске аккаунта {account.phone}.\n\n"
                f"Ошибка: {str(e)}",
                reply_markup=get_telethon_account_keyboard(account_id, worker.id),
                parse_mode=ParseMode.HTML
            )
    
    elif action == "account_stop":
        # Остановка аккаунта через Celery
        try:
            # Проверяем статус воркера перед запросом
            current_time = int(time.time())
            worker_key = f"{WORKER_STATUS_KEY_PREFIX}{worker.name}"
            worker_last_seen_key = f"{WORKER_LAST_SEEN_KEY_PREFIX}{worker.name}"
            
            worker_data_raw = redis_client.get(worker_key)
            last_seen_raw = redis_client.get(worker_last_seen_key)
            
            worker_online = False
            if worker_data_raw and last_seen_raw:
                last_seen = int(last_seen_raw)
                worker_data = json.loads(worker_data_raw)
                
                if (current_time - last_seen <= WORKER_ONLINE_TIMEOUT) and worker_data.get('status') != 'offline':
                    worker_online = True
            
            if not worker_online:
                # Если воркер не в сети, просто обновляем статус в базе данных
                update_account_status(db, account_id, False)
                query.edit_message_text(
                    f"⚠️ Воркер {worker.name} не в сети. Аккаунт {account.phone} помечен как неактивный в базе данных.",
                    reply_markup=get_telethon_account_keyboard(account_id, worker.id),
                    parse_mode=ParseMode.HTML
                )
                return WORKERS_MENU
                
            # Останавливаем аккаунт через Celery
            result = celery_app.send_task(
                'worker.stop_account',
                args=[account_id],
                kwargs={},
                queue=worker.name,
                expires=10
            )
            
            # Ждем результат остановки не более 10 секунд
            task_result = result.get(timeout=10)
            
            if task_result and task_result.get('status') == 'success':
                # Обновляем статус аккаунта в базе данных
                update_account_status(db, account_id, False)
                
                # Сохраняем статус в Redis для быстрого доступа
                redis_client.set(
                    f"account_status:{account_id}", 
                    json.dumps({
                        'status': 'inactive',
                        'is_connected': False,
                        'last_updated': int(time.time())
                    }),
                    ex=300  # Кэшируем на 5 минут
                )
                
                query.edit_message_text(
                    f"✅ Аккаунт {account.phone} успешно остановлен!\n\n"
                    f"Статус: 🔴 Неактивен\n"
                    f"Последнее обновление: {time.strftime('%Y-%m-%d %H:%M:%S')}",
                    reply_markup=get_telethon_account_keyboard(account_id, worker.id),
                    parse_mode=ParseMode.HTML
                )
            else:
                query.edit_message_text(
                    f"⚠️ Не удалось остановить аккаунт {account.phone}.\n\n"
                    f"Ошибка: {task_result.get('message', 'Неизвестная ошибка')}",
                    reply_markup=get_telethon_account_keyboard(account_id, worker.id),
                    parse_mode=ParseMode.HTML
                )
        except Exception as e:
            logger.error(f"Ошибка при остановке аккаунта: {str(e)}")
            query.edit_message_text(
                f"⚠️ Ошибка при остановке аккаунта {account.phone}.\n\n"
                f"Ошибка: {str(e)}",
                reply_markup=get_telethon_account_keyboard(account_id, worker.id),
                parse_mode=ParseMode.HTML
            )
    
    elif action == "account_status":
        # Запрос статуса аккаунта у воркера через Celery
        try:
            # Проверяем статус воркера перед запросом
            current_time = int(time.time())
            worker_key = f"{WORKER_STATUS_KEY_PREFIX}{worker.name}"
            worker_last_seen_key = f"{WORKER_LAST_SEEN_KEY_PREFIX}{worker.name}"
            
            worker_data_raw = redis_client.get(worker_key)
            last_seen_raw = redis_client.get(worker_last_seen_key)
            
            worker_online = False
            if worker_data_raw and last_seen_raw:
                last_seen = int(last_seen_raw)
                worker_data = json.loads(worker_data_raw)
                
                if (current_time - last_seen <= WORKER_ONLINE_TIMEOUT) and worker_data.get('status') != 'offline':
                    worker_online = True
            
            if not worker_online:
                query.edit_message_text(
                    f"⚠️ Воркер {worker.name} не в сети. Невозможно получить статус аккаунта {account.phone}.",
                    reply_markup=get_telethon_account_keyboard(account_id, worker.id),
                    parse_mode=ParseMode.HTML
                )
                return WORKERS_MENU
            
            # Запрос статуса через Celery
            result = check_account_status.delay(worker.name, account_id)
            status_data = result.get(timeout=5)
            
            # Обновляем статус в БД на основе полученных данных
            is_active = status_data.get('status') == 'active'
            update_account_status(db, account_id, is_active)
            
            # Определяем статус для отображения
            status_emoji = "🟢" if is_active else "🔴"
            connected_status = "✅" if status_data.get('is_connected', False) else "❌"
            messages_count = status_data.get('messages_count', 0)
            has_session = "✅" if status_data.get('has_session', False) else "❌"
            
            # Формируем текст сообщения
            text = f"📱 <b>Статус аккаунта {account.phone}</b>\n\n"
            text += f"<b>Статус:</b> {status_emoji} {'Запущен' if is_active else 'Остановлен'}\n"
            text += f"<b>Подключен к Telegram:</b> {connected_status}\n"
            text += f"<b>Сессия сохранена:</b> {has_session}\n"
            text += f"<b>Получено сообщений:</b> {messages_count}\n"
            text += f"<b>Последнее обновление:</b> {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            
            # Обновляем сообщение
            query.edit_message_text(
                text,
                reply_markup=get_telethon_account_keyboard(account_id, worker.id),
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Ошибка при запросе статуса аккаунта: {str(e)}")
            query.edit_message_text(
                f"⚠️ Ошибка при запросе статуса аккаунта {account.phone}.\n\n"
                f"Ошибка: {str(e)}",
                reply_markup=get_telethon_account_keyboard(account_id, worker.id),
                parse_mode=ParseMode.HTML
            )
    
    elif action == "account_delete":
        account = get_account(db, account_id)
        worker_id = account.worker_id
        
        # Удаляем аккаунт
        db_session = db  # Используем текущую сессию как реальный объект Session
        db_session.delete(account)
        db_session.commit()
        
        # Получаем остальные аккаунты воркера для отображения
        worker = get_worker(db, worker_id)
        accounts = get_worker_accounts(db, worker_id)
        
        if accounts:
            text = f"✅ Аккаунт {account.phone} успешно удален.\n\n"
            text += f"Оставшиеся аккаунты воркера {worker.name}:\n\n"
            for i, acc in enumerate(accounts, 1):
                text += f"{i}. {acc.phone} - {'Активен' if acc.is_active else 'Неактивен'}\n"
            
            query.edit_message_text(
                text,
                reply_markup=get_account_selection_keyboard(accounts)
            )
        else:
            query.edit_message_text(
                f"✅ Аккаунт {account.phone} успешно удален.\n\n"
                f"У воркера {worker.name} больше нет аккаунтов.",
                reply_markup=get_worker_control_keyboard(worker_id)
            )
            return WORKERS_MENU
    
    return ACCOUNTS_MENU

def account_selection_callback(update: Update, context: CallbackContext) -> int:
    """Обработчик для выбора аккаунта из списка"""
    query = update.callback_query
    query.answer()
    
    data = query.data
    account_id = int(data.split(":")[-1])
    
    db = next(get_db())
    account = get_account(db, account_id)
    
    if not account:
        query.edit_message_text(
            "⚠️ Аккаунт не найден. Возможно, он был удален.",
            reply_markup=get_accounts_menu()
        )
        return ACCOUNTS_MENU
    
    worker = get_worker(db, account.worker_id)
    
    # Проверяем, активен ли воркер
    current_time = int(time.time())
    worker_key = f"{WORKER_STATUS_KEY_PREFIX}{worker.name}"
    worker_last_seen_key = f"{WORKER_LAST_SEEN_KEY_PREFIX}{worker.name}"
    
    worker_data_raw = redis_client.get(worker_key)
    last_seen_raw = redis_client.get(worker_last_seen_key)
    
    worker_online = False
    if worker_data_raw and last_seen_raw:
        last_seen = int(last_seen_raw)
        worker_data = json.loads(worker_data_raw)
        
        if (current_time - last_seen <= WORKER_ONLINE_TIMEOUT) and worker_data.get('status') != 'offline':
            worker_online = True
    
    # Формируем статус аккаунта
    status_emoji = "🟢" if account.is_active else "🔴"
    worker_status = "🟢 Онлайн" if worker_online else "🔴 Оффлайн"
    
    # Получаем дополнительные данные о статусе аккаунта, если воркер онлайн
    extra_status = ""
    if worker_online and account.is_active:
        try:
            result = check_account_status.delay(worker.name, account_id)
            status_data = result.get(timeout=5)
            
            connected = "✅" if status_data.get('is_connected', False) else "❌"
            messages_count = status_data.get('messages_count', 0)
            
            extra_status += f"Подключен к Telegram: {connected}\n"
            extra_status += f"Получено сообщений: {messages_count}\n"
        except Exception as e:
            logger.error(f"Ошибка при получении статуса аккаунта: {str(e)}")
            extra_status = "⚠️ Не удалось получить дополнительную информацию о статусе аккаунта.\n"
    
    # Формируем текст сообщения
    text = f"📱 <b>Аккаунт {account.phone}</b>\n\n"
    text += f"<b>API ID:</b> {account.api_id}\n"
    text += f"<b>API Hash:</b> {account.api_hash[:5]}...{account.api_hash[-5:]}\n"
    text += f"<b>Статус:</b> {status_emoji} {'Запущен' if account.is_active else 'Остановлен'}\n"
    text += f"<b>Воркер:</b> {worker.name} ({worker_status})\n"
    
    if extra_status:
        text += f"\n<b>Дополнительная информация:</b>\n{extra_status}"
    
    text += f"\n<b>Создан:</b> {account.created_at.strftime('%Y-%m-%d %H:%M:%S')}"
    
    # Отправляем сообщение с клавиатурой управления аккаунтом
    query.edit_message_text(
        text,
        reply_markup=get_telethon_account_keyboard(account.id, worker.id),
        parse_mode=ParseMode.HTML
    )
    
    return ACCOUNTS_MENU

def back_to_accounts_callback(update: Update, context: CallbackContext) -> int:
    """Обработчик для возврата к меню аккаунтов"""
    query = update.callback_query
    query.answer()
    
    # Возвращаемся к меню аккаунтов
    return accounts_menu(update, context)

def accounts_command(update: Update, context: CallbackContext) -> int:
    """Обработчик команды /accounts для прямого доступа к меню аккаунтов"""
    return accounts_menu(update, context) 