"""
Обработчики для работы с шаблонами документов.
"""
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from telegram.constants import ParseMode

from config import MESSAGES, TemplateStates, MAX_TEMPLATES_PER_USER
from database import (
    get_template_by_id,
    get_user_templates,
    get_user_documents,
    get_templates_count,
    insert_template,
    delete_template,
)
from utils import (
    build_templates_keyboard,
    build_confirmation_keyboard,
    get_status_emoji,
)

logger = logging.getLogger(__name__)


# ==================== TEMPLATE CALLBACKS ====================

async def view_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр шаблона и его документов."""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split("|")
    if len(data) < 3:
        return
    
    template_id = int(data[2])
    user_id = query.from_user.id
    
    template = get_template_by_id(template_id, user_id)
    if not template:
        await query.edit_message_text("❌ Шаблон не найден.")
        return
    
    # Получаем документы шаблона
    documents = get_user_documents(user_id, template_id=template_id)
    
    text = f"📁 *Шаблон: {template['name']}*\n\n"
    
    if not documents:
        text += "В этом шаблоне пока нет документов."
    else:
        text += f"📄 Документов: {len(documents)}\n\n"
    
    keyboard = []
    
    # Список документов (первые 5)
    for doc in documents[:5]:
        emoji = get_status_emoji(doc.get("end_date"))
        label = f"{emoji} {doc['name']}"
        if len(label) > 35:
            label = label[:32] + "..."
        keyboard.append([
            InlineKeyboardButton(label, callback_data=f"doc|view|{doc['id']}")
        ])
    
    if len(documents) > 5:
        keyboard.append([
            InlineKeyboardButton(
                f"📄 Ещё {len(documents) - 5} документов",
                callback_data=f"tmpl|docs|{template_id}|0"
            )
        ])
    
    # Действия с шаблоном
    keyboard.append([
        InlineKeyboardButton("🗑️ Удалить шаблон", callback_data=f"tmpl|delete|{template_id}")
    ])
    keyboard.append([
        InlineKeyboardButton("🔙 К списку шаблонов", callback_data="templates|list|0")
    ])
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )


async def template_documents_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Полный список документов шаблона с пагинацией."""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split("|")
    if len(data) < 4:
        return
    
    template_id = int(data[2])
    page = int(data[3])
    user_id = query.from_user.id
    
    template = get_template_by_id(template_id, user_id)
    if not template:
        await query.edit_message_text("❌ Шаблон не найден.")
        return
    
    documents = get_user_documents(user_id, template_id=template_id)
    
    page_size = 10
    total_pages = max(1, (len(documents) + page_size - 1) // page_size)
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, len(documents))
    
    keyboard = []
    for doc in documents[start_idx:end_idx]:
        emoji = get_status_emoji(doc.get("end_date"))
        label = f"{emoji} {doc['name']}"
        if len(label) > 40:
            label = label[:37] + "..."
        keyboard.append([
            InlineKeyboardButton(label, callback_data=f"doc|view|{doc['id']}")
        ])
    
    # Навигация
    if total_pages > 1:
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("◀️", callback_data=f"tmpl|docs|{template_id}|{page - 1}"))
        nav_row.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton("▶️", callback_data=f"tmpl|docs|{template_id}|{page + 1}"))
        keyboard.append(nav_row)
    
    keyboard.append([
        InlineKeyboardButton("🔙 К шаблону", callback_data=f"tmpl|view|{template_id}")
    ])
    
    await query.edit_message_text(
        f"📁 *{template['name']}* — документы (стр. {page + 1}/{total_pages})",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )


async def delete_template_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение удаления шаблона."""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split("|")
    if len(data) < 3:
        return
    
    template_id = int(data[2])
    user_id = query.from_user.id
    
    template = get_template_by_id(template_id, user_id)
    if not template:
        await query.edit_message_text("❌ Шаблон не найден.")
        return
    
    # Считаем документы в шаблоне
    documents = get_user_documents(user_id, template_id=template_id)
    
    text = f"⚠️ Удалить шаблон *{template['name']}*?\n\n"
    if documents:
        text += f"📄 В шаблоне {len(documents)} документов.\n"
        text += "Документы НЕ будут удалены, только отвязаны от шаблона."
    
    keyboard = build_confirmation_keyboard(
        confirm_callback=f"tmpl|delete_yes|{template_id}",
        cancel_callback=f"tmpl|view|{template_id}",
        confirm_text="🗑️ Удалить",
        cancel_text="❌ Отмена"
    )
    
    await query.edit_message_text(
        text,
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )


async def delete_template_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выполнение удаления шаблона."""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split("|")
    if len(data) < 3:
        return
    
    template_id = int(data[2])
    user_id = query.from_user.id
    
    if delete_template(template_id, user_id):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📁 Мои шаблоны", callback_data="templates|list|0")]
        ])
        await query.edit_message_text(
            MESSAGES["template_deleted"],
            reply_markup=keyboard
        )
    else:
        await query.edit_message_text(MESSAGES["error_generic"])


async def templates_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список шаблонов с пагинацией."""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split("|")
    page = int(data[2]) if len(data) > 2 else 0
    
    user_id = query.from_user.id
    templates = get_user_templates(user_id)
    
    if not templates:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Создать шаблон", callback_data="tmpl|create")]
        ])
        await query.edit_message_text(
            MESSAGES["no_templates"],
            reply_markup=keyboard
        )
        return
    
    keyboard = build_templates_keyboard(templates, page=page)
    
    total_docs = sum(t.get("documents_count", 0) for t in templates)
    total_pages = max(1, (len(templates) + 7) // 8)
    
    await query.edit_message_text(
        f"📁 *Мои шаблоны* ({len(templates)} шт., стр. {page + 1}/{total_pages})\n"
        f"📄 Всего документов: {total_docs}",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )


async def create_template_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало создания шаблона."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # Проверяем лимит
    count = get_templates_count(user_id)
    if count >= MAX_TEMPLATES_PER_USER:
        await query.edit_message_text(
            MESSAGES["limit_reached_templates"].format(limit=MAX_TEMPLATES_PER_USER)
        )
        return
    
    context.user_data["creating_template"] = True
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Отмена", callback_data="templates|list|0")]
    ])
    
    await query.edit_message_text(
        MESSAGES["template_create_prompt"],
        reply_markup=keyboard
    )


async def create_template_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение названия нового шаблона."""
    if not context.user_data.get("creating_template"):
        return
    
    name = update.message.text.strip()
    
    if len(name) < 2:
        await update.message.reply_text("❌ Название слишком короткое. Минимум 2 символа.")
        return
    
    if len(name) > 50:
        name = name[:50]
    
    user_id = update.effective_user.id
    
    template_id = insert_template(user_id, name)
    
    if template_id:
        context.user_data.pop("creating_template", None)
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📁 Мои шаблоны", callback_data="templates|list|0")]
        ])
        
        await update.message.reply_text(
            MESSAGES["template_created"].format(name=name),
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(MESSAGES["template_name_exists"])


# ==================== HANDLERS ====================

def get_template_handlers():
    """Получить обработчики для работы с шаблонами."""
    return [
        # Callback handlers
        CallbackQueryHandler(view_template, pattern=r"^tmpl\|view\|"),
        CallbackQueryHandler(template_documents_list, pattern=r"^tmpl\|docs\|"),
        CallbackQueryHandler(delete_template_confirm, pattern=r"^tmpl\|delete\|(?!yes)"),
        CallbackQueryHandler(delete_template_execute, pattern=r"^tmpl\|delete_yes\|"),
        CallbackQueryHandler(templates_list, pattern=r"^templates\|list\|"),
        CallbackQueryHandler(templates_list, pattern=r"^templates\|page\|"),
        CallbackQueryHandler(create_template_start, pattern=r"^tmpl\|create$"),
        
        # Message handler для создания шаблона
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            create_template_name
        ),
    ]
