import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
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
            "market_capture",
            IntervalTrigger(minutes=5, timezone="UTC"),
            scheduled_capture,
            ["market_capture"],
        ),
        (
            "periodic_notification_check",
            IntervalTrigger(minutes=1, timezone="UTC"),
            scheduled_periodic_update,
            [],
        ),
        (
            "market_open",
            CronTrigger(hour=9, minute=0, day_of_week="mon-fri", timezone="Asia/Kolkata"),
            scheduled_capture,
            ["market_open"],
        ),
        (
            "market_close",
            CronTrigger(hour=23, minute=55, day_of_week="mon-thu", timezone="Asia/Kolkata"),
            scheduled_capture,
            ["market_close"],
        ),
        (
            "weekly_close",
            CronTrigger(hour=23, minute=55, day_of_week="fri", timezone="Asia/Kolkata"),
            scheduled_capture,
            ["weekly_close"],
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

    # Save an immediate reading so charts have data after startup/restart.
    try:
        scheduled_capture("startup")
    except Exception:
        log.exception("Startup market capture failed")

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