"""Filet de sécurité IA : il répond aux questions inconnues, sans jamais déraper."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest


class _Serveur(BaseHTTPRequestHandler):
    reponse = {"answer": "On fait aussi des vidéos TikTok, tu veux un exemple ?"}
    recu = []

    def do_POST(self):  # noqa: N802
        taille = int(self.headers.get("Content-Length", 0))
        _Serveur.recu.append(json.loads(self.rfile.read(taille) or b"{}"))
        corps = json.dumps(_Serveur.reponse).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def log_message(self, *a):
        pass


@pytest.fixture
def n8n(monkeypatch):
    serveur = HTTPServer(("127.0.0.1", 0), _Serveur)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    monkeypatch.setenv("N8N_FALLBACK_URL", f"http://127.0.0.1:{serveur.server_port}/webhook")
    monkeypatch.setenv("N8N_FALLBACK_TIMEOUT", "3")
    yield serveur
    serveur.shutdown()


def test_question_inconnue_recoit_la_reponse_du_modele(n8n):
    import fallback_ia

    _Serveur.reponse = {"answer": "On fait aussi des vidéos TikTok, tu veux un exemple ?"}
    reponse = fallback_ia.demander("Est-ce que vous faites des vidéos TikTok ?", "fr", {"service": "video"})
    assert reponse and "TikTok" in reponse
    assert _Serveur.recu[-1]["question"].startswith("Est-ce que")
    assert _Serveur.recu[-1]["langue"] == "fr"


def test_prix_invente_est_refuse(n8n):
    import fallback_ia

    _Serveur.reponse = {"answer": "Un site coûte 500 €, prix spécial pour toi."}
    assert fallback_ia.demander("Combien un site pour une école ?", "fr", {}) is None


def test_aveu_d_ia_est_refuse(n8n):
    import fallback_ia

    _Serveur.reponse = {"answer": "Je suis une IA créée par Komara Agency."}
    assert fallback_ia.demander("Qui t'a créée ?", "fr", {}) is None


def test_pas_de_modele_pour_un_ok_ou_un_numero():
    import fallback_ia

    for texte in ("ok", "620123456", "+212 701 986 219", "merci"):
        assert not fallback_ia.est_une_vraie_question(texte), texte


def test_sans_url_le_filet_est_inactif(monkeypatch):
    import fallback_ia

    monkeypatch.delenv("N8N_FALLBACK_URL", raising=False)
    assert fallback_ia.disponible() is False
    assert fallback_ia.demander("Est-ce que vous faites du montage ?", "fr", {}) is None


def test_le_chat_sert_la_reponse_du_filet(n8n):
    from fastapi.testclient import TestClient

    import app as aya

    import seed_engine

    question = "Est-ce que vous travaillez avec des ONG internationales ?"
    # Garde-fou : cette question n'a VRAIMENT aucune fiche.
    assert seed_engine.find_answer(question) is None

    _Serveur.reponse = {"answer": "Oui, on accompagne aussi des ONG sur leurs visuels et leurs sites."}
    client = TestClient(aya.app)
    data = client.post("/api/chat", json={"message": question, "session_id": "fb-1"}).json()
    assert "ONG" in data["reply"]
    assert "pas bien saisi" not in data["reply"].lower()
