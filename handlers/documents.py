"""
Обработчики для работы с документами.
Включает ConversationHandler для загрузки документов.
"""
import logging
from datetime import date, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from telegram.constants import ParseMode

from config import (
    MESSAGES,
    UploadStates,
    MAX_DOCUMENTS_PER_USER,
)
from database import (
    get_or_create_user,
    insert_document,
    get_document_by_id,
    get_user_documents,
    get_user_templates,
    get_documents_count,
    update_document,
    delete_document,
)
from utils import (
    validate_file,
    get_file_type,
    format_date,
    parse_date,
    format_document_info,
    build_date_keyboard,
    build_confirmation_keyboard,
    build_document_actions_keyboard,
    build_templates_keyboard,
    build_edit_document_keyboard,
    get_status_emoji,
)

logger = logging.getLogger(__name__)


# ==================== UPLOAD CONVERSATION ====================

async def upload_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало загрузки документа - получен файл."""
    user = update.effective_user
    message = update.message
    
    # Регистрируем пользователя
    get_or_create_user(user.id, user.username, user.first_name)
    
    # Проверяем лимит документов
    doc_count = get_documents_count(user.id)
    if doc_count >= MAX_DOCUMENTS_PER_USER:
        await message.reply_text(
            MESSAGES["limit_reached_documents"].format(limit=MAX_DOCUMENTS_PER_USER)
        )
        return ConversationHandler.END
    
    # Получаем информацию о файле
    if message.document:
        file = message.document
        file_name = file.file_name
        file_size = file.file_size
        file_id = file.file_id
    elif message.photo:
        # Берём фото в лучшем качестве
        file = message.photo[-1]
        file_name = f"photo_{file.file_unique_id}.jpg"
        file_size = file.file_size or 0
        file_id = file.file_id
    else:
        await message.reply_text("❌ Отправь файл документа или фото.")
        return ConversationHandler.END
    
    # Валидация файла
    is_valid, error_msg = validate_file(file_name, file_size)
    if not is_valid:
        await message.reply_text(error_msg)
        return ConversationHandler.END
    
    # Сохраняем данные в context
    context.user_data["upload"] = {
        "file_id": file_id,
        "file_name": file_name,
        "file_type": get_file_type(file_name),
    }
    
    await message.reply_text(MESSAGES["upload_start"])
    
    return UploadStates.WAITING_NAME


async def upload_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получено название документа."""
    name = update.message.text.strip()
    
    if len(name) < 2:
        await update.message.reply_text(MESSAGES["upload_name_invalid"])
        return UploadStates.WAITING_NAME
    
    if len(name) > 100:
        name = name[:100]
    
    context.user_data["upload"]["name"] = name
    
    # Показываем выбор даты начала
    keyboard = build_date_keyboard("start", include_today=True, include_skip=False)
    
    await update.message.reply_text(
        MESSAGES["upload_select_start_date"],
        reply_markup=keyboard
    )
    
    return UploadStates.WAITING_START_DATE


async def upload_start_date_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора даты начала через callback."""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split("|")
    if len(data) < 2:
        return UploadStates.WAITING_START_DATE
    
    date_option = data[1]
    today = date.today()
    
    if date_option == "today":
        selected_date = today
    elif date_option == "+1m":
        selected_date = today + timedelta(days=30)
    elif date_option == "+3m":
        selected_date = today + timedelta(days=90)
    elif date_option == "+6m":
        selected_date = today + timedelta(days=180)
    elif date_option == "+1y":
        selected_date = today + timedelta(days=365)
    elif date_option == "+2y":
        selected_date = today + timedelta(days=730)
    elif date_option == "+5y":
        selected_date = today + timedelta(days=1825)
    elif date_option == "manual":
        await query.edit_message_text(
            "✏️ Введи дату начала в формате ДД.ММ.ГГГГ\n"
            "(например: 01.01.2024)"
        )
        context.user_data["upload"]["waiting_manual_start"] = True
        return UploadStates.WAITING_START_DATE
    else:
        return UploadStates.WAITING_START_DATE
    
    context.user_data["upload"]["start_date"] = selected_date
    
    # Переходим к выбору даты окончания
    keyboard = build_date_keyboard("end", include_today=False, include_skip=True)
    
    await query.edit_message_text(
        f"✅ Дата начала: {format_date(selected_date)}\n\n"
        f"{MESSAGES['upload_select_end_date']}",
        reply_markup=keyboard
    )
    
    return UploadStates.WAITING_END_DATE


async def upload_start_date_manual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ручной ввод даты начала."""
    if not context.user_data.get("upload", {}).get("waiting_manual_start"):
        return UploadStates.WAITING_START_DATE
    
    text = update.message.text.strip()
    
    # Пробуем разные форматы
    parsed_date = None
    for fmt in ["%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d"]:
        try:
            from datetime import datetime
            parsed_date = datetime.strptime(text, fmt).date()
            break
        except ValueError:
            continue
    
    if not parsed_date:
        await update.message.reply_text(
            "❌ Неверный формат даты. Введи дату в формате ДД.ММ.ГГГГ\n"
            "(например: 01.01.2024)"
        )
        return UploadStates.WAITING_START_DATE
    
    context.user_data["upload"]["start_date"] = parsed_date
    context.user_data["upload"].pop("waiting_manual_start", None)
    
    # Переходим к выбору даты окончания
    keyboard = build_date_keyboard("end", include_today=False, include_skip=True)
    
    await update.message.reply_text(
        f"✅ Дата начала: {format_date(parsed_date)}\n\n"
        f"{MESSAGES['upload_select_end_date']}",
        reply_markup=keyboard
    )
    
    return UploadStates.WAITING_END_DATE


async def upload_end_date_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора даты окончания через callback."""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split("|")
    if len(data) < 2:
        return UploadStates.WAITING_END_DATE
    
    date_option = data[1]
    today = date.today()
    selected_date = None
    
    if date_option == "skip":
        selected_date = None
    elif date_option == "today":
        selected_date = today
    elif date_option == "+1m":
        selected_date = today + timedelta(days=30)
    elif date_option == "+3m":
        selected_date = today + timedelta(days=90)
    elif date_option == "+6m":
        selected_date = today + timedelta(days=180)
    elif date_option == "+1y":
        selected_date = today + timedelta(days=365)
    elif date_option == "+2y":
        selected_date = today + timedelta(days=730)
    elif date_option == "+5y":
        selected_date = today + timedelta(days=1825)
    elif date_option == "manual":
        await query.edit_message_text(
            "✏️ Введи дату окончания в формате ДД.ММ.ГГГГ\n"
            "(например: 31.12.2025)"
        )
        context.user_data["upload"]["waiting_manual_end"] = True
        return UploadStates.WAITING_END_DATE
    else:
        return UploadStates.WAITING_END_DATE
    
    context.user_data["upload"]["end_date"] = selected_date
    
    # Переходим к выбору шаблона
    return await show_template_selection(query, context)


async def upload_end_date_manual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ручной ввод даты окончания."""
    if not context.user_data.get("upload", {}).get("waiting_manual_end"):
        return UploadStates.WAITING_END_DATE
    
    text = update.message.text.strip()
    
    # Пробуем разные форматы
    parsed_date = None
    for fmt in ["%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d"]:
        try:
            from datetime import datetime
            parsed_date = datetime.strptime(text, fmt).date()
            break
        except ValueError:
            continue
    
    if not parsed_date:
        await update.message.reply_text(
            "❌ Неверный формат даты. Введи дату в формате ДД.ММ.ГГГГ\n"
            "(например: 31.12.2025)"
        )
        return UploadStates.WAITING_END_DATE
    
    context.user_data["upload"]["end_date"] = parsed_date
    context.user_data["upload"].pop("waiting_manual_end", None)
    
    # Переходим к выбору шаблона
    user_id = update.effective_user.id
    templates = get_user_templates(user_id)
    
    if not templates:
        # Нет шаблонов - сохраняем документ
        return await save_document(update, context)
    
    keyboard = build_templates_keyboard(templates, select_mode=True)
    
    await update.message.reply_text(
        MESSAGES["upload_select_template"],
        reply_markup=keyboard
    )
    
    return UploadStates.WAITING_TEMPLATE


async def show_template_selection(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать выбор шаблона."""
    user_id = query.from_user.id
    templates = get_user_templates(user_id)
    
    end_date = context.user_data["upload"].get("end_date")
    date_text = format_date(end_date) if end_date else "Не указана"
    
    if not templates:
        # Нет шаблонов - сохраняем документ
        return await save_document_from_callback(query, context)
    
    keyboard = build_templates_keyboard(templates, select_mode=True)
    
    await query.edit_message_text(
        f"✅ Дата окончания: {date_text}\n\n"
        f"{MESSAGES['upload_select_template']}",
        reply_markup=keyboard
    )
    
    return UploadStates.WAITING_TEMPLATE


async def upload_template_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора шаблона."""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split("|")
    if len(data) < 3:
        return UploadStates.WAITING_TEMPLATE
    
    template_option = data[2]
    
    if template_option == "skip":
        context.user_data["upload"]["template_id"] = None
    else:
        try:
            context.user_data["upload"]["template_id"] = int(template_option)
        except ValueError:
            context.user_data["upload"]["template_id"] = None
    
    return await save_document_from_callback(query, context)


async def save_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохранение документа (из текстового сообщения)."""
    user_id = update.effective_user.id
    upload_data = context.user_data.get("upload", {})
    
    if not upload_data.get("file_id"):
        await update.message.reply_text(MESSAGES["error_generic"])
        return ConversationHandler.END
    
    doc_id = insert_document(
        user_id=user_id,
        name=upload_data.get("name", "Без названия"),
        file_id=upload_data["file_id"],
        file_name=upload_data.get("file_name"),
        file_type=upload_data.get("file_type"),
        start_date=upload_data.get("start_date"),
        end_date=upload_data.get("end_date"),
        template_id=upload_data.get("template_id"),
    )
    
    if doc_id:
        await update.message.reply_text(
            MESSAGES["upload_success"].format(name=upload_data.get("name", "Документ")),
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(MESSAGES["error_generic"])
    
    # Очищаем данные
    context.user_data.pop("upload", None)
    
    return ConversationHandler.END


async def save_document_from_callback(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохранение документа (из callback query)."""
    user_id = query.from_user.id
    upload_data = context.user_data.get("upload", {})
    
    if not upload_data.get("file_id"):
        await query.edit_message_text(MESSAGES["error_generic"])
        return ConversationHandler.END
    
    doc_id = insert_document(
        user_id=user_id,
        name=upload_data.get("name", "Без названия"),
        file_id=upload_data["file_id"],
        file_name=upload_data.get("file_name"),
        file_type=upload_data.get("file_type"),
        start_date=upload_data.get("start_date"),
        end_date=upload_data.get("end_date"),
        template_id=upload_data.get("template_id"),
    )
    
    if doc_id:
        name = upload_data.get("name", "Документ")
        start_date = upload_data.get("start_date")
        end_date = upload_data.get("end_date")
        
        summary = f"✅ Документ *{name}* успешно сохранён!\n\n"
        if start_date:
            summary += f"📅 Начало: {format_date(start_date)}\n"
        if end_date:
            summary += f"📅 Окончание: {format_date(end_date)}\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 Посмотреть", callback_data=f"doc|view|{doc_id}")],
            [InlineKeyboardButton("📚 Мои документы", callback_data="mydocs|list|0")]
        ])
        
        await query.edit_message_text(
            summary,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await query.edit_message_text(MESSAGES["error_generic"])
    
    # Очищаем данные
    context.user_data.pop("upload", None)
    
    return ConversationHandler.END


async def upload_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена загрузки."""
    context.user_data.pop("upload", None)
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(MESSAGES["upload_cancelled"])
    else:
        await update.message.reply_text(MESSAGES["upload_cancelled"])
    
    return ConversationHandler.END


# ==================== DOCUMENT CALLBACKS ====================

async def view_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр документа."""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split("|")
    if len(data) < 3:
        return
    
    doc_id = int(data[2])
    user_id = query.from_user.id
    
    doc = get_document_by_id(doc_id, user_id)
    if not doc:
        await query.edit_message_text("❌ Документ не найден.")
        return
    
    text = format_document_info(doc, detailed=True)
    keyboard = build_document_actions_keyboard(doc_id)
    
    await query.edit_message_text(
        text,
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )


async def download_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Скачивание документа."""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split("|")
    if len(data) < 3:
        return
    
    doc_id = int(data[2])
    user_id = query.from_user.id
    
    doc = get_document_by_id(doc_id, user_id)
    if not doc:
        await query.edit_message_text("❌ Документ не найден.")
        return
    
    # Отправляем файл
    try:
        await context.bot.send_document(
            chat_id=query.message.chat_id,
            document=doc["file_id"],
            caption=f"📄 {doc['name']}"
        )
    except Exception as e:
        logger.error(f"Error sending document: {e}")
        await query.message.reply_text("❌ Не удалось отправить файл.")


async def delete_document_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение удаления документа."""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split("|")
    if len(data) < 3:
        return
    
    doc_id = int(data[2])
    user_id = query.from_user.id
    
    doc = get_document_by_id(doc_id, user_id)
    if not doc:
        await query.edit_message_text("❌ Документ не найден.")
        return
    
    keyboard = build_confirmation_keyboard(
        confirm_callback=f"doc|delete_yes|{doc_id}",
        cancel_callback=f"doc|view|{doc_id}",
        confirm_text="🗑️ Удалить",
        cancel_text="❌ Отмена"
    )
    
    await query.edit_message_text(
        MESSAGES["delete_confirm"].format(name=doc["name"]),
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )


async def delete_document_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выполнение удаления документа."""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split("|")
    if len(data) < 3:
        return
    
    doc_id = int(data[2])
    user_id = query.from_user.id
    
    if delete_document(doc_id, user_id):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📚 Мои документы", callback_data="mydocs|list|0")]
        ])
        await query.edit_message_text(
            MESSAGES["delete_success"],
            reply_markup=keyboard
        )
    else:
        await query.edit_message_text(MESSAGES["delete_error"])


async def edit_document_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню редактирования документа."""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split("|")
    if len(data) < 3:
        return
    
    doc_id = int(data[2])
    user_id = query.from_user.id
    
    doc = get_document_by_id(doc_id, user_id)
    if not doc:
        await query.edit_message_text("❌ Документ не найден.")
        return
    
    keyboard = build_edit_document_keyboard(doc_id)
    
    await query.edit_message_text(
        f"✏️ *Редактирование документа*\n\n"
        f"📄 {doc['name']}\n\n"
        "Что хочешь изменить?",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )


async def mydocs_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список документов с пагинацией."""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split("|")
    page = int(data[2]) if len(data) > 2 else 0
    
    user_id = query.from_user.id
    documents = get_user_documents(user_id)
    
    if not documents:
        await query.edit_message_text(MESSAGES["no_documents"])
        return
    
    page_size = 10
    total_pages = (len(documents) + page_size - 1) // page_size
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
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀️", callback_data=f"mydocs|list|{page - 1}"))
    if total_pages > 1:
        nav_row.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("▶️", callback_data=f"mydocs|list|{page + 1}"))
    
    if nav_row:
        keyboard.append(nav_row)
    
    await query.edit_message_text(
        f"📚 *Мои документы* (стр. {page + 1}/{total_pages})",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )


# ==================== CONVERSATION HANDLER ====================

def get_document_conversation_handler() -> ConversationHandler:
    """Создать ConversationHandler для загрузки документов."""
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Document.ALL, upload_start),
            MessageHandler(filters.PHOTO, upload_start),
        ],
        states={
            UploadStates.WAITING_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, upload_name),
            ],
            UploadStates.WAITING_START_DATE: [
                CallbackQueryHandler(upload_start_date_callback, pattern=r"^start\|"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, upload_start_date_manual),
            ],
            UploadStates.WAITING_END_DATE: [
                CallbackQueryHandler(upload_end_date_callback, pattern=r"^end\|"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, upload_end_date_manual),
            ],
            UploadStates.WAITING_TEMPLATE: [
                CallbackQueryHandler(upload_template_callback, pattern=r"^upload\|template\|"),
            ],
        },
        fallbacks=[
            MessageHandler(filters.COMMAND, upload_cancel),
        ],
        allow_reentry=True,
        name="upload_conversation",
        persistent=False,
    )


def get_document_callback_handlers():
    """Получить обработчики callback для документов."""
    return [
        CallbackQueryHandler(view_document, pattern=r"^doc\|view\|"),
        CallbackQueryHandler(download_document, pattern=r"^doc\|download\|"),
        CallbackQueryHandler(delete_document_confirm, pattern=r"^doc\|delete\|(?!yes)"),
        CallbackQueryHandler(delete_document_execute, pattern=r"^doc\|delete_yes\|"),
        CallbackQueryHandler(edit_document_menu, pattern=r"^doc\|edit\|"),
        CallbackQueryHandler(mydocs_list, pattern=r"^mydocs\|list\|"),
    ]
