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
    """Instructions de création, adaptées au moteur réellement utilisé."""
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
            """
            CREATE TABLE IF NOT EXISTS knowledge_entries (
                id BIGSERIAL PRIMARY KEY,
                lang TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at DOUBLE PRECISION NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS leads (
                id BIGSERIAL PRIMARY KEY,
                session_id TEXT NOT NULL,
                phone TEXT NOT NULL,
                note TEXT,
                created_at DOUBLE PRECISION NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS unanswered (
                id BIGSERIAL PRIMARY KEY,
                session_id TEXT NOT NULL,
                question TEXT NOT NULL,
                lang TEXT,
                created_at DOUBLE PRECISION NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS uploads (
                id BIGSERIAL PRIMARY KEY,
                session_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                content_type TEXT,
                data BYTEA NOT NULL,
                created_at DOUBLE PRECISION NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS alerts (
                id BIGSERIAL PRIMARY KEY,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT,
                seen INTEGER NOT NULL DEFAULT 0,
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
        """
            CREATE TABLE IF NOT EXISTS knowledge_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lang TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at REAL NOT NULL
            )
        """,
        """
            CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            phone TEXT NOT NULL,
            note TEXT,
            created_at REAL NOT NULL
            )
        """,
        """
            CREATE TABLE IF NOT EXISTS unanswered (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            question TEXT NOT NULL,
            lang TEXT,
            created_at REAL NOT NULL
            )
        """,
        """
            CREATE TABLE IF NOT EXISTS uploads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            content_type TEXT,
            data BLOB NOT NULL,
            created_at REAL NOT NULL
            )
        """,
        """
            CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT,
            seen INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL
            )
        """,
    ]


def init_db() -> None:
    """Crée les tables, en basculant sur SQLite si PostgreSQL est injoignable."""
    try:
        db.run_many(_schema())
        return
    except Exception as exc:
        if db.backend() != "postgres":
            raise
        db.fallback_to_sqlite(str(exc).splitlines()[0][:160])
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
        "SELECT id, session_id, service, budget, lang, created_at FROM quote_requests "
        "ORDER BY id DESC LIMIT ?",
        (limit,),
    )


def add_knowledge(lang: str, title: str, content: str) -> int:
    """Ajoute une connaissance saisie par l'administrateur."""
    rows = db.run(
        "INSERT INTO knowledge_entries (lang, title, content, created_at) VALUES (?, ?, ?, ?) "
        "RETURNING id",
        (lang, title, content, time.time()),
    )
    return int(rows[0]["id"]) if rows else 0


def knowledge_entries(lang: str | None = None) -> list[dict[str, Any]]:
    if lang:
        return db.run(
            "SELECT id, lang, title, content, created_at FROM knowledge_entries "
            "WHERE lang = ? ORDER BY id DESC",
            (lang,),
        )
    return db.run(
        "SELECT id, lang, title, content, created_at FROM knowledge_entries ORDER BY id DESC"
    )


def delete_knowledge(entry_id: int) -> int:
    rows = db.run("SELECT COUNT(*) AS total FROM knowledge_entries WHERE id = ?", (entry_id,))
    db.run("DELETE FROM knowledge_entries WHERE id = ?", (entry_id,))
    return int(rows[0]["total"]) if rows else 0


def stats() -> dict[str, Any]:
    sessions = db.run("SELECT COUNT(*) AS total FROM sessions")
    messages = db.run("SELECT COUNT(*) AS total FROM messages")
    knowledge = db.run("SELECT COUNT(*) AS total FROM knowledge_entries")
    return {
        "sessions": int(sessions[0]["total"]) if sessions else 0,
        "messages": int(messages[0]["total"]) if messages else 0,
        "knowledge": int(knowledge[0]["total"]) if knowledge else 0,
        "backend": db.backend(),
    }


def add_lead(session_id: str, phone: str, note: str = "") -> int:
    """Enregistre un numéro laissé par un client (visible dans /admin)."""
    init_db()
    db.run(
        "INSERT INTO leads (session_id, phone, note, created_at) VALUES (?, ?, ?, ?)",
        (session_id, phone, note, time.time()),
    )
    return 1


def leads(limit: int = 50) -> list[dict]:
    init_db()
    return db.run(
        "SELECT id, session_id, phone, note, created_at FROM leads ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )


# ---------------------------------------------------------------- questions sans réponse
def add_unanswered(session_id: str, question: str, lang: str | None = None) -> None:
    """Note une question restée sans réponse : elle remonte dans /admin."""
    init_db()
    db.run(
        "INSERT INTO unanswered (session_id, question, lang, created_at) VALUES (?, ?, ?, ?)",
        (session_id, question.strip()[:500], lang, time.time()),
    )


def unanswered_top(limit: int = 30) -> list[dict[str, Any]]:
    rows = db.run(
        "SELECT question, COUNT(*) AS times, MAX(created_at) AS last_seen, lang "
        "FROM unanswered GROUP BY question, lang ORDER BY times DESC, last_seen DESC LIMIT ?",
        (limit,),
    )
    return rows


# ---------------------------------------------------------------- fichiers des clients
def add_upload(session_id: str, filename: str, content_type: str, data: bytes) -> int:
    init_db()
    rows = db.run(
        "INSERT INTO uploads (session_id, filename, content_type, data, created_at) "
        "VALUES (?, ?, ?, ?, ?) RETURNING id",
        (session_id, filename, content_type, data, time.time()),
    )
    if rows and rows[0].get("id"):
        return int(rows[0]["id"])
    last = db.run("SELECT id FROM uploads ORDER BY id DESC LIMIT 1")
    return int(last[0]["id"]) if last else 0


def uploads(limit: int = 50) -> list[dict[str, Any]]:
    return db.run(
        "SELECT id, session_id, filename, content_type, created_at FROM uploads "
        "ORDER BY id DESC LIMIT ?",
        (limit,),
    )


def upload_for_session(upload_id: int, session_id: str) -> dict[str, Any] | None:
    """Un client ne peut ouvrir QUE ses propres fichiers."""
    rows = db.run(
        "SELECT id, filename, content_type, data FROM uploads WHERE id = ? AND session_id = ?",
        (upload_id, session_id),
    )
    return rows[0] if rows else None


def upload_data(upload_id: int) -> dict[str, Any] | None:
    rows = db.run(
        "SELECT id, filename, content_type, data FROM uploads WHERE id = ?", (upload_id,)
    )
    return rows[0] if rows else None


# ---------------------------------------------------------------- alertes équipe
def add_alert(kind: str, title: str, body: str = "") -> int:
    init_db()
    rows = db.run(
        "INSERT INTO alerts (kind, title, body, seen, created_at) VALUES (?, ?, ?, 0, ?) RETURNING id",
        (kind, title[:200], body[:2000], time.time()),
    )
    if rows and rows[0].get("id"):
        return int(rows[0]["id"])
    last = db.run("SELECT id FROM alerts ORDER BY id DESC LIMIT 1")
    return int(last[0]["id"]) if last else 0


def alerts(limit: int = 40) -> list[dict[str, Any]]:
    return db.run(
        "SELECT id, kind, title, body, seen, created_at FROM alerts ORDER BY id DESC LIMIT ?",
        (limit,),
    )


def mark_alert_seen(alert_id: int) -> int:
    init_db()
    rows = db.run("SELECT COUNT(*) AS total FROM alerts WHERE id = ? AND seen = 0", (alert_id,))
    db.run("UPDATE alerts SET seen = 1 WHERE id = ?", (alert_id,))
    return int(rows[0]["total"]) if rows else 0


# ---------------------------------------------------------------- messages
def delete_message(message_id: int, session_id: str) -> int:
    init_db()
    rows = db.run(
        "SELECT COUNT(*) AS total FROM messages WHERE id = ? AND session_id = ?",
        (message_id, session_id),
    )
    db.run("DELETE FROM messages WHERE id = ? AND session_id = ?", (message_id, session_id))
    return int(rows[0]["total"]) if rows else 0


def search_messages(session_id: str, needle: str, limit: int = 40) -> list[dict[str, Any]]:
    return db.run(
        "SELECT id, role, content, created_at FROM messages "
        "WHERE session_id = ? AND content ILIKE ? ORDER BY id DESC LIMIT ?"
        if db.backend() == "postgres"
        else "SELECT id, role, content, created_at FROM messages "
        "WHERE session_id = ? AND LOWER(content) LIKE LOWER(?) ORDER BY id DESC LIMIT ?",
        (session_id, f"%{needle}%", limit),
    )


# ---------------------------------------------------------------- statistiques
def analytics(days: int = 14) -> dict[str, Any]:
    """Chiffres simples pour /admin : activité, devis, numéros, questions."""
    since = time.time() - days * 86400
    total_sessions = db.run("SELECT COUNT(*) AS total FROM sessions")
    total_messages = db.run("SELECT COUNT(*) AS total FROM messages")
    total_quotes = db.run("SELECT COUNT(*) AS total FROM quote_requests")
    total_leads = db.run("SELECT COUNT(*) AS total FROM leads")
    per_day = db.run(
        "SELECT session_id, created_at FROM messages WHERE created_at >= ?", (since,)
    )
    services = db.run(
        "SELECT service, COUNT(*) AS times FROM quote_requests GROUP BY service ORDER BY times DESC"
    )
    buckets: dict[str, int] = {}
    for row in per_day:
        day = time.strftime("%Y-%m-%d", time.gmtime(float(row["created_at"])))
        buckets[day] = buckets.get(day, 0) + 1
    days_list = sorted(buckets.items())[-days:]
    return {
        "sessions": int(total_sessions[0]["total"]) if total_sessions else 0,
        "messages": int(total_messages[0]["total"]) if total_messages else 0,
        "quotes": int(total_quotes[0]["total"]) if total_quotes else 0,
        "leads": int(total_leads[0]["total"]) if total_leads else 0,
        "per_day": [{"day": day, "messages": count} for day, count in days_list],
        "services": [{"service": r["service"] or "non précisé", "times": int(r["times"])} for r in services],
        "unanswered": len(unanswered_top(200)),
    }
