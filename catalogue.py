"""
Catalogue et panier — les mêmes offres que le bot Telegram.

Les prix viennent du catalogue officiel ; ils sont modifiables depuis /admin
sans redéployer. Un panier appartient à une session (le navigateur), et une
commande est enregistrée en base pour être traitée par l'équipe.
"""
from __future__ import annotations

import time
from typing import Any

import db

# Catalogue officiel Komara Agency — bots et agents IA.
OFFICIAL_SERVICES = [
    ("Bot", "Bot Scripté",
     "Bot WhatsApp/Telegram : FAQ, menu, commandes simples — prêt en 48h", 50.0),
    ("Chatbot", "Chatbot IA Vendeur",
     "Chatbot IA qui vend 24/7 : catalogue, panier et devis intégrés", 100.0),
    ("Agent IA", "Agent IA Premium",
     "Agent IA multicanal : mémoire, relances, prise de commande (+50€/mois)", 150.0),
    ("Maintenance", "Maintenance mensuelle",
     "Agent IA : 50€/mois — Bot : 20€/mois. Mises à jour et corrections incluses", 50.0),
]


def _schema() -> list[str]:
    if db.backend() == "postgres":
        serial, real, blob = "BIGSERIAL PRIMARY KEY", "DOUBLE PRECISION", "BYTEA"
    else:
        serial, real, blob = "INTEGER PRIMARY KEY AUTOINCREMENT", "REAL", "BLOB"
    return [
        f"""
        CREATE TABLE IF NOT EXISTS products (
            id {serial},
            category TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            price {real} NOT NULL,
            active INTEGER DEFAULT 1,
            created_at {real} NOT NULL
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS cart_items (
            id {serial},
            session_id TEXT NOT NULL,
            product_id INTEGER NOT NULL,
            qty INTEGER DEFAULT 1,
            added_at {real} NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_cart_session ON cart_items(session_id)",
        f"""
        CREATE TABLE IF NOT EXISTS orders (
            id {serial},
            session_id TEXT NOT NULL,
            summary TEXT NOT NULL,
            total {real} NOT NULL,
            customer TEXT,
            address TEXT,
            phone TEXT,
            status TEXT DEFAULT 'nouveau',
            created_at {real} NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at)",
    ]


def init_db() -> None:
    """Crée les tables et installe le catalogue officiel s'il est vide."""
    db.run_many(_schema())
    rows = db.run("SELECT COUNT(*) AS n FROM products WHERE active = 1")
    if rows and rows[0]["n"]:
        return
    now = time.time()
    for category, name, description, price in OFFICIAL_SERVICES:
        db.run(
            "INSERT INTO products (category, name, description, price, active, created_at)"
            " VALUES (?, ?, ?, ?, 1, ?)",
            (category, name, description, price, now),
        )


# ------------------------------------------------------------------ produits
def products(active_only: bool = True) -> list[dict[str, Any]]:
    init_db()
    sql = "SELECT id, category, name, description, price, active FROM products"
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY price, id"
    return db.run(sql)


def add_product(category: str, name: str, description: str, price: float) -> int:
    init_db()
    db.run(
        "INSERT INTO products (category, name, description, price, active, created_at)"
        " VALUES (?, ?, ?, ?, 1, ?)",
        (category, name, description, price, time.time()),
    )
    rows = db.run("SELECT id FROM products ORDER BY id DESC LIMIT 1")
    return int(rows[0]["id"]) if rows else 0


def update_price(product_id: int, price: float) -> int:
    init_db()
    db.run("UPDATE products SET price = ? WHERE id = ?", (price, product_id))
    return 1


def deactivate_product(product_id: int) -> int:
    init_db()
    db.run("UPDATE products SET active = 0 WHERE id = ?", (product_id,))
    return 1


# --------------------------------------------------------------------- panier
def add_to_cart(session_id: str, product_id: int, qty: int = 1) -> dict | None:
    init_db()
    rows = db.run("SELECT id, name, price FROM products WHERE id = ? AND active = 1", (product_id,))
    if not rows:
        return None
    product = rows[0]
    existing = db.run(
        "SELECT id, qty FROM cart_items WHERE session_id = ? AND product_id = ?",
        (session_id, product_id),
    )
    if existing:
        db.run("UPDATE cart_items SET qty = qty + ? WHERE id = ?", (qty, existing[0]["id"]))
    else:
        db.run(
            "INSERT INTO cart_items (session_id, product_id, qty, added_at) VALUES (?, ?, ?, ?)",
            (session_id, product_id, qty, time.time()),
        )
    return {"name": product["name"], "price": float(product["price"]), **cart_summary(session_id)}


def cart(session_id: str) -> list[dict[str, Any]]:
    init_db()
    return db.run(
        "SELECT c.id, c.qty, p.id AS product_id, p.name, p.price "
        "FROM cart_items c JOIN products p ON p.id = c.product_id "
        "WHERE c.session_id = ? ORDER BY c.id",
        (session_id,),
    )


def cart_summary(session_id: str) -> dict[str, Any]:
    items = cart(session_id)
    total = sum(float(i["price"]) * int(i["qty"]) for i in items)
    return {"items": items, "count": sum(int(i["qty"]) for i in items), "total": round(total, 2)}


def clear_cart(session_id: str) -> int:
    init_db()
    db.run("DELETE FROM cart_items WHERE session_id = ?", (session_id,))
    return 1


# ------------------------------------------------------------------- commande
def create_order(session_id: str, customer: str = "", address: str = "",
                 phone: str = "") -> dict[str, Any] | None:
    summary = cart_summary(session_id)
    if not summary["items"]:
        return None
    lines = ", ".join(f"{i['name']} x{i['qty']}" for i in summary["items"])
    db.run(
        "INSERT INTO orders (session_id, summary, total, customer, address, phone, status, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, 'nouveau', ?)",
        (session_id, lines, summary["total"], customer, address, phone, time.time()),
    )
    rows = db.run("SELECT id FROM orders ORDER BY id DESC LIMIT 1")
    order_id = int(rows[0]["id"]) if rows else 0
    clear_cart(session_id)
    return {"id": order_id, "summary": lines, "total": summary["total"],
            "customer": customer, "address": address, "phone": phone}


def orders(limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    return db.run(
        "SELECT id, session_id, summary, total, customer, address, phone, status, created_at "
        "FROM orders ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )


def set_order_status(order_id: int, status: str) -> int:
    init_db()
    db.run("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
    return 1
