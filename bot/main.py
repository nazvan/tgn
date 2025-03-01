import logging
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters,
    CallbackQueryHandler, ConversationHandler
)
from config import TG_BOT_TOKEN, ADMIN_IDS
from database.models import create_tables
from .handlers import (
    start, main_menu, workers_menu, accounts_menu,
    worker_callback,
    add_account_phone, add_account_api_id, add_account_api_hash, add_account_worker, account_callback,
    MAIN_MENU, WORKERS_MENU, ACCOUNTS_MENU,
    ADD_ACCOUNT_PHONE, ADD_ACCOUNT_API_ID, ADD_ACCOUNT_API_HASH, ADD_ACCOUNT_WORKER
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def setup_dispatcher(dispatcher):
    """Настройка обработчиков команд бота"""
    
    # Создание ConversationHandler для управления диалогом с пользователем
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            MAIN_MENU: [MessageHandler(Filters.text & ~Filters.command, main_menu)],
            WORKERS_MENU: [
                MessageHandler(Filters.text & ~Filters.command, workers_menu),
                CallbackQueryHandler(worker_callback)
            ],
            ACCOUNTS_MENU: [
                MessageHandler(Filters.text & ~Filters.command, accounts_menu),
                CallbackQueryHandler(account_callback)
            ],
            ADD_ACCOUNT_PHONE: [MessageHandler(Filters.text & ~Filters.command, add_account_phone)],
            ADD_ACCOUNT_API_ID: [MessageHandler(Filters.text & ~Filters.command, add_account_api_id)],
            ADD_ACCOUNT_API_HASH: [MessageHandler(Filters.text & ~Filters.command, add_account_api_hash)],
            ADD_ACCOUNT_WORKER: [CallbackQueryHandler(add_account_worker)]
        },
        fallbacks=[CommandHandler('start', start)],
        allow_reentry=True
    )
    
    # Добавление обработчика диалога
    dispatcher.add_handler(conv_handler)
    
    # Обработчик для неизвестных команд
    dispatcher.add_handler(MessageHandler(Filters.command, start))
    
    return dispatcher

def check_admin(update, context):
    """Проверка, является ли пользователь администратором"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        update.message.reply_text("У вас нет доступа к этому боту.")
        return True
    return True

def run_bot():
    """Запуск бота"""
    # Создание таблиц в базе данных
    create_tables()
    
    # Инициализация бота
    updater = Updater(TG_BOT_TOKEN)
    dispatcher = updater.dispatcher
    
    # Настройка обработчиков
    setup_dispatcher(dispatcher)
    
    # Запуск бота
    updater.start_polling()
    logger.info("Бот запущен")
    
    # Ожидание завершения работы бота
    updater.idle()

if __name__ == '__main__':
    run_bot() 