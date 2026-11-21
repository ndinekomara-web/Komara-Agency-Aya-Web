"""
Mémoire client d'Aya : ce qu'elle sait de la personne en face d'elle.

Une fiche par client (identifiée par la session du navigateur), conservée en
base : prénom, projet, service visé, secteur, budget, téléphone, étape du
tunnel de vente. Elle sert à trois choses :

1. reconnaître un client qui revient (« content de te revoir, Mamadou ») ;
2. ne jamais reposer une question dont on a déjà la réponse ;
3. ne jamais répéter une réponse déjà donnée dans la même conversation.

Tout est local et déterministe : aucune IA, aucune invention. On n'enregistre
que ce que le client a réellement écrit.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

import db

# Étapes du tunnel, de la découverte au closing.
STAGES = ("decouverte", "besoin", "offre", "devis", "closing", "client")

_SERVICES = {
    "chatbot": ("chatbot", "chat bot", "bot", "bots", "robot", "agent ia", "assistant virtuel", "automatisation"),
    "site": ("site", "site web", "site vitrine", "site e-commerce", "site internet", "boutique en ligne", "e-boutique"),
    "logo": ("logo", "identité visuelle", "identite visuelle", "charte graphique"),
    "affiche": ("affiche", "visuel", "flyer", "poster", "bannière", "banniere"),
    "retouche": ("retouche", "retoucher"),
    "moderation": ("modération", "moderation", "gérer ma page", "gerer ma page", "community manager"),
    "video": ("vidéo", "video", "reels", "reel", "pub vidéo"),
}
def _has_word(text: str, words: tuple[str, ...]) -> bool:
    """Vrai si un mot/expression apparaît comme MOT ENTIER (« robotique » ≠ « robot »)."""
    return any(
        re.search(rf"(?<![\wÀ-ÿ]){re.escape(w)}(?![\wÀ-ÿ])", text) for w in words
    )


_CHANNELS = {
    "whatsapp": ("whatsapp", "whats app"),
    "telegram": ("telegram",),
    "facebook": ("facebook", "messenger"),
    "instagram": ("instagram",),
    "site": ("sur mon site", "sur le site"),
}
_SECTORS = {
    "boutique": ("boutique", "magasin", "vêtement", "vetement", "friperie", "e-commerce"),
    "restaurant": ("restaurant", "resto", "traiteur", "fast food", "cuisine"),
    "immobilier": ("immobilier", "agence immobilière", "location", "terrain"),
    "beauté": ("salon", "coiffure", "beauté", "beaute", "cosmétique", "cosmetique", "maquillage"),
    "école": ("école", "ecole", "formation", "cours"),
    "santé": ("clinique", "pharmacie", "cabinet", "santé", "sante"),
    "transport": ("transport", "taxi", "livraison", "logistique"),
}
# Présentation explicite : seule source fiable d'un prénom.
_PHONE_RX = re.compile(r"(?:\+?\d[\d .-]{7,}\d)")

_NAME_RX = re.compile(
    r"\b(?:je m'appelle|je me nomme|moi c'est|mon nom est|mon prénom est|je suis)\s+"
    r"([A-ZÀ-Ÿa-zà-ÿ][\wÀ-ÿ'-]{1,20})",
    re.IGNORECASE,
)
_BUDGET_RX = re.compile(r"(\d[\d\s.,]{1,8})\s*(€|eur|euros?|gnf|fg|francs?|\$|usd|dollars?)", re.IGNORECASE)
# Mots qui ressemblent à un prénom mais n'en sont pas.
_NOT_NAMES = {
    "pour", "un", "une", "le", "la", "les", "ok", "oui", "non", "bon", "bien", "ça", "ca",
    "quoi", "pas", "mon", "ma", "mes", "ton", "ta", "tes", "ici", "là", "la", "merci",
    "intéressé", "interesse", "intéressée", "pressé", "presse", "prêt", "pret", "sûr", "sur",
    "d'accord", "daccord", "bonjour", "salut", "aya", "komara", "agence", "client", "cliente",
    "trop", "très", "tres", "déjà", "deja", "vraiment", "content", "contente", "heureux",
    "désolé", "desole", "fatigué", "fatigue", "occupé", "occupe", "malade", "perdu", "perdue",
    "commerçant", "commercant", "entrepreneur", "étudiant", "etudiant", "debutant", "débutant",
    "nouveau", "nouvelle", "guinéen", "guineen", "guinéenne", "interessé", "à", "a", "en", "de",
    "du", "des", "au", "aux", "dans", "sur", "chez", "avec", "sans", "comme", "juste", "aussi",
}


# --------------------------------------------------------------- stockage
def _ensure() -> None:
    serial = "BIGSERIAL PRIMARY KEY" if db.backend() == "postgres" else "INTEGER PRIMARY KEY AUTOINCREMENT"
    real = "DOUBLE PRECISION" if db.backend() == "postgres" else "REAL"
    db.run_many(
        [
            f"""
            CREATE TABLE IF NOT EXISTS client_profiles (
                session_id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                updated_at {real} NOT NULL
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS client_facts (
                id {serial},
                session_id TEXT NOT NULL,
                fact TEXT NOT NULL,
                created_at {real} NOT NULL
            )
            """,
        ]
    )


_ready = False


def _init() -> None:
    global _ready
    if not _ready:
        _ensure()
        _ready = True


def reset_for_tests() -> None:
    global _ready
    _ready = False


def _blank() -> dict[str, Any]:
    return {
        "name": "",
        "service": "",
        "channel": "",
        "sector": "",
        "budget": "",
        "phone": "",
        "stage": "decouverte",
        "visits": 1,
        "first_seen": time.time(),
        "last_seen": time.time(),
        "said": [],          # clés des fiches déjà données (jamais répétées)
        "last_topic": "",    # dernière fiche donnée
        "last_question": "", # dernière question posée par Aya, en attente de réponse
        "turns": 0,
        "objections": 0,
    }


def get(session_id: str) -> dict[str, Any]:
    _init()
    rows = db.run("SELECT data FROM client_profiles WHERE session_id = ?", (session_id,))
    if not rows:
        return _blank()
    try:
        data = json.loads(rows[0]["data"])
    except (ValueError, TypeError):
        return _blank()
    merged = _blank()
    merged.update(data)
    return merged


def save(session_id: str, profile: dict[str, Any]) -> None:
    _init()
    profile["last_seen"] = time.time()
    db.run(
        "INSERT INTO client_profiles (session_id, data, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT (session_id) DO UPDATE SET data = EXCLUDED.data, updated_at = EXCLUDED.updated_at",
        (session_id, json.dumps(profile, ensure_ascii=False), time.time()),
    )


def forget(session_id: str) -> None:
    _init()
    db.run("DELETE FROM client_profiles WHERE session_id = ?", (session_id,))
    db.run("DELETE FROM client_facts WHERE session_id = ?", (session_id,))


def find_by_phone(phone: str, exclude_session: str = "") -> tuple[str, dict[str, Any]] | None:
    """Retrouve un client par le numéro qu'il a donné dans la conversation.

    C'est la conversation qui identifie le client, jamais l'IP : un client qui
    revient sur un autre téléphone ou après une réinstallation est reconnu
    parce qu'il a redonné son numéro.
    """
    digits = "".join(ch for ch in str(phone) if ch.isdigit())
    if len(digits) < 8:
        return None
    _init()
    rows = db.run("SELECT session_id, data FROM client_profiles") or []
    for row in rows:
        if row["session_id"] == exclude_session:
            continue
        try:
            data = json.loads(row["data"])
        except (ValueError, TypeError):
            continue
        known = "".join(ch for ch in str(data.get("phone", "")) if ch.isdigit())
        if known and known == digits:
            merged = _blank()
            merged.update(data)
            return row["session_id"], merged
    return None


def all_profiles(limit: int = 100) -> list[dict[str, Any]]:
    """Pour /admin : qui sont les clients, où en sont-ils."""
    _init()
    rows = db.run(
        "SELECT session_id, data, updated_at FROM client_profiles ORDER BY updated_at DESC LIMIT ?",
        (limit,),
    )
    out = []
    for row in rows:
        try:
            data = json.loads(row["data"])
        except (ValueError, TypeError):
            continue
        data["session_id"] = row["session_id"]
        out.append(data)
    return out


# ------------------------------------------------------------ apprentissage
def _norm(text: str) -> str:
    return text.casefold()


def learn(session_id: str, text: str, profile: dict[str, Any] | None = None) -> dict[str, Any]:
    """Retient ce que le client vient de dire. Ne devine jamais."""
    profile = profile if profile is not None else get(session_id)
    low = _norm(text)
    profile["turns"] = int(profile.get("turns", 0)) + 1

    # Prénom : uniquement si le client se présente explicitement.
    match = _NAME_RX.search(text)
    if match:
        candidate = match.group(1).strip("-' ")
        if candidate.casefold() not in _NOT_NAMES and len(candidate) >= 2:
            profile["name"] = candidate[:1].upper() + candidate[1:]

    # Service visé : celui cité le PLUS TARD l'emporte (« j'ai un bot et je veux
    # un logo » -> logo). Un nouveau service remplace l'ancien : le client peut
    # changer d'avis en cours de route.
    found = []
    for service, words in _SERVICES.items():
        spots = [
            m.start()
            for word in words
            if (m := re.search(rf"(?<![\wÀ-ÿ]){re.escape(word)}(?![\wÀ-ÿ])", low))
        ]
        if spots:
            found.append((max(spots), service))
    if found:
        new_service = max(found)[1]
        if new_service != profile.get("service"):
            profile["service"] = new_service
            profile["open_question"] = ""
            profile["last_question"] = ""

    for channel, words in _CHANNELS.items():
        if _has_word(low, words):
            profile["channel"] = channel
            break

    for sector, words in _SECTORS.items():
        if any(word in low for word in words):
            profile["sector"] = sector
            break

    budget = _BUDGET_RX.search(text)
    if budget:
        profile["budget"] = f"{budget.group(1).strip()} {budget.group(2).strip()}"

    if any(w in low for w in ("trop cher", "pas les moyens", "pas d'argent", "cher ")):
        profile["objections"] = int(profile.get("objections", 0)) + 1

    # Téléphone laissé dans la conversation : c'est ce qui identifie le client
    # (jamais l'IP). S'il revient sur un autre appareil, on le reconnaît.
    new_phone = _PHONE_RX.search(text)
    if new_phone:
        digits = "".join(ch for ch in new_phone.group(0) if ch.isdigit())
        if 8 <= len(digits) <= 15:
            previous = find_by_phone(digits, exclude_session=session_id)
            if previous:
                _, old = previous
                for field in ("name", "service", "sector", "channel", "stage", "budget"):
                    if not profile.get(field) and old.get(field):
                        profile[field] = old[field]
                profile["returning"] = True
            profile["phone"] = digits

    return profile


def set_stage(profile: dict[str, Any], stage: str) -> None:
    """L'étape ne recule jamais : un client en closing reste en closing."""
    if stage not in STAGES:
        return
    current = profile.get("stage", "decouverte")
    if STAGES.index(stage) > STAGES.index(current):
        profile["stage"] = stage


def mark_said(profile: dict[str, Any], key: str) -> None:
    said = profile.setdefault("said", [])
    if key not in said:
        said.append(key)
    profile["said"] = said[-40:]
    profile["last_topic"] = key


def already_said(profile: dict[str, Any], key: str) -> bool:
    return key in profile.get("said", [])


def returning(profile: dict[str, Any], gap_seconds: int = 1800) -> bool:
    """Vrai si le client revient après une vraie pause (pas un simple rechargement)."""
    return profile.get("turns", 0) > 0 and (time.time() - float(profile.get("last_seen", 0))) > gap_seconds


def summary(profile: dict[str, Any]) -> str:
    """Résumé lisible pour l'équipe (/admin) : ce que le client veut."""
    parts = []
    if profile.get("name"):
        parts.append(profile["name"])
    if profile.get("service"):
        parts.append(f"veut : {profile['service']}")
    if profile.get("channel"):
        parts.append(f"canal : {profile['channel']}")
    if profile.get("sector"):
        parts.append(f"secteur : {profile['sector']}")
    if profile.get("budget"):
        parts.append(f"budget : {profile['budget']}")
    parts.append(f"étape : {profile.get('stage', 'decouverte')}")
    return " · ".join(parts)
