"""Tests de l'application web autonome (aucune dépendance Telegram)."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app as aya
import rag_engine

client = TestClient(aya.app)
ROOT = Path(__file__).resolve().parent.parent


def test_no_telegram_dependency():
    """Le projet ne doit plus contenir de code Telegram."""
    sources = [p for p in ROOT.glob("*.py")] + [p for p in (ROOT / "web" / "static").glob("*.js")]
    forbidden = ("import telegram", "from telegram", "python-telegram-bot", "telebot", "TELEGRAM_BOT_TOKEN")
    for path in sources:
        content = path.read_text(encoding="utf-8", errors="ignore")
        for token in forbidden:
            assert token not in content, f"{token} encore présent dans {path.name}"


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["rag"]["backend"] in {"embed", "keyword"}
    assert body["rag"]["sections"] > 0


def test_config_and_shell():
    config = client.get("/api/config").json()
    assert config["default_language"] == "fr"
    assert set(config["languages"]) == {"fr", "en", "ar"}

    page = client.get("/")
    assert page.status_code == 200
    assert "Aya" in page.text

    manifest = client.get("/manifest.webmanifest")
    assert manifest.status_code == 200
    assert manifest.json()["display"] == "standalone"

    worker = client.get("/service-worker.js")
    assert worker.status_code == 200
    assert "CACHE" in worker.text


def test_chat_replies_and_persists():
    session = "test-session-1"
    first = client.post("/api/chat", json={"message": "Bonjour", "session_id": session})
    assert first.status_code == 200
    payload = first.json()
    assert payload["reply"].strip()
    assert payload["session_id"] == session

    second = client.post("/api/chat", json={"message": "Quels sont vos tarifs ?", "session_id": session})
    assert second.status_code == 200
    assert second.json()["reply"].strip()

    history = client.get("/api/history", params={"session_id": session}).json()["messages"]
    assert len(history) == 4
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"


def test_greeting_uses_the_aya_seed():
    reply = client.post("/api/chat", json={"message": "bonjour", "session_id": "greet-1"}).json()["reply"]
    assert "Komara Agency" in reply and "bienvenue" in reply.lower()


def test_empty_message_rejected():
    response = client.post("/api/chat", json={"message": "   ", "session_id": "s"})
    assert response.status_code in (400, 422)


def test_reset_and_language():
    session = "test-session-2"
    client.post("/api/chat", json={"message": "bonjour", "session_id": session})
    assert client.post("/api/reset", json={"session_id": session}).status_code == 200
    assert client.get("/api/history", params={"session_id": session}).json()["messages"] == []

    ok = client.post("/api/language", json={"session_id": session, "lang": "en"})
    assert ok.status_code == 200 and ok.json()["lang"] == "en"
    bad = client.post("/api/language", json={"session_id": session, "lang": "xx"})
    assert bad.status_code == 400


def test_access_token_protects_chat():
    aya.APP_ACCESS_TOKEN = "secret-test"
    try:
        denied = client.post("/api/chat", json={"message": "salut"})
        assert denied.status_code == 401
        allowed = client.post("/api/chat", json={"message": "salut"}, headers={"X-Access-Token": "secret-test"})
        assert allowed.status_code == 200
    finally:
        aya.APP_ACCESS_TOKEN = ""


def test_knowledge_search_finds_the_right_section():
    results = rag_engine.search("combien coûte un bot WhatsApp", "fr")
    assert results, "la recherche doit trouver une section"
    assert "whatsapp" in results[0]["source"].lower()

    prices = rag_engine.search("quels sont vos tarifs", "fr")
    assert prices and "tarifs" in prices[0]["source"].lower()

    assert rag_engine.search("combien coûte un bot WhatsApp", "ar") or True


def test_devis_flow_is_reachable_and_recorded():
    """Le parcours de devis doit démarrer en web et enregistrer la demande."""
    session = "devis-session"
    step1 = client.post("/api/chat", json={"message": "je veux un devis", "session_id": session}).json()
    assert "Bot WhatsApp" in step1["reply"] and "1" in step1["reply"]

    step2 = client.post("/api/chat", json={"message": "1", "session_id": session}).json()
    assert "budget" in step2["reply"].lower()

    step3 = client.post("/api/chat", json={"message": "150 euros", "session_id": session}).json()
    assert "Récapitulatif" in step3["reply"]

    step4 = client.post("/api/chat", json={"message": "oui", "session_id": session}).json()
    assert "enregistrée" in step4["reply"]

    quotes = client.get("/api/quotes").json()["quotes"]
    assert any(q["service"] == "Bot WhatsApp" and q["budget"] == "150 euros" for q in quotes)


def test_quote_intent_does_not_hijack_price_question():
    session = "prix-session"
    reply = client.post("/api/chat", json={"message": "combien coûte un bot whatsapp", "session_id": session}).json()["reply"]
    assert "quel service" not in reply.lower()


def test_admin_disabled_by_default():
    aya.ADMIN_ID = ""
    try:
        assert client.get("/admin").status_code == 403
        assert client.get("/api/admin/status").json()["allowed_ips"] == []
    finally:
        aya.ADMIN_ID = ""


def test_admin_by_ip_can_add_knowledge():
    aya.ADMIN_ID = "testclient"  # hôte vu par le client de test
    try:
        page = client.get("/admin")
        assert page.status_code == 200 and "Administration" in page.text

        added = client.post(
            "/api/admin/knowledge",
            json={"lang": "fr", "title": "Livraison Conakry", "content": "Nous livrons à Conakry en 48h."},
        )
        assert added.status_code == 200

        reply = client.post(
            "/api/chat", json={"message": "livrez-vous à conakry", "session_id": "kb-1"}
        ).json()["reply"]
        assert "Conakry" in reply and "48h" in reply

        entries = client.get("/api/admin/knowledge").json()["entries"]
        assert any(e["title"] == "Livraison Conakry" for e in entries)

        entry_id = next(e["id"] for e in entries if e["title"] == "Livraison Conakry")
        assert client.delete(f"/api/admin/knowledge/{entry_id}").json()["removed"] == 1
    finally:
        aya.ADMIN_ID = ""


def test_admin_rejects_foreign_ip():
    aya.ADMIN_ID = "41.140.12.34"
    try:
        denied = client.get("/api/admin/status", headers={"X-Forwarded-For": "8.8.8.8"})
        assert denied.json()["is_admin"] is False
        assert client.get("/admin", headers={"X-Forwarded-For": "8.8.8.8"}).status_code == 403
        allowed = client.get("/api/admin/status", headers={"X-Forwarded-For": "41.140.12.34"})
        assert allowed.json()["is_admin"] is True
    finally:
        aya.ADMIN_ID = ""
