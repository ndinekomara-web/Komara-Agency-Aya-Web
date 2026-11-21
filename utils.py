"""
Utilitaires partagés : cache TTL, nettoyage texte, emojis.
"""
import re
import unicodedata
from cachetools import TTLCache
from config import MAX_CACHE_SIZE, CACHE_TTL_SECONDS


# === Caches TTL (évite les fuites mémoire) ===
LAST_LANG_CACHE = TTLCache(maxsize=MAX_CACHE_SIZE, ttl=CACHE_TTL_SECONDS)
GREETED_SESSIONS = TTLCache(maxsize=MAX_CACHE_SIZE, ttl=CACHE_TTL_SECONDS)
PENDING_QUESTIONS = TTLCache(maxsize=MAX_CACHE_SIZE, ttl=3600)  # 1h


def clean_text(text: str) -> str:
    """Nettoie le texte : normalise unicode, enlève espaces multiples."""
    if not text:
        return ""
    # Normaliser unicode (NFC)
    text = unicodedata.normalize("NFC", text)
    # Enlever espaces multiples
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_digits(text: str) -> str:
    """Extrait uniquement les chiffres d'un texte."""
    return re.sub(r"\D", "", text)


def is_single_digit(text: str) -> tuple[bool, int]:
    """Vérifie si le texte est un chiffre unique (1-9), gère les emojis keycap."""
    digits = extract_digits(text)
    if len(digits) == 1:
        num = int(digits)
        if 1 <= num <= 9:
            return True, num
    return False, 0


def is_secret_probe(text: str) -> bool:
    """Détecte les tentatives d'extraction de prompts/secrets."""
    cleaned = clean_text(text.lower())
    # Enlever tous les espaces pour contrer "c o d e"
    no_spaces = cleaned.replace(" ", "")

    secret_patterns = [
        "codesource", "code_source", "prompt system", "promptsystem",
        "prompt système", "instruct", "systemprompt", "system_prompt",
        "developer mode", "jailbreak", "dan mode",
        "ton code", "github", "railway", "depot", "dépôt", "repository",
        # Configuration et infrastructure : jamais divulguées au client.
        "variable", "variables d'environnement", "variables environnement",
        "environment variable", "env var", "mot de passe", "password",
        "token", "clé api", "cle api", "api key", "secret",
        "adresse ip", "ton ip", "mon ip", "quelle ip",
        "base de données", "base de donnees", "database", "postgres", "sqlite",
        "serveur", "hébergement", "hebergement", "hébergeur", "hebergeur",
        "hébergée", "hebergee", "hébergé", "heberge",
        # « admin » seul est trop large (un client peut gérer sa boutique) :
        # on cible l'espace interne.
        "page admin", "/admin", "espace admin", "panneau admin",
        "interface admin", "admin du site", "tableau de bord interne",
        # Fonctionnement interne : on explique le service, pas la mécanique.
        "prompt", "system prompt", "quel modèle", "quel modele", "quel llm",
        "gpt", "openai", "anthropic", "claude", "llm", "reranker", "embedding",
        "mémoire interne", "memoire interne", "tu stockes", "où sont stockées",
        "ou sont stockees", "tes fichiers", "ta configuration",
    ]

    for pattern in secret_patterns:
        p_compact = pattern.replace(" ", "")
        # Chaîne vide = toujours vraie : on ignore (bug arabes compactées)
        if p_compact and (pattern in cleaned or p_compact in no_spaces):
            return True
    return False


def detect_language_simple(text: str) -> str:
    """Détection de langue simple basée sur les caractères et mots-clés."""
    try:
        from langdetect import detect
        lang = detect(text)
        if lang in ["fr", "ar", "en"]:
            return lang
        # Mapper les langues proches
        lang_map = {
            "ar": "ar", "fa": "ar",  # Persan -> arabe (approximatif)
            "fr": "fr", "it": "fr", "es": "fr", "pt": "fr", "de": "fr",
            "en": "en",
        }
        return lang_map.get(lang, "fr")
    except Exception:
        return "fr"


# === Messages génériques multilingues ===
GENERIC_MESSAGES = {
    "fr": {
        "no_understand": "Pardon, j'ai pas bien saisi 😅 Tu peux me redire ça avec tes mots ?",
        "greeting": "Salut 👋 Dis-moi ce que tu veux lancer, je m'occupe du reste.",
        "farewell": "Merci à toi 🙏 À très vite, et bon business !",
        "secret_blocked": "Ça reste interne à Komara Agency 🙏 Je ne partage pas ces détails. "
                          "Par contre, sur ton projet je peux tout te dire : dis-moi ce que tu veux lancer ?",
        "ask_precision": "Pourriez-vous préciser votre question ? Je veux vous donner la meilleure réponse possible.",
    },
    "ar": {
        "no_understand": "عذراً، لم أفهم جيداً 😅 هل يمكنك قولها بطريقة أخرى؟",
        "greeting": "مرحبا! 👋 كيف يمكنني مساعدتك اليوم؟",
        "farewell": "شكرا لرسالتك! إلى اللقاء قريبا. 👋",
        "secret_blocked": "لا يمكنني مشاركة هذه المعلومات. كيف يمكنني مساعدتك بطريقة أخرى؟",
        "ask_precision": "هل يمكنك توضيح سؤالك؟ أريد أن أعطيك أفضل إجابة ممكنة.",
    },
    "en": {
        "no_understand": "Sorry, I didn't quite catch that 😅 Can you say it another way?",
        "greeting": "Hello! 👋 How can I help you today?",
        "farewell": "Thanks for your message! See you soon. 👋",
        "secret_blocked": "I can't share that information. How else can I help you?",
        "ask_precision": "Could you clarify your question? I want to give you the best possible answer.",
    },
}
