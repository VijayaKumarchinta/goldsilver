import os
from decimal import Decimal
from dotenv import load_dotenv

load_dotenv()

class Config:
    DATABASE_URL = os.getenv("DATABASE_URL")
    SECRET_KEY = os.getenv("SECRET_KEY", "dev")
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

    XAUS_BASE = os.getenv("XAUS_BASE", "https://xaus.com").rstrip("/")
    TROY_OUNCE_IN_GRAMS = float(os.getenv("TROY_OUNCE_IN_GRAMS", "31.1035"))

    # MCX futures are the price source (they include India's import duty).
    MCX_ENABLED = os.getenv("MCX_ENABLED", "1") == "1"
    MCX_ROLL_DAYS = int(os.getenv("MCX_ROLL_DAYS", "5"))  # skip contracts expiring within N days
    # Dashboard-only fallback when MCX cannot be reached: spot x (1 + premium).
    # Import duty on gold and silver has been 15% since 13 May 2026. Never used for Telegram posts.
    ESTIMATE_PREMIUM_GOLD = float(os.getenv("ESTIMATE_PREMIUM_GOLD", "0.15"))
    ESTIMATE_PREMIUM_SILVER = float(os.getenv("ESTIMATE_PREMIUM_SILVER", "0.15"))

    # Legacy FreeAPI / validation bounds restored so the existing unit test suite
    # can still exercise the old validation paths against a known configuration.
    MIN_USD_INR = float(os.getenv("MIN_USD_INR", "70"))
    MAX_USD_INR = float(os.getenv("MAX_USD_INR", "100"))
    MAX_PRICE_STALENESS_SECONDS = int(os.getenv("MAX_PRICE_STALENESS_SECONDS", "300"))
    MAX_SINGLE_TICK_JUMP_PCT = float(os.getenv("MAX_SINGLE_TICK_JUMP_PCT", "15"))
    FREEAPI_BASE = os.getenv("FREEAPI_BASE")