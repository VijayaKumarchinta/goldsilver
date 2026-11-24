import logging
import time
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

log = logging.getLogger(__name__)


NOTIFY_EVENTS = {"market_open", "market_close", "weekly_close"}


def _all_live(snap: dict) -> bool:
    return all(snap.get("metals", {}).get(s, {}).get("live") for s in ("XAU", "XAG"))


def _wait_for_live_prices(event_type: str):
    """Scheduled posts retry for about 3 minutes, then are skipped. An estimate is never sent."""
    for attempt in range(3):
        time.sleep(60)
        snap = get_latest_snapshot()
        if _all_live(snap):
            return snap
        log.warning("%s: live MCX prices still unavailable (retry %s/3)", event_type, attempt + 1)
    return None


def scheduled_capture(event_type: str):
    if event_type == "hourly_update":
        return scheduled_periodic_update()

    log.info("Scheduler fired: %s", event_type)
    try:
        snap = get_latest_snapshot()
        if not _all_live(snap):
            snap = _wait_for_live_prices(event_type) if event_type in NOTIFY_EVENTS else None
            if snap is None:
                log.error("%s skipped: live MCX prices are unavailable, so nothing was saved or sent", event_type)
                return
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
        if not all(
            snapshot.get("metals", {}).get(symbol, {}).get("live")
            for symbol in ("XAU", "XAG")
        ):
            raise RuntimeError("Telegram update skipped because live market data is unavailable")

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