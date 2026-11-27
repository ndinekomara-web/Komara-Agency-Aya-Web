"""Tâches de fond : relances toutes les 10 minutes, sauvegarde une fois par jour.

Tout est protégé : une erreur ne casse jamais le site.
"""
from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger("aya.scheduler")

RELANCE_TOUTES = 600      # 10 minutes
SAUVEGARDE_TOUTES = 3600  # vérifié chaque heure, écrit une fois par jour


def actif() -> bool:
    return (os.getenv("SCHEDULER_ENABLED", "1") or "1").strip() != "0"


async def _boucle() -> None:
    import backup
    import followups

    dernier_backup = 0.0
    while True:
        try:
            if actif():
                envoyees = followups.run_once()
                if envoyees:
                    logger.info("relances envoyées : %s", envoyees)
                if asyncio.get_event_loop().time() - dernier_backup > SAUVEGARDE_TOUTES:
                    backup.run()
                    dernier_backup = asyncio.get_event_loop().time()
        except Exception:
            logger.exception("tâche de fond en erreur (ignorée)")
        await asyncio.sleep(RELANCE_TOUTES)


def demarrer() -> None:
    try:
        asyncio.get_event_loop().create_task(_boucle())
    except RuntimeError:
        pass
