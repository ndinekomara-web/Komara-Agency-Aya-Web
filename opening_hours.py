"""Horaires : ouvert 08h-23h. Fermé, le bot note mais ne prend aucune commande."""
from __future__ import annotations

import datetime as dt
import os
from zoneinfo import ZoneInfo

OUVERTURE = int(os.getenv("OPEN_HOUR", "8"))
FERMETURE = int(os.getenv("CLOSE_HOUR", "23"))
TZ = os.getenv("APP_TZ", "Africa/Conakry")


def _tz() -> ZoneInfo:
    try:
        return ZoneInfo(TZ)
    except Exception:
        return ZoneInfo("UTC")


def now() -> dt.datetime:
    return dt.datetime.now(_tz())


def is_open(moment: dt.datetime | None = None) -> bool:
    """Vrai entre 08h00 et 22h59, tous les jours."""
    m = moment or now()
    return OUVERTURE <= m.hour < FERMETURE


def prochaine_ouverture(moment: dt.datetime | None = None) -> dt.datetime:
    m = moment or now()
    if is_open(m):
        return m
    debut = m.replace(hour=OUVERTURE, minute=0, second=0, microsecond=0)
    if m.hour >= FERMETURE:
        debut += dt.timedelta(days=1)
    return debut


def libelle_ouverture() -> str:
    return f"{OUVERTURE}h00"


def closed_reply(lang: str = "fr", service: str = "") -> str:
    """Réponse hors horaires : on note, on ne prend pas de commande."""
    quand = "demain" if now().hour >= FERMETURE else "aujourd'hui"
    if lang == "en":
        return (
            f"We're closed right now. I've saved your request and Ndine answers you {quand} "
            f"from {OUVERTURE}:00. Nothing is lost."
        )
    if lang == "ar":
        return (
            f"نحن مغلقون الآن. سجّلت طلبك وسيتواصل معك ندين {quand} ابتداءً من الساعة {OUVERTURE}:00."
        )
    if lang == "es":
        return (
            f"Estamos cerrados ahora. He guardado tu solicitud y Ndine te responde {quand} "
            f"a partir de las {OUVERTURE}:00."
        )
    quoi = f" pour ton projet {service}" if service else ""
    return (
        f"On est fermé là, on rouvre à {libelle_ouverture()} 😊 "
        f"J'ai bien noté ta demande{quoi}, Ndine te répond dès l'ouverture. Rien n'est perdu."
    )
