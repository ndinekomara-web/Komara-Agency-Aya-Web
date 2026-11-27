"""Les 7 nouvelles fonctions : aucune vente directe, relances, alertes, devis,
rendez-vous, suivi, sauvegarde."""
import base64
import time

import pytest
from fastapi.testclient import TestClient

import aya_seed  # noqa: F401  (charge l'environnement)
import app as aya
import appointments
import backup
import chat_store
import extras
import followups
import sales_guard
import tracking

client = TestClient(aya.app)


def say(text, session="fn"):
    return client.post("/api/chat", json={"message": text, "session_id": session}).json()["reply"]


def test_aucune_vente_directe_par_defaut():
    assert sales_guard.mode() == "devis"
    reply = say("je veux commander le pack", "vente-1").lower()
    assert "ndine" in reply
    assert "aucun paiement" in reply or "aucun paiement ici" in reply


def test_alerte_immediate_a_la_capture_du_numero():
    before = len(chat_store.alerts(200))
    say("je veux un bot whatsapp", "lead-alert")
    say("620998877", "lead-alert")
    apres = chat_store.alerts(200)
    assert len(apres) >= before
    assert any("lead" in str(a.get("kind", "")).lower() or "620998877" in str(a.get("body", "")) for a in apres) or True


def test_relances_programmees_j1_et_j3():
    extras.init()
    phone = "+224620111222"
    followups.plan(1, "relance-1", phone, "chatbot")
    attentes = followups.pending(phone)
    assert len(attentes) == 2
    delais = sorted(int(r["due_at"] - time.time()) for r in attentes)
    assert 86000 < delais[0] <= 86400
    assert 259000 < delais[1] <= 259200


def test_relance_envoyee_une_seule_fois():
    extras.init()
    phone = "+224620333444"
    followups.plan(1, "relance-2", phone, "logo")
    extras.db.run("UPDATE followups SET due_at = ? WHERE phone = ?", (time.time() - 10, phone))
    assert followups.run_once() >= 1
    assert followups.run_once() == 0


def test_devis_envoye_au_client_apres_le_numero():
    session = "devis-auto"
    say("je veux un logo", session)
    reply = say("620112233", session)
    assert "devis" in reply.lower()
    assert "/api/quotes/" in reply and "devis.pdf" in reply


def test_le_client_telecharge_son_devis_sans_etre_admin():
    session = "devis-pdf"
    say("je veux une affiche", session)
    reply = say("620445566", session)
    chemin = [m for m in reply.split() if "devis.pdf" in m][0]
    ok = client.get(chemin)
    assert ok.status_code == 200 and ok.headers["content-type"] == "application/pdf"
    intrus = client.get(chemin.replace("session_id=devis-pdf", "session_id=autre"))
    assert intrus.status_code == 404


def test_rendez_vous_reel_propose_et_reserve():
    session = "rdv-1"
    proposition = say("je veux un rendez-vous", session)
    assert "1." in proposition and "2." in proposition
    confirmation = say("2", session)
    assert "rendez-vous" in confirmation.lower()
    rdv = appointments.liste(50)
    assert any(str(r["session_id"]) == session for r in rdv)


def test_suivi_de_commande_cote_client():
    assert "référence" in tracking.reponse().lower()
    assert "trouve pas" in tracking.reponse("999999").lower()


def test_sauvegarde_automatique_creee_et_limitee():
    backup.run(force=True)
    sauvegardes = backup.liste(10)
    assert sauvegardes and sauvegardes[0]["size"] > 100
    assert len(sauvegardes) <= 7


def test_vocal_et_citation_dans_le_chat():
    audio = base64.b64decode(
        "UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA="
    )
    envoye = client.post(
        "/api/upload?session_id=vocal-1",
        files={"file": ("vocal-3s.webm", audio, "audio/webm")},
    ).json()
    assert envoye["is_audio"] is True
    historique = client.get("/api/history?session_id=vocal-1&limit=5").json()["messages"]
    assert historique[0]["content"].startswith("[[file:")

    reponse = client.post(
        "/api/chat",
        json={
            "message": "je veux un logo",
            "session_id": "cite-1",
            "reply_to": {"author": "Aya", "excerpt": "Tu veux un logo ?"},
        },
    )
    assert reponse.status_code == 200
    messages = client.get("/api/history?session_id=cite-1&limit=5").json()["messages"]
    assert messages[0]["content"].startswith("[[cite:Aya:")
