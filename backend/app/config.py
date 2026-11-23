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

    # FreeAPI local market reference (India gold/silver buy/sell + GST)
    FREEAPI_BASE = os.getenv("FREEAPI_BASE", "https://api.oropocket.com/public").rstrip("/")
    FREEAPI_CACHE_SECONDS = int(os.getenv("FREEAPI_CACHE_SECONDS", "60"))
    FREEAPI_MAX_STALENESS_SECONDS = int(os.getenv("FREEAPI_MAX_STALENESS_SECONDS", "300"))
    TROY_OUNCE_IN_GRAMS = Decimal("31.1035")
    MAX_PRICE_STALENESS_SECONDS = int(os.getenv("MAX_PRICE_STALENESS_SECONDS", "300"))
    MAX_SINGLE_TICK_JUMP_PCT = Decimal(os.getenv("MAX_SINGLE_TICK_JUMP_PCT", "15.0"))
    MAX_JUMP_REFERENCE_AGE_SECONDS = int(os.getenv("MAX_JUMP_REFERENCE_AGE_SECONDS", "3600"))
    MIN_USD_INR = Decimal(os.getenv("MIN_USD_INR", "50"))
    MAX_USD_INR = Decimal(os.getenv("MAX_USD_INR", "150"))