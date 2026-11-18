"""
Accès base de données : PostgreSQL en production, SQLite en local.

Sur Railway, ajoutez le plugin PostgreSQL : la variable ``DATABASE_URL`` est
fournie automatiquement et l'application bascule dessus sans autre réglage.
En local, si ``DATABASE_URL`` est absent, on utilise un fichier SQLite dans
``MEMORY_DIR`` — aucune installation de serveur n'est nécessaire.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
from typing import Any, Iterable, Sequence

from config import MEMORY_DIR, SQLITE_DB_PATH

logger = logging.getLogger("aya.db")

DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()
_lock = threading.Lock()
_forced_sqlite = False
_fallback_reason: str | None = None


def backend() -> str:
    """Retourne ``postgres`` si une base distante est configurée, sinon ``sqlite``."""
    if _forced_sqlite:
        return "sqlite"
    return "postgres" if DATABASE_URL else "sqlite"


def fallback_to_sqlite(reason: str) -> None:
    """Bascule sur SQLite quand PostgreSQL est injoignable.

    L'application doit rester en ligne même si la base distante est mal
    configurée : mieux vaut perdre la persistance que refuser le service.
    """
    global _forced_sqlite, _fallback_reason
    _forced_sqlite = True
    _fallback_reason = reason
    logger.error("PostgreSQL injoignable (%s) : bascule sur SQLite", reason)


def describe() -> dict[str, Any]:
    """Informations affichées par /api/health."""
    if backend() == "postgres":
        host = DATABASE_URL.split("@")[-1].split("/")[0] if "@" in DATABASE_URL else "distante"
        return {"backend": "postgres", "host": host, "configured": True}
    return {
        "backend": "sqlite",
        "path": SQLITE_DB_PATH,
        "configured": False,
        "hint": (
            f"PostgreSQL configuré mais injoignable ({_fallback_reason})"
            if _fallback_reason
            else "DATABASE_URL absent : ajoutez une référence au service PostgreSQL"
        ),
    }


def _host() -> str:
    """Hôte de la base, sans identifiants (pour adapter le réglage SSL)."""
    tail = DATABASE_URL.split("@")[-1]
    return tail.split("/")[0].split(":")[0].lower()


def _is_private_host() -> bool:
    """Réseau interne Railway (ou local) : le SSL n'y est pas disponible."""
    host = _host()
    return (
        host.endswith(".railway.internal")
        or host in {"localhost", "127.0.0.1", "postgres", "db"}
        or host.startswith("10.")
        or host.startswith("192.168.")
    )


def _dsn() -> str:
    """Railway fournit parfois ``postgres://`` : on normalise le schéma.

    Le SSL est forcé pour une base distante (Supabase, Neon, Railway public),
    mais PAS pour le réseau interne Railway : celui-ci refuse les connexions
    SSL, et ``sslmode=require`` y provoquerait « server does not support SSL ».
    """
    dsn = DATABASE_URL
    if dsn.startswith("postgres://"):
        dsn = "postgresql://" + dsn[len("postgres://"):]
    if "sslmode=" not in dsn and not _is_private_host():
        dsn += ("&" if "?" in dsn else "?") + "sslmode=require"
    return dsn


# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------
def _sqlite_connect() -> sqlite3.Connection:
    os.makedirs(MEMORY_DIR, exist_ok=True)
    connection = sqlite3.connect(SQLITE_DB_PATH, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------
def _pg_connect(attempts: int = 3):
    """Connexion PostgreSQL avec quelques tentatives (la base peut démarrer
    après l'application sur Railway)."""
    import psycopg2

    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            try:
                connection = psycopg2.connect(_dsn(), connect_timeout=10)
            except Exception as ssl_error:
                # Base interne qui refuse le SSL malgré tout : on réessaie sans.
                if "SSL" in str(ssl_error) and "sslmode=" in _dsn():
                    logger.warning("SSL refusé par la base, nouvelle tentative sans SSL")
                    connection = psycopg2.connect(
                        _dsn().replace("sslmode=require", "sslmode=disable"),
                        connect_timeout=10,
                    )
                else:
                    raise
            connection.autocommit = True
            return connection
        except Exception as exc:  # pragma: no cover - dépend du réseau
            last_error = exc
            wait = min(2 ** attempt, 3)
            logger.warning(
                "PostgreSQL indisponible (tentative %s/%s) : %s — nouvelle tentative dans %ss",
                attempt + 1,
                attempts,
                exc,
                wait,
            )
            time.sleep(wait)
    raise RuntimeError(f"Connexion PostgreSQL impossible : {last_error}")


# ---------------------------------------------------------------------------
# API commune
# ---------------------------------------------------------------------------
def _sql(query: str) -> str:
    """Traduit les marqueurs ``?`` (SQLite) vers ``%s`` (PostgreSQL)."""
    return query.replace("?", "%s") if backend() == "postgres" else query


def run(query: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    """Exécute une requête et renvoie les lignes sous forme de dictionnaires."""
    with _lock:
        if backend() == "postgres":
            import psycopg2.extras

            connection = _pg_connect()
            try:
                with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                    cursor.execute(_sql(query), tuple(params))
                    if cursor.description is None:
                        return []
                    return [dict(row) for row in cursor.fetchall()]
            finally:
                connection.close()
        connection = _sqlite_connect()
        try:
            cursor = connection.execute(query, tuple(params))
            rows = [dict(row) for row in cursor.fetchall()] if cursor.description else []
            connection.commit()
            return rows
        finally:
            connection.close()


def run_many(statements: Iterable[str]) -> None:
    """Exécute plusieurs instructions DDL."""
    with _lock:
        if backend() == "postgres":
            connection = _pg_connect()
            try:
                with connection.cursor() as cursor:
                    for statement in statements:
                        cursor.execute(statement)
            finally:
                connection.close()
            return
        connection = _sqlite_connect()
        try:
            for statement in statements:
                connection.execute(statement)
            connection.commit()
        finally:
            connection.close()
