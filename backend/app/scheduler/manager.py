import logging
from app.scheduler.jobs import scheduled_periodic_update

log = logging.getLogger(__name__)
_scheduler = None


def start_scheduler():
    global _scheduler
    if _scheduler:
        return _scheduler

    _scheduler = BackgroundScheduler(timezone="UTC")

    # Only the 30-minute Telegram delivery is a recurring job. The live price
    # event is broadcast to every Socket.IO client by the same job when a
    # fresh market snapshot is available, so the dashboard never polls REST.
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

    # Rebuild the chart from the startup reading, then post a 30-minute
    # Telegram update once the feed is healthy. Neither emits a price event:
    # the live quote is broadcast by get_latest_snapshot instead.
    try:
        result = scheduled_capture("startup")
        log.info("Startup capture: %s", result)
    except Exception:
        log.exception("Startup capture failed")

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