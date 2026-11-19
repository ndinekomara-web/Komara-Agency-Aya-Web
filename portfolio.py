"""Portfolio : liste les visuels de web/static/portfolio.

Déposez une image (.jpg .png .webp) dans ce dossier : elle apparaît dans la
galerie au prochain chargement. Le fichier captions.json donne les légendes.
"""
from __future__ import annotations

import json
from pathlib import Path

DIR = Path(__file__).resolve().parent / "web" / "static" / "portfolio"
EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def _captions() -> dict[str, str]:
    path = DIR / "captions.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def list_items() -> list[dict[str, str]]:
    if not DIR.is_dir():
        return []
    captions = _captions()
    items = []
    for file in sorted(DIR.iterdir()):
        if file.suffix.lower() not in EXTENSIONS:
            continue
        label = captions.get(file.name) or file.stem.split("_", 1)[-1].replace("_", " ").capitalize()
        items.append({"url": f"/static/portfolio/{file.name}", "title": label})
    return items
