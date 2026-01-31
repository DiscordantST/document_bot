#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram Documents Bot
======================

Бот для хранения и управления документами в Telegram.

Функции:
- Хранение документов (файлы и фото)
- Шаблоны для комплектов документов
- Напоминания об истекающих документах
- Поиск и фильтрация
- Экспорт данных

Запуск:
    python main.py

Переменные окружения:
    BOT_TOKEN - токен Telegram бота (обязательно)
    DB_PATH - путь к SQLite базе данных (по умолчанию: docs.db)
    ADMIN_IDS - список ID администраторов через запятую
"""

import logging
import sys

from telegram.ext import ApplicationBuilder
from telegram.request import HTTPXRequest

from config import BOT_TOKEN, CONNECT_TIMEOUT, READ_TIMEOUT
from database import init_db
from handlers import register_all_handlers
from jobs import setup_jobs


# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logger = logging.getLogger(__name__)


def main():
    """Точка входа"""
    
    # Проверка токена
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set! Please set it in .env file or environment.")
        sys.exit(1)
    
    logger.info("Initializing database...")
    init_db()
    
    logger.info("Building application...")
    
    # Настройка HTTP с увеличенными таймаутами
    request = HTTPXRequest(
        connect_timeout=CONNECT_TIMEOUT,
        read_timeout=READ_TIMEOUT,
    )
    
    # Создание приложения
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .request(request)
        .build()
    )
    
    # Регистрация обработчиков
    logger.info("Registering handlers...")
    register_all_handlers(app)
    
    # Настройка фоновых задач
    logger.info("Setting up background jobs...")
    setup_jobs(app)
    
    # Запуск бота
    logger.info("Starting bot...")
    print("=" * 50)
    print("  Documents Bot started successfully!")
    print("  Press Ctrl+C to stop")
    print("=" * 50)
    
    app.run_polling(
        allowed_updates=["message", "callback_query"],
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
