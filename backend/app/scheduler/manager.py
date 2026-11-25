import logging
from app.config import Config
from app.scheduler.jobs import scheduled_periodic_update
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

log = logging.getLogger(__name__)
_scheduler = None


def start_scheduler():
    global _scheduler
    if _scheduler:
        return _scheduler

    _scheduler = BackgroundScheduler(timezone="UTC")

    jobs = [
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

    # Guard so a misconfigured deploy (e.g. wrong bot token in Render env)
    # never loops and never emits 400s to a wrong chat. The check below is
    # informational: the actual delivery determinism lives in
    # scheduled_periodic_update().
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
