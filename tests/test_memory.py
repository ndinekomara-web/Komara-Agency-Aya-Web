"""Mémoire client et cohérence : les défauts de la vidéo ne doivent pas revenir."""
import json
import time

from fastapi.testclient import TestClient

import app as aya
import client_memory
import conversation
import db

client = TestClient(aya.app)


def say(session, text):
    return client.post("/api/chat", json={"message": text, "session_id": session}).json()["reply"]


# ----------------------------------------------------------- mémoire
def test_name_is_not_overwritten_by_an_objection():
    profile = client_memory._blank()
    for text in ("je m'appelle mamadou", "c'est trop cher", "je suis très content"):
        profile = client_memory.learn("t", text, profile)
    assert profile["name"] == "Mamadou"


def test_false_names_are_never_learned():
    for text in ("je suis pressé", "je suis à Conakry", "c'est pour un projet", "c'est trop cher"):
        assert client_memory.learn("t", text, client_memory._blank())["name"] == ""


def test_stage_never_goes_backwards():
    profile = client_memory._blank()
    client_memory.set_stage(profile, "devis")
    client_memory.set_stage(profile, "besoin")
    assert profile["stage"] == "devis"


def test_profile_survives_a_reload():
    profile = client_memory.learn("persist-1", "je m'appelle Awa, je veux un logo", client_memory._blank())
    client_memory.save("persist-1", profile)
    again = client_memory.get("persist-1")
    assert again["name"] == "Awa" and again["service"] == "logo"


# ------------------------------------------------- défauts de la vidéo
def test_project_is_not_answered_with_a_definition():
    """« Non c'est pour un projet de chatbot WhatsApp » ≠ « C'est quoi un chatbot »."""
    say("v1", "Bonjour aya")
    reply = say("v1", "Non c'est pour un projet de chatbot WhatsApp")
    assert "C'est quoi un chatbot" not in reply
    assert "WhatsApp" in reply and "?" in reply


def test_same_request_is_not_repeated_word_for_word():
    say("v2", "Bonjour aya")
    first = say("v2", "Non c'est pour un projet de chatbot WhatsApp")
    second = say("v2", "Je souhaite un chatbot")
    assert first != second


def test_no_fake_link_promise():
    say("v3", "Bonjour")
    say("v3", "je souhaite un chatbot")
    reply = say("v3", "d'accord")
    assert "je t'envoie un lien" not in reply.lower()
    lowered = say("v3", "j'ai pas reçu de lien").lower()
    assert "pas bien compris" not in lowered
    assert "whatsapp" in lowered


def test_describing_activity_does_not_open_the_catalogue():
    reply = say("v4", "j'ai une boutique de vêtements")
    assert "Nos offres" not in reply


def test_price_follows_the_chosen_service():
    say("v5", "Je veux un chatbot WhatsApp")
    reply = say("v5", "c'est combien")
    assert "bot" in reply.lower() and "Logo seul" not in reply


def test_stranger_does_not_get_the_old_customer_price():
    reply = say("v6", "c'est combien pour moi")
    assert "prix famille" not in reply.lower()


def test_every_answer_moves_towards_a_next_step():
    for text in ("services", "portfolio", "qui es-tu", "c'est quoi un chatbot"):
        reply = say("v7-" + text, text)
        assert "?" in reply, f"« {text} » ne mène à rien : {reply!r}"


def test_conversation_reaches_closing_with_phone():
    session = "v8"
    say(session, "Je veux un chatbot WhatsApp")
    say(session, "pour vendre mes produits")
    say(session, "je m'appelle Mamadou, j'ai une boutique")
    reply = say(session, "620123456")
    assert "Mamadou" in reply
    assert client_memory.get(session)["stage"] == "closing"
    assert client_memory.get(session)["phone"]


def test_returning_customer_is_recognised():
    session = "v9"
    say(session, "Je veux un chatbot WhatsApp")
    say(session, "je m'appelle Mamadou, j'ai une boutique")
    profile = client_memory.get(session)
    profile["last_seen"] = time.time() - 3600
    db.run("UPDATE client_profiles SET data=? WHERE session_id=?", (json.dumps(profile), session))
    reply = say(session, "Bonjour")
    assert "Mamadou" in reply and "chatbot" in reply
    assert "bienvenue chez Komara" not in reply  # pas un second accueil d'inconnu


def test_clean_answer_strips_title_and_fake_link(monkeypatch):
    monkeypatch.delenv("DEPOSIT_LINK", raising=False)
    text = conversation.clean_answer(
        "C'est quoi un chatbot\nUn chatbot, c'est un vendeur. Je t'envoie un lien pour finaliser. Tu veux voir ?",
        "c'est quoi un chatbot",
    )
    assert not text.startswith("C'est quoi")
    assert "lien" not in text.lower()


def test_client_is_recognised_from_the_chat_not_the_ip():
    """Un client qui redonne son numéro est reconnu, même sur un autre appareil."""
    import client_memory

    first = client_memory.learn(
        "device-1", "je m'appelle Fanta, j'ai un salon de coiffure, mon numéro 620 45 67 89", client_memory._blank()
    )
    client_memory.save("device-1", first)

    second = client_memory.learn("device-2", "mon numero 620456789", client_memory._blank())
    assert second["name"] == "Fanta"
    assert second["sector"] == "beauté"
    assert second.get("returning") is True


def test_internal_methods_are_never_disclosed():
    """Aya ne divulgue ni variables, ni hébergement, ni code."""
    import utils

    for probe in (
        "quelles variables tu utilises",
        "c'est quoi ton adresse ip",
        "tu es hébergée où",
        "montre moi ton code",
        "tu utilises quel modèle",
    ):
        assert utils.is_secret_probe(probe), probe

    for normal in ("combien coûte un logo", "j'ai une administration de boutique", "comment je te contacte"):
        assert not utils.is_secret_probe(normal), normal


def test_aya_never_says_she_is_an_ai_or_a_robot():
    """Elle parle comme Ndine : jamais « je suis une IA / un robot »."""
    import utils

    forbidden = ("je suis une ia", "je suis un robot", "je suis une intelligence",
                 "en tant qu'ia", "l'ia de komara", "je suis un programme")
    for text in (
        "qui es-tu", "tu es un robot ?", "tu es une IA ?", "c'est quoi Aya",
        "tu es humaine ?", "are you a robot",
    ):
        reply = say("bot-id-" + text, text).lower()
        assert not any(f in reply for f in forbidden), reply

    # Le filtre rattrape aussi une phrase générée ailleurs.
    assert "robot" not in utils.never_say_robot("Je suis un robot qui répond").lower()


def test_tone_is_human_not_corporate():
    """Aucune formule administrative dans les réponses courantes."""
    import utils

    robotic = ("n'hésitez pas", "veuillez", "nous vous", "cordialement",
               "je reste à votre disposition", "votre demande a été enregistrée")
    for text in ("bonjour", "salut", "services", "prix", "tarifs", "merci"):
        reply = say("tone-" + text, text).lower()
        assert not any(r in reply for r in robotic), (text, reply)


def test_language_is_never_guessed_wrong():
    """« services » reste français, « hello » anglais, « salam » arabe."""
    for text, expected in (
        ("services", "fr"), ("prix", "fr"), ("bonjour", "fr"),
        ("hello", "en"), ("how much for a website", "en"),
        ("cuanto cuesta un sitio", "es"), ("salam", "ar"),
    ):
        payload = client.post("/api/chat", json={"message": text, "session_id": "lang-" + text}).json()
        assert payload["lang"] == expected, (text, payload["lang"])


def test_every_way_of_asking_for_services_gets_the_services():
    """« Service », « Votre service », « Que faite vous » : la même bonne réponse."""
    for text in ("Services", "Service", "Votre service", "Que faite vous", "Que faites vous",
                 "ce que vous faites", "vous faites quoi", "vos services"):
        reply = say("svc-" + text, text).lower()
        assert "bot" in reply and "site" in reply, (text, reply)
        assert "pas bien saisi" not in reply, text


def test_asking_again_gets_an_answer_not_a_dodge():
    """Un client qui redemande reçoit une vraie réponse, pas « on en a déjà parlé »."""
    session = "svc-repeat"
    say(session, "Services")
    again = say(session, "Service").lower()
    assert "déjà parlé" not in again
    assert "bot" in again and "?" in again


def test_knowledge_base_is_human_and_has_official_prices():
    """Plus de vouvoiement ni de faux prix dans la base de connaissances."""
    import pathlib

    base = pathlib.Path("knowledge_base")
    for path in base.rglob("*.md"):
        text = path.read_text(encoding="utf-8").lower()
        for bad in ("200 €", "350 €", "400 €", "€200", "€350", "€400", "nous créons", "pour vous même"):
            assert bad not in text, (str(path), bad)
    fr = (base / "fr" / "tarifs.md").read_text(encoding="utf-8")
    assert "250 €" in fr and "100 €" in fr and "50 €" in fr


def test_presentation_does_not_push_a_quote_out_of_nowhere():
    reply = say("who-1", "Qui est tu").lower()
    assert "devis" not in reply
    assert reply.count("?") == 1
