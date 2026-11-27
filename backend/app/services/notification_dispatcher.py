from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.extensions import get_db
from app.messaging.telegram import TelegramSender
from app.repositories.destinations import list_enabled
from app.services.message_formatter import format_price_message
from psycopg2.extras import RealDictCursor

MAX_ATTEMPTS = 3
BACKOFF_SECONDS = [30, 120, 480]
_hourly_schema_ready = False


def create_sender() -> TelegramSender:
    return TelegramSender()


def ensure_hourly_notification_schema():
    global _hourly_schema_ready
    if _hourly_schema_ready:
        return

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            ALTER TABLE goldbot.notification_jobs
              ADD COLUMN IF NOT EXISTS scheduled_for TIMESTAMPTZ,
              ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            """)
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_notification_schedule_slot
            ON goldbot.notification_jobs (event_type, scheduled_for, destination_id)
            WHERE scheduled_for IS NOT NULL
            """)
        conn.commit()
        _hourly_schema_ready = True
    finally:
        conn.close()


def get_notification_status() -> dict:
    ensure_hourly_notification_schema()
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT
                MAX(updated_at) FILTER (WHERE status = 'sent') AS last_sent_at,
                MAX(updated_at) FILTER (
                    WHERE status = 'sent'
                      AND event_type IN ('periodic_update', 'hourly_update', 'hourly')
                ) AS last_periodic_sent_at,
                MAX(COALESCE(scheduled_for, updated_at)) FILTER (
                    WHERE event_type IN ('periodic_update', 'hourly_update', 'hourly')
                ) AS last_periodic_attempt_at
            FROM goldbot.notification_jobs
            """)
        status = dict(cur.fetchone())
        cur.execute("""
            SELECT status
            FROM goldbot.notification_jobs
            WHERE event_type IN ('periodic_update', 'hourly_update', 'hourly')
            ORDER BY COALESCE(scheduled_for, updated_at) DESC, id DESC
            LIMIT 1
            """)
        latest_periodic = cur.fetchone()
        status["last_periodic_status"] = (
            latest_periodic["status"] if latest_periodic else None
        )

        interval = timedelta(minutes=30)
        now = datetime.now(timezone.utc)
        baseline = max(
            (
                value
                for value in (
                    status["last_sent_at"],
                    status["last_periodic_attempt_at"],
                )
                if value is not None
            ),
            default=None,
        )
        if baseline is None or now >= baseline + interval:
            status["next_send_at"] = _next_cron_slot_ist(now)
        else:
            status["next_send_at"] = _next_cron_slot_ist(baseline + interval)
        status["interval_minutes"] = 30
        return status
    finally:
        conn.close()


def _next_cron_slot_ist(moment: datetime) -> datetime:
    """Next IST :00/:30 tick, so 'Next send' uses the same clock as the
    dashboard and the Telegram 'Next update'. The apscheduler cron for the
    periodic_update job still runs in UTC, but the value the UI reads is the
    IST slate it understands, so it is never a stale UTC timestamp that the
    dashboard shows as already past.
    """
    moment = moment.astimezone(ZoneInfo("Asia/Kolkata"))
    moment = moment.replace(second=0, microsecond=0)
    if moment.minute in (0, 30):
        return moment.astimezone(timezone.utc)
    if moment.minute < 30:
        return moment.replace(minute=30).astimezone(timezone.utc)
    return (moment + timedelta(hours=1)).replace(minute=0).astimezone(timezone.utc)


def has_scheduled_slot(scheduled_for: datetime) -> bool:
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM goldbot.notification_jobs
                WHERE event_type = 'periodic_update'
                  AND scheduled_for = %s
            )
            """,
            (scheduled_for,),
        )
        return cur.fetchone()[0]
    finally:
        conn.close()


def create_jobs(
    snapshot_id: int,
    event_type: str,
    scheduled_for: datetime | None = None,
) -> int:
    ensure_hourly_notification_schema()
    destinations = list_enabled()
    if not destinations:
        return 0
    conn = get_db()
    created = 0
    try:
        cur = conn.cursor()
        for d in destinations:
            cur.execute(
                """
                INSERT INTO notification_jobs
                    (snapshot_id, destination_id, event_type, status, scheduled_for)
                VALUES (%s, %s, %s, 'pending', %s)
                ON CONFLICT DO NOTHING
                """,
                (snapshot_id, d["id"], event_type, scheduled_for),
            )
            created += cur.rowcount
        conn.commit()
        return created
    finally:
        conn.close()


def _finish_job(
    cur,
    job_id: int,
    new_attempts: int,
    outcome: dict,
    results: dict,
) -> None:
    """Apply the outcome of one delivery attempt to the job row and counters.

    Three outcomes exist: the message was accepted (``ok``), the job exhausted
    its retry budget, or a backoff slot still remains. The same three branches
    were repeated inline in ``dispatch_pending``; this helper keeps that logic
    in a single place. Returned values are appended to ``results`` in place.
    """
    if outcome.get("ok"):
        cur.execute(
            """
            UPDATE notification_jobs
            SET status = 'sent', attempts = %s, last_error = NULL, updated_at = NOW()
            WHERE id = %s
            """,
            (new_attempts, job_id),
        )
        results["sent"] += 1
        return

    if new_attempts >= MAX_ATTEMPTS:
        cur.execute(
            """
            UPDATE notification_jobs
            SET status = 'failed', attempts = %s, last_error = %s, updated_at = NOW()
            WHERE id = %s
            """,
            (new_attempts, outcome.get("detail"), job_id),
        )
        results["exhausted"] += 1
        return

    delay = BACKOFF_SECONDS[new_attempts - 1]
    next_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
    cur.execute(
        """
        UPDATE notification_jobs
        SET status = 'pending', attempts = %s, last_error = %s,
            next_attempt_at = %s, updated_at = NOW()
        WHERE id = %s
        """,
        (new_attempts, outcome.get("detail"), next_at, job_id),
    )
    results["retry_scheduled"] += 1


def _load_snapshot(cur, snapshot_id: int) -> dict:
    cur.execute(
        """
        SELECT s.captured_at, s.base_currency, s.output_currency,
               (SELECT jsonb_object_agg(
                   symbol,
                   jsonb_build_object(
                       'usd_per_oz', usd_per_oz,
                       'inr_per_gram', inr_per_gram,
                       'updated_at', provider_updated_at,
                       'source', provider
                   )
               ) FROM metal_prices WHERE snapshot_id = s.id) AS metals,
               (SELECT jsonb_object_agg(base || '_' || quote, rate)
                FROM fx_rates WHERE snapshot_id = s.id) AS fx,
               (SELECT provider
                FROM fx_rates
                WHERE snapshot_id = s.id AND base = 'USD' AND quote = 'INR'
                LIMIT 1) AS fx_source
        FROM price_snapshots s
        WHERE s.id = %s
        """,
        (snapshot_id,),
    )
    row = cur.fetchone()
    return {
        "captured_at": row["captured_at"].isoformat(),
        "base_currency": row["base_currency"],
        "output_currency": row["output_currency"],
        "metals": {
            k: {
                **v,
                "usd_per_oz": str(v["usd_per_oz"]),
                "inr_per_gram": str(v["inr_per_gram"]),
                "updated_at": v["updated_at"],
            }
            for k, v in row["metals"].items()
        },
        "fx": {k: str(v) for k, v in (row["fx"] or {}).items()},
        "fx_source": row["fx_source"],
    }


def dispatch_pending(sender: TelegramSender | None = None, limit: int = 20) -> dict:


    if sender is None:
        sender = create_sender()
    ensure_hourly_notification_schema()
    conn = get_db()
    results = {"sent": 0, "failed": 0, "retry_scheduled": 0, "exhausted": 0}
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            SELECT j.id, j.event_type, j.attempts, j.snapshot_id,
                   d.id AS destination_id, d.channel, d.identifier
            FROM notification_jobs j
            JOIN destinations d ON d.id = j.destination_id
            WHERE j.status IN ('pending', 'sending', 'failed')
              AND d.enabled = TRUE
              AND j.attempts < %s
              AND j.next_attempt_at <= NOW()
            ORDER BY j.id
            FOR UPDATE OF j SKIP LOCKED
            """,
            (MAX_ATTEMPTS,),
        )
        jobs = cur.fetchall()

        for job in jobs:
            cur.execute(
                """
                UPDATE notification_jobs
                SET status = 'sending', updated_at = NOW()
                WHERE id = %s
                """,
                (job["id"],),
            )
            snap = _load_snapshot(cur, job["snapshot_id"])
            text = format_price_message(snap, job["event_type"])
            # destination_id is the local destinations row id; Telegram needs
            # the chat identifier stored alongside it.
            outcome = sender.send(job["identifier"], text)
            new_attempts = job["attempts"] + 1
            _finish_job(
                cur,
                job["id"],
                new_attempts,
                outcome,
                results,
            )

        conn.commit()
        return results
    finally:
        conn.close()
