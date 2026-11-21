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
