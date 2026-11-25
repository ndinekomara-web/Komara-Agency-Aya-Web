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
    # Elle peut dire qu'elle prépare les devis (c'est son rôle), mais ne doit
    # pas proposer d'« passer au devis » à quelqu'un qui demande juste qui elle est.
    assert "on passe au devis" not in reply and "je m'en occupe maintenant" not in reply
    assert reply.count("?") == 1


def test_contact_questions_give_the_number_from_the_variable(monkeypatch):
    """« Votre numéro », « Numéro », « Contact » : le vrai numéro, pas « pas saisi »."""
    monkeypatch.setenv("KOMARA_WHATSAPP", "+212 600 111 222")
    import importlib

    import aya_seed
    import seed_engine

    importlib.reload(aya_seed)
    importlib.reload(seed_engine)
    for text in ("Votre numéro", "Numéro", "Contact", "comment te contacter"):
        hit = seed_engine.find_answer(text)
        assert hit, text
        assert "+212 600 111 222" in hit["answer"], (text, hit["answer"])


def test_no_number_is_written_in_the_repository():
    """Le numéro vit uniquement dans la variable d'hébergement."""
    import pathlib

    for path in pathlib.Path(".").rglob("*.py"):
        if "tests" in str(path):
            continue
        assert "701 986" not in path.read_text(encoding="utf-8"), str(path)


def test_rules_stay_neutral():
    """Pas de fausse urgence, pas de fausse promo, pas de promesse invérifiable."""
    forbidden = ("offre spéciale", "offre limitee", "offre limitée", "dernière chance",
                 "derniere chance", "places limitées", "aujourd'hui seulement",
                 "au lieu de", "100% garanti", "garantie de résultat", "résultat garanti")
    for text in ("prix", "tarifs", "services", "prix du bot", "devis", "combien coûte un site"):
        reply = say("neutre-" + text, text).lower()
        assert not any(f in reply for f in forbidden), (text, reply)


def test_answer_to_the_poster_question_is_understood():
    """« Pour mon anniversaire » répond à « quel événement ? » : plus de « pas saisi »."""
    session = "poster-1"
    say(session, "Une affiche")
    reply = say(session, "Pour mon anniversaire").lower()
    assert "pas bien saisi" not in reply
    assert "anniversaire" in reply and "30 €" in reply


def test_every_qualification_question_understands_its_answer():
    for first, answer in (
        ("une retouche photo", "oui"),
        ("modération de page", "5000 abonnés"),
        ("une vidéo", "une pub"),
        ("un logo", "oui j'ai un nom"),
    ):
        session = "qual-" + first
        say(session, first)
        assert "pas bien saisi" not in say(session, answer).lower(), (first, answer)


def test_client_sees_own_file_and_nobody_elses():
    """L'image envoyée s'affiche pour son auteur, et reste invisible pour les autres."""
    import base64

    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    sent = client.post("/api/upload?session_id=owner-A", files={"file": ("a.png", png, "image/png")}).json()
    assert sent["is_image"] and "Ndine" in sent["reply"]

    mine = client.get(sent["url"])
    assert mine.status_code == 200 and mine.headers["content-type"] == "image/png"

    other = client.get(f"/api/upload/{sent['id']}?session_id=owner-B")
    assert other.status_code == 404

    history = client.get("/api/history?session_id=owner-A&limit=5").json()["messages"]
    assert history[0]["content"].startswith("[[file:")


def test_uploaded_html_never_runs_in_the_page():
    trap = client.post(
        "/api/upload?session_id=owner-C", files={"file": ("x.html", b"<script>1</script>", "text/html")}
    ).json()
    reply = client.get(trap["url"])
    assert reply.headers["content-disposition"].startswith("attachment")
    assert reply.headers["x-content-type-options"] == "nosniff"


# ------------------------------------------------- vidéos du 25/11 : parcours jusqu'au closing
def _journey(session, messages):
    return [say(session, m) for m in messages]


def test_politeness_is_never_answered_with_the_phone_number():
    """« Comment vous allez » reçoit une réponse polie, pas le numéro WhatsApp."""
    for text in ("Comment vous allez", "Comment allez-vous", "Comment tu vas", "ça va"):
        reply = say("polite-" + text, text)
        assert "+212" not in reply and "WhatsApp direct" not in reply, (text, reply)
        assert reply.lower().count("dis-moi") <= 1, reply


def test_yes_answers_the_last_question_not_a_bot_script():
    """« Oui » à « on te met en relation ? » demande les coordonnées, rien d'autre."""
    session = "yes-contact"
    say(session, "Contact")
    reply = say(session, "Oui").lower()
    assert "numéro" in reply and "nom de ta page" not in reply


def test_a_client_with_no_project_is_asked_what_he_wants():
    session = "yes-noproject"
    say(session, "Bonjour")
    say(session, "Comment vous allez")
    reply = say(session, "oui").lower()
    assert "nom de ta page" not in reply
    assert "bot" in reply and "site" in reply


def test_bot_price_is_precise_never_a_vague_range():
    """Plus de « un bot va de 50 € à 150 € » : le prix du bot choisi."""
    replies = _journey("price-bot", ["Je souhaite créer un bot", "Vendre"])
    assert "50 € à 150 €" not in replies[1]
    assert "100 €" in replies[1]


def test_site_price_is_never_50_euros():
    replies = _journey("price-site", ["je veux un site", "vitrine"])
    import re

    assert "250 €" in replies[1]
    assert not re.search(r"(?<!\d)50 €, livré", replies[1])


def test_activity_is_understood_and_repeated_back_before_asking_the_number():
    """« Je crée des digitaux » : Aya comprend, propose l'offre, PUIS demande le numéro."""
    replies = _journey("activity-1", ["Je souhaite créer un bot", "Vendre", "Je crée des digitaux"])
    last = replies[-1].lower()
    assert "tu crées des digitaux" in last
    assert "100 €" in last and "numéro" in last


def test_full_journey_to_closing_without_looping():
    """Découverte -> besoin -> offre -> devis -> closing, sans répétition."""
    session = "closing-1"
    replies = _journey(session, [
        "Bonjour", "Comment tu vas", "Je souhaite créer un bot", "Vendre",
        "Je crée des digitaux", "Ok", "620123456", "Ok", "Ok",
    ])
    assert not any("pas bien saisi" in r.lower() for r in replies)
    assert "tel" not in replies[-1] and "numéro whatsapp et ndine finalise" not in replies[-1].lower()
    # Après le numéro, deux « Ok » successifs ne donnent jamais la même phrase.
    assert replies[-1] != replies[-2]
    import client_memory

    profile = client_memory.get(session)
    assert profile["stage"] == "closing" and profile["phone"]


def test_repeated_ok_does_not_ask_for_the_number_forever():
    session = "ok-loop"
    _journey(session, ["Je souhaite créer un bot", "Vendre", "Je crée des digitaux"])
    answers = [say(session, "Ok") for _ in range(4)]
    assert len(set(answers)) >= 3, answers


def test_team_number_is_never_saved_as_a_client(monkeypatch):
    """Si on donne le numéro de l'équipe, on demande le vrai numéro du client."""
    monkeypatch.setenv("KOMARA_WHATSAPP", "+212 600 111 222")
    session = "team-number"
    _journey(session, ["Je souhaite créer un bot", "Vendre", "Je crée des digitaux", "Ok"])
    reply = say(session, "+212600111222").lower()
    assert "équipe" in reply and "propre numéro" in reply
    import client_memory

    assert not client_memory.get(session).get("phone")


def test_same_number_twice_is_not_saved_twice():
    session = "same-number"
    _journey(session, ["Je souhaite créer un bot", "Vendre", "Je crée des digitaux", "Ok"])
    say(session, "620998877")
    assert "déjà noté" in say(session, "620998877").lower()


def test_activities_are_rephrased_in_second_person():
    import conversation

    assert conversation._activity_phrase("Je crée des digitaux", "").startswith("Tu crées des digitaux")
    assert conversation._activity_phrase("J'ai un salon de coiffure", "").startswith("Tu as un salon de coiffure")
    assert "Conakry" in conversation._activity_phrase("J'ai mon restaurant à Conakry", "")
