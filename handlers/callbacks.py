"""
Общий диспетчер callback-запросов.
Обрабатывает callbacks, которые не обработаны другими handlers.
"""
import logging

from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler

logger = logging.getLogger(__name__)


async def noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пустой callback (для информационных кнопок)."""
    query = update.callback_query
    await query.answer()


async def unknown_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик неизвестных callback-запросов."""
    query = update.callback_query
    await query.answer("❓ Неизвестная команда")
    logger.warning(f"Unknown callback: {query.data}")


def get_callback_dispatcher():
    """
    Получить финальный обработчик callback-запросов.
    
    ВАЖНО: Этот handler должен быть зарегистрирован ПОСЛЕДНИМ,
    чтобы не перехватывать callbacks для ConversationHandler и других handlers.
    """
    return [
        # Пустой callback для информационных кнопок
        CallbackQueryHandler(noop_callback, pattern=r"^noop$"),
        
        # Обработчик неизвестных callbacks (ловит всё остальное)
        # ВАЖНО: Если это мешает ConversationHandler, можно закомментировать
        # CallbackQueryHandler(unknown_callback),
    ]
