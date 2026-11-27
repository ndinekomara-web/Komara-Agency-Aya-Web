"""Tables des nouvelles fonctions : relances, rendez-vous, sauvegardes.

Aucune modification des tables existantes : on ajoute, on ne touche pas.
Compatible PostgreSQL (Railway) et SQLite (tests locaux).
"""
from __future__ import annotations

import time
from typing import Any

import db

_PG = [
    """CREATE TABLE IF NOT EXISTS followups (
        id BIGSERIAL PRIMARY KEY, lead_id BIGINT, session_id TEXT, phone TEXT,
        stage INT, due_at DOUBLE PRECISION, sent_at DOUBLE PRECISION, message TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS appointments (
        id BIGSERIAL PRIMARY KEY, session_id TEXT, name TEXT, phone TEXT, service TEXT,
        slot_iso TEXT, status TEXT, created_at DOUBLE PRECISION
    )""",
    """CREATE TABLE IF NOT EXISTS backups (
        id BIGSERIAL PRIMARY KEY, created_at DOUBLE PRECISION, size INT, data BYTEA
    )""",
    """CREATE TABLE IF NOT EXISTS lead_state (
        id BIGSERIAL PRIMARY KEY, phone TEXT, session_id TEXT, service TEXT,
        status TEXT, created_at DOUBLE PRECISION
    )""",
]

_SQLITE = [
    """CREATE TABLE IF NOT EXISTS followups (
        id INTEGER PRIMARY KEY AUTOINCREMENT, lead_id INTEGER, session_id TEXT, phone TEXT,
        stage INTEGER, due_at REAL, sent_at REAL, message TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS appointments (
        id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, name TEXT, phone TEXT, service TEXT,
        slot_iso TEXT, status TEXT, created_at REAL
    )""",
    """CREATE TABLE IF NOT EXISTS backups (
        id INTEGER PRIMARY KEY AUTOINCREMENT, created_at REAL, size INTEGER, data BLOB
    )""",
    """CREATE TABLE IF NOT EXISTS lead_state (
        id INTEGER PRIMARY KEY AUTOINCREMENT, phone TEXT, session_id TEXT, service TEXT,
        status TEXT, created_at REAL
    )""",
]

_ready = False


def init() -> None:
    global _ready
    if _ready:
        return
    for statement in (_PG if db.backend() == "postgres" else _SQLITE):
        try:
            db.run(statement)
        except Exception:
            pass
    _ready = True


def last_id(table: str) -> int:
    rows = db.run(f"SELECT id FROM {table} ORDER BY id DESC LIMIT 1")
    return int(rows[0]["id"]) if rows else 0


def now() -> float:
    return time.time()


def rows(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    init()
    try:
        return db.run(query, params)
    except Exception:
        return []
