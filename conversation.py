"""
Couche conversation d'Aya : transforme une fiche trouvée en une vraie réponse.

Le seed contient tes réponses ; ce module décide COMMENT les dire :

- elle ne répète jamais une fiche déjà donnée (elle avance à la place) ;
- elle tient compte de ce que le client a déjà dit (service, canal, secteur) ;
- elle ne promet jamais ce qu'elle ne peut pas tenir (un lien qui n'existe pas) ;
- elle termine toujours par UNE prochaine étape, tournée vers le closing ;
- elle salue un client qui revient, par son prénom s'il l'a donné.

Aucune IA, aucune invention : on choisit, on adapte, on enchaîne les réponses
déjà écrites par l'équipe.
"""
from __future__ import annotations

import os
import re
import random
from typing import Any

import client_memory as memory

WHATSAPP = os.getenv("KOMARA_WHATSAPP", "").strip()
SITE_URL = os.getenv("SITE_URL", "https://komaraagency.github.io/komara-agency-site/")


def _deposit_link() -> str:
    return os.getenv("DEPOSIT_LINK", "").strip()


# ---------------------------------------------------------------- étapes
# Chaque étape du tunnel a UNE question qui fait avancer vers la vente.
# {service} et {channel} sont remplis avec ce que le client a déjà dit.
_NEXT_STEP = {
    "decouverte": [
        "Tu as un projet en tête, ou tu veux d'abord que je te montre ce qu'on fait ?",
        "Dis-moi ce que tu veux améliorer dans ton business, et je te dis comment on peut t'aider ?",
    ],
    "besoin": [
        "Tu fais quoi comme activité, que je te propose quelque chose de vraiment adapté ?",
        "C'est pour quel type de business ?",
    ],
    "offre": [
        "Je te prépare un devis gratuit ? Ça prend 2 minutes.",
        "Tu veux que je te fasse un devis tout de suite ?",
    ],
    "devis": [
        "On le lance ? Dis-moi *devis* et je prends ta demande.",
        "Si ça te convient, on passe au devis. Je m'en occupe maintenant ?",
    ],
    "closing": [
        "Pour démarrer, c'est 50% à la commande. Laisse-moi ton numéro WhatsApp et l'équipe te contacte.",
        "Il ne reste qu'à valider. Tu me donnes ton numéro WhatsApp pour que l'équipe finalise avec toi ?",
    ],
    "client": [
        "Je suis là si tu as besoin d'autre chose.",
    ],
}

# Questions de suite adaptées au service déjà cité : plus précises, donc plus humaines.
_SERVICE_NEXT = {
    "chatbot": "Ton bot serait pour vendre, répondre aux questions, ou prendre des rendez-vous ?",
    "site": "Ton site, ce serait une vitrine ou une boutique en ligne ?",
    "logo": "Tu as déjà un nom pour ton business, que je te prépare le logo ?",
    "affiche": "C'est pour quel événement ou quelle promotion, l'affiche ?",
    "retouche": "Tu m'envoies la photo avec le trombone, et je te dis ce qu'on peut faire ?",
    "moderation": "Ta page a combien d'abonnés environ, que je te propose le bon niveau ?",
    "video": "C'est une pub, un Reel, ou une présentation de ton activité ?",
}

# Quand le client confirme (« d'accord », « ok », « oui ») sans préciser quoi.
_CONFIRMATIONS = {
    "d'accord", "daccord", "dac", "ok", "okay", "oui", "yes", "ouais", "ça marche", "ca marche",
    "parfait", "super", "très bien", "tres bien", "bien sûr", "bien sur", "allons-y", "go",
    "vas-y", "vas y", "c'est bon", "ok pour moi", "je veux bien", "volontiers",
}

_THANKS_CLOSE = {"merci", "merci beaucoup", "thanks", "شكرا"}

# Texte qui ressemble à une promesse de lien : interdit si aucun lien n'existe.
_LINK_PROMISE = re.compile(
    r"[^.!?\n]*\b(je\s+t['’]envoie|j['’]envoie|je\s+vous\s+envoie|je\s+te\s+transmets)\b[^.!?\n]*"
    r"\b(lien|link)\b[^.!?\n]*[.!?]?",
    re.IGNORECASE,
)
_WAIT_LINK = re.compile(r"[^.!?\n]*\ben\s+attendant\s+le\s+lien\b[^.!?\n]*[.!?]?", re.IGNORECASE)


def _norm(text: str) -> str:
    return re.sub(r"[^\w\s']", " ", text.casefold()).strip()


def is_confirmation(text: str) -> bool:
    cleaned = _norm(text)
    return cleaned in _CONFIRMATIONS or re.fullmatch(r"(oui|ok|d'accord)[\s,!.]*(merci)?", cleaned) is not None


# ------------------------------------------------------------- nettoyage
def clean_answer(answer: str, question_title: str = "") -> str:
    """Enlève les défauts de forme des fiches brutes."""
    text = answer.strip()

    # Titre court sur la première ligne (« Bots WhatsApp et Telegram »), sans
    # ponctuation finale : c'est un en-tête de document, pas une phrase.
    lines = text.split("\n")
    if len(lines) > 1 and len(lines[0]) <= 48 and not re.search(r"[.!?:]$", lines[0].strip()):
        text = "\n".join(lines[1:]).lstrip()

    # Le titre de la fiche ne doit jamais être recopié en tête de réponse.
    if question_title:
        title = question_title.strip().rstrip("?").strip()
        pattern = re.compile(rf"^\s*{re.escape(title)}\s*\??\s*[\n:–-]+\s*", re.IGNORECASE)
        text = pattern.sub("", text, count=1)

    # Promesse de lien : uniquement si un vrai lien existe.
    if not _deposit_link():
        text = _LINK_PROMISE.sub("", text)
        text = _WAIT_LINK.sub("", text)

    # Espaces et ponctuation propres.
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\s+([,.;!?])", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def has_question(text: str) -> bool:
    """Vrai si le texte pose déjà une question : on n'en empile pas une seconde."""
    return "?" in text


def ends_with_question(text: str) -> bool:
    tail = re.sub(r"[\s👇🔥🙏😊😉🚀✨💪🇬🇳\)\(]+$", "", text.strip())
    return tail.endswith("?") or bool(re.search(r"\?\s*\((oui|non)[^)]*\)$", tail, re.IGNORECASE))


# ------------------------------------------------------------ prochaine étape
def next_question(profile: dict[str, Any], avoid: str = "") -> str:
    """Une seule question, adaptée à ce que le client a déjà dit."""
    stage = profile.get("stage", "decouverte")
    service = profile.get("service", "")

    # Closing : on demande le numéro, sauf s'il est déjà connu.
    if stage == "closing" and profile.get("phone"):
        return "L'équipe te contacte très vite sur WhatsApp. Tu as autre chose à me demander en attendant ?"

    # Un service précis déjà cité : on creuse CE service, pas autre chose.
    if service and stage in ("decouverte", "besoin") and service in _SERVICE_NEXT:
        question = _SERVICE_NEXT[service]
        if question != avoid:
            return question

    options = [q for q in _NEXT_STEP.get(stage, _NEXT_STEP["decouverte"]) if q != avoid]
    return random.choice(options or _NEXT_STEP["decouverte"])


def advance_stage(profile: dict[str, Any], topic_key: str) -> None:
    """Fait avancer le tunnel selon le sujet traité."""
    key = topic_key.casefold()
    if any(w in key for w in ("prix", "tarif", "combien", "coût", "cout")):
        memory.set_stage(profile, "offre")
    elif any(w in key for w in ("devis", "accord", "valid", "commander", "commande")):
        memory.set_stage(profile, "devis")
    elif any(w in key for w in ("payer", "paiement", "acompte", "démarrer", "demarrer")):
        memory.set_stage(profile, "closing")
    elif profile.get("service"):
        memory.set_stage(profile, "besoin")


# --------------------------------------------------------------- accueil
_GREETINGS = {"bonjour", "salut", "bonsoir", "hello", "coucou", "salam", "bonjour aya", "salut aya", "hello aya"}


def is_greeting_only(text: str) -> bool:
    return _norm(text) in _GREETINGS


def reply_returning_greeting(profile: dict[str, Any]) -> str | None:
    """Un client connu dit bonjour : on le salue pour de bon, sans refaire l'accueil."""
    if profile.get("turns", 0) <= 1:
        return None
    name = profile.get("name", "")
    service = profile.get("service", "")
    stage = profile.get("stage", "decouverte")
    # Rien de retenu (ni prénom, ni projet, ni secteur) : un simple bonjour,
    # pas un faux « content de te revoir ».
    if not (name or service or profile.get("sector") or profile.get("phone")):
        return "Bonjour 😊 Moi c'est Aya, de Komara Agency. Tu veux lancer quoi : un bot, un site, un logo ?"
    hello = f"Bonjour {name} 😊" if name else "Bonjour 😊"
    label = _service_label(service)
    if label:
        tail = {
            "decouverte": f"On reprend ton projet {label} ?",
            "besoin": f"On reprend ton projet {label} ? Dis-moi où tu en es.",
            "offre": f"Tu as pu réfléchir à ton projet {label} ? Je peux te faire le devis maintenant.",
            "devis": f"Ton devis {label} t'attend. On le finalise ?",
            "closing": f"L'équipe a ton numéro pour ton projet {label}. Tu as eu de leurs nouvelles ?",
            "client": "Ravie de te revoir. Qu'est-ce qu'on prépare ensuite ?",
        }.get(stage, f"On reprend ton projet {label} ?")
        return f"{hello} {tail}"
    return f"{hello} Content de te revoir. Qu'est-ce que je peux faire pour toi aujourd'hui ?"


def greeting_prefix(profile: dict[str, Any]) -> str:
    """Salue un client qui revient, avec son prénom si on le connaît."""
    if not memory.returning(profile):
        return ""
    if not (profile.get("name") or profile.get("service") or profile.get("sector") or profile.get("phone")):
        return ""
    name = profile.get("name", "")
    service = profile.get("service", "")
    if name and service:
        return f"Content de te revoir {name} 😊 On reprend ton projet {_service_label(service)} ?\n\n"
    if name:
        return f"Content de te revoir {name} 😊\n\n"
    if service:
        return f"Content de te revoir 😊 On reprend ton projet {_service_label(service)} ?\n\n"
    return "Content de te revoir 😊\n\n"


def _service_label(service: str) -> str:
    return {
        "chatbot": "de chatbot",
        "site": "de site web",
        "logo": "de logo",
        "affiche": "d'affiche",
        "retouche": "de retouche photo",
        "moderation": "de modération de page",
        "video": "de vidéo",
    }.get(service, "")


# --------------------------------------------------------- réponses de lien
_LINK_WORDS = re.compile(r"\b(lien|link|paiement|payer|acompte)\b", re.IGNORECASE)
_NOT_RECEIVED = re.compile(
    r"(pas\s+(re[cç]u|vu|eu)|je\s+n['’]ai\s+(rien|pas)\s+(re[cç]u|vu)|toujours\s+rien|où\s+est|ou\s+est)",
    re.IGNORECASE,
)


def reply_link_question(text: str, profile: dict[str, Any]) -> str | None:
    """Le client demande un lien ou dit ne pas l'avoir reçu : réponse honnête."""
    if not _LINK_WORDS.search(text):
        return None
    if not (_NOT_RECEIVED.search(text) or re.search(r"\b(envoie|donne|passe|manda)\b", text, re.IGNORECASE)):
        return None
    link = _deposit_link()
    if link:
        return f"Voilà le lien pour l'acompte 👉 {link}\n\nDis-moi quand c'est fait, et on lance ton projet."
    return (
        "Je n'ai pas de lien automatique pour le moment, désolée pour la confusion 🙏 "
        f"Le plus simple : écris directement à l'équipe sur WhatsApp au {WHATSAPP}, "
        "ils te donnent les infos de paiement (Orange Money, MTN ou virement) tout de suite. "
        "Tu veux que je note ton numéro pour qu'on t'appelle ?"
    )


# ------------------------------------------------------------ assemblage
# Fiches qui supposent qu'on connaît déjà le client (« tu le sais », « mon frère »).
# Servies à un inconnu, elles sonnent faux : on les réserve aux clients revenus.
_KNOW_ME = ("tu me connais", "est-ce que tu me connais", "tu me connais ?")


def reply_know_me(profile: dict[str, Any]) -> str | None:
    """« Tu me connais ? » : on ne le dit que si la mémoire le confirme."""
    name = profile.get("name", "")
    label = _service_label(profile.get("service", ""))
    if name and label:
        return f"Bien sûr {name} 😊 Tu m'as parlé de ton projet {label}. On continue ?"
    if name:
        return f"Bien sûr {name} 😊 Tu veux qu'on reprenne où on s'est arrêtés ?"
    return None


_ANCIEN_CLIENT = (
    "prix pour moi", "c'est combien pour moi", "j'ai encore besoin de toi",
    "j ai encore besoin de toi", "tu m'as oublié", "tu m as oublie", "tu m'a oublié",
)


def is_returning_only(topic_title: str) -> bool:
    return topic_title.casefold().strip() in _ANCIEN_CLIENT


_PRICE_TOPICS = ("prix", "tarifs", "c'est combien", "combien ça coûte", "quels sont vos tarifs")


def is_price_topic(topic_title: str) -> bool:
    return topic_title.casefold().strip() in _PRICE_TOPICS


# Après une présentation, on ne parle PAS de devis : on demande ce que veut le client.
_TOPIC_FOLLOWUP = {
    "qui es-tu": "Et toi, c'est quoi ton projet ?",
    "tu es qui": "Et toi, c'est quoi ton projet ?",
    "qui est tu": "Et toi, c'est quoi ton projet ?",
    "qui êtes vous": "Et toi, c'est quoi ton projet ?",
    "services": "Dis-moi ce qui t'intéresse, je t'explique comment ça marche.",
    "portfolio": "Tu aimerais quoi pour ton business, dans ce style ?",
    "bonjour": "Tu as un projet en tête ?",
    "salut": "Tu as un projet en tête ?",
}


def _topic_followup(topic_title: str) -> str:
    return _TOPIC_FOLLOWUP.get(topic_title.casefold().strip(), "")


def build_reply(
    profile: dict[str, Any],
    topic_key: str,
    topic_title: str,
    answer: str,
    *,
    first_message: bool = False,
) -> str:
    """Compose la réponse finale à partir d'une fiche du seed."""
    # Fiche « ancien client » servie à quelqu'un qu'on ne connaît pas : on
    # répond au besoin réel (le prix) au lieu de faire semblant de le connaître.
    if topic_title.casefold().strip() in _KNOW_ME:
        known = reply_know_me(profile)
        if known:
            return known
    if is_returning_only(topic_title) and profile.get("turns", 0) < 6 and not profile.get("visits", 1) > 1:
        return _generic_price_answer(profile)

    # Le client a déjà choisi un service : on lui donne CE prix, pas toute la grille.
    if is_price_topic(topic_title) and profile.get("service") in _PRICE_HINT:
        memory.set_stage(profile, "offre")
        service = profile["service"]
        return (
            f"{_PRICE_HINT[service]} Express 24h : +30%. "
            "Paiement : 50% au démarrage, 50% à la livraison. Je te prépare le devis ?"
        )

    body = clean_answer(answer, topic_title)

    # Fiche déjà donnée : le client la redemande, donc on lui répond, plus court,
    # sans refaire le même texte mot pour mot et sans esquiver sa question.
    if memory.already_said(profile, topic_key) and not _is_core(topic_key):
        return _repeat_answer(profile, topic_key, topic_title, body)

    memory.mark_said(profile, topic_key)
    advance_stage(profile, topic_key)

    if not has_question(body):
        follow = _topic_followup(topic_title) or next_question(
            profile, avoid=profile.get("last_question", "")
        )
        body = f"{body}\n\n{follow}"
    body = _one_question_only(body)

    remember_question(profile, body)
    if first_message:
        body = greeting_prefix(profile) + body
    return body


_QUALIF = ("vendre", "activité", "type de business", "vitrine ou une boutique", "quel événement")


def remember_question(profile: dict[str, Any], message: str) -> None:
    """Retient la dernière question, et garde ouverte celle de qualification."""
    asked = _last_question(message)
    if not asked:
        return
    profile["last_question"] = asked
    if any(k in asked.casefold() for k in _QUALIF):
        profile["open_question"] = asked


def _last_question(text: str) -> str:
    """La dernière phrase interrogative d'une réponse."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    for sentence in reversed(sentences):
        if "?" in sentence:
            return sentence.strip()
    return ""


def _is_core(topic_key: str) -> bool:
    """Les réponses de politesse et d'info pratique peuvent se répéter."""
    key = topic_key.casefold()
    return any(w in key for w in ("merci", "au revoir", "bonjour", "salut", "prix", "tarif", "contact"))


_SHORT_REPEAT = {
    "services": "Je te le redis en bref : des bots WhatsApp et Telegram, des sites web, des logos, "
                "des affiches, des vidéos et la modération de pages. Lequel t'intéresse ?",
    "portfolio": "Tu peux les revoir juste au-dessus 😊 Lequel te plaît le plus ?",
}


def _repeat_answer(profile: dict[str, Any], topic_key: str, title: str, body: str) -> str:
    """Une question reposée reçoit une vraie réponse, reformulée."""
    key = title.casefold().strip()
    if key in _SHORT_REPEAT:
        return _SHORT_REPEAT[key]
    # Pas de version courte écrite : on redonne la fiche, une seule question en fin.
    follow = "" if has_question(body) else "\n\n" + next_question(
        profile, avoid=profile.get("last_question", "")
    )
    return _one_question_only(f"{body}{follow}")


def _already_covered(profile: dict[str, Any], title: str) -> str:
    """Le client repose un sujet déjà traité : on enchaîne, sans radoter."""
    name = profile.get("name", "")
    lead = f"On en a parlé, {name}." if name else "On en a déjà parlé 😊"
    return f"{lead} {next_question(profile)}"


# --------------------------------------------------- confirmation seule
def reply_confirmation(profile: dict[str, Any]) -> str | None:
    """« d'accord », « ok », « oui » : on répond à la question qu'Aya vient de poser."""
    stage = profile.get("stage", "decouverte")
    service = profile.get("service", "")
    name = profile.get("name", "")
    hello = f"Super {name} 🙌" if name else "Super 🙌"
    asked = (profile.get("last_question") or "").casefold()

    # « Tu veux que je te mette en relation maintenant ? » -> oui = on prend ses coordonnées.
    if "mette en relation" in asked or "te mette en contact" in asked:
        profile["last_question"] = ""
        memory.set_stage(profile, "closing")
        return (
            f"{hello} Donne-moi ton prénom et ton numéro WhatsApp, "
            "et Ndine te contacte directement pour ton projet."
        )

    # « Tu veux voir nos services ? » / « Tu veux les prix ? » -> oui = on les donne.
    if "voir nos services" in asked or "tu veux les prix" in asked or "tu veux voir" in asked:
        profile["last_question"] = ""
        return (
            f"{hello} On fait des bots WhatsApp qui vendent à ta place, des sites, des logos et des affiches. "
            "Qu'est-ce qui t'intéresse le plus pour ton activité ?"
        )

    # Aucun projet exprimé : « oui » ne doit PAS lancer un script de bot.
    # On demande d'abord ce que le client veut.
    if not service and not profile.get("project") and stage in ("decouverte", "besoin"):
        return f"{hello} Dis-moi ce que tu veux lancer : un bot, un site, un logo ou une affiche ?"

    if stage in ("decouverte", "besoin") and service:
        asked = profile.get("last_question", "")
        # On vient déjà de poser la question de ce service : on passe à l'offre.
        if asked and asked == _SERVICE_NEXT.get(service):
            memory.set_stage(profile, "offre")
            return f"{hello} Je te prépare un devis gratuit. Tu fais quoi comme activité, que je l'adapte à toi ?"
        if asked and _SERVICE_NEXT.get(service) == asked:
            memory.set_stage(profile, "offre")
            return f"{hello} Je te prépare un devis gratuit. Tu fais quoi comme activité, que je l'adapte à toi ?"
        return f"{hello} {_SERVICE_NEXT.get(service, next_question(profile))}"
    if stage == "offre":
        memory.set_stage(profile, "devis")
        # Projet déjà clair (service + activité connus) : on ne redemande rien,
        # on passe au numéro pour que l'équipe envoie le devis.
        if service and (profile.get("sector") or profile.get("usage") or profile.get("project")):
            return (
                f"{hello} J'ai tout ce qu'il me faut pour ton devis. "
                "Donne-moi ton numéro WhatsApp et l'équipe te l'envoie rapidement."
            )
        return f"{hello} Je te prépare le devis. Dis-moi juste ce que tu veux exactement, en une phrase."
    if stage == "devis":
        memory.set_stage(profile, "closing")
        profile["asked_phone"] = 1
        return (
            f"{hello} Pour lancer le projet, c'est 50% au démarrage et 50% à la livraison. "
            "Laisse-moi ton numéro WhatsApp et Ndine finalise avec toi."
        )
    if stage == "closing":
        # Numéro déjà reçu : le projet est lancé, on conclut, on ne répète rien.
        if profile.get("phone"):
            profile["closed"] = int(profile.get("closed", 0)) + 1
            if profile["closed"] == 1:
                who = f" {name}" if name else ""
                return (
                    f"Parfait{who}, c'est noté. Ndine te contacte très vite sur WhatsApp 🙏 "
                    "Tu as autre chose à ajouter pour ton projet ?"
                )
            return "Tout est bon de mon côté 🙌 Ndine te contacte très vite. À très vite !"
        # Numéro pas encore donné : on le redemande UNE fois, autrement, puis on propose une sortie.
        asks = int(profile.get("asked_phone", 0))
        profile["asked_phone"] = asks + 1
        if asks <= 1:
            return "Parfait 🙌 Il me manque juste ton numéro WhatsApp pour que Ndine te contacte."
        return (
            "Pas de souci 😊 Tu peux aussi écrire directement à Ndine quand tu veux, "
            "ou me laisser ton numéro plus tard, je garde ton projet."
        )
    return None


# =================================================================
# INTENTIONS : ce que le client veut vraiment, avant de chercher une fiche
# =================================================================
# « Je souhaite un chatbot » est un projet, pas la question « c'est quoi un
# chatbot ? ». On le détecte pour répondre comme un vendeur, pas comme un
# dictionnaire.
_BUY = re.compile(
    r"\b(je\s+(souhaite|voudrais|veux?|veut|vx|aimerais|cherche|ai\s+besoin|besoin)|j['’]aimerais|j['’]ai\s+besoin|"
    r"il\s+me\s+faut|mon\s+projet|c['’]est\s+pour\s+(un|une|mon|ma)|je\s+suis\s+int[ée]ress[ée]|"
    r"je\s+prends|je\s+commande|on\s+peut\s+(faire|cr[ée]er)|pouvez-vous\s+(faire|cr[ée]er)|"
    r"tu\s+peux\s+(me\s+)?(faire|cr[ée]er))\b",
    re.IGNORECASE,
)
_DEFINITION = re.compile(
    r"\b(c['’]est\s+quoi|qu['’]est[- ]ce\s+qu|ça\s+veut\s+dire|que\s+signifie|explique|définition)\b",
    re.IGNORECASE,
)


_SERVICE_ONLY = re.compile(
    r"^\s*(un\s+|une\s+|le\s+|la\s+)?(retouche(\s+photo)?|logo|affiche|visuel|site(\s+web)?|"
    r"chatbot|bot|vid[ée]o|mod[ée]ration)\s*(svp|stp|s'il\s+(vous|te)\s+pla[iî]t|please)?\s*[.!]*\s*$",
    re.IGNORECASE,
)


def is_buy_intent(text: str) -> bool:
    """Vrai si le client exprime un projet ou un besoin (pas une simple question)."""
    if _DEFINITION.search(text):
        return False
    return bool(_BUY.search(text)) or bool(_SERVICE_ONLY.match(text))


def reply_buy_intent(profile: dict[str, Any], text: str) -> str | None:
    """Réponse de vendeur à un projet : on accueille, on précise, on avance."""
    service = profile.get("service", "")
    if not service:
        return None
    # Même projet déjà accueilli : on ne refait pas le même accueil, on avance.
    if memory.already_said(profile, f"projet:{service}"):
        return _project_followup(profile)
    memory.mark_said(profile, f"projet:{service}")
    name = profile.get("name", "")
    channel = profile.get("channel", "")
    hello = f"Parfait {name} 🙌" if name else "Parfait 🙌"
    memory.set_stage(profile, "besoin")

    if service == "chatbot":
        where = {
            "whatsapp": "sur WhatsApp",
            "telegram": "sur Telegram",
            "facebook": "sur Facebook et Messenger",
            "instagram": "sur Instagram",
            "site": "sur ton site",
        }.get(channel, "")
        intro = f"{hello} Un chatbot {where}".strip() + ", c'est exactement ce qu'on fait."
        ask = "Il servirait surtout à quoi : vendre, répondre aux questions de tes clients, ou prendre des rendez-vous ?"
        if profile.get("sector"):
            ask = f"Pour ton activité ({profile['sector']}), il servirait surtout à vendre, répondre aux questions, ou prendre des rendez-vous ?"
        return f"{intro} {ask}"

    label = _service_label(service)
    intro = f"{hello} Un projet {label}, on le fait en {_DELAIS.get(service, 'quelques jours')}."
    return f"{intro} {_SERVICE_NEXT.get(service, next_question(profile))}"


_DELAIS = {
    "site": "7 jours",
    "logo": "24h",
    "affiche": "24 à 48h",
    "retouche": "24 à 48h",
    "moderation": "quelques jours",
    "video": "quelques jours",
}


def _project_followup(profile: dict[str, Any]) -> str:
    """Le client répète son besoin : on passe à l'étape suivante du tunnel."""
    name = profile.get("name", "")
    service = profile.get("service", "")
    stage = profile.get("stage", "decouverte")
    lead = f"Oui {name}, on s'en occupe." if name else "Oui, on s'en occupe."
    if stage in ("decouverte", "besoin"):
        memory.set_stage(profile, "offre")
        price = _PRICE_HINT.get(service, "")
        extra = f" {price}" if price else ""
        return f"{lead}{extra} Je te prépare un devis gratuit. Tu fais quoi comme activité, que je l'adapte à toi ?"
    return f"{lead} {next_question(profile, avoid=profile.get('last_question', ''))}"


def _price(name: str, default: str) -> str:
    """Prix lu dans les mêmes variables que la grille du seed : jamais deux chiffres."""
    return os.getenv(f"PRICE_{name}", default)


class _Prices(dict):
    def __missing__(self, key):
        raise KeyError(key)

    def get(self, key, default=None):
        builders = {
            "chatbot": lambda: (
                f"Le bot WhatsApp vendeur, c'est {_price('BOT_WHATSAPP', '100 €')}, "
                "avec les devis, les relances et le paiement."
            ),
            "site": lambda: f"Un site vitrine, c'est {_price('SITE', '250 €')}, livré en 7 jours.",
            "logo": lambda: f"Un logo, c'est {_price('LOGO', '50 €')}, livré en 24h.",
            "affiche": lambda: f"Une affiche, c'est {_price('AFFICHE', '30 €')}, en 24 à 48h.",
            "retouche": lambda: f"Une retouche photo, c'est {_price('RETOUCHE', '10 €')}.",
        }
        return builders[key]() if key in builders else default

    def __contains__(self, key):
        return key in ("chatbot", "site", "logo", "affiche", "retouche")

    def __getitem__(self, key):
        value = self.get(key)
        if value is None:
            raise KeyError(key)
        return value


_PRICE_HINT = _Prices()


def _price_once(profile: dict[str, Any]) -> str:
    """Le prix du service, une seule fois par conversation (jamais répété)."""
    service = profile.get("service", "")
    key = f"prix:{service}"
    if memory.already_said(profile, key) or service not in _PRICE_HINT:
        return ""
    memory.mark_said(profile, key)
    return _PRICE_HINT[service] + " "


def _generic_price_answer(profile: dict[str, Any]) -> str:
    """Un client qu'on ne connaît pas demande « c'est combien » : on répond vraiment."""
    service = profile.get("service", "")
    memory.set_stage(profile, "offre")
    hint = _price_once(profile).strip()
    if hint:
        return f"{hint} Express 24h : +30%. Je te prépare un devis gratuit ?"
    if service in _PRICE_HINT:
        return "Je t'ai donné le tarif juste avant 😊 Pour le devis exact, tu me donnes ton numéro WhatsApp ?"
    return (
        f"Ça dépend de ce que tu veux : logo {_price('LOGO', '50 €')}, affiche {_price('AFFICHE', '30 €')}, "
        f"site vitrine {_price('SITE', '250 €')}, bot WhatsApp {_price('BOT_WHATSAPP', '100 €')}. "
        "C'est pour quel projet, que je te donne le prix exact ?"
    )


# =================================================================
# RÉPONSE À LA QUESTION POSÉE : le client répond à Aya, on enchaîne
# =================================================================
_USAGE = {
    "vendre": ("vendre", "vente", "commande", "commandes", "produit", "produits", "clients"),
    "répondre": ("répondre", "repondre", "question", "questions", "faq", "renseign", "info"),
    "rendez-vous": ("rendez-vous", "rendez vous", "rdv", "réserv", "reserv"),
}


def reply_to_last_question(profile: dict[str, Any], text: str) -> str | None:
    """Si Aya vient de poser une question précise, on traite la réponse du client."""
    # La question de qualification reste ouverte même si une autre question a
    # été posée entre-temps (ex. le client a demandé le prix au passage).
    asked = (profile.get("open_question") or profile.get("last_question", "")).casefold()
    low = text.casefold()
    if not asked:
        return None
    # Le client pose lui-même une vraie question (prix, délai...) : elle passe d'abord.
    if _is_own_question(low):
        return None
    name = profile.get("name", "")
    thanks = f"Très bien {name}" if name else "Très bien"

    # « vendre, répondre aux questions, ou prendre des rendez-vous ? »
    if "vendre" in asked and "rendez" in asked:
        for usage, words in _USAGE.items():
            if any(w in low for w in words):
                memory.set_stage(profile, "offre")
                profile["usage"] = usage
                profile["last_question"] = ""
                profile["open_question"] = ""
                label = {
                    "vendre": "il présente tes produits et prend les commandes tout seul, même la nuit",
                    "répondre": "il répond aux questions de tes clients à ta place, 24h/24",
                    "rendez-vous": "il prend et confirme les rendez-vous sans que tu bouges",
                }[usage]
                return (
                    f"{thanks} 👌 Dans ce cas, {label}. "
                    f"{_price_once(profile)}"
                    "Tu fais quoi comme activité, que je te prépare un devis adapté ?"
                ).replace("  ", " ")

    # « une vitrine ou une boutique en ligne ? »
    if "vitrine" in asked and "boutique" in asked:
        kind = "boutique" if any(w in low for w in ("boutique", "e-commerce", "ecommerce", "vendre", "en ligne")) else "vitrine"
        if kind or any(w in low for w in ("vitrine", "boutique")):
            memory.set_stage(profile, "offre")
            profile["last_question"] = ""
            profile["open_question"] = ""
            profile["site_kind"] = kind
            label = (
                "un site vitrine : il présente ton activité, tes services et tes contacts"
                if kind == "vitrine"
                else "une boutique en ligne : tes clients choisissent et commandent directement"
            )
            return (
                f"{thanks} 👌 Donc {label}. {_price_once(profile)}"
                "Tu fais quoi comme activité, que je te prépare un devis adapté ?"
            ).replace("  ", " ")

    # « Tu as déjà un nom pour ton business ? »
    if "un nom" in asked and "logo" in asked:
        memory.set_stage(profile, "offre")
        profile["last_question"] = ""
        profile["open_question"] = ""
        return (
            f"{thanks} 👌 {_price_once(profile)}"
            "Envoie-moi le nom et ton activité, et l'équipe te prépare une première version en 24h. "
            "Ton numéro WhatsApp pour qu'on t'envoie le devis ?"
        ).replace("  ", " ")

    # « C'est pour quel événement ou quelle promotion, l'affiche ? »
    if "quel événement" in asked or "quelle promotion" in asked:
        memory.set_stage(profile, "offre")
        profile["last_question"] = ""
        profile["open_question"] = ""
        subject = _clean_subject(text)
        if subject:
            profile["project"] = subject
        about = f" pour {subject}" if subject else ""
        return (
            f"{thanks} 👌 Une affiche{about}, c'est noté. {_price_once(profile)}"
            "Envoie-moi les infos à mettre dessus (nom, date, lieu, photo si tu en as) "
            "et on s'en occupe. "
            "Ton numéro WhatsApp pour qu'on t'envoie le devis ?"
        ).replace("  ", " ")

    # « Tu m'envoies la photo avec le trombone, et je te dis ce qu'on peut faire ? »
    if "photo" in asked and ("trombone" in asked or "envoies" in asked):
        memory.set_stage(profile, "offre")
        profile["last_question"] = ""
        profile["open_question"] = ""
        return (
            f"{thanks} 👌 Dès que j'ai ta photo, on voit ce qu'on peut faire. {_price_once(profile)}"
            "Ton numéro WhatsApp pour qu'on t'envoie le devis ?"
        ).replace("  ", " ")

    # « Ta page a combien d'abonnés environ ? »
    if "abonnés" in asked or "abonnes" in asked:
        memory.set_stage(profile, "offre")
        profile["last_question"] = ""
        profile["open_question"] = ""
        return (
            f"{thanks} 👌 C'est noté, on adapte la modération à ton volume. "
            "Ton numéro WhatsApp pour qu'on te fasse une proposition adaptée ?"
        )

    # « C'est une pub, un Reel, ou une présentation de ton activité ? »
    if "reel" in asked and ("pub" in asked or "présentation" in asked):
        memory.set_stage(profile, "offre")
        profile["last_question"] = ""
        profile["open_question"] = ""
        return (
            f"{thanks} 👌 C'est noté. Le prix dépend de la durée et du style, "
            "donc on te fait un devis gratuit. Ton numéro WhatsApp pour te l'envoyer ?"
        )

    # « Tu fais quoi comme activité ? » : on reprend SES mots, on propose l'offre adaptée,
    # puis seulement on demande le numéro (offre -> devis -> closing).
    if "activité" in asked or "quel type de business" in asked:
        if profile.get("sector") or len(low.split()) <= 10:
            memory.set_stage(profile, "devis")
            profile["last_question"] = ""
            profile["open_question"] = ""
            sector = profile.get("sector", "")
            about = _activity_phrase(text, sector)
            offer = _offer_for(profile)
            return (
                f"{thanks} 👌 {about}{offer} "
                "Je te prépare le devis gratuit : laisse-moi ton numéro WhatsApp et Ndine te l'envoie."
            ).replace("  ", " ")
    return None


def _to_second_person(text: str) -> str:
    text = re.sub(r"\bmon\b", "ton", text, flags=re.I)
    text = re.sub(r"\bma\b", "ta", text, flags=re.I)
    text = re.sub(r"\bmes\b", "tes", text, flags=re.I)
    text = re.sub(r"\bj['’]ai\b", "tu as", text, flags=re.I)
    text = re.sub(r"\bje\s+suis\b", "tu es", text, flags=re.I)
    return text


def _activity_phrase(text: str, sector: str) -> str:
    """Reprend l'activité du client avec ses mots, à la 2e personne, sans phrase bancale."""
    clean = text.strip(" .!?,;")
    low = clean.casefold()

    # « je crée / je vends / je fais / je gère X » -> « tu crées / vends / fais / gères X »
    verbs = {"crée": "crées", "cree": "crées", "vends": "vends", "vend": "vends", "fais": "fais",
             "gère": "gères", "gere": "gères", "tiens": "tiens", "propose": "proposes",
             "produis": "produis", "organise": "organises", "propose": "proposes"}
    m = re.match(r"^je\s+(" + "|".join(verbs) + r")\s+(.+)$", clean, flags=re.I)
    if m and len(m.group(2).split()) <= 7:
        return f"Tu {verbs[m.group(1).casefold()]} {_to_second_person(m.group(2))}, c'est noté. "

    # « j'ai un salon / une boutique / mon restaurant » -> « tu as un salon »
    m = re.match(r"^j['’]ai\s+(.+)$", clean, flags=re.I)
    if m and len(m.group(1).split()) <= 7:
        return f"Tu as {_to_second_person(m.group(1))}, c'est noté. "

    # « je suis coiffeuse / dans la mode » -> « tu es coiffeuse / dans la mode »
    m = re.match(r"^je\s+suis\s+(.+)$", clean, flags=re.I)
    if m and len(m.group(1).split()) <= 6:
        return f"Tu es {_to_second_person(m.group(1))}, c'est noté. "

    # Réponse courte (« la mode », « coach sportif », « restaurant »)
    if 0 < len(clean.split()) <= 4:
        return f"{_to_second_person(clean).capitalize()}, c'est noté. "
    return f"Une activité dans {sector}, c'est noté. " if sector else ""


def _offer_for(profile: dict[str, Any]) -> str:
    """L'offre qui correspond au service choisi, avec son vrai prix."""
    service = profile.get("service", "")
    usage = profile.get("usage", "")
    if service == "chatbot":
        what = {
            "vendre": "un bot WhatsApp qui présente tes produits et prend les commandes à ta place",
            "répondre": "un bot WhatsApp qui répond à tes clients 24h/24",
            "rendez-vous": "un bot WhatsApp qui prend et confirme tes rendez-vous",
        }.get(usage, "un bot WhatsApp qui travaille pour toi")
        return f"Pour toi, ce serait {what}. {_PRICE_HINT.get('chatbot', '')}"
    if service in _PRICE_HINT:
        return _PRICE_HINT[service]
    return ""


_OWN_QUESTION = re.compile(
    r"\b(combien|prix|tarif|co[uû]t|c['’]est\s+quoi|quel(le)?s?\s+(est|sont)|comment|d[ée]lai|"
    r"livr|pay|garantie|rembours|marche|fonctionne|diff[ée]rence|exemple)\b|\?",
    re.IGNORECASE,
)


def _clean_subject(text: str) -> str:
    """« Pour mon anniversaire » -> « ton anniversaire » (on reprend ses mots, à la 2e personne)."""
    subject = re.sub(r"^(c['’]est\s+)?(pour|pr|pour\s+le|pour\s+la)\s+", "", text.strip(), flags=re.I)
    subject = subject.strip(" .!?,;")
    if not subject or len(subject.split()) > 10:
        return ""
    # « la fête de mon salon » -> « la fête de ton salon » : on parle à lui, à la 2e personne.
    subject = re.sub(r"\bmon\b", "ton", subject, flags=re.I)
    subject = re.sub(r"\bma\b", "ta", subject, flags=re.I)
    subject = re.sub(r"\bmes\b", "tes", subject, flags=re.I)
    return subject


def _is_own_question(low: str) -> bool:
    """Le client pose une question à lui : elle prime sur la nôtre."""
    return bool(_OWN_QUESTION.search(low))


def phone_thanks(profile: dict[str, Any], lang: str) -> str | None:
    """Remerciement après un numéro : on rappelle ce qui a été compris."""
    if lang != "fr":
        return None
    name = profile.get("name", "")
    service = profile.get("service", "")
    who = f"Merci {name}" if name else "Merci"
    what = f" pour ton projet {_service_label(service)}" if service and _service_label(service) else ""
    return (
        f"{who}, c'est noté 🙌 L'équipe Komara te contacte très vite sur WhatsApp{what}. "
        "En attendant, tu as une question ou quelque chose à ajouter ?"
    )


# =================================================================
# PRÉSENTATION : le client se présente ou décrit son activité
# =================================================================
_INTRO = re.compile(
    r"\b(je\s+m['’]appelle|je\s+me\s+nomme|moi\s+c['’]est|mon\s+nom\s+est|"
    r"j['’]ai\s+(une|un|mon|ma)\s+\w+|je\s+(vends|tiens|g[èe]re|travaille|fais|suis\s+(commer|entrepre|g[ée]rant|patron)))",
    re.IGNORECASE,
)


def is_introduction(text: str) -> bool:
    """Le client parle de lui : prénom, activité. Pas une question."""
    return bool(_INTRO.search(text)) and "?" not in text


def reply_introduction(profile: dict[str, Any], text: str, before: dict[str, Any]) -> str | None:
    """Accueille ce que le client vient de dire sur lui, puis fait avancer."""
    name = profile.get("name", "")
    sector = profile.get("sector", "")
    service = profile.get("service", "")
    learned_name = bool(name) and name != before.get("name")
    learned_sector = bool(sector) and sector != before.get("sector")
    if not (learned_name or learned_sector):
        return None

    hello = f"Enchantée {name} 🙌" if learned_name else "Parfait 🙌"
    sector_line = {
        "boutique": "Une boutique, c'est idéal pour un bot : il présente tes articles et prend les commandes même la nuit.",
        "restaurant": "Un restaurant, c'est parfait : le bot prend les commandes et les réservations à ta place.",
        "immobilier": "En immobilier, le bot qualifie les clients et planifie les visites tout seul.",
        "beauté": "Dans la beauté, le bot gère les rendez-vous et relance tes clientes.",
        "école": "Pour une école ou une formation, le bot répond aux parents et gère les inscriptions.",
        "santé": "Dans la santé, le bot gère les rendez-vous et répond aux questions courantes.",
        "transport": "Dans le transport, le bot prend les réservations et confirme les trajets.",
    }.get(sector, "")

    profile["open_question"] = ""
    if service:
        memory.set_stage(profile, "offre")
        close = "Je te prépare un devis gratuit pour ton projet ? Laisse-moi ton numéro WhatsApp et l'équipe te l'envoie."
    else:
        memory.set_stage(profile, "besoin")
        close = "Dis-moi ce que tu veux mettre en place, et je te propose la bonne solution."
    return " ".join(part for part in (hello, sector_line, close) if part)


def _one_question_only(text: str) -> str:
    """Garde une seule question : la dernière, qui fait avancer la vente.

    Deux questions à la suite (« Tu veux voir nos services ? Tu as un projet ? »)
    donnent une impression de formulaire. On garde la dernière.
    """
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    questions = [i for i, sentence in enumerate(sentences) if "?" in sentence]
    if len(questions) <= 1:
        return text.strip()
    keep = questions[-1]
    out = [sentence for i, sentence in enumerate(sentences) if "?" not in sentence or i == keep]
    return " ".join(out).strip()


# =================================================================
# SALUTAISONS ET « COMMENT TU VAS » : on répond comme un humain,
# puis on ramène au projet (sinon on tombe sur une fiche au hasard).
# =================================================================
_WELLBEING_RX = re.compile(
    r"\b(comment (tu |vous )?vas?( ?-?tu| ?-?vous)?|tu vas bien|vous allez bien|"
    r"ca va|ça va|sa va|comment ca va|comment ça va|comment vas tu|tu va bien|"
    r"et toi|et vous|how are you|todo bien)\b",
    re.I,
)


def wellbeing_reply(text: str, profile: dict, lang: str = "fr") -> str | None:
    """Répond à « comment tu vas » / « tu vas bien » sans sortir une fiche tarif."""
    low = (text or "").casefold().strip()
    # Langage SMS courant : « slt cv », « bjr sa va »
    for sms, full in (("slt", "salut"), ("cv", "ca va"), ("bjr", "bonjour"), ("bsr", "bonsoir"), ("sa va", "ca va")):
        low = low.replace(sms, full)
    if not low or len(low.split()) > 9:
        return None
    if not _WELLBEING_RX.search(low):
        return None

    name = (profile or {}).get("name", "")
    service = (profile or {}).get("service", "")
    who = f" {name}" if name else ""

    if service:
        label = _service_label(service)
        return (
            f"Ça va bien{who}, merci 😊 Content que tu repasses.\n\n"
            f"On avance sur ton projet {label} ? Dis-moi où tu en es."
        )
    return f"Ça va très bien{who}, merci 😊 Et toi ? Dis-moi ce que tu veux lancer, je m'occupe du reste."
