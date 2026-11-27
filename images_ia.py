"""Génération d'images gratuite, sans clé API : Pollinations.

Aucune inscription, aucune carte bancaire, aucun jeton. Si le service est
indisponible, on renvoie None et Aya continue normalement : jamais de blocage.
"""
from __future__ import annotations

import os
import urllib.parse
import urllib.request

import chat_store

ACTIF = os.getenv("IMAGES_IA", "1") not in ("0", "false", "False")
MODELE = os.getenv("IMAGES_MODELE", "flux")
BASE = os.getenv("IMAGES_BASE", "https://image.pollinations.ai/prompt/")
DELAI = float(os.getenv("IMAGES_DELAI", "45"))

STYLE = (
    "professional graphic design, clean composition, high contrast, "
    "modern typography space, no watermark, no text errors"
)


def disponible() -> bool:
    return ACTIF


def construire_prompt(demande: str, secteur: str = "", service: str = "logo") -> str:
    """Traduit la demande du client en consigne d'image."""
    base = (demande or "").strip()
    if service == "affiche":
        return f"promotional poster design for {base}, bold layout, {STYLE}"
    if service == "visuel":
        return f"social media visual for {base}, modern flat design, {STYLE}"
    return f"minimalist logo for {base}, vector style, centered, white background, {STYLE}"


def generer(demande: str, secteur: str = "", service: str = "logo") -> tuple[int, str] | None:
    """Génère l'image et l'enregistre comme fichier de la session."""
    if not ACTIF or not (demande or "").strip():
        return None
    prompt = construire_prompt(demande, secteur, service)
    largeur, hauteur = (1024, 1024) if service == "logo" else (1024, 1280)
    url = (
        BASE
        + urllib.parse.quote(prompt)
        + f"?width={largeur}&height={hauteur}&model={MODELE}&nologo=true&seed={abs(hash(demande)) % 99999}"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "KomaraAgency/1.0"})
        with urllib.request.urlopen(req, timeout=DELAI) as rep:
            data = rep.read()
        if len(data) < 5000:
            return None
        nom = f"{service}-{abs(hash(prompt)) % 999999}.jpg"
        upload_id = chat_store.add_upload("ia", nom, "image/jpeg", data)
        return upload_id, nom
    except Exception:
        return None
