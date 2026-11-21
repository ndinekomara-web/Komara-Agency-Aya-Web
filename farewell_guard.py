"""
Détection des messages d'adieu pour éviter de relancer la conversation.
"""
import re

FAREWELL_PATTERNS = {
    "fr": [
        r"\b(merci|au revoir|a bientôt|a plus|bonne journée|bonne soirée|bye|ciao|adieu)\b",
        r"\b(merci beaucoup|merci bien|c'est tout|c est tout)\b",
    ],
    "ar": [
        r"\b(شكرا|مع السلامة|الى اللقاء|وداعا|تصبح على خير|باي)\b",
        r"\b(شكرا جزيلا|شكرا لك|هذا كل شيء)\b",
    ],
    "en": [
        r"\b(thanks|thank you|goodbye|bye|see you|have a good|take care|cheers)\b",
        r"\b(thanks a lot|thank you very much|that's all|thats all)\b",
    ],
}


def is_farewell(text: str, lang: str = "fr") -> bool:
    """Détecte si un message est un adieu/remerciement."""
    text_lower = text.strip().lower()
    patterns = FAREWELL_PATTERNS.get(lang, FAREWELL_PATTERNS["fr"])

    for pattern in patterns:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True
    return False


def get_farewell_response(lang: str = "fr") -> str:
    """Retourne une réponse d'adieu appropriée."""
    responses = {
        "fr": "Avec plaisir 🙏 Reviens quand tu veux, et bon business !",
        "ar": "شكرا لك! لا تتردد في العودة إذا كان لديك أسئلة أخرى. إلى اللقاء! 👋",
        "en": "Anytime 🙏 Come back whenever you like, and good business!",
    }
    return responses.get(lang, responses["fr"])
