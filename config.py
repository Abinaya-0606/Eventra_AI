"""Central configuration. Every secret/setting comes from environment variables (.env)."""
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


class Config:
    # Used to sign session cookies (needed from Phase 2). Set SECRET_KEY in .env for production.
    SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_hex(32)
    MAX_CONTENT_LENGTH = 1 * 1024 * 1024  # reject request bodies over 1 MB

    # --- database (SQLite file; the instance/ folder is git-ignored) ---
    DATABASE = os.getenv("DATABASE_PATH", str(BASE_DIR / "instance" / "eventai.db"))
    PASSWORD_HASH_METHOD = "scrypt"
    COLLEGE_NAME = os.getenv("COLLEGE_NAME", "")  # shown on proposal covers (optional)

    # --- sessions / cookies ---
    SESSION_COOKIE_HTTPONLY = True   # JavaScript cannot read the cookie
    SESSION_COOKIE_SAMESITE = "Lax"  # not sent on cross-site POSTs
    SESSION_COOKIE_SECURE = False    # True in production (HTTPS only)
    PERMANENT_SESSION_LIFETIME = 7 * 24 * 3600

    # --- login protection and password reset ---
    MAX_FAILED_LOGINS = _int("MAX_FAILED_LOGINS", 5)
    LOCKOUT_SECONDS = _int("LOCKOUT_SECONDS", 600)
    RESET_TOKEN_MINUTES = _int("RESET_TOKEN_MINUTES", 30)
    # Public address used inside reset emails, e.g. https://eventra-ai.onrender.com. Falls back to the request host.
    APP_BASE_URL = os.getenv("APP_BASE_URL", "").strip()

    # --- email (optional; without SMTP, reset links are printed to the console in development) ---
    SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
    SMTP_PORT = _int("SMTP_PORT", 587)
    SMTP_USER = os.getenv("SMTP_USER", "").strip()
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    MAIL_FROM = os.getenv("MAIL_FROM", "").strip() or os.getenv("SMTP_USER", "").strip() or "no-reply@eventra.local"

    # --- hosting ---
    TRUST_PROXY = False  # True in production: believe X-Forwarded-* headers set by the host's proxy (real client IP, https)
    # Optional first admin, created at start-up ONLY when no admin exists yet (for hosts without a shell). Remove afterwards.
    ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "").strip()
    ADMIN_NAME = os.getenv("ADMIN_NAME", "").strip() or "Administrator"
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

    # --- Groq (LLM) ---
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
    GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant").strip()
    # Tamil needs a stronger model; falls back to GROQ_MODEL when not set.
    GROQ_MODEL_TAMIL = os.getenv("GROQ_MODEL_TAMIL", "").strip() or GROQ_MODEL
    LLM_TIMEOUT = _float("LLM_TIMEOUT", 45.0)

    # --- RAG / ChromaDB ---
    DATA_DIR = BASE_DIR / "data"
    CHROMA_DIR = os.getenv("CHROMA_DIR", str(BASE_DIR / "chroma_db"))
    RAG_COLLECTION = "college_events_v2"
    RAG_TOP_K = _int("RAG_TOP_K", 4)
    # Cosine distance: smaller = more similar. Chunks farther than this are ignored.
    RAG_MAX_DISTANCE = _float("RAG_MAX_DISTANCE", 1.0)


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    GROQ_API_KEY = "test-key"
    PASSWORD_HASH_METHOD = "pbkdf2:sha256:1000"  # fast hashing keeps the test suite quick


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    TRUST_PROXY = os.getenv("TRUST_PROXY", "1") != "0"


CONFIGS = {"development": DevelopmentConfig, "testing": TestingConfig, "production": ProductionConfig}
