"""
Модуль работы с базой данных SQLite.
"""
import sqlite3
import logging
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from config import DB_PATH

logger = logging.getLogger(__name__)


@contextmanager
def get_connection():
    """Контекстный менеджер для соединения с БД."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        conn.close()


def init_db():
    """Инициализация базы данных - создание таблиц."""
    with get_connection() as conn:
        cur = conn.cursor()
        
        # Таблица пользователей
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица шаблонов
        cur.execute("""
            CREATE TABLE IF NOT EXISTS templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id),
                UNIQUE(user_id, name)
            )
        """)
        
        # Таблица документов
        cur.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                file_id TEXT NOT NULL,
                file_name TEXT,
                file_type TEXT,
                start_date DATE,
                end_date DATE,
                template_id INTEGER,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id),
                FOREIGN KEY (template_id) REFERENCES templates(id) ON DELETE SET NULL
            )
        """)
        
        # Таблица напоминаний (для отслеживания отправленных уведомлений)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS reminders_sent (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                days_before INTEGER NOT NULL,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
                UNIQUE(document_id, days_before)
            )
        """)
        
        # Индексы для оптимизации запросов
        cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_user ON documents(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_end_date ON documents(end_date)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_templates_user ON templates(user_id)")
        
        logger.info("Database initialized successfully")


# ==================== USERS ====================

def get_or_create_user(telegram_id: int, username: str = None, first_name: str = None) -> Dict:
    """Получить или создать пользователя."""
    with get_connection() as conn:
        cur = conn.cursor()
        
        cur.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        user = cur.fetchone()
        
        if user:
            # Обновляем last_active
            cur.execute(
                "UPDATE users SET last_active = ?, username = ?, first_name = ? WHERE telegram_id = ?",
                (datetime.now(), username, first_name, telegram_id)
            )
            return dict(user)
        
        # Создаём нового пользователя
        cur.execute(
            "INSERT INTO users (telegram_id, username, first_name) VALUES (?, ?, ?)",
            (telegram_id, username, first_name)
        )
        
        cur.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        return dict(cur.fetchone())


# ==================== DOCUMENTS ====================

def insert_document(
    user_id: int,
    name: str,
    file_id: str,
    file_name: str = None,
    file_type: str = None,
    start_date: date = None,
    end_date: date = None,
    template_id: int = None,
    notes: str = None
) -> Optional[int]:
    """Добавить новый документ. Возвращает ID документа или None."""
    with get_connection() as conn:
        cur = conn.cursor()
        
        cur.execute("""
            INSERT INTO documents 
            (user_id, name, file_id, file_name, file_type, start_date, end_date, template_id, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, name, file_id, file_name, file_type, start_date, end_date, template_id, notes))
        
        doc_id = cur.lastrowid
        logger.info(f"Document inserted: id={doc_id}, user={user_id}, name={name}")
        return doc_id


def get_document_by_id(doc_id: int, user_id: int) -> Optional[Dict]:
    """Получить документ по ID (с проверкой владельца)."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT d.*, t.name as template_name 
            FROM documents d
            LEFT JOIN templates t ON d.template_id = t.id
            WHERE d.id = ? AND d.user_id = ?
        """, (doc_id, user_id))
        row = cur.fetchone()
        return dict(row) if row else None


def get_user_documents(user_id: int, template_id: int = None) -> List[Dict]:
    """Получить все документы пользователя."""
    with get_connection() as conn:
        cur = conn.cursor()
        
        if template_id:
            cur.execute("""
                SELECT d.*, t.name as template_name 
                FROM documents d
                LEFT JOIN templates t ON d.template_id = t.id
                WHERE d.user_id = ? AND d.template_id = ?
                ORDER BY d.end_date ASC NULLS LAST, d.created_at DESC
            """, (user_id, template_id))
        else:
            cur.execute("""
                SELECT d.*, t.name as template_name 
                FROM documents d
                LEFT JOIN templates t ON d.template_id = t.id
                WHERE d.user_id = ?
                ORDER BY d.end_date ASC NULLS LAST, d.created_at DESC
            """, (user_id,))
        
        return [dict(row) for row in cur.fetchall()]


def get_documents_count(user_id: int) -> int:
    """Получить количество документов пользователя."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM documents WHERE user_id = ?", (user_id,))
        return cur.fetchone()[0]


def update_document(
    doc_id: int,
    user_id: int,
    name: str = None,
    start_date: date = None,
    end_date: date = None,
    template_id: int = None,
    notes: str = None
) -> bool:
    """Обновить документ. Возвращает True если обновлено."""
    with get_connection() as conn:
        cur = conn.cursor()
        
        # Строим динамический запрос
        updates = []
        params = []
        
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if start_date is not None:
            updates.append("start_date = ?")
            params.append(start_date)
        if end_date is not None:
            updates.append("end_date = ?")
            params.append(end_date if end_date != "NULL" else None)
        if template_id is not None:
            updates.append("template_id = ?")
            params.append(template_id if template_id != -1 else None)
        if notes is not None:
            updates.append("notes = ?")
            params.append(notes)
        
        if not updates:
            return False
        
        updates.append("updated_at = ?")
        params.append(datetime.now())
        
        params.extend([doc_id, user_id])
        
        query = f"UPDATE documents SET {', '.join(updates)} WHERE id = ? AND user_id = ?"
        cur.execute(query, params)
        
        updated = cur.rowcount > 0
        if updated:
            logger.info(f"Document updated: id={doc_id}, user={user_id}")
        return updated


def delete_document(doc_id: int, user_id: int) -> bool:
    """Удалить документ. Возвращает True если удалено."""
    with get_connection() as conn:
        cur = conn.cursor()
        
        # Сначала проверяем существование
        cur.execute("SELECT id FROM documents WHERE id = ? AND user_id = ?", (doc_id, user_id))
        if not cur.fetchone():
            logger.warning(f"Document not found for deletion: id={doc_id}, user={user_id}")
            return False
        
        # Удаляем связанные напоминания
        cur.execute("DELETE FROM reminders_sent WHERE document_id = ?", (doc_id,))
        
        # Удаляем документ
        cur.execute("DELETE FROM documents WHERE id = ? AND user_id = ?", (doc_id, user_id))
        
        deleted = cur.rowcount > 0
        if deleted:
            logger.info(f"Document deleted: id={doc_id}, user={user_id}")
        return deleted


def search_documents(user_id: int, query: str) -> List[Dict]:
    """Поиск документов по названию."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT d.*, t.name as template_name 
            FROM documents d
            LEFT JOIN templates t ON d.template_id = t.id
            WHERE d.user_id = ? AND d.name LIKE ?
            ORDER BY d.name
        """, (user_id, f"%{query}%"))
        return [dict(row) for row in cur.fetchall()]


# ==================== TEMPLATES ====================

def insert_template(user_id: int, name: str, description: str = None) -> Optional[int]:
    """Создать новый шаблон. Возвращает ID или None если уже существует."""
    with get_connection() as conn:
        cur = conn.cursor()
        
        # Проверяем уникальность
        cur.execute(
            "SELECT id FROM templates WHERE user_id = ? AND name = ?",
            (user_id, name)
        )
        if cur.fetchone():
            return None
        
        cur.execute(
            "INSERT INTO templates (user_id, name, description) VALUES (?, ?, ?)",
            (user_id, name, description)
        )
        
        template_id = cur.lastrowid
        logger.info(f"Template created: id={template_id}, user={user_id}, name={name}")
        return template_id


def get_template_by_id(template_id: int, user_id: int) -> Optional[Dict]:
    """Получить шаблон по ID."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM templates WHERE id = ? AND user_id = ?",
            (template_id, user_id)
        )
        row = cur.fetchone()
        return dict(row) if row else None


def get_user_templates(user_id: int) -> List[Dict]:
    """Получить все шаблоны пользователя с количеством документов."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT t.*, COUNT(d.id) as documents_count
            FROM templates t
            LEFT JOIN documents d ON t.id = d.template_id
            WHERE t.user_id = ?
            GROUP BY t.id
            ORDER BY t.name
        """, (user_id,))
        return [dict(row) for row in cur.fetchall()]


def get_templates_count(user_id: int) -> int:
    """Получить количество шаблонов пользователя."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM templates WHERE user_id = ?", (user_id,))
        return cur.fetchone()[0]


def delete_template(template_id: int, user_id: int) -> bool:
    """Удалить шаблон. Документы НЕ удаляются, только отвязываются."""
    with get_connection() as conn:
        cur = conn.cursor()
        
        # Проверяем существование
        cur.execute("SELECT id FROM templates WHERE id = ? AND user_id = ?", (template_id, user_id))
        if not cur.fetchone():
            return False
        
        # Отвязываем документы от шаблона
        cur.execute("UPDATE documents SET template_id = NULL WHERE template_id = ?", (template_id,))
        
        # Удаляем шаблон
        cur.execute("DELETE FROM templates WHERE id = ? AND user_id = ?", (template_id, user_id))
        
        deleted = cur.rowcount > 0
        if deleted:
            logger.info(f"Template deleted: id={template_id}, user={user_id}")
        return deleted


# ==================== REMINDERS ====================

def get_expiring_documents(days: int) -> List[Dict]:
    """Получить документы, истекающие через указанное количество дней."""
    with get_connection() as conn:
        cur = conn.cursor()
        target_date = date.today()
        
        # Используем julianday для точного расчёта дней
        cur.execute("""
            SELECT d.*, u.telegram_id as user_telegram_id, u.first_name as user_first_name
            FROM documents d
            JOIN users u ON d.user_id = u.telegram_id
            WHERE d.end_date IS NOT NULL
            AND CAST(julianday(d.end_date) - julianday(?) AS INTEGER) = ?
        """, (target_date, days))
        
        return [dict(row) for row in cur.fetchall()]


def is_reminder_sent(doc_id: int, days_before: int) -> bool:
    """Проверить, было ли отправлено напоминание."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM reminders_sent WHERE document_id = ? AND days_before = ?",
            (doc_id, days_before)
        )
        return cur.fetchone() is not None


def mark_reminder_sent(doc_id: int, days_before: int):
    """Отметить напоминание как отправленное."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO reminders_sent (document_id, days_before) VALUES (?, ?)",
            (doc_id, days_before)
        )


def get_documents_statistics(user_id: int) -> Dict:
    """Получить статистику документов пользователя."""
    with get_connection() as conn:
        cur = conn.cursor()
        
        today = date.today()
        
        # Общее количество
        cur.execute("SELECT COUNT(*) FROM documents WHERE user_id = ?", (user_id,))
        total = cur.fetchone()[0]
        
        # Истекшие
        cur.execute(
            "SELECT COUNT(*) FROM documents WHERE user_id = ? AND end_date < ?",
            (user_id, today)
        )
        expired = cur.fetchone()[0]
        
        # Истекают в течение 30 дней
        cur.execute("""
            SELECT COUNT(*) FROM documents 
            WHERE user_id = ? AND end_date >= ? AND end_date <= date(?, '+30 days')
        """, (user_id, today, today))
        expiring_soon = cur.fetchone()[0]
        
        # Без даты окончания
        cur.execute(
            "SELECT COUNT(*) FROM documents WHERE user_id = ? AND end_date IS NULL",
            (user_id,)
        )
        no_end_date = cur.fetchone()[0]
        
        return {
            "total": total,
            "expired": expired,
            "expiring_soon": expiring_soon,
            "no_end_date": no_end_date,
            "active": total - expired
        }
