import os
from decimal import Decimal
from dotenv import load_dotenv

load_dotenv()

class Config:
    DATABASE_URL = os.getenv("DATABASE_URL")
    SECRET_KEY = os.getenv("SECRET_KEY", "dev")
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

    TROY_OUNCE_IN_GRAMS = float(os.getenv("TROY_OUNCE_IN_GRAMS", "31.1035"))
    # How long a live quote may be missing before the dashboard flags the feed.
    FEED_STALE_SECONDS = int(os.getenv("FEED_STALE_SECONDS", "300"))

    # Legacy FreeAPI / validation bounds restored so the existing unit test suite
    # can still exercise the old validation paths against a known configuration.
    MIN_USD_INR = float(os.getenv("MIN_USD_INR", "70"))
    MAX_USD_INR = float(os.getenv("MAX_USD_INR", "100"))
    MAX_PRICE_STALENESS_SECONDS = int(os.getenv("MAX_PRICE_STALENESS_SECONDS", "300"))
    MAX_SINGLE_TICK_JUMP_PCT = float(os.getenv("MAX_SINGLE_TICK_JUMP_PCT", "15"))
    FREEAPI_BASE = os.getenv("FREEAPI_BASE")