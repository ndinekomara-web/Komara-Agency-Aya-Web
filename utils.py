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


# Mots partagés entre plusieurs langues : « services » n'est pas de l'anglais.
_AMBIGUOUS_FR = {
    "services", "service", "prix", "prix?", "tarif", "tarifs", "info", "infos",
    "ok", "okay", "merci", "bonjour", "salut", "bonsoir", "catalogue", "panier",
    "commande", "commander", "devis", "contact", "whatsapp", "telegram", "logo",
    "site", "web", "video", "vidéo", "photo", "design", "delai", "délai",
}
_FR_MARKERS = (
    " le ", " la ", " les ", " un ", " une ", " des ", " du ", " de ", " je ",
    " tu ", " vous ", " nous ", " mon ", " ma ", " mes ", " ton ", " ta ",
    " c'est ", " est ", " combien", " quel ", " quelle ", " pour ", " avec ",
    " svp", " stp", " merci", " veux ", " veut ", " besoin ", " coûte", " coute",
)
_EN_MARKERS = (" the ", " a ", " an ", " how ", " much", " what ", " i want", " need ", " price", " cost",
               "hello", "hey", "thanks", "please", "i am", "i'm")
_ES_MARKERS = (" cuanto", " precio", " quiero", " necesito", " pagina", " sitio ", " hola", " gracias")


def detect_language_simple(text: str) -> str:
    """Détection de langue simple basée sur les caractères et mots-clés."""
    low = f" {(text or '').casefold().strip()} "
    words = [w for w in low.split() if w]
    # Un seul mot courant (« services », « prix ») : on reste en français,
    # sinon « services » partait en anglais et la fiche anglaise répondait.
    if len(words) <= 2 and all(w.strip("?!.") in _AMBIGUOUS_FR for w in words):
        return "fr"
    # L'espagnol et l'anglais d'abord : « un », « de », « a » sont partagés,
    # donc un marqueur fort doit gagner avant les mots-outils français.
    if any(marker in low for marker in _ES_MARKERS):
        return "es"
    if any(marker in low for marker in _EN_MARKERS):
        return "en"
    if any(marker in low for marker in _FR_MARKERS):
        return "fr"
    if len(words) <= 2:
        return "fr"
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


# =================================================================
# IDENTITÉ : Aya ne se présente JAMAIS comme une IA ou un robot.
# Filtre appliqué à toutes les réponses sortantes.
# =================================================================
_ROBOT_SELF_RX = re.compile(
    r"\b(?:je suis (?:une? )?(?:ia|i\.a\.|intelligence artificielle|robot|"
    r"programme|machine|chatbot|assistant virtuel|algorithme)|"
    r"en tant qu'?(?:ia|intelligence artificielle|robot|assistant virtuel)|"
    r"i am an? (?:ai|robot|bot|machine)|soy (?:una |un )?(?:ia|robot|maquina)|"
    r"أنا (?:ذكاء اصطناعي|روبوت))\b[^.!?\n]*",
    re.IGNORECASE,
)

_SELF_REPLACEMENT = {
    "fr": "Moi c'est Aya, de Komara Agency 😊 Je m'occupe des messages et des devis pour Ndine",
    "en": "I'm Aya, from Komara Agency 😊 I handle messages and quotes for Ndine",
    "es": "Soy Aya, de Komara Agency 😊 Me encargo de los mensajes y presupuestos de Ndine",
    "ar": "أنا آيا، من وكالة كومارا 😊 أتولى الرسائل وعروض الأسعار لـ ندين",
}


def never_say_robot(text: str, lang: str = "fr") -> str:
    """Remplace toute auto-présentation « je suis une IA / un robot ».

    Aya parle comme Ndine : elle ne dit jamais qu'elle est une IA, un robot ou
    un programme, et elle ne prétend pas non plus être humaine. Si la phrase
    entière parle d'elle, on la remplace par sa présentation naturelle.
    """
    if not text or not _ROBOT_SELF_RX.search(text):
        return text
    replacement = _SELF_REPLACEMENT.get(lang, _SELF_REPLACEMENT["fr"])
    # On remplace la phrase fautive, pas tout le message (qui peut contenir
    # une vraie information commerciale).
    cleaned = _ROBOT_SELF_RX.sub(replacement, text)
    return cleaned
