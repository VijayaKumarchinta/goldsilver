import logging
from datetime import datetime, timedelta, timezone

from app.config import Config
from app.services.market_data import get_latest_snapshot
from app.repositories.destinations import list_enabled
from app.repositories.prices import save_snapshot
from app.services.notification_dispatcher import (
    create_jobs,
    dispatch_pending,
    ensure_hourly_notification_schema,
    get_notification_status,
    has_scheduled_slot,
)
from app.services.validation import validate_snapshot_for_persistence

log = logging.getLogger(__name__)


def scheduled_capture(event_type: str):
    if event_type == "hourly_update":
        return scheduled_periodic_update()

    log.info("Scheduler fired: %s", event_type)
    try:
        snap = get_latest_snapshot()
        try:
            validate_snapshot_for_persistence(snap)
        except ValueError as exc:
            log.warning("Skipping %s snapshot because market data is invalid: %s", event_type, exc)
            return {"saved": False, "reason": "invalid_market_data"}
        snapshot_id = save_snapshot(snap, event_type=event_type)
        if event_type in {"market_open", "market_close", "weekly_close"}:
            created = create_jobs(snapshot_id, event_type)
            log.info("Snapshot %s saved, %s notification jobs queued", snapshot_id, created)
            result = dispatch_pending()
            log.info("Dispatch result: %s", result)
        else:
            log.info("Snapshot %s saved for history only (%s)", snapshot_id, event_type)
    except Exception as e:
        log.exception("Scheduled job failed for %s: %s", event_type, e)
        raise


def scheduled_periodic_update():
    log.info("Checking whether the 30-minute Telegram update is due")
    try:
        ensure_hourly_notification_schema()
        dispatch_pending()
        status = get_notification_status()
        if status["last_periodic_status"] in {"pending", "sending"}:
            return {"due": False, "reason": "notification_pending"}

        now = datetime.now(timezone.utc)
        baseline = max(
            (
                value
                for value in (status["last_sent_at"], status["last_periodic_attempt_at"])
                if value is not None
            ),
            default=None,
        )
        if baseline is not None and now < baseline + timedelta(minutes=30):
            return {"due": False, "next_send_at": baseline + timedelta(minutes=30)}

        if not Config.TELEGRAM_BOT_TOKEN:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
        if not list_enabled():
            raise RuntimeError("No enabled Telegram destinations are configured")

        scheduled_for = now.replace(second=0, microsecond=0)
        if has_scheduled_slot(scheduled_for):
            return {"due": False, "reason": "interval_already_processed"}

        snapshot = get_latest_snapshot()
        try:
            validate_snapshot_for_persistence(snapshot)
        except ValueError as exc:
            raise RuntimeError(
                f"Telegram update skipped because live market data is unavailable: {exc}"
            ) from exc

        snapshot_id = save_snapshot(snapshot, event_type="periodic_update")
        created = create_jobs(snapshot_id, "periodic_update", scheduled_for=scheduled_for)
        if not created:
            if has_scheduled_slot(scheduled_for):
                return {"due": False, "reason": "interval_already_processed"}
            raise RuntimeError("Periodic Telegram update did not create any notification jobs")

        result = dispatch_pending()
        log.info(
            "Periodic snapshot %s queued %s notification jobs; dispatch result: %s",
            snapshot_id,
            created,
            result,
        )
        return {"due": True, "snapshot_id": snapshot_id, "created": created, "dispatch": result}
    except Exception:
        log.exception("Periodic Telegram update failed")
        raise