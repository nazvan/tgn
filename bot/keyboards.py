from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

# Главное меню
def get_main_menu():
    """Создает инлайн-клавиатуру главного меню"""
    keyboard = [
        [
            InlineKeyboardButton("👥 Воркеры", callback_data="main_workers"),
            InlineKeyboardButton("📱 Аккаунты", callback_data="main_accounts")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# Меню воркеров
def get_workers_menu():
    """Создает инлайн-клавиатуру меню воркеров"""
    keyboard = [
        [
            InlineKeyboardButton("📋 Список всех воркеров", callback_data="workers_list")
        ],
        [
            InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# Меню аккаунтов
def get_accounts_menu():
    """Создает инлайн-клавиатуру меню аккаунтов"""
    keyboard = [
        [
            InlineKeyboardButton("➕ Добавить аккаунт", callback_data="accounts_add"),
            InlineKeyboardButton("📋 Список аккаунтов", callback_data="accounts_list")
        ],
        [
            InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# Инлайн-клавиатура для управления воркером
def get_worker_control_keyboard(worker_id):
    """Создает инлайн-клавиатуру для управления воркером"""
    keyboard = [
        [
            InlineKeyboardButton("📊 Статус", callback_data=f"worker_status:{worker_id}")
        ],
        [
            InlineKeyboardButton("👤 Аккаунты", callback_data=f"worker_accounts:{worker_id}")
        ],
        [
            InlineKeyboardButton("➕ Добавить аккаунт", callback_data=f"worker_add_account:{worker_id}")
        ],
        [
            InlineKeyboardButton("🗑️ Удалить", callback_data=f"worker_delete:{worker_id}")
        ],
        [
            InlineKeyboardButton("🔙 Назад", callback_data="back_to_workers")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# Инлайн-клавиатура для управления аккаунтом
def get_account_control_keyboard(account_id):
    """Создает инлайн-клавиатуру для управления аккаунтом"""
    keyboard = [
        [
            InlineKeyboardButton("▶️ Запустить", callback_data=f"account_start:{account_id}"),
            InlineKeyboardButton("⏹️ Остановить", callback_data=f"account_stop:{account_id}")
        ],
        [
            InlineKeyboardButton("📊 Статус", callback_data=f"account_status:{account_id}"),
            InlineKeyboardButton("🗑️ Удалить", callback_data=f"account_delete:{account_id}")
        ],
        [
            InlineKeyboardButton("🔙 Назад", callback_data=f"back_to_worker:{account_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# Инлайн-клавиатура для выбора воркера
def get_worker_selection_keyboard(workers):
    """Создает инлайн-клавиатуру для выбора воркера"""
    keyboard = []
    for worker in workers:
        keyboard.append([
            InlineKeyboardButton(
                f"{worker.name} ({'✅' if worker.is_active else '❌'})",
                callback_data=f"select_worker:{worker.id}"
            )
        ])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(keyboard)

# Инлайн-клавиатура для выбора аккаунта
def get_account_selection_keyboard(accounts):
    """Создает инлайн-клавиатуру для выбора аккаунта"""
    keyboard = []
    for account in accounts:
        keyboard.append([
            InlineKeyboardButton(
                f"{account.phone} ({'✅' if account.is_active else '❌'})",
                callback_data=f"select_account:{account.id}"
            )
        ])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(keyboard)

# Инлайн-клавиатура для управления аккаунтом Telethon
def get_telethon_account_keyboard(account_id, worker_id):
    """Возвращает клавиатуру управления аккаунтом Telethon"""
    keyboard = [
        [
            InlineKeyboardButton("🔄 Обновить статус", callback_data=f"account_status:{account_id}")
        ],
        [
            InlineKeyboardButton("▶️ Запустить", callback_data=f"account_start:{account_id}"),
            InlineKeyboardButton("⏹️ Остановить", callback_data=f"account_stop:{account_id}")
        ],
        [
            InlineKeyboardButton("🗑️ Удалить", callback_data=f"account_delete:{account_id}")
        ],
        [
            InlineKeyboardButton("🔙 К списку аккаунтов", callback_data=f"worker_accounts:{worker_id}")
        ],
        [
            InlineKeyboardButton("🔙 К воркеру", callback_data=f"select_worker:{worker_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_worker_selection_keyboard_for_accounts(db):
    """Возвращает клавиатуру для выбора воркера при добавлении аккаунта"""
    from database.operations import get_all_workers
    
    workers = get_all_workers(db, active_only=True)
    
    keyboard = []
    for worker in workers:
        keyboard.append([
            InlineKeyboardButton(
                f"{worker.name} ({'🟢' if worker.is_active else '🔴'})",
                callback_data=f"worker_add_account:{worker.id}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_accounts")])
    return InlineKeyboardMarkup(keyboard) 