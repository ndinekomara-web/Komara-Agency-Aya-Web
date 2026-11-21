"""
Routeur de messages : découpe la logique de _process_text en fonctions modulaires.
Chaîne de responsabilité pour traiter les messages dans le bon ordre.
"""
import re
from utils import clean_text, is_secret_probe, GENERIC_MESSAGES
from language_detector import detect_language, get_language
from pending_question import get_pending, is_valid_answer, clear_pending
from logical_steps import process_devis_step, get_flow_state, start_devis_flow
from farewell_guard import is_farewell, get_farewell_response
from sector_reply import get_sector_response
import rag_engine
import seed_engine
import checkout
import client_memory
import conversation
import closer_skills
import phone_validation
import chat_store


_PHONE_THANKS = {
    "fr": "Bien reçu 🙌 J'ai noté ton numéro, l'équipe Komara te contacte rapidement. On prépare quoi en premier ?",
    "en": "Got it 🙌 I saved your number, the Komara team will reach out shortly. What should we prepare first?",
    "es": "Anotado 🙌 El equipo de Komara te contacta pronto. ¿Qué preparamos primero?",
    "ar": "تم الحفظ 🙌 سيتواصل فريق كومارا قريباً. ماذا نحضر أولاً؟",
}


_CANCEL_MSG = {
    "fr": "D'accord, on laisse le devis de côté. Dis-moi ce qui t'intéresse 👇",
    "en": "Alright, let's drop the quote. Tell me what you need 👇",
    "es": "De acuerdo, dejamos el presupuesto. Dime qué necesitas 👇",
    "ar": "حسناً، نترك عرض السعر. أخبرني بما تحتاجه 👇",
}
_CANCEL_RX = re.compile(r"\b(annul\w*|stop|abandon\w*|laisse tomber|cancel)\b", re.I)


def _is_cancel(text: str) -> bool:
    return bool(_CANCEL_RX.search(text))


_PHONE_RX = re.compile(r"(?:\+|00)?\d[\d\s.\-]{6,}\d")


def _looks_like_phone(text: str) -> bool:
    """Un numéro dans un message court (« mon numero est 620123456 »)."""
    stripped = text.strip()
    if len(stripped) > 45:
        return False
    match = _PHONE_RX.search(stripped)
    if not match:
        return False
    digits = sum(ch.isdigit() for ch in match.group(0))
    return 8 <= digits <= 15


def route_message(chat_id: int, user_text: str, bot_send_func) -> bool:
    """
    Route un message texte vers le bon handler.

    Args:
        chat_id: ID du chat
        user_text: Texte du message
        bot_send_func: Fonction pour envoyer une réponse (bot.send_message)

    Returns:
        True si le message a été traité, False sinon
    """
    # 1. Nettoyage
    text = clean_text(user_text)
    if not text:
        return False

    # 2. Détection de langue
    lang = detect_language(text, chat_id)

    # 2b. Mémoire du client : on retient ce qu'il dit, on charge ce qu'on sait déjà.
    profile = client_memory.get(str(chat_id))
    welcome_back = conversation.greeting_prefix(profile) if profile.get("turns", 0) > 0 else ""
    before = dict(profile)
    profile = client_memory.learn(str(chat_id), text, profile)

    def nonlocal_welcome_off() -> None:
        nonlocal welcome_back
        welcome_back = ""

    def reply(message: str) -> bool:
        """Envoie la réponse et enregistre la mémoire (une seule fois par tour)."""
        if welcome_back and not message.startswith("Content de te revoir"):
            message = welcome_back + message
        conversation.remember_question(profile, message)
        client_memory.save(str(chat_id), profile)
        bot_send_func(chat_id, message)
        return True

    # 2c. Salutation ou « comment tu vas » : on répond humainement.
    small_talk = conversation.wellbeing_reply(text, profile, lang)
    if small_talk:
        return reply(small_talk)

    # 3. Sécurité : bloquer les tentatives d'extraction de prompts
    if is_secret_probe(text):
        bot_send_func(chat_id, GENERIC_MESSAGES[lang]["secret_blocked"])
        return True

    # 3b. Demandes interdites (faux documents, piratage, deepfakes...)
    if closer_skills.is_offlimits(text):
        bot_send_func(chat_id, closer_skills.refusal_message(lang))
        return True

    # 3c. Client mécontent : empathie + passage direct au boss
    if closer_skills.is_negative_emotion(text):
        bot_send_func(chat_id, closer_skills.empathy_message(lang))
        return True

    # 3d. Numéro de téléphone laissé par le client : on le garde pour l'équipe
    if _looks_like_phone(text):
        valid, _reason = phone_validation.check(text)
        if valid:
            phone = phone_validation.normalize(text)
            chat_store.add_lead(chat_id, phone, text)
            try:
                import notify

                notify.phone_captured(str(chat_id), phone)
            except Exception:
                pass
            profile["phone"] = phone
            profile["open_question"] = ""
            client_memory.set_stage(profile, "closing")
            return reply(conversation.phone_thanks(profile, lang) or _PHONE_THANKS.get(lang, _PHONE_THANKS["fr"]))

    # 4c. Commande guidée en cours (panier -> nom -> livraison -> confirmation)
    if checkout.in_checkout(chat_id):
        order_reply = checkout.step(chat_id, text, lang)
        if order_reply:
            bot_send_func(chat_id, order_reply)
            return True

    # 4d. Catalogue, panier, ajout, commande
    shop_reply = checkout.handle(chat_id, text, lang)
    if shop_reply:
        bot_send_func(chat_id, shop_reply)
        return True

    # 5. Vérifier les questions en attente
    pending = get_pending(chat_id)
    if pending:
        is_valid, answer = is_valid_answer(chat_id, text)
        if is_valid:
            # Traiter la réponse
            flow_response = process_devis_step(chat_id, text, lang)
            if flow_response:
                bot_send_func(chat_id, flow_response)
                return True

    # 6. Vérifier les flux actifs (devis, etc.)
    flow = get_flow_state(chat_id)
    if flow and _is_cancel(text):
        from logical_steps import clear_flow_state
        clear_flow_state(chat_id)
        clear_pending(chat_id)
        bot_send_func(chat_id, _CANCEL_MSG.get(lang, _CANCEL_MSG["fr"]))
        return True
    if flow:
        flow_response = process_devis_step(chat_id, text, lang)
        if flow_response:
            bot_send_func(chat_id, flow_response)
            return True

    # 3d-bis. Le client demande un lien ou dit ne pas l'avoir reçu : réponse honnête.
    link_reply = conversation.reply_link_question(text, profile)
    if link_reply:
        return reply(link_reply)

    # 3d-ter. Simple confirmation (« d'accord », « ok ») : on réagit à ce qui précède.
    if lang == "fr" and conversation.is_confirmation(text) and profile.get("turns", 0) > 1:
        confirmed = conversation.reply_confirmation(profile)
        if confirmed:
            return reply(confirmed)

    # 3d-00. Le client se présente ou décrit son activité : on accueille, on avance.
    if lang == "fr" and conversation.is_introduction(text):
        intro_reply = conversation.reply_introduction(profile, text, before)
        if intro_reply:
            return reply(intro_reply)

    # 3d-0. Un client connu dit bonjour : salutation personnalisée, une seule voix.
    if lang == "fr" and conversation.is_greeting_only(text):
        known = conversation.reply_returning_greeting(profile)
        if known:
            nonlocal_welcome_off()
            return reply(known)

    # 3d-pre. Le client répond à la question qu'Aya vient de poser.
    if lang == "fr":
        answered = conversation.reply_to_last_question(profile, text)
        if answered:
            return reply(answered)

    # 3d-quater. Le client exprime un projet : on répond en vendeur, pas en dictionnaire.
    if lang == "fr" and conversation.is_buy_intent(text):
        buy_reply = conversation.reply_buy_intent(profile, text)
        if buy_reply:
            return reply(buy_reply)

    # 3e. Demande de devis explicite : parcours guidé (service, budget, confirmation)
    if is_quote_intent(text) and not get_flow_state(chat_id):
        bot_send_func(chat_id, start_devis_flow(chat_id, lang))
        return True

    # 3f. Connaissances écrites par l'équipe via /admin : elles font foi
    admin_answer = seed_engine.find_admin_answer(text, lang)
    if admin_answer:
        return reply(conversation.build_reply(profile, "admin:" + admin_answer[:40], "", admin_answer))

    # 4b. Adieux (repli si le seed n'a pas de fiche)
    if is_farewell(text, lang):
        bot_send_func(chat_id, get_farewell_response(lang))
        return True

    # 4. Réponses d'Aya (seed) : prioritaires, y compris « merci » / « au revoir »
    #    qui ont leur propre fiche au ton de l'agence. Un parcours en cours
    #    (devis) garde la main, voir plus bas.
    in_flow = bool(get_flow_state(chat_id)) or bool(get_pending(chat_id))
    if not in_flow:
        seed_hit = seed_engine.find_answer(text, lang)
        if seed_hit:
            title = seed_hit.get("question") or ""
            topic = title or seed_hit["answer"][:40]
            return reply(
                conversation.build_reply(
                    profile, topic, title, seed_hit["answer"], first_message=False
                )
            )

    # 8. Connaissances ajoutées via /admin + anciens fichiers génériques
    rag_response = get_sector_response(text, lang)
    if rag_response:
        bot_send_func(chat_id, rag_response)
        return True

    # 9. Fallback : message générique
    bot_send_func(chat_id, GENERIC_MESSAGES[lang]["no_understand"])
    return True


_QUOTE_PATTERNS = (
    "devis", "quote", "quotation", "estimation", "offre de prix",
    "عرض سعر", "تسعير", "سعر خاص",
)


def is_quote_intent(text: str) -> bool:
    """Détecte une demande de devis explicite (et non une simple question de prix)."""
    lowered = text.casefold()
    return any(pattern in lowered for pattern in _QUOTE_PATTERNS)


def handle_punctuation_only(text: str) -> bool:
    """Vérifie si le message ne contient que de la ponctuation."""
    cleaned = re.sub(r'[^\w\s]', '', text)
    return len(cleaned.strip()) == 0


def handle_greeting(text: str, lang: str) -> str | None:
    """Détecte et répond aux salutations."""
    greetings = {
        "fr": ["bonjour", "hello", "salut", "hi", "coucou"],
        "ar": ["مرحبا", "السلام", "اهلا", "سلام"],
        "en": ["hello", "hi", "hey", "good morning", "good afternoon"],
    }

    text_lower = text.lower()
    for greeting in greetings.get(lang, []):
        if greeting in text_lower:
            return GENERIC_MESSAGES[lang]["greeting"]

    return None
