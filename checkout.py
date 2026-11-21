"""
Commande guidée : panier → nom → livraison → confirmation.

Le parcours est volontairement court (trois questions) : au-delà, les clients
abandonnent. La commande est enregistrée en base et une alerte part vers
l'équipe.
"""
from __future__ import annotations

import re

import catalogue
import chat_store
import notify
from pending_question import clear_pending, get_pending, set_pending

TAG_PREFIX = "order_"
# Données du parcours (nom, livraison) — la question en attente ne stocke que l'étape.
_DATA: dict[str, dict] = {}

_MESSAGES = {
    "fr": {
        "catalogue_head": "🛍️ *Nos offres*\n\n{items}\n\nDis-moi *ajoute 2* pour choisir, ou *panier* pour voir ton panier.",
        "catalogue_item": "{n}. *{name}* — {price:g} €\n   {desc}",
        "catalogue_empty": "Le catalogue arrive bientôt. Dis-moi *devis* en attendant 🙏",
        "added": "✅ *{name}* ajouté au panier.\n🛒 {count} article(s) — {total:g} €\n\n*panier* pour vérifier, *commander* pour finaliser.",
        "not_found": "Je ne trouve pas ce numéro. Dis *catalogue* pour revoir la liste 🙏",
        "cart_head": "🛒 *Ton panier*\n\n{items}\n\n➡️ Total : *{total:g} €*\n\n*commander* pour finaliser, *vider* pour tout retirer.",
        "cart_line": "• {name} x{qty} — {line:g} €",
        "cart_empty": "Ton panier est vide. Dis *catalogue* pour voir les offres 👀",
        "cleared": "Panier vidé 🙏 Dis *catalogue* quand tu veux.",
        "ask_name": "🚀 On finalise.\n\n{items}\n➡️ Total : *{total:g} €*\n\n👤 C'est à quel nom ?",
        "ask_address": "📍 Où livrer ? (ville, quartier, ou *retrait*)",
        "ask_confirm": "✅ Récapitulatif\n\n{items}\n➡️ Total : *{total:g} €*\n👤 {customer}\n📍 {address}\n\nDis *confirmer* pour valider, *annuler* pour arrêter.",
        "done": "🎉 Commande #{oid} enregistrée !\n\n{items}\n➡️ Total : *{total:g} €*\n\nL'équipe te contacte sous 24h pour le paiement et la livraison. Merci de ta confiance 🇬🇳",
        "cancelled": "D'accord, commande annulée. Ton panier est conservé 🙂",
        "empty_checkout": "Ton panier est vide. Dis *catalogue* pour choisir une offre 👀",
    },
    "en": {
        "catalogue_head": "🛍️ *Our offers*\n\n{items}\n\nSay *add 2* to choose, or *cart* to see your cart.",
        "catalogue_item": "{n}. *{name}* — {price:g} €\n   {desc}",
        "catalogue_empty": "The catalogue is coming soon. Say *quote* meanwhile 🙏",
        "added": "✅ *{name}* added to your cart.\n🛒 {count} item(s) — {total:g} €\n\n*cart* to check, *order* to finish.",
        "not_found": "I can't find that number. Say *catalogue* to see the list again 🙏",
        "cart_head": "🛒 *Your cart*\n\n{items}\n\n➡️ Total: *{total:g} €*\n\n*order* to finish, *clear* to empty.",
        "cart_line": "• {name} x{qty} — {line:g} €",
        "cart_empty": "Your cart is empty. Say *catalogue* to see the offers 👀",
        "cleared": "Cart cleared 🙏 Say *catalogue* anytime.",
        "ask_name": "🚀 Let's finish.\n\n{items}\n➡️ Total: *{total:g} €*\n\n👤 What name is it for?",
        "ask_address": "📍 Where should we deliver? (city, area, or *pickup*)",
        "ask_confirm": "✅ Summary\n\n{items}\n➡️ Total: *{total:g} €*\n👤 {customer}\n📍 {address}\n\nSay *confirm* to validate, *cancel* to stop.",
        "done": "🎉 Order #{oid} registered!\n\n{items}\n➡️ Total: *{total:g} €*\n\nThe team contacts you within 24h for payment and delivery. Thank you 🇬🇳",
        "cancelled": "Alright, order cancelled. Your cart is kept 🙂",
        "empty_checkout": "Your cart is empty. Say *catalogue* to pick an offer 👀",
    },
}
_MESSAGES["es"] = _MESSAGES["en"]
_MESSAGES["ar"] = _MESSAGES["en"]

_ADD_RX = re.compile(r"^(?:ajoute|ajouter|add|prends|je prends)\s+(\d+)$", re.I)
_NUMBER_RX = re.compile(r"^(\d+)$")
# « tarifs », « prix » et « services » restent au seed : c'est la grille
# officielle. « catalogue » ouvre les offres achetables (panier).
# Demande explicite seulement : « j'ai une boutique » décrit une activité, ça
# n'ouvre pas le catalogue. On exige le mot seul ou une formule de demande.
_CATALOGUE_RX = re.compile(
    r"^\s*(le\s+|ton\s+|votre\s+|vos\s+|nos\s+)?(catalogue|produits?|offres?)\s*[?!.]*\s*$|"
    r"\b(montre|voir|affiche|envoie|donne|liste|ouvre)\b.{0,25}\b(catalogue|produits|offres)\b|"
    r"\b(votre|ton|le)\s+catalogue\b",
    re.I,
)
_CART_RX = re.compile(r"\b(panier|cart|mon panier)\b", re.I)
_ORDER_RX = re.compile(r"\b(commander|commande|order|checkout|finaliser|je commande)\b", re.I)
_CLEAR_RX = re.compile(r"\b(vider|clear|vide le panier)\b", re.I)
_YES_RX = re.compile(r"\b(confirmer|confirme|oui|ok|yes|confirm|valider|valide)\b", re.I)
_NO_RX = re.compile(r"\b(annuler|annule|cancel|non|no|stop)\b", re.I)


def _t(lang: str) -> dict:
    return _MESSAGES.get(lang, _MESSAGES["fr"])


def _lines(summary: dict, lang: str) -> str:
    t = _t(lang)
    return "\n".join(
        t["cart_line"].format(name=i["name"], qty=i["qty"], line=float(i["price"]) * int(i["qty"]))
        for i in summary["items"]
    )


def show_catalogue(lang: str) -> str:
    t = _t(lang)
    items = catalogue.products()
    if not items:
        return t["catalogue_empty"]
    body = "\n".join(
        t["catalogue_item"].format(n=n, name=p["name"], price=float(p["price"]), desc=p["description"])
        for n, p in enumerate(items, start=1)
    )
    return t["catalogue_head"].format(items=body)


def show_cart(session_id: str, lang: str) -> str:
    t = _t(lang)
    summary = catalogue.cart_summary(session_id)
    if not summary["items"]:
        return t["cart_empty"]
    return t["cart_head"].format(items=_lines(summary, lang), total=summary["total"])


def add_by_number(session_id: str, number: int, lang: str) -> str:
    t = _t(lang)
    items = catalogue.products()
    if not 1 <= number <= len(items):
        return t["not_found"]
    product = items[number - 1]
    result = catalogue.add_to_cart(session_id, int(product["id"]))
    if not result:
        return t["not_found"]
    return t["added"].format(name=result["name"], count=result["count"], total=result["total"])


def start_checkout(session_id: str, lang: str) -> str:
    t = _t(lang)
    summary = catalogue.cart_summary(session_id)
    if not summary["items"]:
        return t["empty_checkout"]
    _DATA[session_id] = {}
    set_pending(session_id, "open", TAG_PREFIX + "name")
    return t["ask_name"].format(items=_lines(summary, lang), total=summary["total"])


def in_checkout(session_id: str) -> bool:
    pending = get_pending(session_id)
    tag = (pending or {}).get("context") or ""
    return tag.startswith(TAG_PREFIX)


def step(session_id: str, text: str, lang: str) -> str | None:
    """Avance le parcours de commande. None si le message n'est pas une étape."""
    pending = get_pending(session_id)
    if not pending:
        return None
    tag = pending.get("context") or ""
    if not tag.startswith(TAG_PREFIX):
        return None

    t = _t(lang)
    state = tag[len(TAG_PREFIX):]
    summary = catalogue.cart_summary(session_id)

    if state == "name":
        if not text.strip():
            return t["ask_name"].format(items=_lines(summary, lang), total=summary["total"])
        _DATA[session_id] = {"customer": text.strip()}
        set_pending(session_id, "open", TAG_PREFIX + "address")
        return t["ask_address"]

    if state == "address":
        customer = (_DATA.get(session_id) or {}).get("customer", "")
        _DATA[session_id] = {"customer": customer, "address": text.strip()}
        set_pending(session_id, "open", TAG_PREFIX + "confirm")
        return t["ask_confirm"].format(
            items=_lines(summary, lang), total=summary["total"],
            customer=customer or "—", address=text.strip(),
        )

    if state == "confirm":
        data = _DATA.get(session_id) or {}
        if _NO_RX.search(text):
            clear_pending(session_id)
            return t["cancelled"]
        if not _YES_RX.search(text):
            return t["ask_confirm"].format(
                items=_lines(summary, lang), total=summary["total"],
                customer=data.get("customer", "—"), address=data.get("address", "—"),
            )
        order = catalogue.create_order(
            session_id,
            customer=data.get("customer", ""),
            address=data.get("address", ""),
        )
        clear_pending(session_id)
        _DATA.pop(session_id, None)
        if not order:
            return t["empty_checkout"]
        notify.order_received(order)
        return t["done"].format(
            oid=order["id"], items=order["summary"], total=order["total"],
        )

    return None


def handle(session_id: str, text: str, lang: str) -> str | None:
    """Point d'entrée : catalogue, panier, ajout, commande, vidage."""
    cleaned = text.strip()

    if _CLEAR_RX.search(cleaned):
        catalogue.clear_cart(session_id)
        return _t(lang)["cleared"]

    match = _ADD_RX.match(cleaned)
    if match:
        return add_by_number(session_id, int(match.group(1)), lang)

    if _CART_RX.search(cleaned):
        return show_cart(session_id, lang)

    if _ORDER_RX.search(cleaned):
        return start_checkout(session_id, lang)

    if _CATALOGUE_RX.search(cleaned):
        return show_catalogue(lang)

    # Un simple numéro, juste après avoir vu le catalogue
    if _NUMBER_RX.match(cleaned):
        pending = get_pending(session_id)
        if pending and (pending.get("context") or "") == "catalogue":
            return add_by_number(session_id, int(cleaned), lang)

    return None
