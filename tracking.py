"""Suivi de commande côté client : référence + numéro, jamais de données d'autrui."""
from __future__ import annotations

from typing import Any

import catalogue

ETAPES = {
    "nouvelle": "Commande reçue ✅",
    "en_cours": "En cours de préparation 🎨",
    "prete": "Prête, livraison imminente 📦",
    "livree": "Livrée 🎉",
    "annulee": "Annulée",
}

ALIAS = {
    "new": "nouvelle", "pending": "nouvelle", "recue": "nouvelle", "reçue": "nouvelle",
    "progress": "en_cours", "en cours": "en_cours", "production": "en_cours",
    "ready": "prete", "prête": "prete", "done": "livree", "livre": "livree",
    "delivered": "livree", "cancelled": "annulee", "canceled": "annulee",
}


def _norm(statut: str) -> str:
    cle = (statut or "").strip().casefold()
    return ALIAS.get(cle, cle if cle in ETAPES else "nouvelle")


def chercher(reference: str = "", phone: str = "") -> list[dict[str, Any]]:
    """Retrouve les commandes d'un client par référence ou par numéro."""
    commandes = catalogue.orders(500)
    digits = "".join(c for c in (phone or "") if c.isdigit())
    ref = (reference or "").strip().lstrip("#").upper()
    trouvees = []
    for cmd in commandes:
        tel = "".join(c for c in str(cmd.get("phone", "")) if c.isdigit())
        par_ref = ref and (str(cmd.get("id")) == ref or f"CMD{cmd.get('id')}" == ref)
        par_tel = digits and tel and (tel == digits or tel.endswith(digits[-8:]))
        if par_ref or par_tel:
            trouvees.append(cmd)
    return trouvees


def rendre(cmd: dict[str, Any]) -> str:
    statut = _norm(str(cmd.get("status", "")))
    etapes = ["nouvelle", "en_cours", "prete", "livree"]
    if statut == "annulee":
        fil = "Commande annulée."
    else:
        fil = " → ".join(("●" if etapes.index(e) <= etapes.index(statut) else "○") + " " + ETAPES[e].split(" ")[0]
                         for e in etapes)
        fil = f"{fil}\n\n{ETAPES[statut]}"
    return (
        f"Commande #{cmd.get('id')}\n"
        f"{cmd.get('summary', '')}\n"
        f"Total : {cmd.get('total', '')}\n\n{fil}"
    )


def reponse(reference: str = "", phone: str = "") -> str:
    if not reference and not phone:
        return "Donne-moi ta référence de commande (exemple : 12) ou le numéro utilisé pour commander."
    trouvees = chercher(reference, phone)
    if not trouvees:
        return "Je ne trouve pas cette commande 🤔 Vérifie la référence, ou donne-moi le numéro utilisé."
    return "\n\n".join(rendre(c) for c in trouvees[:3])
