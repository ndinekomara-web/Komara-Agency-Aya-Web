"""
Configuration centrale d'Aya — application web autonome.

Aucune dépendance à Telegram : l'application se lance comme un serveur web
(ordinateur, serveur ou téléphone via le navigateur, installable en PWA).
"""
import os
from dotenv import load_dotenv

load_dotenv()

# === Application ===
APP_NAME = os.getenv("APP_NAME", "Aya — Komara Agency")
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("PORT", os.getenv("APP_PORT", "8000")))
# Jeton d'accès facultatif : s'il est défini, l'application demande ce mot de
# passe avant d'ouvrir la conversation (utile si elle est exposée en ligne).
APP_ACCESS_TOKEN = os.getenv("APP_ACCESS_TOKEN", "").strip()

# === Google (facultatif) ===
GOOGLE_SHEETS_ID = os.getenv("GOOGLE_SHEETS_ID", "")
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "./credentials.json")
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON", "")

# === Langue ===
DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANGUAGE", "fr")
SUPPORTED_LANGUAGES = ["fr", "ar", "en"]

# === RAG ===
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "3"))
RAG_MIN_SCORE = float(os.getenv("RAG_MIN_SCORE", "0.65"))
KNOWLEDGE_BASE_PATH = os.getenv("KNOWLEDGE_BASE_PATH", "./knowledge_base")
# Moteur de recherche :
#   auto   -> embeddings si sentence-transformers est installé, sinon mots-clés
#   embed  -> embeddings obligatoires
#   keyword-> mots-clés uniquement (installation légère, aucun modèle à télécharger)
RAG_BACKEND = os.getenv("RAG_BACKEND", "auto").strip().lower()

# === Performance ===
MAX_CACHE_SIZE = int(os.getenv("MAX_CACHE_SIZE", "10000"))
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "86400"))
SHEETS_LOG_ASYNC = True

# === Chemins ===
def _default_memory_dir() -> str:
    """Choisit le dossier de stockage selon l'environnement d'exécution.

    Sur Railway (et la plupart des plateformes), le disque de l'application
    est effacé à chaque déploiement : on privilégie donc le volume persistant
    monté sur /app/data. En local, on reste dans ./data.
    """
    explicit = os.getenv("MEMORY_DIR", "").strip()
    if explicit:
        return explicit
    if os.getenv("RAILWAY_ENVIRONMENT") or os.path.isdir("/app/data"):
        return "/app/data"
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


MEMORY_DIR = _default_memory_dir()
SQLITE_DB_PATH = os.path.join(MEMORY_DIR, "memory.db")
