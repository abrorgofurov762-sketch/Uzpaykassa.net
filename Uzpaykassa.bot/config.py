"""Application configuration.

Sensitive values must be configured as environment variables in Render.
Do not commit BOT_TOKEN or provider credentials to source control.
"""
import os


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value.strip())
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer") from exc


def _bool_env(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


DATABASE_PATH = os.getenv("DATABASE_PATH", "bot_database.db").strip() or "bot_database.db"
ADMIN_ID = _int_env("ADMIN_ID", 1242592772)
MIN_DEPOSIT = _int_env("MIN_DEPOSIT", 15000)
MAX_DEPOSIT = _int_env("MAX_DEPOSIT", 10000000)
NOTIFICATION_CHANNEL_ID = _int_env("NOTIFICATION_CHANNEL_ID", -100123456789)
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
BOT_ACTIVE = _bool_env("BOT_ACTIVE", True)

# API configuration placeholders only. No provider API integration is implemented here.
MOSTBET_API_KEY = os.getenv("MOSTBET_API_KEY", "").strip()
MOSTBET_API_SECRET = os.getenv("MOSTBET_API_SECRET", "").strip()
MOSTBET_API_BASE_URL = os.getenv("MOSTBET_API_BASE_URL", "").strip()
XBET_API_KEY = os.getenv("XBET_API_KEY", "").strip()
XBET_API_SECRET = os.getenv("XBET_API_SECRET", "").strip()
XBET_API_BASE_URL = os.getenv("XBET_API_BASE_URL", "").strip()
MOBCASH_API_KEY = os.getenv("MOBCASH_API_KEY", "").strip()
MOBCASH_API_SECRET = os.getenv("MOBCASH_API_SECRET", "").strip()
MOBCASH_API_BASE_URL = os.getenv("MOBCASH_API_BASE_URL", "").strip()
