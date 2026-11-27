"""Reconnaître ce que le client envoie : image, PDF, tableau, document, audio, lien, code."""
from __future__ import annotations

import re

IMAGES = ("image/",)
SHEETS = (".csv", ".xls", ".xlsx", ".ods")
DOCS = (".doc", ".docx", ".odt", ".txt", ".rtf", ".ppt", ".pptx")
PDF = (".pdf",)
ARCHIVES = (".zip", ".rar", ".7z")
LINKS = re.compile(r"https?://\S+", re.I)
CODE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{4,24}$")


def classify(filename: str = "", content_type: str = "", text: str = "") -> str:
    """Type réel du fichier, sans se fier au seul nom."""
    ctype = (content_type or "").lower()
    name = (filename or "").lower()
    if ctype.startswith(IMAGES) or name.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic")):
        return "image"
    if ctype == "application/pdf" or name.endswith(PDF):
        return "pdf"
    if "spreadsheet" in ctype or "excel" in ctype or name.endswith(SHEETS):
        return "tableau"
    if ctype.startswith("audio/") or name.endswith((".ogg", ".mp3", ".wav", ".m4a", ".webm")):
        return "audio"
    if name.endswith(ARCHIVES):
        return "archive"
    if "word" in ctype or "text/" in ctype or name.endswith(DOCS):
        return "document"
    if LINKS.search(text or ""):
        return "lien"
    if CODE.match((text or "").strip()):
        return "code"
    return "document"


def is_link(text: str) -> bool:
    return bool(LINKS.search(text or ""))


def first_link(text: str) -> str:
    m = LINKS.search(text or "")
    return m.group(0) if m else ""


def is_code(text: str) -> bool:
    """Une référence ou un code, pas une phrase."""
    t = (text or "").strip()
    return bool(CODE.match(t)) and not t.replace("-", "").isdigit()


ATTENDU = {
    "image": "l'image",
    "pdf": "le PDF",
    "tableau": "le tableau",
    "document": "le document",
    "audio": "le message vocal",
    "archive": "l'archive",
}


def ack(kind: str, filename: str = "") -> str:
    """Ce qu'Aya dit en recevant le fichier, selon son type réel."""
    nom = f" « {filename} »" if filename else ""
    if kind == "image":
        return f"Bien reçu, j'ai ton image{nom} 📎 Ndine la voit dans son espace. Tu veux qu'on en fasse quoi : la retoucher, s'en inspirer pour un visuel, ou la garder pour ton projet ?"
    if kind == "pdf":
        return f"Bien reçu, j'ai ton PDF{nom} 📄 Ndine le voit dans son espace, je le garde pour ton dossier. Tu veux que je note une demande précise dessus ?"
    if kind == "tableau":
        return f"Bien reçu, j'ai ton tableau{nom} 📊 Ndine le voit dans son espace. Si tu veux, on peut en sortir un visuel ou un récap propre."
    if kind == "audio":
        return "Bien reçu, j'ai ton message vocal 🎧 Je l'écoute et je te réponds ici."
    if kind == "archive":
        return f"Bien reçu, j'ai ton archive{nom} 📦 Je la transmets à Ndine avec ton projet."
    return f"Bien reçu, j'ai ton document{nom} 📎 Ndine le voit dans son espace, je le garde pour ton dossier."
