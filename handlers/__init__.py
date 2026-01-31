"""
Модуль обработчиков команд и callback-запросов.
"""
from handlers.commands import get_command_handlers
from handlers.documents import get_document_conversation_handler, get_document_callback_handlers
from handlers.templates import get_template_handlers
from handlers.callbacks import get_callback_dispatcher

__all__ = [
    "get_command_handlers",
    "get_document_conversation_handler",
    "get_document_callback_handlers",
    "get_template_handlers",
    "get_callback_dispatcher",
]
