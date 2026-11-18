"""Tests de la couche base de données (SQLite en local, PostgreSQL en prod)."""
import db
import chat_store


def test_local_backend_is_sqlite():
    assert db.backend() == "sqlite"
    assert db.describe()["backend"] == "sqlite"
    assert chat_store.stats()["backend"] == "sqlite"


def test_placeholder_translation(monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "postgres://user:pass@host:5432/db")
    assert db.backend() == "postgres"
    assert db._sql("SELECT 1 FROM sessions WHERE session_id = ?") == (
        "SELECT 1 FROM sessions WHERE session_id = %s"
    )
    assert db._dsn().startswith("postgresql://")
    assert "sslmode=require" in db._dsn()
    assert "sslmode=require" not in db._dsn() or db._dsn().count("sslmode=") == 1


def test_internal_railway_host_skips_ssl(monkeypatch):
    """Le réseau interne Railway refuse le SSL : on ne doit pas le forcer."""
    monkeypatch.setattr(db, "DATABASE_URL", "postgresql://u:p@postgres.railway.internal:5432/railway")
    assert "sslmode" not in db._dsn()
    monkeypatch.setattr(db, "DATABASE_URL", "postgresql://u:p@localhost:5432/db")
    assert "sslmode" not in db._dsn()


def test_external_host_forces_ssl(monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "postgresql://u:p@db.abc.supabase.co:5432/postgres")
    assert db._dsn().endswith("sslmode=require")


def test_dsn_keeps_existing_ssl(monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "postgresql://u:p@h/db?sslmode=disable")
    assert db._dsn().count("sslmode=") == 1


def test_postgres_schema_is_valid(monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "postgresql://u:p@h/db")
    statements = chat_store._schema()
    joined = " ".join(statements)
    assert "BIGSERIAL" in joined
    assert "DOUBLE PRECISION" in joined
    assert "AUTOINCREMENT" not in joined

    monkeypatch.setattr(db, "DATABASE_URL", "")
    sqlite_schema = " ".join(chat_store._schema())
    assert "AUTOINCREMENT" in sqlite_schema


def test_psycopg2_driver_installed():
    import psycopg2  # noqa: F401

    assert psycopg2.__version__


def test_session_upsert_keeps_language():
    """L'upsert doit conserver la langue quand on ne la repasse pas."""
    chat_store.init_db()
    chat_store.touch_session("sess-lang", "ar")
    chat_store.touch_session("sess-lang")
    rows = db.run("SELECT lang FROM sessions WHERE session_id = ?", ("sess-lang",))
    assert rows[0]["lang"] == "ar"


def test_fallback_to_sqlite_keeps_app_alive(monkeypatch):
    """Une base distante injoignable ne doit pas empêcher l'application de tourner."""
    import importlib
    import db as db_module
    import chat_store as store

    monkeypatch.setattr(db_module, "DATABASE_URL", "postgresql://u:p@postgres.railway.internal:5432/railway")
    assert db_module.backend() == "postgres"

    try:
        store.init_db()  # échoue réellement (hôte inexistant) puis bascule
    except Exception:
        pass
    assert db_module.backend() == "sqlite"
    assert db_module.describe()["backend"] == "sqlite"
    store.touch_session("fallback-session")
    assert store.stats()["sessions"] >= 1
