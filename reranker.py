"""reranker — relecture des candidats, sans dépendance lourde.

Deux moteurs, choisis automatiquement :

1. **cross-encoder** (si `sentence_transformers` est installé) : le modèle
   ms-marco relit chaque paire (message, question de la fiche). Meilleur,
   mais ~2 Go de torch : impossible sur un petit conteneur Railway.

2. **lexical pondéré** (défaut, aucune dépendance) : c'est le moteur qui
   tourne réellement en production. Il relit chaque candidat avec
   - un recouvrement pondéré par l'IDF (les mots rares comptent plus),
   - une similarité de trigrammes (fautes, langage SMS, « kel » pour « quel »),
   - une expansion par synonymes (bot / robot / chatbot, prix / tarif / combien),
   - un bonus de phrase exacte.
   Score final dans [0, 1] : au-dessus du seuil on répond, en dessous on
   préfère « je n'ai pas compris » à une réponse devinée.

Env :
    RERANK_ENABLED     auto (défaut) | 1 | 0
    RERANK_THRESHOLD   seuil de pertinence (défaut : 0.32 lexical, 0.05 cross)
    RERANK_TOP_K       nombre de candidats relus (défaut 8)
    RERANK_ENGINE      auto (défaut) | lexical | cross
"""
from __future__ import annotations

import logging
import math
import os
import re
import time
import unicodedata

logger = logging.getLogger("komara.rerank")

_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"

_ENGINE_LEXICAL = "lexical"
_ENGINE_CROSS = "cross"

_engine: str | None = None
_model = None
_load_attempted = False


# ------------------------------------------------------------------ utilitaires
def _env(name: str, default: str) -> str:
    return (os.environ.get(name) or default).strip().lower()


def is_enabled() -> bool:
    flag = _env("RERANK_ENABLED", "auto")
    if flag in {"0", "false", "off", "no", "non"}:
        return False
    return True


def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


# Langage SMS et abréviations relevés dans les vraies conversations.
_SMS = {
    "slt": "salut", "slt": "salut", "bjr": "bonjour", "bsr": "bonsoir",
    "kel": "quel", "kelle": "quelle", "ke": "que", "ki": "qui", "koi": "quoi",
    "comb1": "combien", "cb": "combien", "pri": "prix", "pris": "prix",
    "jve": "je veux", "jveux": "je veux", "jsuis": "je suis", "jai": "j ai",
    "bcp": "beaucoup", "pcq": "parce que", "pk": "pourquoi", "stp": "s il te plait",
    "svp": "s il vous plait", "cv": "ca va", "mrc": "merci", "slt": "salut",
    "dmd": "demande", "info": "information", "infos": "informations",
}

_STOP = {
    "le", "la", "les", "un", "une", "des", "du", "de", "d", "l", "et", "ou",
    "a", "au", "aux", "en", "dans", "pour", "par", "sur", "avec", "sans",
    "je", "tu", "il", "elle", "on", "nous", "vous", "ils", "elles", "me", "te",
    "se", "mon", "ma", "mes", "ton", "ta", "tes", "son", "sa", "ses", "ce",
    "cette", "ces", "que", "qui", "quoi", "dont", "est", "es", "suis", "etre",
    "ai", "as", "avons", "avez", "ont", "avoir", "fais", "fait", "faire",
    "plus", "moins", "tres", "bien", "tout", "tous", "toute", "comme", "si",
    "ne", "pas", "y", "s", "qu", "j", "n", "m", "t", "ca", "cela", "the",
    "and", "of", "to", "in", "is", "it", "for", "you", "me", "my",
}

# Groupes de synonymes : un mot d'un groupe vaut les autres.
_SYNONYM_GROUPS = [
    {"bot", "robot", "chatbot", "agent", "assistant", "ia", "chat"},
    {"prix", "tarif", "tarifs", "combien", "cout", "budget", "cher", "price"},
    {"site", "web", "vitrine", "internet", "page", "ecommerce", "boutique"},
    {"logo", "identite", "marque", "visuel", "chartegraphique"},
    {"affiche", "flyer", "poster", "visuelpub"},
    {"retouche", "retoucher", "photoshop", "photo"},
    {"delai", "temps", "jours", "duree", "rapidite", "quand", "livraison"},
    {"paiement", "payer", "paye", "orange", "mtn", "virement", "acompte", "cash"},
    {"contact", "whatsapp", "numero", "telephone", "appeler", "joindre"},
    {"merci", "remercie", "thanks"},
    {"bonjour", "salut", "bonsoir", "salam", "hello", "hey"},
    {"video", "reel", "reels", "pub", "montage"},
    {"moderation", "moderer", "commentaires", "page"},
    {"devis", "quote", "estimation", "proforma"},
]

_SYNONYM_OF: dict[str, set[str]] = {}
for _group in _SYNONYM_GROUPS:
    for _word in _group:
        _SYNONYM_OF.setdefault(_word, set()).update(_group)


def normalise(text: str) -> str:
    text = _strip_accents(str(text or "")).lower()
    text = re.sub(r"['’`]", " ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokens(text: str) -> list[str]:
    """Mots utiles : SMS développés, accents retirés, pluriels ramenés au singulier."""
    words: list[str] = []
    for word in normalise(text).split():
        word = _SMS.get(word, word)
        for part in word.split():
            if len(part) <= 1 or part in _STOP:
                continue
            if len(part) > 4 and part.endswith("s"):
                part = part[:-1]
            if len(part) > 5 and part.endswith("x"):
                part = part[:-1]
            words.append(part)
    return words


def _trigrams(text: str) -> set[str]:
    clean = f" {normalise(text)} "
    return {clean[i:i + 3] for i in range(len(clean) - 2)}


def _dice(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return 2 * len(a & b) / (len(a) + len(b))


def _expand(word: str) -> set[str]:
    return _SYNONYM_OF.get(word, {word})


# ------------------------------------------------------------------- moteur lexical
def _idf_table() -> dict[str, float]:
    """IDF calculé une fois sur les questions du seed (les mots rares pèsent plus)."""
    global _IDF
    if _IDF is not None:
        return _IDF
    corpus: list[str] = []
    try:
        import aya_seed

        for questions, _answer in aya_seed.SEED_QR:
            corpus.extend(questions)
        for entries in getattr(aya_seed, "SEED_QR_ML", {}).values():
            for questions, _answer in entries:
                corpus.extend(questions)
    except Exception:  # pragma: no cover - seed absent
        corpus = []

    docs = [set(tokens(q)) for q in corpus] or [set()]
    total = len(docs)
    df: dict[str, int] = {}
    for doc in docs:
        for word in doc:
            df[word] = df.get(word, 0) + 1
    _IDF = {w: math.log((total + 1) / (n + 0.5)) + 1.0 for w, n in df.items()}
    _IDF["__default__"] = math.log(total + 1) + 1.0
    return _IDF


_IDF: dict[str, float] | None = None


def _weight(word: str, idf: dict[str, float]) -> float:
    return idf.get(word, idf["__default__"])


def lexical_score(message: str, question: str) -> float:
    """Pertinence 0..1 d'une fiche pour un message, sans aucune dépendance."""
    msg_tokens = tokens(message)
    q_tokens = tokens(question)
    if not msg_tokens or not q_tokens:
        return 0.0

    idf = _idf_table()

    # 1) recouvrement pondéré, avec synonymes (bot = robot = chatbot)
    msg_expanded: set[str] = set()
    for word in msg_tokens:
        msg_expanded |= _expand(word)
    q_expanded: set[str] = set()
    for word in q_tokens:
        q_expanded |= _expand(word)

    shared = msg_expanded & q_expanded
    msg_weight = sum(_weight(w, idf) for w in msg_expanded)
    shared_weight = sum(_weight(w, idf) for w in shared)
    coverage = shared_weight / msg_weight if msg_weight else 0.0

    # 2) trigrammes : tolérance aux fautes et au langage SMS
    fuzzy = _dice(_trigrams(message), _trigrams(question))

    # 3) phrase exacte contenue dans la fiche
    msg_norm = normalise(message)
    q_norm = normalise(question)
    phrase = 0.0
    if msg_norm and q_norm:
        if msg_norm == q_norm:
            phrase = 1.0
        elif msg_norm in q_norm or q_norm in msg_norm:
            phrase = 0.7
        else:
            # mots consécutifs communs (au moins deux)
            for size in (4, 3, 2):
                grams = {
                    " ".join(msg_tokens[i:i + size])
                    for i in range(len(msg_tokens) - size + 1)
                }
                if any(g and g in " ".join(q_tokens) for g in grams):
                    phrase = 0.5
                    break

    score = 0.50 * coverage + 0.30 * fuzzy + 0.20 * phrase
    return max(0.0, min(1.0, score))


# --------------------------------------------------------------------- chargement
def _try_cross_encoder():
    """Charge le cross-encoder seulement si demandé et installé."""
    mode = _env("RERANK_ENGINE", "auto")
    if mode == _ENGINE_LEXICAL:
        return None
    try:
        from sentence_transformers import CrossEncoder
    except Exception:
        if mode == _ENGINE_CROSS:
            logger.warning(
                "[RERANK] RERANK_ENGINE=cross mais sentence_transformers absent "
                "— moteur lexical pondéré actif"
            )
        return None
    started = time.time()
    try:
        model = CrossEncoder(_MODEL_NAME)
        logger.info("[RERANK] cross-encoder chargé en %.1fs", time.time() - started)
        return model
    except Exception as exc:
        logger.warning("[RERANK] cross-encoder indisponible (%s)", exc)
        return None


def _load():
    """UNE seule tentative par process. Retourne le moteur actif."""
    global _engine, _model, _load_attempted
    if _load_attempted:
        return _engine
    _load_attempted = True

    if not is_enabled():
        _engine = None
        logger.info("[RERANK] désactivé par RERANK_ENABLED")
        return None

    _model = _try_cross_encoder()
    if _model is not None:
        _engine = _ENGINE_CROSS
        return _engine

    _engine = _ENGINE_LEXICAL
    logger.info(
        "[RERANK] moteur lexical pondéré actif (IDF + trigrammes + synonymes) "
        "— aucune dépendance lourde"
    )
    return _engine


def engine() -> str | None:
    return _load()


def threshold() -> float:
    """Seuil de pertinence, adapté au moteur réellement actif."""
    default = "0.05" if (_load() == _ENGINE_CROSS) else "0.32"
    try:
        return float(_env("RERANK_THRESHOLD", default).replace(",", "."))
    except ValueError:
        return float(default)


def top_k() -> int:
    try:
        return int(_env("RERANK_TOP_K", "8"))
    except ValueError:
        return 8


def rerank(question: str, candidates: list) -> list | None:
    """Relit les candidats et les reclasse.

    candidates : [(score_lexical, answer, question_de_la_fiche), ...]
    Retourne [(answer, question, score), ...] trié du meilleur au pire,
    ou None si le reranker est désactivé.
    """
    active = _load()
    if active is None or not candidates:
        return None

    if active == _ENGINE_CROSS and _model is not None:
        try:
            pairs = [[question, (c[2] if c[2] else c[1])[:512]] for c in candidates]
            logits = _model.predict(pairs, show_progress_bar=False)
            scored = [
                (c[1], c[2] if len(c) > 2 else "", 1 / (1 + math.exp(-float(s))))
                for c, s in zip(candidates, logits)
            ]
            return sorted(scored, key=lambda x: x[2], reverse=True)
        except Exception as exc:
            logger.warning("[RERANK] cross-encoder en échec (%s) — lexical", exc)

    scored = [
        (c[1], (c[2] if len(c) > 2 else ""), lexical_score(question, c[2] if len(c) > 2 else c[1]))
        for c in candidates
    ]
    return sorted(scored, key=lambda x: x[2], reverse=True)


def is_relevant(score) -> bool:
    """Au-dessus du seuil on répond ; en dessous, pas de réponse devinée."""
    try:
        return float(score) >= threshold()
    except (TypeError, ValueError):
        return False
