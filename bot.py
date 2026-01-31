#!/usr/bin/env python3
"""
Telegram бот для управления документами.
Точка входа приложения.
"""
import logging
import sys

from telegram.ext import Application

from config import BOT_TOKEN
from database import init_db
from handlers import (
    get_command_handlers,
    get_document_conversation_handler,
    get_document_callback_handlers,
    get_template_handlers,
    get_callback_dispatcher,
)
from jobs import setup_jobs

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ]
)

# Уменьшаем шум от httpx
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def main():
    """Запуск бота."""
    
    # Проверяем токен
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.error("Bot token not configured! Set BOT_TOKEN environment variable.")
        sys.exit(1)
    
    # Инициализируем базу данных
    logger.info("Initializing database...")
    init_db()
    
    # Создаём приложение
    logger.info("Creating bot application...")
    application = Application.builder().token(BOT_TOKEN).build()
    
    # ==================== РЕГИСТРАЦИЯ HANDLERS ====================
    # ВАЖНО: Порядок регистрации имеет значение!
    # ConversationHandler должен быть зарегистрирован ДО глобальных handlers
    
    # 1. Команды (высший приоритет)
    for handler in get_command_handlers():
        application.add_handler(handler)
    logger.info("Command handlers registered")
    
    # 2. ConversationHandler для загрузки документов
    # Это должно быть ПЕРЕД другими MessageHandler и CallbackQueryHandler
    conv_handler = get_document_conversation_handler()
    application.add_handler(conv_handler)
    logger.info("Document upload conversation handler registered")
    
    # 3. Callback handlers для документов (с конкретными pattern)
    for handler in get_document_callback_handlers():
        application.add_handler(handler)
    logger.info("Document callback handlers registered")
    
    # 4. Handlers для шаблонов
    for handler in get_template_handlers():
        application.add_handler(handler)
    logger.info("Template handlers registered")
    
    # 5. Общий callback dispatcher (ПОСЛЕДНИМ!)
    # Ловит только те callbacks, которые не обработаны выше
    for handler in get_callback_dispatcher():
        application.add_handler(handler)
    logger.info("Callback dispatcher registered")
    
    # ==================== ФОНОВЫЕ ЗАДАЧИ ====================
    setup_jobs(application)
    
    # ==================== ЗАПУСК ====================
    logger.info("Starting bot...")
    
    # Запускаем polling
    application.run_polling(
        allowed_updates=["message", "callback_query"],
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
