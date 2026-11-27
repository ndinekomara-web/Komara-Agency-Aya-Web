"""
Aya — application web autonome (sans Telegram).

Lancement :
    python app.py                 # http://localhost:8000
    uvicorn app:app --reload      # développement

L'interface est une PWA : elle s'installe sur ordinateur et sur téléphone
depuis le navigateur, comme une application classique.
"""
from __future__ import annotations

import asyncio
import logging
import time
import os
import secrets
import uuid
from pathlib import Path

from fastapi import UploadFile, File, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

import catalogue
import chat_store
import db
import invoices
import notify
import portfolio
import rag_engine
import seed_engine
from config import (
    ADMIN_ID,
    APP_ACCESS_TOKEN,
    APP_NAME,
    APP_PORT,
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
)
from language_detector import change_language, detect_language, get_language
from message_router import handle_greeting, route_message
import appointments
import backup
import extras
import files_kind
import scheduler
import tracking
import utils
from utils import GENERIC_MESSAGES

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("aya.web")

WEB_DIR = Path(__file__).resolve().parent / "web"

app = FastAPI(title=APP_NAME, docs_url="/api/docs", redoc_url=None)
chat_store.init_db()


# ---------------------------------------------------------------------------
# Modèles
# ---------------------------------------------------------------------------
# Temps de « réflexion » perçu : une réponse instantanée fait robot.
# Bornes réglables sans redéployer le code.
RESPONSE_DELAY_MIN = float(os.getenv("RESPONSE_DELAY_MIN", "3"))
RESPONSE_DELAY_MAX = float(os.getenv("RESPONSE_DELAY_MAX", "8"))


def _thinking_delay(reply: str) -> float:
    """Durée d'attente avant d'afficher la réponse, entre 3 et 8 secondes.

    Une réponse courte se prépare vite, une longue demande plus de temps :
    l'attente suit la longueur, dans les bornes demandées.
    """
    low = max(0.0, RESPONSE_DELAY_MIN)
    high = max(low, RESPONSE_DELAY_MAX)
    if high <= 0:
        return 0.0
    scaled = low + len(reply or "") / 260.0
    return round(min(high, max(low, scaled)), 2)


# Anti-spam : quelques messages par minute et par session, jamais bloquant
# pour un client normal.
RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_MINUTE", "15"))
_rate_seen: dict[str, list[float]] = {}


def _rate_ok(key: str) -> bool:
    if RATE_LIMIT <= 0:
        return True
    now = time.monotonic()
    window = [t for t in _rate_seen.get(key, []) if now - t < 60]
    if len(window) >= RATE_LIMIT:
        _rate_seen[key] = window
        return False
    window.append(now)
    _rate_seen[key] = window
    return True


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = Field(default=None, max_length=80)
    lang: str | None = None
    reply_to: dict | None = None  # {author, excerpt} quand le client répond à un message


class SessionRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=80)
    lang: str | None = None


class LoginRequest(BaseModel):
    token: str = Field(min_length=1, max_length=200)


# ---------------------------------------------------------------------------
# Accès (facultatif)
# ---------------------------------------------------------------------------
def _authorized(request: Request) -> bool:
    if not APP_ACCESS_TOKEN:
        return True
    supplied = request.headers.get("x-access-token") or request.cookies.get("aya_access") or ""
    return secrets.compare_digest(supplied, APP_ACCESS_TOKEN)


def _client_ip(request: Request) -> str:
    """IP réelle du visiteur, même derrière le proxy de Railway."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return (request.client.host if request.client else "") or ""


def admin_ips() -> list[str]:
    """Liste des IP autorisées (ADMIN_ID, séparées par des virgules)."""
    return [ip.strip() for ip in ADMIN_ID.replace(";", ",").split(",") if ip.strip()]


def is_admin(request: Request) -> bool:
    allowed = admin_ips()
    return bool(allowed) and _client_ip(request) in allowed


def require_admin(request: Request) -> None:
    if not admin_ips():
        raise HTTPException(
            status_code=403,
            detail="Administration désactivée : définissez ADMIN_ID avec votre IP.",
        )
    if not is_admin(request):
        raise HTTPException(
            status_code=403,
            detail=f"IP non autorisée ({_client_ip(request)}). Ajoutez-la à ADMIN_ID.",
        )
    if not _authorized(request):
        raise HTTPException(status_code=401, detail="Connectez-vous d'abord à Aya.")


def require_access(request: Request) -> None:
    if not _authorized(request):
        raise HTTPException(status_code=401, detail="Accès protégé par mot de passe.")


# ---------------------------------------------------------------------------
# Logique de conversation
# ---------------------------------------------------------------------------
def _wants_gallery(question: str) -> bool:
    """La galerie s'affiche quand la fiche « portfolio » du seed répond."""
    hit = seed_engine.find_answer(question)
    if not hit:
        return False
    return "portfolio" in hit["question"].casefold() or hit["answer"].startswith("Voici quelques-unes de nos réalisations")


def _answer(session_id: str, text: str, is_new_session: bool = False) -> dict:
    """Traite un message et renvoie la réponse (exécuté dans un thread)."""
    lang = detect_language(text, session_id)
    replies: list[str] = []

    def send(_session: str, message: str) -> None:
        if message and message not in replies:
            replies.append(message)

    route_message(session_id, text, send)

    generic = GENERIC_MESSAGES.get(lang, GENERIC_MESSAGES["fr"])["no_understand"]
    reply = "\n\n".join(r for r in replies if r != generic).strip() or generic
    reply = utils.never_say_robot(reply, lang)
    return {"reply": reply, "lang": lang, "gallery": _wants_gallery(text)}


# ---------------------------------------------------------------------------
# Routes API
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def _demarrer_taches() -> None:
    """Relances + sauvegarde quotidienne, en tâche de fond, sans bloquer le site."""
    try:
        extras.init()
        scheduler.demarrer()
    except Exception:
        logger.exception("tâches de fond non démarrées")


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "app": APP_NAME,
        "auth": bool(APP_ACCESS_TOKEN),
        "rag": rag_engine.stats(),
        "version": os.getenv("RAILWAY_GIT_COMMIT_SHA", "dev")[:7],
        "database": db.describe(),
        "store": chat_store.stats(),
    }


@app.post("/api/login")
def login(payload: LoginRequest, response: Response) -> dict:
    if not APP_ACCESS_TOKEN:
        return {"ok": True}
    if not secrets.compare_digest(payload.token, APP_ACCESS_TOKEN):
        raise HTTPException(status_code=401, detail="Mot de passe incorrect.")
    response.set_cookie(
        "aya_access",
        APP_ACCESS_TOKEN,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
    )
    return {"ok": True}


@app.post("/api/chat", dependencies=[Depends(require_access)])
async def chat(payload: ChatRequest) -> dict:
    text = payload.message.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message vide.")

    if not _rate_ok(payload.session_id or "anonyme"):
        raise HTTPException(
            status_code=429,
            detail="Trop de messages d'un coup. Patiente une minute, je réponds à tout.",
        )

    session_id = payload.session_id or str(uuid.uuid4())
    if payload.lang in SUPPORTED_LANGUAGES:
        change_language(session_id, payload.lang)

    is_new_session = not chat_store.history(session_id, limit=1)
    chat_store.touch_session(session_id, payload.lang)
    # Réponse à un message : on garde la citation pour l'affichage, jamais dans l'analyse.
    cite = ""
    if payload.reply_to:
        auteur = str(payload.reply_to.get("author", ""))[:20].replace("]", "")
        extrait = str(payload.reply_to.get("excerpt", ""))[:80].replace("]", "")
        if extrait:
            cite = f"[[cite:{auteur}:{extrait}]]\n"
    chat_store.add_message(session_id, "user", cite + text, payload.lang)

    started = time.monotonic()
    try:
        result = await run_in_threadpool(_answer, session_id, text, is_new_session)
    except Exception:  # pragma: no cover - garde-fou
        logger.exception("Erreur pendant le traitement du message")
        lang = get_language(session_id)
        result = {
            "reply": GENERIC_MESSAGES.get(lang, GENERIC_MESSAGES["fr"])["no_understand"],
            "lang": lang,
        }

    # Question restée sans réponse : notée pour /admin (le bot s'améliore ensuite)
    generic = GENERIC_MESSAGES.get(result["lang"], GENERIC_MESSAGES["fr"])["no_understand"]
    if result["reply"].strip() == generic:
        notify.unanswered(session_id, text, result["lang"])

    # Attente maîtrisée : jamais moins de 3 s, jamais plus de 8 s au total.
    wait = _thinking_delay(result["reply"]) - (time.monotonic() - started)
    if wait > 0:
        await asyncio.sleep(wait)

    chat_store.add_message(session_id, "assistant", result["reply"], result["lang"])
    return {
        "reply": result["reply"],
        "lang": result["lang"],
        "session_id": session_id,
        "gallery": bool(result.get("gallery")),
    }


@app.get("/api/history", dependencies=[Depends(require_access)])
def history(session_id: str, limit: int = 100) -> dict:
    limit = max(1, min(limit, 500))
    return {"messages": chat_store.history(session_id, limit)}


@app.post("/api/reset", dependencies=[Depends(require_access)])
def reset(payload: SessionRequest) -> dict:
    removed = chat_store.clear(payload.session_id)
    return {"removed": removed}


class KnowledgeRequest(BaseModel):
    lang: str = Field(default="fr", max_length=5)
    title: str = Field(min_length=2, max_length=120)
    content: str = Field(min_length=5, max_length=4000)


@app.get("/api/admin/status")
def admin_status(request: Request) -> dict:
    """Permet à la page d'administration de savoir où elle en est."""
    return {
        "ip": _client_ip(request),
        "allowed_ips": admin_ips(),
        "is_admin": is_admin(request),
        "auth_required": bool(APP_ACCESS_TOKEN),
    }


@app.get("/api/admin/knowledge", dependencies=[Depends(require_admin)])
def admin_list_knowledge(lang: str | None = None) -> dict:
    return {"entries": chat_store.knowledge_entries(lang)}


@app.post("/api/admin/knowledge", dependencies=[Depends(require_admin)])
def admin_add_knowledge(payload: KnowledgeRequest) -> dict:
    if payload.lang not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail="Langue non supportée.")
    entry_id = chat_store.add_knowledge(payload.lang, payload.title.strip(), payload.content.strip())
    rag_engine.reload_knowledge_base()
    return {"id": entry_id, "sections": rag_engine.stats()["sections"]}


@app.delete("/api/admin/knowledge/{entry_id}", dependencies=[Depends(require_admin)])
def admin_delete_knowledge(entry_id: int) -> dict:
    removed = chat_store.delete_knowledge(entry_id)
    rag_engine.reload_knowledge_base()
    return {"removed": removed}


@app.get("/api/catalogue")
def public_catalogue() -> dict:
    """Offres et prix publics (aucune donnée client)."""
    return {"products": catalogue.products()}


@app.get("/api/admin/orders", dependencies=[Depends(require_admin)])
def admin_orders(limit: int = 50) -> dict:
    return {"orders": catalogue.orders(max(1, min(limit, 200)))}


@app.post("/api/admin/orders/{order_id}/status", dependencies=[Depends(require_admin)])
def admin_order_status(order_id: int, payload: dict) -> dict:
    status = str(payload.get("status", "")).strip()
    if not status:
        raise HTTPException(status_code=400, detail="Statut manquant.")
    catalogue.set_order_status(order_id, status)
    return {"ok": True, "status": status}


@app.get("/api/admin/products", dependencies=[Depends(require_admin)])
def admin_products() -> dict:
    return {"products": catalogue.products(active_only=False)}


@app.post("/api/admin/products", dependencies=[Depends(require_admin)])
def admin_add_product(payload: dict) -> dict:
    name = str(payload.get("name", "")).strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nom manquant.")
    try:
        price = float(payload.get("price", 0))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Prix invalide.")
    product_id = catalogue.add_product(
        str(payload.get("category", "Service")).strip() or "Service",
        name,
        str(payload.get("description", "")).strip(),
        price,
    )
    return {"id": product_id}


@app.patch("/api/admin/products/{product_id}", dependencies=[Depends(require_admin)])
def admin_update_product(product_id: int, payload: dict) -> dict:
    if "price" in payload:
        try:
            catalogue.update_price(product_id, float(payload["price"]))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Prix invalide.")
    return {"ok": True}


@app.delete("/api/admin/products/{product_id}", dependencies=[Depends(require_admin)])
def admin_delete_product(product_id: int) -> dict:
    catalogue.deactivate_product(product_id)
    return {"ok": True}


@app.get("/api/portfolio")
def get_portfolio() -> dict:
    return {"items": portfolio.list_items()}


@app.post("/api/upload", dependencies=[Depends(require_access)])
async def upload(file: UploadFile = File(...), session_id: str = "") -> dict:
    """Photo ou fichier envoyé par un client (logo, produit, ancienne affiche)."""
    data = await file.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Fichier trop lourd (8 Mo maximum).")
    if not data:
        raise HTTPException(status_code=400, detail="Fichier vide.")
    session = session_id or "anonyme"
    upload_id = chat_store.add_upload(session, file.filename or "fichier", file.content_type or "", data)
    notify.file_received(session, file.filename or "fichier")

    lang = get_language(session)
    # Réponse adaptée au type RÉEL du fichier (image, PDF, tableau, doc, audio).
    genre = files_kind.classify(file.filename or "", file.content_type or "")
    reply = files_kind.ack(genre, file.filename or "")
    # Le message du client garde un lien vers SON fichier : l'image s'affiche
    # dans la bulle, et revient après rechargement de la page.
    is_image = (file.content_type or "").startswith("image/")
    is_audio = (file.content_type or "").startswith("audio/")
    kind = "img" if is_image else ("aud" if is_audio else "doc")
    marker = f"[[file:{upload_id}:{kind}:{file.filename or 'fichier'}]]"
    chat_store.add_message(session, "user", marker, lang)
    chat_store.add_message(session, "assistant", reply, lang)
    return {
        "id": upload_id,
        "filename": file.filename,
        "is_image": is_image,
        "is_audio": is_audio,
        "url": f"/api/upload/{upload_id}?session_id={session}",
        "reply": reply,
        "session_id": session,
    }


@app.get("/api/upload/{upload_id}", dependencies=[Depends(require_access)])
def my_upload(upload_id: int, session_id: str = ""):
    """Le client revoit son propre fichier (jamais celui d'un autre)."""
    row = chat_store.upload_for_session(upload_id, session_id or "anonyme")
    if not row:
        raise HTTPException(status_code=404, detail="Fichier introuvable.")
    content_type = row.get("content_type") or "application/octet-stream"
    # Seules les images s'affichent dans la page ; le reste se télécharge.
    disposition = "inline" if content_type.startswith("image/") else "attachment"
    return Response(
        content=row["data"],
        media_type=content_type,
        headers={
            "Content-Disposition": f'{disposition}; filename="{row["filename"]}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=3600",
        },
    )


@app.get("/api/admin/uploads", dependencies=[Depends(require_admin)])
def admin_uploads(limit: int = 50) -> dict:
    """Fichiers reçus, avec le client tel qu'Aya l'a appris dans la conversation."""
    import client_memory

    files = chat_store.uploads(max(1, min(limit, 200)))
    for file in files:
        profile = client_memory.get(str(file.get("session_id", "")))
        file["client"] = profile.get("name") or "Client sans prénom"
        file["project"] = profile.get("service") or ""
        file["is_image"] = str(file.get("content_type", "")).startswith("image/")
    return {"uploads": files}


@app.get("/api/admin/uploads/{upload_id}", dependencies=[Depends(require_admin)])
def admin_upload(upload_id: int):
    row = chat_store.upload_data(upload_id)
    if not row:
        raise HTTPException(status_code=404, detail="Fichier introuvable.")
    return Response(
        content=row["data"],
        media_type=row.get("content_type") or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{row["filename"]}"'},
    )


@app.get("/api/admin/appointments", dependencies=[Depends(require_admin)])
def admin_rdv(limit: int = 50) -> dict:
    items = appointments.liste(max(1, min(limit, 200)))
    for item in items:
        item["human"] = appointments.lisible(str(item.get("slot_iso", "")))
    return {"appointments": items}


@app.post("/api/admin/appointments/{rdv_id}/status", dependencies=[Depends(require_admin)])
def admin_rdv_statut(rdv_id: int, payload: dict) -> dict:
    statut = str(payload.get("status", "")).strip() or "confirme"
    return {"ok": appointments.changer_statut(rdv_id, statut)}


@app.get("/api/admin/backups", dependencies=[Depends(require_admin)])
def admin_backups() -> dict:
    return {"backups": backup.liste(10)}


@app.post("/api/admin/backup", dependencies=[Depends(require_admin)])
def admin_backup_now() -> dict:
    return backup.run(force=True)


@app.get("/api/admin/backup/latest", dependencies=[Depends(require_admin)])
def admin_backup_latest():
    row = backup.dernier()
    if not row:
        raise HTTPException(status_code=404, detail="Aucune sauvegarde.")
    return Response(
        content=bytes(row["data"]),
        media_type="application/gzip",
        headers={"Content-Disposition": 'attachment; filename="komara-backup.json.gz"'},
    )


@app.get("/api/admin/alerts", dependencies=[Depends(require_admin)])
def admin_alerts(limit: int = 40) -> dict:
    return {"alerts": chat_store.alerts(max(1, min(limit, 200)))}


@app.post("/api/admin/alerts/{alert_id}/seen", dependencies=[Depends(require_admin)])
def admin_alert_seen(alert_id: int) -> dict:
    return {"updated": chat_store.mark_alert_seen(alert_id)}


@app.get("/api/admin/unanswered", dependencies=[Depends(require_admin)])
def admin_unanswered(limit: int = 30) -> dict:
    return {"questions": chat_store.unanswered_top(max(1, min(limit, 200)))}


@app.get("/api/admin/analytics", dependencies=[Depends(require_admin)])
def admin_analytics(days: int = 14) -> dict:
    return chat_store.analytics(max(1, min(days, 90)))


@app.get("/api/admin/export/{kind}.csv", dependencies=[Depends(require_admin)])
def admin_export(kind: str):
    if kind == "quotes":
        rows, header = chat_store.quotes(500), ["id", "service", "budget", "lang", "created_at"]
    elif kind == "leads":
        rows, header = chat_store.leads(500), ["id", "phone", "note", "created_at"]
    else:
        raise HTTPException(status_code=404, detail="Export inconnu (quotes ou leads).")
    lines = [";".join(header)]
    for row in rows:
        lines.append(";".join(str(row.get(key, "")).replace(";", ",") for key in header))
    return Response(
        content="\ufeff" + "\n".join(lines),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="aya-{kind}.csv"'},
    )


@app.get("/api/quotes/{quote_id}/invoice.pdf", dependencies=[Depends(require_admin)])
def quote_invoice(quote_id: int):
    rows = [q for q in chat_store.quotes(500) if int(q["id"]) == quote_id]
    if not rows:
        raise HTTPException(status_code=404, detail="Devis introuvable.")
    quote = rows[0]
    pdf = invoices.build_quote_pdf(
        reference=f"AYA-{quote_id:05d}",
        service=quote.get("service", ""),
        budget=quote.get("budget", ""),
        created_at=quote.get("created_at"),
        deposit_link=os.getenv("DEPOSIT_LINK", "").strip(),
        contact=os.getenv("KOMARA_WHATSAPP", ""),
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="facture-{quote_id}.pdf"'},
    )


@app.delete("/api/message/{message_id}", dependencies=[Depends(require_access)])
def delete_message(message_id: int, session_id: str) -> dict:
    return {"removed": chat_store.delete_message(message_id, session_id)}


@app.get("/api/search", dependencies=[Depends(require_access)])
def search(session_id: str, q: str) -> dict:
    needle = q.strip()
    if len(needle) < 2:
        return {"messages": []}
    return {"messages": chat_store.search_messages(session_id, needle)}


@app.get("/api/leads", dependencies=[Depends(require_access)])
def list_leads(limit: int = 50) -> dict:
    """Numéros laissés par les clients (réservé à l'équipe)."""
    limit = max(1, min(limit, 200))
    return {"leads": chat_store.leads(limit)}


@app.get("/api/appointments/slots", dependencies=[Depends(require_access)])
def rdv_slots() -> dict:
    return {"slots": [{"iso": s, "human": appointments.lisible(s)} for s in appointments.slots()]}


@app.post("/api/appointments", dependencies=[Depends(require_access)])
def rdv_creer(payload: dict) -> dict:
    session = str(payload.get("session_id", "")) or "anonyme"
    slot = str(payload.get("slot", ""))
    if not slot or slot not in appointments.slots():
        raise HTTPException(status_code=400, detail="Créneau indisponible.")
    profile = client_memory.get(session)
    return appointments.reserver(session, slot, profile)


@app.get("/api/track", dependencies=[Depends(require_access)])
def suivi(reference: str = "", phone: str = "") -> dict:
    return {"reply": tracking.reponse(reference, phone)}


@app.get("/api/quotes/{quote_id}/devis.pdf", dependencies=[Depends(require_access)])
def quote_pdf_client(quote_id: int, session_id: str = ""):
    """Le client télécharge SON devis, sans accès admin."""
    rows = [q for q in chat_store.quotes(500) if int(q["id"]) == quote_id]
    if not rows or str(rows[0].get("session_id")) != str(session_id):
        raise HTTPException(status_code=404, detail="Devis introuvable.")
    quote = rows[0]
    pdf = invoices.build_quote_pdf(
        reference=f"AYA-{quote_id:05d}",
        service=quote.get("service", ""),
        budget=quote.get("budget", ""),
        created_at=quote.get("created_at"),
        contact=os.getenv("KOMARA_WHATSAPP", "").strip(),
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="devis-AYA-{quote_id:05d}.pdf"'},
    )


@app.get("/api/quotes", dependencies=[Depends(require_access)])
def list_quotes(limit: int = 50) -> dict:
    """Demandes de devis confirmées (réservé à l'équipe)."""
    limit = max(1, min(limit, 200))
    return {"quotes": chat_store.quotes(limit)}


@app.post("/api/language", dependencies=[Depends(require_access)])
def set_language(payload: SessionRequest) -> dict:
    if payload.lang not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail="Langue non supportée.")
    change_language(payload.session_id, payload.lang)
    return {"lang": payload.lang, "current": get_language(payload.session_id)}


@app.get("/api/config")
def client_config() -> dict:
    return {
        "app_name": APP_NAME,
        "default_language": DEFAULT_LANGUAGE,
        "languages": SUPPORTED_LANGUAGES,
        "auth_required": bool(APP_ACCESS_TOKEN),
        "contact_whatsapp": os.getenv("KOMARA_WHATSAPP", "").strip(),
        "deposit_available": bool(os.getenv("DEPOSIT_LINK", "").strip()),
    }


# ---------------------------------------------------------------------------
# Interface (PWA)
# ---------------------------------------------------------------------------
class NoCacheStatic(StaticFiles):
    """Fichiers statiques revalidés à chaque visite : un correctif atteint
    immédiatement les téléphones, sans vider le cache à la main."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


if (WEB_DIR / "static").is_dir():
    app.mount("/static", NoCacheStatic(directory=WEB_DIR / "static"), name="static")


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    return FileResponse(WEB_DIR / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/service-worker.js", include_in_schema=False)
def service_worker():
    return FileResponse(
        WEB_DIR / "service-worker.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/admin", include_in_schema=False)
def admin_page(request: Request):
    """Page d'administration, réservée aux IP déclarées dans ADMIN_ID."""
    if not admin_ips():
        return JSONResponse(
            {
                "detail": "Administration désactivée.",
                "comment": "Ajoutez la variable ADMIN_ID avec votre adresse IP dans Railway.",
                "votre_ip": _client_ip(request),
            },
            status_code=403,
        )
    if not is_admin(request):
        return JSONResponse(
            {
                "detail": "Cette adresse IP n'est pas autorisée à administrer Aya.",
                "votre_ip": _client_ip(request),
                "ip_autorisee": admin_ips(),
                "comment": "Mettez à jour ADMIN_ID avec l'IP affichée ci-dessus.",
            },
            status_code=403,
        )
    return FileResponse(WEB_DIR / "admin.html", headers={"Cache-Control": "no-cache"})


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.exception_handler(404)
def not_found(_request: Request, _exc):  # pragma: no cover
    return JSONResponse({"detail": "Introuvable"}, status_code=404)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=APP_PORT, reload=False)
