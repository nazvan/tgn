from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

# Главное меню
def get_main_menu():
    """Создает клавиатуру главного меню"""
    keyboard = [
        ['👥 Воркеры', '👤 Аккаунты'],
        ['📊 Статистика', '⚙️ Настройки']
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Меню воркеров
def get_workers_menu():
    """Создает клавиатуру меню воркеров"""
    keyboard = [
        ['📋 Список воркеров'],
        ['🔙 Назад']
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Меню аккаунтов
def get_accounts_menu():
    """Создает клавиатуру меню аккаунтов"""
    keyboard = [
        ['➕ Добавить аккаунт', '📋 Список аккаунтов'],
        ['🔙 Назад']
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Инлайн-клавиатура для управления воркером
def get_worker_control_keyboard(worker_id):
    """Создает инлайн-клавиатуру для управления воркером"""
    keyboard = [
        [
            InlineKeyboardButton("📋 Аккаунты", callback_data=f"worker_accounts:{worker_id}"),
            InlineKeyboardButton("📊 Статус", callback_data=f"worker_status:{worker_id}")
        ],
        [
            InlineKeyboardButton("✅ Активировать", callback_data=f"worker_activate:{worker_id}"),
            InlineKeyboardButton("❌ Деактивировать", callback_data=f"worker_deactivate:{worker_id}")
        ],
        [
            InlineKeyboardButton("🗑️ Удалить", callback_data=f"worker_delete:{worker_id}")
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