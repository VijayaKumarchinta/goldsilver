import logging

from app.config import Config
from app.repositories.destinations import ensure_telegram_destination, list_enabled
from app.scheduler.jobs import scheduled_periodic_update

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def main():
    if not Config.DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")
    if not Config.TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")

    ensure_telegram_destination()
    if not list_enabled():
        raise RuntimeError("No enabled Telegram destinations are configured")

    result = scheduled_periodic_update()
    logging.info("Periodic notification check: %s", result)


if __name__ == "__main__":
    main()
