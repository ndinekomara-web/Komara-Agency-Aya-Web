"""Mode « devis seulement » : Aya ne vend rien, toute commande part vers Ndine.

Activable par variable : SALES_MODE=devis (défaut) ou SALES_MODE=direct.
Aucun paiement en ligne n'est proposé, quel que soit le mode.
"""
from __future__ import annotations

import os
import re
from typing import Any

import chat_store

_ACHAT = re.compile(
    r"\b(je\s+(veux\s+)?commande[rn]?|commander|j['’]achète|j['’]achete|acheter|"
    r"je\s+prends|je\s+valide|panier|ajoute[rz]?\s+au\s+panier|"
    r"je\s+paie|payer|paiement|acompte|r[ée]gler\s+maintenant|"
    r"c['’]est\s+bon\s+je\s+prends|on\s+y\s+va\s+je\s+paie)\b",
    re.IGNORECASE,
)


def mode() -> str:
    return (os.getenv("SALES_MODE", "devis") or "devis").strip().lower()


def ventes_directes() -> bool:
    return mode() == "direct"


def is_purchase(text: str) -> bool:
    return bool(_ACHAT.search(text or ""))


def redirect_reply(profile: dict[str, Any], lang: str = "fr") -> str:
    """Réponse unique : on ne vend pas, on passe la main à Ndine."""
    prenom = profile.get("name", "")
    service = profile.get("service", "")
    who = f" {prenom}" if prenom else ""
    quoi = f" pour ton projet {service}" if service else ""
    try:
        chat_store.add_alert(
            "vente",
            f"Commande à valider{quoi or ' (service non précisé)'}",
            f"{prenom or 'Client'} · {profile.get('phone') or 'numéro non donné'} · {service or '—'}",
        )
    except Exception:
        pass
    return (
        f"C'est noté{who} 🙌 Pour l'instant, c'est Ndine qui valide chaque commande lui-même, "
        "je ne prends aucun paiement ici. "
        "Laisse-moi ton numéro WhatsApp et il te confirme le devis, le délai et le moyen de paiement."
    )
