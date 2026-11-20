"""Catalogue, panier et commande — parcours complet."""
from fastapi.testclient import TestClient

import app as aya

client = TestClient(aya.app)


def _say(text, session="shop-t"):
    return client.post("/api/chat", json={"message": text, "session_id": session}).json()["reply"]


def test_catalogue_flow_creates_order():
    listing = _say("catalogue")
    assert "Bot Scripté" in listing

    assert "panier" in _say("ajoute 1").lower()
    assert "Total" in _say("panier")

    assert "nom" in _say("commander").lower()
    assert "livrer" in _say("Awa Diallo").lower()
    assert "confirmer" in _say("Kankan").lower()
    assert "Commande #" in _say("confirmer")


def test_prices_question_stays_on_official_grid():
    assert "Logo seul" in _say("quels sont vos tarifs", session="shop-t2")
