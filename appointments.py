"""Prise de rendez-vous réelle : créneaux réels, confirmation, rappel.

Fuseau par défaut : Africa/Conakry (UTC+0). Modifiable via RDV_TZ_OFFSET.
"""
from __future__ import annotations

import datetime as dt
import os
from typing import Any

import chat_store
import extras

DUREE = 30  # minutes
HEURES = (9, 10, 11, 12, 14, 15, 16, 17)
JOURS = 10


def _offset() -> int:
    try:
        return int(os.getenv("RDV_TZ_OFFSET", "0"))
    except ValueError:
        return 0


def _tz() -> dt.timezone:
    return dt.timezone(dt.timedelta(hours=_offset()))


def _pris() -> set[str]:
    extras.init()
    return {
        str(r["slot_iso"])
        for r in extras.rows("SELECT slot_iso FROM appointments WHERE status != 'annule'")
    }


def slots(jours: int = JOURS) -> list[str]:
    """Les prochains créneaux libres, du plus proche au plus loin."""
    extras.init()
    pris = _pris()
    maintenant = dt.datetime.now(_tz())
    libres: list[str] = []
    jour = maintenant.date()
    for _ in range(jours * 2):
        if len(libres) >= jours * 3:
            break
        if jour.weekday() < 6:  # dimanche fermé
            for heure in HEURES:
                debut = dt.datetime(jour.year, jour.month, jour.day, heure, 0, tzinfo=_tz())
                if debut <= maintenant + dt.timedelta(hours=2):
                    continue
                cle = debut.isoformat()
                if cle not in pris:
                    libres.append(cle)
        jour += dt.timedelta(days=1)
    return libres[:12]


def proposer(profile: dict[str, Any]) -> str:
    """Trois créneaux proposés au client, numérotés."""
    dispo = slots()[:3]
    if not dispo:
        return "Je n'ai plus de créneau libre cette semaine. Laisse-moi ton numéro et Ndine t'appelle."
    profile["rdv_slots"] = dispo
    lignes = "\n".join(f"{i + 1}. {lisible(s)}" for i, s in enumerate(dispo))
    return f"Je te propose ces créneaux 👇\n\n{lignes}\n\nRéponds 1, 2 ou 3, ou donne-moi un autre moment."


def lisible(iso: str) -> str:
    try:
        d = dt.datetime.fromisoformat(iso)
    except ValueError:
        return iso
    jours = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
            "septembre", "octobre", "novembre", "décembre"]
    return f"{jours[d.weekday()]} {d.day} {mois[d.month - 1]} à {d.hour:02d}h{d.minute:02d}"


def reserver(session_id: str, slot_iso: str, profile: dict[str, Any]) -> dict[str, Any]:
    """Enregistre le rendez-vous et prévient Ndine."""
    extras.init()
    nom = profile.get("name", "")
    tel = profile.get("phone", "")
    service = profile.get("service", "")
    extras.db.run(
        "INSERT INTO appointments (session_id, name, phone, service, slot_iso, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (session_id, nom, tel, service, slot_iso, "confirme", extras.now()),
    )
    rdv_id = extras.last_id("appointments")
    chat_store.add_alert(
        "rdv",
        f"Rendez-vous confirmé : {lisible(slot_iso)}",
        f"{nom or 'Client'} · {tel or 'sans numéro'} · {service or '—'}",
    )
    profile.pop("rdv_slots", None)
    return {"id": rdv_id, "slot": slot_iso, "human": lisible(slot_iso)}


def choisir(profile: dict[str, Any], texte: str) -> str | None:
    """« 1 », « 2 », « 3 » -> le créneau correspondant."""
    dispo = profile.get("rdv_slots") or []
    if not dispo:
        return None
    chiffre = texte.strip().strip(".!")[:1]
    if chiffre in "123" and len(texte.strip()) <= 3:
        return dispo[int(chiffre) - 1]
    return None


def liste(limit: int = 50) -> list[dict[str, Any]]:
    extras.init()
    return extras.rows(
        "SELECT id, session_id, name, phone, service, slot_iso, status, created_at "
        "FROM appointments ORDER BY slot_iso ASC LIMIT ?",
        (limit,),
    )


def changer_statut(rdv_id: int, statut: str) -> bool:
    extras.init()
    try:
        extras.db.run("UPDATE appointments SET status = ? WHERE id = ?", (statut, rdv_id))
        return True
    except Exception:
        return False
