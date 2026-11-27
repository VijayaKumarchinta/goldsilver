import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import Config
from app.scheduler.jobs import scheduled_capture, scheduled_periodic_update

log = logging.getLogger(__name__)
_scheduler = None


def start_scheduler():
    global _scheduler
    if _scheduler:
        return _scheduler

    _scheduler = BackgroundScheduler(timezone="UTC")

    jobs = [
        (
            "chart_snapshot",
            CronTrigger(minute="*/5", second=0, timezone="Asia/Kolkata"),
            scheduled_capture,
            ["chart_update"],
        ),
        (
            "periodic_update",
            CronTrigger(minute="*/30", second=0, timezone="Asia/Kolkata"),
            scheduled_periodic_update,
            [],
        ),
    ]
    for name, trigger, callback, args in jobs:
        _scheduler.add_job(
            callback,
            trigger=trigger,
            args=args,
            id=name,
            replace_existing=True,
            misfire_grace_time=300,
            coalesce=True,
            max_instances=1,
        )
        log.info("Registered job: %s -> %s", name, trigger)
    _scheduler.start()

    if not Config.TELEGRAM_BOT_TOKEN:
        log.warning(
            "Telegram delivery disabled at startup: TELEGRAM_BOT_TOKEN is not configured"
        )
    elif not Config.TELEGRAM_CHAT_ID:
        log.warning(
            "Telegram delivery disabled at startup: TELEGRAM_CHAT_ID is not configured"
        )

    try:
        result = scheduled_periodic_update()
        log.info("Startup Telegram update: %s", result)
    except Exception:
        log.exception("Startup Telegram update failed")

    return _scheduler


def shutdown_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
