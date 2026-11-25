"""Filet de sécurité IA — pour les questions qu'aucune fiche ne couvre.

Principe : Aya reste la même. Quand AUCUNE fiche ne répond, on demande à un
modèle (via n8n, qui garde la clé API hors du dépôt) une réponse courte et
conforme, on la contrôle, puis on la sert au client. La question est
enregistrée par n8n dans une feuille « à ajouter au seed » pour que Ndine
l'ajoute ensuite via /admin.

Rien n'est inventé : prix hors grille, promesse de lien, aveu d'IA ou réponse
trop longue = on jette et on garde le message générique d'avant.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

# Prix officiels : toute autre somme est refusée.
PRIX_AUTORISES = {10, 30, 50, 100, 150, 250}
MAX_LONGUEUR = 600

_INTERDITS = re.compile(
    r"(je suis (?:une? )?(?:ia|robot|intelligence artificielle|programme|machine|chatbot)|"
    r"en tant qu'?(?:ia|assistant virtuel)|je\s+t['’]envoie le lien|"
    r"offre (?:spéciale|limitée)|dernière chance|100\s*%\s*garanti|résultat garanti)",
    re.IGNORECASE,
)
_PRIX_RX = re.compile(r"(\d{1,4})\s*(?:€|euros?)", re.IGNORECASE)


def disponible() -> bool:
    """Le filet n'est actif que si l'URL n8n est configurée."""
    return bool(os.getenv("N8N_FALLBACK_URL", "").strip())


def _url() -> str:
    return os.getenv("N8N_FALLBACK_URL", "").strip()


def _delai() -> float:
    try:
        return float(os.getenv("N8N_FALLBACK_TIMEOUT", "8"))
    except ValueError:
        return 8.0


def est_une_vraie_question(texte: str) -> bool:
    """On ne sollicite pas le modèle pour « ok », un numéro ou un salut."""
    t = (texte or "").strip()
    if len(t.split()) < 3:
        return False
    if re.fullmatch(r"[\d\s+.\-()]{6,}", t):
        return False
    return "?" in t or bool(
        re.match(
            r"^(comment|pourquoi|quand|quel|quelle|quels|quelles|est ce que|est-ce que|"
            r"peut on|peut-on|puis je|puis-je|combien|où|ou |qui |que |quoi )",
            t.casefold(),
        )
    )


def _contexte(profile: dict[str, Any]) -> dict[str, Any]:
    """Ce qu'Aya sait déjà, pour une réponse cohérente (jamais de données brutes)."""
    return {
        "prenom": profile.get("name", ""),
        "service": profile.get("service", ""),
        "secteur": profile.get("sector", ""),
        "etape": profile.get("stage", ""),
    }


def demander(question: str, lang: str, profile: dict[str, Any]) -> str | None:
    """Appelle n8n et renvoie une réponse sûre, ou None."""
    if not disponible():
        return None

    charge = json.dumps(
        {
            "question": question[:500],
            "langue": lang,
            "client": _contexte(profile),
            "source": "aya-web",
        }
    ).encode("utf-8")

    requete = urllib.request.Request(
        _url(),
        data=charge,
        headers={"Content-Type": "application/json", "User-Agent": "Aya/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(requete, timeout=_delai()) as reponse:
            data = json.loads(reponse.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None

    texte = (data.get("answer") or data.get("reponse") or "").strip()
    return _verifier(texte)


def _verifier(texte: str) -> str | None:
    """Contrôle de conformité : on préfère aucune réponse à une réponse risquée."""
    if not texte or len(texte) > MAX_LONGUEUR:
        return None
    if _INTERDITS.search(texte):
        return None
    for montant in _PRIX_RX.findall(texte):
        if int(montant) not in PRIX_AUTORISES:
            return None
    if texte.count("?") > 1:
        # Une seule question maximum, comme partout ailleurs chez Aya.
        phrases = re.split(r"(?<=[.!?])\s+", texte)
        garde = [p for p in phrases if "?" not in p] + [next((p for p in phrases if "?" in p), "")]
        texte = " ".join(p for p in garde if p).strip()
    return texte or None
