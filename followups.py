"""Relance automatique des leads : J+1 puis J+3, jamais plus.

Aucune dépendance externe. La relance est écrite dans la conversation du client
(il la voit en revenant) et remonte dans /admin pour Ndine.
"""
from __future__ import annotations

import time
from typing import Any

import chat_store
import extras

JOUR = 86400
PLAN = ((1, "J+1"), (3, "J+3"))


def plan(lead_id: int, session_id: str, phone: str, service: str = "") -> int:
    """Programme les relances d'un lead fraîchement capté."""
    extras.init()
    created = 0
    for stage, label in PLAN:
        existe = extras.rows(
            "SELECT id FROM followups WHERE phone = ? AND stage = ? LIMIT 1", (phone, stage)
        )
        if existe:
            continue
        texte = build_message(service, label)
        try:
            extras.db.run(
                "INSERT INTO followups (lead_id, session_id, phone, stage, due_at, sent_at, message) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (lead_id, session_id, phone, stage, extras.now() + stage * JOUR, None, texte),
            )
            created += 1
        except Exception:
            pass
    return created


def build_message(service: str, label: str) -> str:
    quoi = f" ton projet {service}" if service else " ton projet"
    if label == "J+1":
        return (
            f"Salut 😊 Je repense à{quoi}. Tu veux que je te prépare le devis "
            "aujourd'hui ? Réponds-moi ici, je m'en occupe."
        )
    return (
        f"Je te relance une dernière fois{quoi} 🙌 Si le moment n'est pas le bon, "
        "dis-le-moi simplement et je te laisse tranquille."
    )


def due(limit: int = 20) -> list[dict[str, Any]]:
    extras.init()
    return extras.rows(
        "SELECT id, lead_id, session_id, phone, stage, due_at, message FROM followups "
        "WHERE sent_at IS NULL AND due_at <= ? ORDER BY due_at ASC LIMIT ?",
        (extras.now(), limit),
    )


def run_once(limit: int = 20) -> int:
    """Envoie les relances dues. Renvoie le nombre envoyé."""
    sent = 0
    for row in due(limit):
        try:
            chat_store.add_message(str(row["session_id"]), "assistant", row["message"])
            extras.db.run("UPDATE followups SET sent_at = ? WHERE id = ?", (time.time(), row["id"]))
            chat_store.add_alert(
                "relance",
                f"Relance J+{row['stage']} envoyée",
                f"{row['phone']} · {row['message'][:120]}",
            )
            sent += 1
        except Exception:
            continue
    return sent


def pending(phone: str) -> list[dict[str, Any]]:
    extras.init()
    return extras.rows(
        "SELECT id, stage, due_at, message FROM followups WHERE phone = ? AND sent_at IS NULL", (phone,)
    )
