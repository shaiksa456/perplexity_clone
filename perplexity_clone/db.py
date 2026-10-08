"""
Lightweight SQLite persistence layer for users, chat threads, and messages.

Kept dependency-free (stdlib sqlite3 only) so it drops into the existing
Flask app without touching requirements.txt.
"""
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.db")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                theme TEXT NOT NULL DEFAULT 'dark',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS threads (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL DEFAULT 'New search',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT NOT NULL,
                question TEXT NOT NULL,
                answer_markdown TEXT,
                answer_plain TEXT,
                sources_json TEXT,
                followups_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (thread_id) REFERENCES threads (id) ON DELETE CASCADE
            )
            """
        )


# ---------------------------------------------------------------- users ----

def create_user(username: str, email: str, password_hash: str) -> int:
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (username, email, password_hash, _now()),
        )
        return cur.lastrowid


def get_user_by_id(user_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def get_user_by_username(username: str):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        return dict(row) if row else None


def get_user_by_email(email: str):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None


def get_user_by_login(identifier: str):
    """Look a user up by username OR email, whichever was typed into the login form."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? OR email = ?",
            (identifier, identifier),
        ).fetchone()
        return dict(row) if row else None


def update_user_profile(user_id: int, username: str, email: str):
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET username = ?, email = ? WHERE id = ?",
            (username, email, user_id),
        )


def update_user_password(user_id: int, password_hash: str):
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (password_hash, user_id),
        )


def update_user_theme(user_id: int, theme: str):
    with get_db() as conn:
        conn.execute("UPDATE users SET theme = ? WHERE id = ?", (theme, user_id))


def delete_user(user_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


# -------------------------------------------------------------- threads ----

def create_thread(user_id: int, thread_id: str | None = None, title: str = "New search") -> str:
    thread_id = thread_id or str(uuid.uuid4())
    now = _now()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO threads (id, user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (thread_id, user_id, title, now, now),
        )
    return thread_id


def get_thread(thread_id: str):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM threads WHERE id = ?", (thread_id,)).fetchone()
        return dict(row) if row else None


def thread_belongs_to_user(thread_id: str, user_id: int) -> bool:
    thread = get_thread(thread_id)
    return bool(thread) and thread["user_id"] == user_id


def touch_thread(thread_id: str, title: str | None = None):
    with get_db() as conn:
        if title:
            conn.execute(
                "UPDATE threads SET updated_at = ?, title = ? WHERE id = ?",
                (_now(), title, thread_id),
            )
        else:
            conn.execute(
                "UPDATE threads SET updated_at = ? WHERE id = ?", (_now(), thread_id)
            )


def list_threads_for_user(user_id: int, limit: int = 100):
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT t.id, t.title, t.created_at, t.updated_at,
                   (SELECT COUNT(*) FROM messages m WHERE m.thread_id = t.id) AS message_count
            FROM threads t
            WHERE t.user_id = ?
            ORDER BY t.updated_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def delete_thread(thread_id: str, user_id: int):
    with get_db() as conn:
        conn.execute(
            "DELETE FROM threads WHERE id = ? AND user_id = ?", (thread_id, user_id)
        )


# ------------------------------------------------------------- messages ----

def add_message(thread_id: str, question: str, result: dict):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO messages
                (thread_id, question, answer_markdown, answer_plain, sources_json, followups_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                thread_id,
                question,
                result.get("answer_markdown", ""),
                result.get("answer_plain", ""),
                json.dumps(result.get("sources", [])),
                json.dumps(result.get("followups", [])),
                _now(),
            ),
        )


def get_messages_for_thread(thread_id: str):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE thread_id = ? ORDER BY id ASC", (thread_id,)
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["sources"] = json.loads(d.pop("sources_json") or "[]")
            d["followups"] = json.loads(d.pop("followups_json") or "[]")
            out.append(d)
        return out


def get_history_pairs(thread_id: str) -> list[dict]:
    """Shape expected by rag.pipeline.run_query: [{question, answer_plain}, ...]."""
    return [
        {"question": m["question"], "answer_plain": m["answer_plain"]}
        for m in get_messages_for_thread(thread_id)
    ]