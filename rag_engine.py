"""
Moteur de recherche de la base de connaissances d'Aya.

Deux moteurs, interchangeables sans changer le reste du code :

* ``embed``   : embeddings multilingues (sentence-transformers) — meilleure
  compréhension, mais télécharge un modèle d'environ 120 Mo au premier lancement.
* ``keyword`` : recherche par mots-clés pondérés — aucun modèle, démarrage
  instantané, installation très légère.

``RAG_BACKEND=auto`` (par défaut) utilise les embeddings s'ils sont installés,
et bascule automatiquement sur les mots-clés sinon. L'application ne plante
donc jamais à cause d'une dépendance manquante.
"""
from __future__ import annotations

import os
import re
import threading
import unicodedata
from typing import Any

try:  # numpy est la seule dépendance numérique du mode embeddings
    import numpy as np
except Exception:  # pragma: no cover - numpy est dans requirements
    np = None  # type: ignore

from config import (
    EMBEDDING_MODEL,
    KNOWLEDGE_BASE_PATH,
    RAG_BACKEND,
    RAG_MIN_SCORE,
    RAG_TOP_K,
    SUPPORTED_LANGUAGES,
)

# Un seuil plus bas est nécessaire en mode mots-clés : les scores y sont
# calculés différemment (recouvrement de tokens, pas de similarité cosinus).
KEYWORD_MIN_SCORE = 0.32

# === Modèle d'embedding (chargé une seule fois, si disponible) ===
_model: Any = None
_model_lock = threading.Lock()
_model_failed = False


def _embeddings_available() -> bool:
    if RAG_BACKEND == "keyword":
        return False
    if _model is not None:
        return True
    if _model_failed:
        return False
    try:
        import importlib.util

        return importlib.util.find_spec("sentence_transformers") is not None
    except Exception:
        return False


def _get_model():
    """Charge le modèle d'embedding (lazy loading, thread-safe)."""
    global _model, _model_failed
    if _model is None and not _model_failed:
        with _model_lock:
            if _model is None and not _model_failed:
                try:
                    from sentence_transformers import SentenceTransformer

                    _model = SentenceTransformer(EMBEDDING_MODEL)
                except Exception:
                    _model_failed = True
                    _model = None
    return _model


# === Base de connaissances en mémoire ===
_kb_cache: dict[str, list[dict]] = {}
_kb_lock = threading.Lock()

_query_cache: dict[str, list] = {}
_QUERY_CACHE_MAX = 512


def active_backend() -> str:
    """Retourne le moteur réellement utilisé."""
    return "embed" if _embeddings_available() else "keyword"


# ---------------------------------------------------------------------------
# Préparation du texte (commun aux deux moteurs)
# ---------------------------------------------------------------------------
def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text.casefold())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9\u0600-\u06ff]+", " ", text).strip()


_STOPWORDS = {
    "le", "la", "les", "un", "une", "des", "de", "du", "et", "ou", "a", "au",
    "aux", "en", "pour", "par", "avec", "sur", "dans", "que", "qui", "quoi",
    "est", "sont", "ce", "cette", "ces", "je", "tu", "il", "elle", "nous",
    "vous", "ils", "elles", "mon", "ma", "mes", "votre", "vos", "the", "and",
    "for", "with", "you", "your", "how", "what", "is", "are", "do", "can",
    "من", "في", "على", "هل", "ما", "هو", "هي", "و",
    # interrogatifs et formules de politesse (ils ne portent pas le sujet)
    "quel", "quelle", "quels", "quelles", "sont", "vos", "votre", "veux",
    "voudrais", "proposez", "propose", "avez", "avoir", "faites", "faire",
    "puis", "peux", "peut", "svp", "merci", "bonjour", "salut",
}


def _tokens(text: str) -> list[str]:
    return [w for w in _normalize(text).split() if len(w) > 2 and w not in _STOPWORDS]


def _encode(text: str) -> list:
    """Encode une requête avec cache (mode embeddings uniquement)."""
    key = text.strip().casefold()
    cached = _query_cache.get(key)
    if cached is not None:
        return cached
    model = _get_model()
    if model is None:
        return []
    emb = model.encode(text, show_progress_bar=False).tolist()
    if len(_query_cache) >= _QUERY_CACHE_MAX:
        _query_cache.pop(next(iter(_query_cache)))
    _query_cache[key] = emb
    return emb


def _split_into_sections(content: str, filename: str) -> list[dict]:
    """Découpe un fichier markdown en sections, en gardant le titre du fichier.

    Le titre H1 du fichier (« Tarifs et Prix ») est conservé : il aide à
    retrouver une section quand la question porte sur le thème du fichier.
    """
    sections: list[dict] = []
    file_title = filename.replace(".md", "")
    current_title = file_title
    current_text = ""

    def _flush():
        if current_text.strip():
            sections.append(
                {
                    "text": f"{current_title}\n{current_text.strip()}",
                    "source": f"{filename}#{current_title}",
                    "title": f"{file_title} {current_title}".strip(),
                }
            )

    for line in content.split("\n"):
        if line.startswith("## "):
            _flush()
            current_title = line[3:].strip()
            current_text = ""
        elif line.startswith("# "):
            _flush()
            file_title = line[2:].strip().replace("—", " ").strip()
            current_title = file_title
            current_text = ""
        else:
            current_text += line + "\n"
    _flush()
    return sections


def _load_knowledge_base() -> None:
    """Charge la base de connaissances en mémoire (embeddings ou tokens)."""
    global _kb_cache
    use_embeddings = active_backend() == "embed"
    model = _get_model() if use_embeddings else None

    cache: dict[str, list[dict]] = {}
    for lang in SUPPORTED_LANGUAGES:
        lang_dir = os.path.join(KNOWLEDGE_BASE_PATH, lang)
        if not os.path.isdir(lang_dir):
            continue
        entries: list[dict] = []
        for filename in sorted(os.listdir(lang_dir)):
            if not filename.endswith(".md"):
                continue
            filepath = os.path.join(lang_dir, filename)
            with open(filepath, "r", encoding="utf-8") as handle:
                content = handle.read()
            for section in _split_into_sections(content, filename):
                text = section["text"].strip()
                if len(text) < 20:
                    continue
                entry = {
                    "text": text,
                    "source": section["source"],
                    "lang": lang,
                    "tokens": _tokens(text),
                    "title_tokens": _tokens(section.get("title", "")),
                }
                if use_embeddings and model is not None:
                    entry["embedding"] = model.encode(
                        text, show_progress_bar=False
                    ).tolist()
                entries.append(entry)
        cache[lang] = entries

    _merge_admin_knowledge(cache)

    with _kb_lock:
        _kb_cache = cache


def _merge_admin_knowledge(cache: dict[str, list[dict]]) -> None:
    """Ajoute les connaissances saisies par l'administrateur (stockées en base).

    Elles vivent en base et non dans un fichier : elles survivent donc aux
    redéploiements, contrairement au disque de l'application.
    """
    try:
        import chat_store

        rows = chat_store.knowledge_entries()
    except Exception:
        return
    if not rows:
        return

    use_embeddings = active_backend() == "embed"
    model = _get_model() if use_embeddings else None
    for row in rows:
        lang = row.get("lang") or "fr"
        text = f"{row.get('title', '')}\n{row.get('content', '')}".strip()
        if len(text) < 5:
            continue
        entry = {
            "text": text,
            "source": f"admin#{row.get('title', 'note')}",
            "lang": lang,
            "tokens": _tokens(text),
            "title_tokens": _tokens(row.get("title", "")),
            # Une information donnée explicitement par Komara Agency prime
            # sur une fiche générique de la base de connaissances.
            "boost": 1.25,
        }
        if use_embeddings and model is not None:
            entry["embedding"] = model.encode(text, show_progress_bar=False).tolist()
        cache.setdefault(lang, []).append(entry)


def reload_knowledge_base() -> None:
    """Recharge la base de connaissances (après mise à jour des fichiers)."""
    global _kb_cache
    with _kb_lock:
        _kb_cache = {}
    _load_knowledge_base()


def _ensure_loaded() -> None:
    if not _kb_cache:
        _load_knowledge_base()


def _cosine(a: list, b: list) -> float:
    if np is None:
        return 0.0
    va, vb = np.array(a), np.array(b)
    norm = float(np.linalg.norm(va) * np.linalg.norm(vb))
    return float(np.dot(va, vb) / norm) if norm else 0.0


def _match_tokens(unique: set[str], pool: set[str]) -> set[str]:
    """Tokens de la question présents dans le pool (avec tolérance morphologique)."""
    if not pool:
        return set()
    direct = {t for t in unique if t in pool}
    fuzzy = {
        t
        for t in unique - direct
        if any((t in e or e in t) and len(t) > 4 and len(e) > 4 for e in pool)
    }
    return direct | fuzzy


def _keyword_score(
    query_tokens: list[str], entry_tokens: list[str], title_tokens: list[str] | None = None
) -> float:
    """Score de pertinence : correspondance du contenu et du titre.

    Une section dont le titre reprend les mots de la question (« Bot WhatsApp »
    pour « tarif bot whatsapp ») passe devant une section qui ne fait que les
    mentionner au détour d'une phrase. Une question réduite à un thème
    (« tarifs ») trouve ainsi la bonne section même si le mot n'apparaît pas
    dans le corps du texte.
    """
    unique = set(query_tokens)
    if not unique or not entry_tokens:
        return 0.0

    in_body = _match_tokens(unique, set(entry_tokens))
    in_title = _match_tokens(unique, set(title_tokens or []))
    if not in_body and not in_title:
        return 0.0

    coverage = len(in_body) / len(unique)
    title_coverage = len(in_title) / len(unique)
    density = min(len(in_body) / (len(set(entry_tokens)) ** 0.5), 2.0) * 0.04
    return min(1.0, coverage * 0.55 + title_coverage * 0.42 + density)


def search(
    query: str,
    lang: str,
    top_k: int = RAG_TOP_K,
    min_score: float | None = None,
) -> list[dict]:
    """Recherche les sections les plus pertinentes, dans la langue demandée.

    Aucun mélange de langues : si la langue n'a pas de contenu, on renvoie
    une liste vide (le routeur produira alors une réponse générique).
    """
    _ensure_loaded()
    entries = _kb_cache.get(lang, [])
    if not entries:
        return []

    backend = active_backend()
    if backend == "embed":
        query_vector = _encode(query)
        if not query_vector:
            backend = "keyword"
        else:
            threshold = RAG_MIN_SCORE if min_score is None else min_score
            scored = [
                (entry, _cosine(query_vector, entry["embedding"]))
                for entry in entries
                if entry.get("embedding")
            ]
            scored = [(e, s) for e, s in scored if s >= threshold]
            scored.sort(key=lambda item: item[1], reverse=True)
            return [
                {"text": e["text"], "source": e["source"], "score": round(s, 4)}
                for e, s in scored[:top_k]
            ]

    threshold = KEYWORD_MIN_SCORE if min_score is None else min_score
    query_tokens = _tokens(query)
    scored = []
    for entry in entries:
        score = _keyword_score(
            query_tokens, entry.get("tokens", []), entry.get("title_tokens", [])
        )
        score = min(1.0, score * entry.get("boost", 1.0))
        if score >= threshold:
            scored.append((entry, score))
    scored.sort(key=lambda item: item[1], reverse=True)
    return [
        {"text": e["text"], "source": e["source"], "score": round(s, 4)}
        for e, s in scored[:top_k]
    ]


def search_async(query: str, lang: str) -> list[dict]:
    """Version exécutée dans un thread : ne bloque jamais la boucle web."""
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        return pool.submit(search, query, lang).result()


def get_best_answer(query: str, lang: str) -> str | None:
    """Meilleure réponse de la base de connaissances, ou None."""
    results = search(query, lang)
    return results[0]["text"] if results else None


def get_context_for_generation(query: str, lang: str) -> str:
    """Contexte formaté (utile pour un futur branchement LLM)."""
    results = search(query, lang)
    if not results:
        return ""
    return "\n\n---\n\n".join(
        f"[Source {i} - {r['source']} (score: {r['score']:.2f})]\n{r['text']}"
        for i, r in enumerate(results, 1)
    )


def stats() -> dict:
    """Informations d'état pour la page /health."""
    _ensure_loaded()
    return {
        "backend": active_backend(),
        "sections": sum(len(v) for v in _kb_cache.values()),
        "languages": sorted(k for k, v in _kb_cache.items() if v),
    }
