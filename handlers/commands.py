"""
Обработчики команд бота.
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler
from telegram.constants import ParseMode

from config import MESSAGES
from database import (
    get_or_create_user,
    get_user_documents,
    get_user_templates,
    get_documents_statistics,
)
from utils import (
    format_document_info,
    get_status_emoji,
    build_templates_keyboard,
)

logger = logging.getLogger(__name__)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start."""
    user = update.effective_user
    
    # Регистрируем/обновляем пользователя
    get_or_create_user(user.id, user.username, user.first_name)
    
    await update.message.reply_text(
        MESSAGES["welcome"],
        parse_mode=ParseMode.MARKDOWN
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help."""
    await update.message.reply_text(
        MESSAGES["help"],
        parse_mode=ParseMode.MARKDOWN
    )


async def cmd_mydocs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /mydocs - показать список документов."""
    user_id = update.effective_user.id
    
    # Получаем документы
    documents = get_user_documents(user_id)
    
    if not documents:
        await update.message.reply_text(MESSAGES["no_documents"])
        return
    
    # Статистика
    stats = get_documents_statistics(user_id)
    
    # Формируем сообщение
    header = (
        f"📚 *Мои документы* ({stats['total']} шт.)\n"
        f"🟢 Активных: {stats['active']} | "
        f"🔴 Истекших: {stats['expired']}\n"
    )
    
    if stats['expiring_soon'] > 0:
        header += f"⚠️ Истекает скоро: {stats['expiring_soon']}\n"
    
    header += "\n"
    
    # Список документов (первые 10)
    page_size = 10
    docs_to_show = documents[:page_size]
    
    keyboard = []
    for doc in docs_to_show:
        emoji = get_status_emoji(doc.get("end_date"))
        label = f"{emoji} {doc['name']}"
        if len(label) > 40:
            label = label[:37] + "..."
        keyboard.append([
            InlineKeyboardButton(label, callback_data=f"doc|view|{doc['id']}")
        ])
    
    # Пагинация
    if len(documents) > page_size:
        keyboard.append([
            InlineKeyboardButton(
                f"📄 Ещё ({len(documents) - page_size})",
                callback_data="mydocs|list|1"
            )
        ])
    
    # Кнопки фильтров
    keyboard.append([
        InlineKeyboardButton("📁 По шаблонам", callback_data="mydocs|bytemplates"),
        InlineKeyboardButton("🔍 Поиск", callback_data="mydocs|search"),
    ])
    
    await update.message.reply_text(
        header,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )


async def cmd_templates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /templates - управление шаблонами."""
    user_id = update.effective_user.id
    
    templates = get_user_templates(user_id)
    
    if not templates:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Создать шаблон", callback_data="tmpl|create")]
        ])
        await update.message.reply_text(
            MESSAGES["no_templates"],
            reply_markup=keyboard
        )
        return
    
    # Формируем клавиатуру с шаблонами
    keyboard = build_templates_keyboard(templates, page=0)
    
    total_docs = sum(t.get("documents_count", 0) for t in templates)
    
    await update.message.reply_text(
        f"📁 *Мои шаблоны* ({len(templates)} шт.)\n"
        f"📄 Всего документов в шаблонах: {total_docs}\n\n"
        "Выбери шаблон для просмотра:",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /cancel - отмена текущей операции."""
    # Очищаем данные пользователя
    context.user_data.clear()
    
    await update.message.reply_text(
        "❌ Операция отменена.\n\n"
        "Отправь документ для загрузки или используй /mydocs"
    )
    
    # Возвращаем ConversationHandler.END если нужно
    from telegram.ext import ConversationHandler
    return ConversationHandler.END


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /stats - статистика пользователя."""
    user_id = update.effective_user.id
    
    stats = get_documents_statistics(user_id)
    templates = get_user_templates(user_id)
    
    text = (
        "📊 *Твоя статистика*\n\n"
        f"📄 Всего документов: {stats['total']}\n"
        f"🟢 Активных: {stats['active']}\n"
        f"🔴 Истекших: {stats['expired']}\n"
        f"🟡 Истекает скоро: {stats['expiring_soon']}\n"
        f"📁 Шаблонов: {len(templates)}\n"
    )
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


def get_command_handlers():
    """Получить список обработчиков команд."""
    return [
        CommandHandler("start", cmd_start),
        CommandHandler("help", cmd_help),
        CommandHandler("mydocs", cmd_mydocs),
        CommandHandler("templates", cmd_templates),
        CommandHandler("cancel", cmd_cancel),
        CommandHandler("stats", cmd_stats),
    ]
