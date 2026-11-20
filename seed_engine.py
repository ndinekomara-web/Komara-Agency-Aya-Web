"""
Réponses du seed d'Aya (aya_seed.py) : correspondance sur les questions.

Le seed est une liste de fiches ([questions...], réponse). On cherche la
fiche dont une question ressemble le plus au message du client :

1. correspondance exacte (après normalisation) : score 1.0 ;
2. la question de la fiche est contenue dans le message, ou l'inverse ;
3. recouvrement de mots significatifs.

Aucun modèle, aucune API : la réponse est exactement celle écrite dans le seed.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

import aya_seed

# Mots sans valeur pour distinguer deux questions.
_STOP = {
    "le", "la", "les", "un", "une", "des", "de", "du", "et", "ou", "a", "au", "aux",
    "en", "pour", "par", "avec", "sur", "dans", "que", "qui", "quoi", "est", "sont",
    "ce", "cette", "ces", "je", "tu", "il", "elle", "nous", "vous", "ils", "mon",
    "ma", "mes", "ton", "ta", "tes", "votre", "vos", "me", "te", "se", "moi", "toi",
    "the", "and", "for", "with", "you", "your", "is", "are", "do", "to", "of", "it",
    "svp", "stp", "merci", "s", "l", "d", "j", "c", "qu", "n", "m", "t",
}

MIN_SCORE = 0.62

# Synonymes : plusieurs façons de dire la même chose renvoient à la même fiche.
# Appliqués au message avant comparaison, sans toucher au seed lui-même.
_SYNONYMS = {
    "realisations": "portfolio", "realisation": "portfolio", "exemples": "portfolio",
    "projets": "portfolio", "travaux": "portfolio", "galerie": "portfolio",
    "tarifs": "prix", "tarif": "prix", "cout": "prix", "couts": "prix",
    "combien": "prix", "coute": "prix", "coutent": "prix",
    "delais": "delai", "livraison": "delai", "duree": "delai",
    "offres": "services", "prestations": "services", "propose": "services",
    "payer": "paiement", "reglement": "paiement",
}

_index: dict[str, list[dict[str, Any]]] | None = None


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFD", (text or "").casefold())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^a-z0-9\u0600-\u06ff]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# Intentions : formulations libres qui pointent vers une fiche existante du seed
# (on cite la question de la fiche cible, jamais une réponse écrite ici).
_INTENTS: list[tuple[re.Pattern, str]] = [
    # Question générale sur les prix (sans produit précis) -> la liste des tarifs.
    (re.compile(r"^(quels? (sont|est) )?(vos |votre |les |le )?(tarifs?|prix|couts?)( de vos services| de vos prestations)?$"),
     "prix"),
    (re.compile(r"^(c est |c'est )?combien (ca|ça) (coute|coûte)$"), "combien ça coûte"),
    (re.compile(r"\b(je veux|j ai besoin d|il me faut|fais moi|cree moi|crée moi|fabrique moi)\b.*\blogo\b"),
     "crée moi un logo"),
    (re.compile(r"\b(je veux|j ai besoin d|il me faut|fais moi|cree moi|crée moi)\b.*\b(affiche|visuel|flyer)\b"),
     "prix d'une affiche"),
    (re.compile(r"\b(je veux|j ai besoin d|il me faut|fais moi|cree moi|crée moi)\b.*\b(site|site web)\b"),
     "je veux créer un site web"),
]


def _words(text: str) -> set[str]:
    return {w for w in _norm(text).split() if w not in _STOP and len(w) > 1}


def _canon(text: str) -> str:
    """Message normalisé avec synonymes unifiés (pour le repli de recherche)."""
    return " ".join(_SYNONYMS.get(w, w) for w in _norm(text).split())


def _lang_of(text: str) -> str:
    if re.search(r"[\u0600-\u06ff]", text):
        return "ar"
    return "fr"


def _build() -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {"fr": [], "en": [], "es": [], "ar": []}

    def add(lang: str, questions: list[str], answer: str) -> None:
        for question in questions:
            norm = _norm(question)
            if not norm:
                continue
            index.setdefault(lang, []).append(
                {
                    "norm": norm,
                    "words": _words(question),
                    "question": question,
                    "answer": answer,
                }
            )

    for questions, answer in aya_seed.SEED_QR:
        add("fr", questions, answer)
    for lang, entries in getattr(aya_seed, "SEED_QR_ML", {}).items():
        for questions, answer in entries:
            add(lang, questions, answer)
    return index


def _get_index() -> dict[str, list[dict[str, Any]]]:
    global _index
    if _index is None:
        _index = _build()
    return _index


def reload() -> None:
    global _index
    _index = None


def stats() -> dict[str, int]:
    idx = _get_index()
    return {lang: len(items) for lang, items in idx.items() if items}


def _score(message_norm: str, message_words: set[str], entry: dict[str, Any]) -> float:
    question = entry["norm"]
    if message_norm == question:
        return 1.0

    q_words = entry["words"]
    # Question courte (« prix », « délai », « merci ») : seulement en exact ou
    # si le message est lui-même court, sinon elle volerait toutes les phrases.
    if len(q_words) <= 1:
        if message_words == q_words and q_words:
            return 0.98
        if question and re.search(rf"(^| ){re.escape(question)}( |$)", message_norm) and len(message_words) <= 3:
            return 0.9
        return 0.0

    # Question complète présente dans le message (« dis moi c'est quoi un bot svp »).
    if re.search(rf"(^| ){re.escape(question)}( |$)", message_norm):
        return 0.95

    if not message_words or not q_words:
        return 0.0

    common = message_words & q_words
    if not common:
        return 0.0
    recall = len(common) / len(q_words)        # la fiche est-elle couverte ?
    precision = len(common) / len(message_words)  # le message est-il expliqué ?
    if recall < 0.6:
        return 0.0
    return min(0.94, 0.55 * recall + 0.45 * precision)


def _local_search(message: str) -> str | None:
    """Second moteur : celui du bot Telegram (fautes, SMS, paraphrases)."""
    try:
        import local_search
    except Exception:
        return None
    kb = [
        {"questions": list(qs), "answer": ans}
        for qs, ans in (list(aya_seed.SEED_QR) + [e for items in getattr(aya_seed, "SEED_QR_ML", {}).values() for e in items])
    ]
    try:
        answer = local_search.trouver_meilleure_reponse(message, kb, [])
    except Exception:
        return None
    if not answer:
        return None
    # Le service doit exister chez Komara Agency (règle du bot Telegram).
    try:
        import service_guard
        if not service_guard.is_compatible(message, message, answer):
            return None
    except Exception:
        pass
    return answer


def find_answer(message: str, lang: str | None = None) -> dict[str, Any] | None:
    """Meilleure fiche pour ce message, ou None."""
    message_norm = _norm(message)
    if not message_norm:
        return None
    message_words = _words(message)
    idx = _get_index()

    languages = [lang] if lang in idx and idx[lang] else []
    languages += [code for code in ("fr", "en", "es", "ar") if code not in languages]

    best: dict[str, Any] | None = None
    best_score = 0.0
    # Intention explicite : on redirige vers la question de la fiche cible.
    norm_full = _norm(message)
    for pattern, target in _INTENTS:
        if pattern.search(norm_full):
            hit = _exact(idx, target)
            if hit:
                return hit

    # Message brut d'abord ; si rien ne correspond, on retente avec les synonymes.
    for attempt in (message, _canon(message)):
        message_norm = _norm(attempt)
        message_words = _words(attempt)
        best, best_score = _search(idx, languages, lang, message_norm, message_words)
        if best and best_score >= MIN_SCORE:
            return best

    # 2e chance : moteur tolérant (celui du bot Telegram)
    answer = _local_search(message)
    if answer:
        return {"question": message, "answer": answer, "lang": lang or "fr", "score": 0.5, "engine": "local_search"}
    return None


def _exact(idx, question: str) -> dict[str, Any] | None:
    target = _norm(question)
    for code, items in idx.items():
        for entry in items:
            if entry["norm"] == target:
                return {**entry, "lang": code, "score": 1.0}
    return None


def _search(idx, languages, lang, message_norm, message_words):
    best = None
    best_score = 0.0
    for code in languages:
        for entry in idx.get(code, []):
            score = _score(message_norm, message_words, entry)
            # Priorité à la langue détectée en cas d'égalité.
            if code == lang:
                score += 0.01
            if score > best_score:
                best_score = score
                best = {**entry, "lang": code, "score": round(score, 3)}
    return best, best_score


def find_admin_answer(message: str, lang: str | None = None) -> str | None:
    """Réponse issue d'une connaissance ajoutée par l'équipe via /admin.

    Elle prime sur le seed : si Komara Agency a écrit une information, c'est
    elle qui fait foi (livraison, horaires, conditions...).
    """
    try:
        import chat_store
        import local_search
    except Exception:
        return None
    rows = chat_store.knowledge_entries(lang) if lang else chat_store.knowledge_entries()
    if not rows:
        return None
    kb = [{"questions": [row["title"]], "answer": row["content"]} for row in rows]
    try:
        return local_search.trouver_meilleure_reponse(message, kb, [])
    except Exception:
        return None
