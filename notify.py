"""
Alertes à l'équipe : un devis confirmé ou un numéro laissé ne doit pas dormir.

Trois canaux, tous facultatifs et sans dépendance :
1. toujours : l'alerte est enregistrée en base et visible dans /admin ;
2. ``ALERT_WEBHOOK_URL`` : POST JSON (Make, Zapier, n8n → WhatsApp/SMS) ;
3. ``ALERT_EMAIL_TO`` + SMTP : e-mail récapitulatif.

Aucun identifiant n'est inventé : sans variable, l'alerte reste dans /admin.
"""
from __future__ import annotations

import json
import logging
import os
import smtplib
import urllib.request
from email.message import EmailMessage

import chat_store

logger = logging.getLogger("aya.notify")


def _webhook(title: str, body: str) -> None:
    url = os.getenv("ALERT_WEBHOOK_URL", "").strip()
    if not url:
        return
    payload = json.dumps({"title": title, "body": body}, ensure_ascii=False).encode()
    request = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        urllib.request.urlopen(request, timeout=8).read()
    except Exception as exc:  # pragma: no cover - dépend du réseau
        logger.warning("Webhook d'alerte injoignable : %s", exc)


def _email(title: str, body: str) -> None:
    to = os.getenv("ALERT_EMAIL_TO", "").strip()
    host = os.getenv("SMTP_HOST", "").strip()
    if not to or not host:
        return
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASSWORD", "")
    message = EmailMessage()
    message["Subject"] = f"Aya — {title}"
    message["From"] = user or f"aya@{host}"
    message["To"] = to
    message.set_content(f"{title}\n\n{body}")
    try:
        with smtplib.SMTP(host, port, timeout=10) as smtp:
            smtp.starttls()
            if user and password:
                smtp.login(user, password)
            smtp.send_message(message)
    except Exception as exc:  # pragma: no cover - dépend du réseau
        logger.warning("E-mail d'alerte non envoyé : %s", exc)


def alert(kind: str, title: str, body: str = "") -> None:
    """Enregistre l'alerte puis prévient l'équipe par les canaux configurés."""
    try:
        chat_store.add_alert(kind, title, body)
    except Exception:  # pragma: no cover - la base ne doit jamais bloquer la réponse
        logger.exception("Alerte non enregistrée")
    _webhook(title, body)
    _email(title, body)


def quote_confirmed(session_id: str, service: str, budget: str, lang: str) -> None:
    alert(
        "devis",
        "Nouvelle demande de devis",
        f"Service : {service}\nBudget : {budget}\nLangue : {lang}\nSession : {session_id}",
    )


def phone_captured(session_id: str, phone: str) -> None:
    alert(
        "telephone",
        "Un client a laissé son numéro",
        f"Numéro : {phone}\nSession : {session_id}",
    )


def file_received(session_id: str, filename: str) -> None:
    alert(
        "fichier",
        "Un client a envoyé un fichier",
        f"Fichier : {filename}\nSession : {session_id}",
    )


def unanswered(session_id: str, question: str, lang: str) -> None:
    """Question sans réponse : on la note, sans alerter (trop bruyant)."""
    try:
        chat_store.add_unanswered(session_id, question, lang)
    except Exception:  # pragma: no cover
        logger.exception("Question non enregistrée")
