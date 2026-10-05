"""All settings in one place.

Values come from a `.env` file next to this project (copy `.env.example`),
or from normal environment variables. Environment variables win.
"""
import os
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent


def _load_env():
    f = ROOT / ".env"
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env()


def _get(name, default):
    return os.environ.get(name) or default


# --- the model (any OpenAI-compatible endpoint) ---
BASE_URL = _get("LLM_BASE_URL", "http://localhost:11434/v1").rstrip("/")
API_KEY = _get("LLM_API_KEY", "ollama")
MODEL = _get("LLM_MODEL", "gemma4:e2b")
HOST = urlparse(BASE_URL).hostname or ""
IS_LOCAL = HOST in ("localhost", "127.0.0.1", "::1")
DELAY = float(_get("LLM_DELAY", "0" if IS_LOCAL else "4.5"))  # pause between indexing calls

# --- the database ---
MONGODB_URI = os.environ.get("MONGODB_URI") or None  # unset = local SQLite
MONGODB_DB = _get("MONGODB_DB", "screen_memory")
SQLITE_PATH = Path(_get("SQLITE_PATH", str(Path.home() / "screen_memory_v2.db")))

# --- the screenshots ---
SHOTS_DIR = Path(_get("SHOTS_DIR", str(Path.home() / "Pictures" / "Screenshots")))
EXTS = {".png", ".jpg", ".jpeg"}

# --- agent ---
MAX_AGENT_STEPS = int(_get("MAX_AGENT_STEPS", "6"))


def where():
    return "LOCAL" if IS_LOCAL else "REMOTE"


def summary():
    db = "MongoDB Atlas" if MONGODB_URI else f"SQLite ({SQLITE_PATH})"
    return (
        f"Model endpoint : {BASE_URL}\n"
        f"Model          : {MODEL}\n"
        f"Model runs on  : {where()}\n"
        f"Database       : {db}\n"
        f"Screenshots    : {SHOTS_DIR}"
    )
