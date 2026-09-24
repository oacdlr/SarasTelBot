"""Configuration loaded from environment variables (.env locally).

Values are read lazily so that importing SARAS modules (e.g. in tests)
never requires real credentials.
"""
import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"
DEFAULT_GEMINI_FAST_MODEL = "gemini-3.5-flash-lite"


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required setting {name}. Add it to your .env file.")
    return value


def telegram_bot_token() -> str:
    return _required("TELEGRAM_BOT_TOKEN")


@lru_cache
def telegram_allowed_user_ids() -> frozenset[int]:
    raw = _required("TELEGRAM_ALLOWED_USER_IDS")
    return frozenset(int(part) for part in raw.split(",") if part.strip())


def gemini_api_key() -> str:
    return _required("GEMINI_API_KEY")


def gemini_model() -> str:
    return os.environ.get("GEMINI_MODEL", "").strip() or DEFAULT_GEMINI_MODEL


def gemini_fast_model() -> str:
    return os.environ.get("GEMINI_FAST_MODEL", "").strip() or DEFAULT_GEMINI_FAST_MODEL


def obsidian_vault_path() -> str:
    return _required("OBSIDIAN_VAULT_PATH")
