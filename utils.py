"""
Вспомогательные функции для бота.
"""
import os
from datetime import date, datetime, timedelta
from typing import Optional, List, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config import ALLOWED_EXTENSIONS, MAX_FILE_SIZE


def validate_file(file_name: str, file_size: int) -> Tuple[bool, str]:
    """
    Проверить файл на допустимость.
    Возвращает (is_valid, error_message).
    """
    if not file_name:
        return False, "Не удалось определить имя файла."
    
    ext = os.path.splitext(file_name.lower())[1]
    
    if ext not in ALLOWED_EXTENSIONS:
        formats = ", ".join(sorted(ALLOWED_EXTENSIONS))
        return False, f"Неподдерживаемый формат файла ({ext}).\n\nРазрешённые форматы: {formats}"
    
    if file_size > MAX_FILE_SIZE:
        max_mb = MAX_FILE_SIZE / (1024 * 1024)
        return False, f"Файл слишком большой. Максимальный размер: {max_mb:.0f} МБ"
    
    return True, ""


def get_file_type(file_name: str) -> str:
    """Определить тип файла по расширению."""
    if not file_name:
        return "unknown"
    
    ext = os.path.splitext(file_name.lower())[1]
    
    type_mapping = {
        (".pdf",): "pdf",
        (".doc", ".docx", ".odt", ".rtf"): "document",
        (".xls", ".xlsx", ".ods"): "spreadsheet",
        (".ppt", ".pptx", ".odp"): "presentation",
        (".jpg", ".jpeg", ".png", ".gif", ".webp"): "image",
        (".zip", ".rar", ".7z"): "archive",
        (".txt",): "text",
    }
    
    for extensions, file_type in type_mapping.items():
        if ext in extensions:
            return file_type
    
    return "other"


def format_date(d: Optional[date], default: str = "—") -> str:
    """Форматировать дату для отображения."""
    if not d:
        return default
    
    if isinstance(d, str):
        try:
            d = datetime.strptime(d, "%Y-%m-%d").date()
        except ValueError:
            return default
    
    return d.strftime("%d.%m.%Y")


def parse_date(date_str: str) -> Optional[date]:
    """Парсить дату из строки (формат YYYY-MM-DD)."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None


def get_days_until(end_date: Optional[date]) -> Optional[int]:
    """Получить количество дней до даты."""
    if not end_date:
        return None
    
    if isinstance(end_date, str):
        end_date = parse_date(end_date)
        if not end_date:
            return None
    
    delta = end_date - date.today()
    return delta.days


def get_status_emoji(end_date: Optional[date]) -> str:
    """Получить эмодзи статуса документа."""
    days = get_days_until(end_date)
    
    if days is None:
        return "📄"  # Без даты окончания
    elif days < 0:
        return "🔴"  # Истёк
    elif days <= 7:
        return "🟠"  # Скоро истекает (неделя)
    elif days <= 30:
        return "🟡"  # Истекает в течение месяца
    else:
        return "🟢"  # Действует


def get_status_text(end_date: Optional[date]) -> str:
    """Получить текст статуса документа."""
    days = get_days_until(end_date)
    
    if days is None:
        return "Без срока"
    elif days < 0:
        return f"Истёк {abs(days)} дн. назад"
    elif days == 0:
        return "Истекает сегодня!"
    elif days == 1:
        return "Истекает завтра!"
    elif days <= 7:
        return f"Истекает через {days} дн."
    elif days <= 30:
        return f"Истекает через {days} дн."
    else:
        return f"Действует ({days} дн.)"


def format_document_info(doc: dict, detailed: bool = False) -> str:
    """Форматировать информацию о документе."""
    emoji = get_status_emoji(doc.get("end_date"))
    name = doc.get("name", "Без названия")
    
    if not detailed:
        status = get_status_text(doc.get("end_date"))
        return f"{emoji} *{name}*\n   └ {status}"
    
    lines = [f"{emoji} *{name}*"]
    
    start_date = doc.get("start_date")
    end_date = doc.get("end_date")
    
    if start_date:
        lines.append(f"📅 Начало: {format_date(start_date)}")
    
    if end_date:
        lines.append(f"📅 Окончание: {format_date(end_date)}")
        lines.append(f"⏳ {get_status_text(end_date)}")
    
    template_name = doc.get("template_name")
    if template_name:
        lines.append(f"📁 Шаблон: {template_name}")
    
    file_name = doc.get("file_name")
    if file_name:
        lines.append(f"📎 Файл: {file_name}")
    
    return "\n".join(lines)


# ==================== KEYBOARD BUILDERS ====================

def build_date_keyboard(
    callback_prefix: str,
    include_today: bool = True,
    include_skip: bool = False,
    quick_options: bool = True
) -> InlineKeyboardMarkup:
    """Построить клавиатуру выбора даты."""
    keyboard = []
    today = date.today()
    
    if include_today:
        keyboard.append([
            InlineKeyboardButton(
                f"📅 Сегодня ({format_date(today)})",
                callback_data=f"{callback_prefix}|today"
            )
        ])
    
    if quick_options:
        # Быстрые опции
        quick_dates = [
            ("+1m", "Через 1 мес.", 30),
            ("+3m", "Через 3 мес.", 90),
            ("+6m", "Через 6 мес.", 180),
            ("+1y", "Через 1 год", 365),
            ("+2y", "Через 2 года", 730),
            ("+5y", "Через 5 лет", 1825),
        ]
        
        # По 2 кнопки в ряд
        row = []
        for code, label, days in quick_dates:
            target_date = today + timedelta(days=days)
            row.append(InlineKeyboardButton(
                label,
                callback_data=f"{callback_prefix}|{code}"
            ))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
    
    # Ввод вручную
    keyboard.append([
        InlineKeyboardButton(
            "✏️ Ввести дату вручную",
            callback_data=f"{callback_prefix}|manual"
        )
    ])
    
    if include_skip:
        keyboard.append([
            InlineKeyboardButton(
                "⏭️ Пропустить",
                callback_data=f"{callback_prefix}|skip"
            )
        ])
    
    return InlineKeyboardMarkup(keyboard)


def build_confirmation_keyboard(
    confirm_callback: str,
    cancel_callback: str,
    confirm_text: str = "✅ Да",
    cancel_text: str = "❌ Нет"
) -> InlineKeyboardMarkup:
    """Построить клавиатуру подтверждения."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(confirm_text, callback_data=confirm_callback),
            InlineKeyboardButton(cancel_text, callback_data=cancel_callback),
        ]
    ])


def build_pagination_keyboard(
    items: List,
    page: int,
    page_size: int,
    callback_prefix: str,
    item_callback_prefix: str,
    get_item_label: callable,
    get_item_id: callable,
    back_callback: str = None
) -> InlineKeyboardMarkup:
    """Построить клавиатуру с пагинацией."""
    keyboard = []
    
    total_pages = (len(items) + page_size - 1) // page_size
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, len(items))
    
    # Элементы текущей страницы
    for item in items[start_idx:end_idx]:
        label = get_item_label(item)
        item_id = get_item_id(item)
        keyboard.append([
            InlineKeyboardButton(label, callback_data=f"{item_callback_prefix}|{item_id}")
        ])
    
    # Навигация по страницам
    if total_pages > 1:
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton(
                "◀️ Назад",
                callback_data=f"{callback_prefix}|page|{page - 1}"
            ))
        nav_row.append(InlineKeyboardButton(
            f"{page + 1}/{total_pages}",
            callback_data=f"{callback_prefix}|current"
        ))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(
                "Вперёд ▶️",
                callback_data=f"{callback_prefix}|page|{page + 1}"
            ))
        keyboard.append(nav_row)
    
    # Кнопка назад
    if back_callback:
        keyboard.append([
            InlineKeyboardButton("🔙 Назад", callback_data=back_callback)
        ])
    
    return InlineKeyboardMarkup(keyboard)


def build_document_actions_keyboard(doc_id: int, include_back: bool = True) -> InlineKeyboardMarkup:
    """Построить клавиатуру действий с документом."""
    keyboard = [
        [
            InlineKeyboardButton("📥 Скачать", callback_data=f"doc|download|{doc_id}"),
            InlineKeyboardButton("✏️ Изменить", callback_data=f"doc|edit|{doc_id}"),
        ],
        [
            InlineKeyboardButton("🗑️ Удалить", callback_data=f"doc|delete|{doc_id}"),
        ]
    ]
    
    if include_back:
        keyboard.append([
            InlineKeyboardButton("🔙 К списку", callback_data="mydocs|list|0")
        ])
    
    return InlineKeyboardMarkup(keyboard)


def build_edit_document_keyboard(doc_id: int) -> InlineKeyboardMarkup:
    """Построить клавиатуру редактирования документа."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✏️ Название", callback_data=f"edit|name|{doc_id}"),
            InlineKeyboardButton("📅 Даты", callback_data=f"edit|dates|{doc_id}"),
        ],
        [
            InlineKeyboardButton("📁 Шаблон", callback_data=f"edit|template|{doc_id}"),
        ],
        [
            InlineKeyboardButton("🔙 Назад", callback_data=f"doc|view|{doc_id}")
        ]
    ])


def build_templates_keyboard(
    templates: List[dict],
    page: int = 0,
    page_size: int = 8,
    select_mode: bool = False,
    doc_id: int = None
) -> InlineKeyboardMarkup:
    """Построить клавиатуру шаблонов."""
    keyboard = []
    
    total_pages = max(1, (len(templates) + page_size - 1) // page_size)
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, len(templates))
    
    # Шаблоны текущей страницы
    for tmpl in templates[start_idx:end_idx]:
        count = tmpl.get("documents_count", 0)
        label = f"📁 {tmpl['name']} ({count})"
        
        if select_mode:
            callback = f"upload|template|{tmpl['id']}"
        else:
            callback = f"tmpl|view|{tmpl['id']}"
        
        keyboard.append([InlineKeyboardButton(label, callback_data=callback)])
    
    # Навигация по страницам
    if total_pages > 1:
        nav_row = []
        prefix = "upload|tmplpage" if select_mode else "templates|page"
        
        if page > 0:
            nav_row.append(InlineKeyboardButton("◀️", callback_data=f"{prefix}|{page - 1}"))
        nav_row.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton("▶️", callback_data=f"{prefix}|{page + 1}"))
        keyboard.append(nav_row)
    
    # Дополнительные кнопки
    if select_mode:
        keyboard.append([
            InlineKeyboardButton("⏭️ Без шаблона", callback_data="upload|template|skip")
        ])
    else:
        keyboard.append([
            InlineKeyboardButton("➕ Создать шаблон", callback_data="tmpl|create")
        ])
    
    return InlineKeyboardMarkup(keyboard)
