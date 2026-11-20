"""
Facture proforma en PDF, sans dépendance externe.

Un PDF minimal (Helvetica, texte + lignes) suffit pour un acompte : il est
lisible sur téléphone, imprimable, et ne casse jamais un déploiement.
"""
from __future__ import annotations

import time
from typing import Iterable


_MAP = {"€": "EUR", "’": "'", "‘": "'", "–": "-", "—": "-", "…": "...", "«": '"', "»": '"'}


def _escape(text: str) -> str:
    text = str(text)
    for src, dst in _MAP.items():
        text = text.replace(src, dst)
    return (
        text
        .replace("\\", r"\\")
        .replace("(", r"\(")
        .replace(")", r"\)")
    )


def _pdf(lines: Iterable[tuple[str, int, bool]]) -> bytes:
    """lines = (texte, taille, gras)."""
    content = ["BT", "50 790 Td", "14 TL"]
    for text, size, bold in lines:
        font = "/F2" if bold else "/F1"
        content.append(f"{font} {size} Tf")
        content.append(f"({_escape(text)}) Tj T*")
    content.append("ET")
    stream = "\n".join(content).encode("latin-1", "replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    ).encode()
    return bytes(out)


def build_quote_pdf(
    reference: str,
    service: str,
    budget: str,
    created_at: float | None = None,
    deposit_link: str = "",
    contact: str = "",
) -> bytes:
    """Facture proforma d'une demande de devis."""
    date = time.strftime("%d/%m/%Y", time.gmtime(created_at or time.time()))
    lines: list[tuple[str, int, bool]] = [
        ("KOMARA AGENCY", 22, True),
        ("Bots, sites, logos et automatisation", 11, False),
        (contact or "", 11, False),
        ("", 10, False),
        ("FACTURE PROFORMA", 16, True),
        (f"Reference : {reference}", 11, False),
        (f"Date : {date}", 11, False),
        ("", 10, False),
        ("Service demande", 12, True),
        (service or "Non precise", 11, False),
        ("", 10, False),
        ("Budget annonce par le client", 12, True),
        (budget or "A confirmer", 11, False),
        ("", 10, False),
        ("Conditions", 12, True),
        ("50 % a la commande, 50 % a la livraison.", 11, False),
        ("Orange Money, MTN, paiement mobile, virement.", 11, False),
        ("Devis valable 30 jours.", 11, False),
    ]
    if deposit_link:
        lines += [("", 10, False), ("Lien de paiement de l'acompte", 12, True), (deposit_link, 10, False)]
    lines += [
        ("", 12, False),
        ("Merci de votre confiance.", 11, False),
    ]
    return _pdf(lines)
