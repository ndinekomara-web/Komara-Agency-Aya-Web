"""Sauvegarde automatique de la base, une fois par jour, sans dépendance externe.

Sauvegarde logique (JSON gzip) de toutes les tables applicatives, conservée dans
la table `backups`. Les 7 dernières sont gardées. Téléchargeable depuis /admin.
"""
from __future__ import annotations

import gzip
import json
import os
import time
from typing import Any

import db
import extras

TABLES = (
    "sessions", "messages", "quote_requests", "knowledge_entries", "leads",
    "unanswered", "uploads", "alerts", "orders", "products", "followups",
    "appointments",
)
GARDER = 7
INTERVALLE = 86400


def _dump() -> bytes:
    contenu: dict[str, Any] = {"date": time.time(), "backend": db.backend(), "tables": {}}
    for table in TABLES:
        try:
            lignes = db.run(f"SELECT * FROM {table}")
        except Exception:
            continue
        propre = []
        for ligne in lignes:
            item = {}
            for cle, valeur in ligne.items():
                if isinstance(valeur, (bytes, bytearray, memoryview)):
                    item[cle] = f"<{len(bytes(valeur))} octets>"
                elif isinstance(valeur, (int, float, str, bool)) or valeur is None:
                    item[cle] = valeur
                else:
                    item[cle] = str(valeur)
            propre.append(item)
        contenu["tables"][table] = propre
    return gzip.compress(json.dumps(contenu, ensure_ascii=False).encode("utf-8"))


def run(force: bool = False) -> dict[str, Any]:
    """Crée une sauvegarde si la dernière a plus de 24 h (ou si force)."""
    extras.init()
    dernier = extras.rows("SELECT created_at FROM backups ORDER BY id DESC LIMIT 1")
    if dernier and not force and time.time() - float(dernier[0]["created_at"]) < INTERVALLE:
        return {"ok": True, "skipped": True}

    data = _dump()
    db.run(
        "INSERT INTO backups (created_at, size, data) VALUES (?, ?, ?)",
        (time.time(), len(data), data),
    )
    # On ne garde que les 7 dernières.
    vieilles = extras.rows("SELECT id FROM backups ORDER BY id DESC OFFSET ?", (GARDER,))
    for row in vieilles:
        try:
            db.run("DELETE FROM backups WHERE id = ?", (row["id"],))
        except Exception:
            pass
    return {"ok": True, "size": len(data), "kept": GARDER}


def liste(limit: int = 10) -> list[dict[str, Any]]:
    extras.init()
    return extras.rows(
        "SELECT id, created_at, size FROM backups ORDER BY id DESC LIMIT ?", (limit,)
    )


def dernier() -> dict[str, Any] | None:
    extras.init()
    rows = extras.rows("SELECT id, created_at, size, data FROM backups ORDER BY id DESC LIMIT 1")
    return rows[0] if rows else None
