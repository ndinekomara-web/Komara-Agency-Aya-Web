"""
Stockage des conversations — PostgreSQL en production, SQLite en local.

Une « session » remplace ici le chat Telegram : c'est un identifiant créé par
le navigateur et conservé sur l'appareil. Les messages y sont enregistrés pour
que l'historique survive à un rechargement de page, à un redémarrage du
serveur ou à un redéploiement (avec PostgreSQL).
"""
from __future__ import annotations

import time
from typing import Any

import db


def _schema() -> list[str]:
    if db.backend() == "postgres":
        return [
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                lang TEXT,
                created_at DOUBLE PRECISION NOT NULL,
                last_seen DOUBLE PRECISION NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS messages (
                id BIGSERIAL PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                lang TEXT,
                created_at DOUBLE PRECISION NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id)",
            """
            CREATE TABLE IF NOT EXISTS quote_requests (
                id BIGSERIAL PRIMARY KEY,
                session_id TEXT NOT NULL,
                service TEXT,
                budget TEXT,
                lang TEXT,
                created_at DOUBLE PRECISION NOT NULL
            )
            """,
        ]
    return [
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            lang TEXT,
            created_at REAL NOT NULL,
            last_seen REAL NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            lang TEXT,
            created_at REAL NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id)",
        """
        CREATE TABLE IF NOT EXISTS quote_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            service TEXT,
            budget TEXT,
            lang TEXT,
            created_at REAL NOT NULL
        )
        """,
    ]


def init_db() -> None:
    db.run_many(_schema())


def touch_session(session_id: str, lang: str | None = None) -> None:
    now = time.time()
    db.run(
        "INSERT INTO sessions (session_id, lang, created_at, last_seen) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (session_id) DO UPDATE SET "
        "last_seen = EXCLUDED.last_seen, lang = COALESCE(EXCLUDED.lang, sessions.lang)",
        (session_id, lang, now, now),
    )


def add_message(session_id: str, role: str, content: str, lang: str | None = None) -> None:
    db.run(
        "INSERT INTO messages (session_id, role, content, lang, created_at) VALUES (?, ?, ?, ?, ?)",
        (session_id, role, content, lang, time.time()),
    )


def history(session_id: str, limit: int = 200) -> list[dict[str, Any]]:
    rows = db.run(
        "SELECT role, content, lang, created_at FROM messages "
        "WHERE session_id = ? ORDER BY id DESC LIMIT ?",
        (session_id, limit),
    )
    return list(reversed(rows))


def clear(session_id: str) -> int:
    rows = db.run("SELECT COUNT(*) AS total FROM messages WHERE session_id = ?", (session_id,))
    db.run("DELETE FROM messages WHERE session_id = ?", (session_id,))
    return int(rows[0]["total"]) if rows else 0


def add_quote(session_id: str, service: str, budget: str, lang: str | None = None) -> None:
    """Enregistre une demande de devis confirmée."""
    db.run(
        "INSERT INTO quote_requests (session_id, service, budget, lang, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (session_id, service, budget, lang, time.time()),
    )


def quotes(limit: int = 50) -> list[dict[str, Any]]:
    return db.run(
        "SELECT session_id, service, budget, lang, created_at FROM quote_requests "
        "ORDER BY id DESC LIMIT ?",
        (limit,),
    )


def stats() -> dict[str, Any]:
    sessions = db.run("SELECT COUNT(*) AS total FROM sessions")
    messages = db.run("SELECT COUNT(*) AS total FROM messages")
    return {
        "sessions": int(sessions[0]["total"]) if sessions else 0,
        "messages": int(messages[0]["total"]) if messages else 0,
        "backend": db.backend(),
    }
