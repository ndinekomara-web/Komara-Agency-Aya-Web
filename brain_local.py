"""Cerveau local : compose une réponse sans aucune API externe.

Principe : aucune invention. Le cerveau assemble uniquement des faits officiels
(services, prix, délais) avec la demande du client, et varie la formulation
pour ne jamais répéter la même phrase deux fois.
"""
from __future__ import annotations

import random
import re

import aya_seed

SERVICES = {
    "logo": ("un logo", aya_seed.PRICES["LOGO"], "en 24h"),
    "pack": ("un pack identité visuelle", aya_seed.PRICES["PACK_PREMIUM"], "en 3 à 5 jours"),
    "affiche": ("une affiche", aya_seed.PRICES["AFFICHE"], "en 24 à 48h"),
    "site": ("un site vitrine", aya_seed.PRICES["SITE"], "en 7 jours"),
    "bot": ("un bot WhatsApp vendeur", aya_seed.PRICES.get("BOT_WHATSAPP", "100 €"), "en 5 à 7 jours"),
    "telegram": ("un bot Telegram", "50 €", "en 2 à 3 jours"),
    "retouche": ("une retouche photo", aya_seed.PRICES["RETOUCHE"], "en 24h"),
}

OUVERTURES = (
    "Voilà ce que je peux te proposer :",
    "Pour ton projet, je vois deux choses :",
    "Bonne nouvelle, c'est dans nos cordes :",
)

LIAISONS = (
    "Concrètement,",
    "En clair,",
    "Pour faire simple,")


def _nettoyer(texte: str) -> str:
    return re.sub(r"\s+", " ", (texte or "").strip()).strip(" .!?")


def service_demande(texte: str) -> str:
    """Quel service le client demande, d'après ses mots."""
    t = (texte or "").casefold()
    if any(w in t for w in ("logo", "identité", "identite")):
        return "logo" if "pack" not in t else "pack"
    if any(w in t for w in ("affiche", "flyer", "poster")):
        return "affiche"
    if any(w in t for w in ("site", "web", "vitrine")):
        return "site"
    if "telegram" in t:
        return "telegram"
    if any(w in t for w in ("bot", "chatbot", "agent")):
        return "bot"
    if any(w in t for w in ("retouche", "photo")):
        return "retouche"
    return ""


def composer(demande: str, secteur: str = "", name: str = "") -> str:
    """Assemble une réponse personnalisée, sans API, à partir des faits officiels."""
    cle = service_demande(demande)
    qui = f" {name}" if name else ""
    if not cle:
        return (
            f"D'accord{qui} 😊 Dis-moi juste ce que tu veux lancer : un logo, une affiche, "
            "un site ou un bot. Je te donne le prix exact et le délai."
        )
    libelle, prix, delai = SERVICES[cle]
    contexte = f" pour {_nettoyer(secteur)}" if secteur else ""
    return (
        f"{random.choice(OUVERTURES)} {libelle}{contexte}, c'est {prix}, livré {delai}. "
        f"{random.choice(LIAISONS)} tu envoies ton contenu, on te prépare une première version, "
        "et on ajuste jusqu'à ce que ça te plaise. Je te prépare le devis ?"
    )


def resume_client(profil: dict) -> str:
    """Résumé en trois lignes pour Ndine, à partir de ce que le client a dit."""
    morceaux = []
    if profil.get("name"):
        morceaux.append(f"Client : {profil['name']}")
    if profil.get("service"):
        morceaux.append(f"Projet : {profil['service']}")
    if profil.get("sector"):
        morceaux.append(f"Activité : {profil['sector']}")
    if profil.get("usage"):
        morceaux.append(f"Besoin : {profil['usage']}")
    if profil.get("phone"):
        morceaux.append(f"Contact : {profil['phone']}")
    return " · ".join(morceaux) if morceaux else "Client sans information encore."
