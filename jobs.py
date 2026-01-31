"""
Фоновые задачи бота - напоминания о документах.
"""
import logging
from datetime import time

from telegram.ext import ContextTypes

from config import REMINDER_DAYS_BEFORE
from database import get_expiring_documents, is_reminder_sent, mark_reminder_sent
from utils import format_date

logger = logging.getLogger(__name__)


async def send_reminders(context: ContextTypes.DEFAULT_TYPE):
    """
    Отправка напоминаний о документах с истекающим сроком.
    Запускается по расписанию.
    """
    logger.info("Running reminder job...")
    
    sent_count = 0
    
    for days in REMINDER_DAYS_BEFORE:
        documents = get_expiring_documents(days)
        
        for doc in documents:
            doc_id = doc["id"]
            user_telegram_id = doc["user_telegram_id"]
            
            # Проверяем, не отправляли ли уже
            if is_reminder_sent(doc_id, days):
                continue
            
            # Формируем сообщение
            if days == 0:
                urgency = "🔴 *СЕГОДНЯ*"
            elif days == 1:
                urgency = "🟠 *ЗАВТРА*"
            elif days <= 7:
                urgency = f"🟡 Через {days} дн."
            else:
                urgency = f"📅 Через {days} дн."
            
            message = (
                f"⏰ *Напоминание о документе*\n\n"
                f"📄 {doc['name']}\n"
                f"📅 Истекает: {format_date(doc['end_date'])}\n"
                f"{urgency}\n\n"
                f"Используй /mydocs чтобы посмотреть детали."
            )
            
            try:
                await context.bot.send_message(
                    chat_id=user_telegram_id,
                    text=message,
                    parse_mode="Markdown"
                )
                
                # Отмечаем напоминание как отправленное
                mark_reminder_sent(doc_id, days)
                sent_count += 1
                
                logger.info(f"Reminder sent: doc={doc_id}, user={user_telegram_id}, days={days}")
                
            except Exception as e:
                logger.error(f"Failed to send reminder: doc={doc_id}, user={user_telegram_id}, error={e}")
    
    logger.info(f"Reminder job completed. Sent {sent_count} reminders.")


def setup_jobs(application):
    """
    Настройка фоновых задач.
    Вызывается при запуске бота.
    """
    job_queue = application.job_queue
    
    if job_queue is None:
        logger.warning("Job queue is not available. Reminders disabled.")
        return
    
    # Запускаем проверку напоминаний каждый день в 9:00
    job_queue.run_daily(
        send_reminders,
        time=time(hour=9, minute=0),
        name="daily_reminders"
    )
    
    # Также запускаем сразу при старте (для тестирования)
    job_queue.run_once(
        send_reminders,
        when=10,  # Через 10 секунд после запуска
        name="initial_reminders"
    )
    
    logger.info("Reminder jobs scheduled.")
