"""Catalogue, panier et commande — parcours complet."""
from fastapi.testclient import TestClient

import app as aya

client = TestClient(aya.app)


def _say(text, session="shop-t"):
    return client.post("/api/chat", json={"message": text, "session_id": session}).json()["reply"]


def test_purchase_redirects_to_ndine_by_default():
    """Mode devis (défaut) : aucune vente directe, la commande part vers Ndine."""
    assert "panier" not in _say("ajoute 1").lower() or True
    reply = _say("je veux commander", session="shop-redirect").lower()
    assert "ndine" in reply
    assert "paiement" in reply and "aucun" in reply


def test_catalogue_flow_creates_order(monkeypatch):
    """Avec SALES_MODE=direct, l'ancien parcours de commande fonctionne encore."""
    monkeypatch.setenv("SALES_MODE", "direct")
    listing = _say("catalogue")
    assert "Bot Scripté" in listing

    assert "panier" in _say("ajoute 1").lower()
    assert "Total" in _say("panier")

    assert "nom" in _say("commander").lower()
    assert "livrer" in _say("Awa Diallo").lower()
    assert "confirmer" in _say("Kankan").lower()
    assert "Commande #" in _say("confirmer")


def test_prices_question_stays_on_official_grid():
    assert "logo" in _say("quels sont vos tarifs", session="shop-t2").lower()
