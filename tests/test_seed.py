"""Les réponses viennent du seed d'Aya (aya_seed.py), pas d'une invention."""
import seed_engine
import aya_seed
from fastapi.testclient import TestClient

import app as aya

client = TestClient(aya.app)


def ask(text, session="seed-t"):
    return client.post("/api/chat", json={"message": text, "session_id": session}).json()


def test_seed_loaded():
    assert len(aya_seed.SEED_QR) >= 60
    assert seed_engine.stats()["fr"] > 100


def test_prices_come_from_seed():
    reply = ask("quels sont vos tarifs")["reply"]
    assert "Logo seul" in reply and "50" in reply and "Affiche" in reply and "30" in reply


def test_real_user_messages_from_screenshot():
    """Les trois messages qui échouaient sur le téléphone."""
    for message in ("Montre-moi vos réalisations", "Bonjour", "Portfolio"):
        reply = ask(message)["reply"]
        assert "pas bien compris" not in reply


def test_gallery_flag_for_portfolio():
    assert ask("Montre-moi vos réalisations")["gallery"] is True
    assert ask("Portfolio")["gallery"] is True
    assert ask("prix")["gallery"] is False
    assert len(client.get("/api/portfolio").json()["items"]) >= 6


def test_no_telegram_only_instructions():
    answers = " ".join(a for _, a in aya_seed.SEED_QR)
    for dead in ("Tape le bouton", "Tape 'menu'", "Tape 'humain'", "/promo"):
        assert dead not in answers, dead


def test_objection_and_intent():
    assert "chaque euro" in ask("c'est trop cher")["reply"].lower()
    assert "logo" in ask("je veux un logo")["reply"].lower()


def test_unknown_still_polite():
    """Le charabia reçoit une réponse humaine, pas une fiche au hasard."""
    reply = ask("blablabla xyz qsdf", session="unknown-fresh")["reply"].lower()
    assert "saisi" in reply or "redire" in reply
    assert "50" not in reply


def test_prices_can_be_changed_by_env(monkeypatch):
    import importlib

    monkeypatch.setenv("PRICE_LOGO", "75 €")
    importlib.reload(aya_seed)
    seed_engine.reload()
    assert "75 €" in seed_engine.find_answer("prix")["answer"]
    monkeypatch.delenv("PRICE_LOGO")
    importlib.reload(aya_seed)
    seed_engine.reload()


def test_official_prices_everywhere():
    """Les prix du site officiel, partout, et un prix par service."""
    grid = ask("tarifs", session="p-grid")["reply"]
    assert "250" in grid and "Site vitrine" in grid

    site = ask("combien coûte un site vitrine", session="p-site")["reply"]
    assert "250" in site and "Logo seul" not in site

    logo = ask("prix d'un logo", session="p-logo")["reply"]
    assert "50" in logo and "250" not in logo


def test_no_invented_discount():
    """Aucune fausse promo : le bot ne s'invente pas de prix barrés."""
    reply = ask("prix du bot", session="p-bot")["reply"].lower()
    assert "au lieu de" not in reply and "200" not in reply


def test_greeting_variants_are_understood():
    """« Comment tu vas » et « Tu va bien » ne tombent plus sur une fiche tarif."""
    for text in ("Comment tu vas", "Tu va bien"):
        reply = ask(text, session="p-how-" + text)["reply"].lower()
        assert "tarif" not in reply and "devis" not in reply
        assert "merci" in reply
