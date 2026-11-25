import logging
import threading
from datetime import datetime, timezone, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.config import Config
from app.extensions import get_db
from app.messaging.base import Sender
from app.providers import metals_tradingview
log = logging.getLogger(__name__)
_BOOT_AT = datetime.now(timezone.utc)
_last_live_at: datetime | None = None

_broadcast_lock = threading.Lock()
_price_event = {"last": None, "last_at": None}


def subscribe_price_event():
    """Return a copy of the latest live price event, safe to read without locks."""
    with _broadcast_lock:
        return dict(_price_event)


def _json_safe(obj):
    """Recursively convert Decimal (and other non-JSON types) to a JSON-safe Python type.

    The snapshot is an arbitrarily nested dict/list emitted straight to every
    Socket.IO client.  The decimal fields come out of PostgreSQL raw, so each
    leaf is coerced to float; mappings and sequences are walked instead of
    rejected.
    """
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    if isinstance(obj, dict):
        return {key: _json_safe(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(item) for item in obj]
    if isinstance(obj, (datetime,)):
        return obj.isoformat() if obj.tzinfo else obj.isoformat()
    return obj


def set_price_event(snapshot: dict | None):
    """Record the newest live market snapshot and notify every Socket.IO client.

    The snapshot is serialised to JSON first so ``Decimal`` values (which come
    straight out of PostgreSQL) are converted to ``float`` and can be sent
    over the Socket.IO payload.
    """
    with _broadcast_lock:
        _price_event["last"] = snapshot
        _price_event["last_at"] = datetime.now(timezone.utc)
        _last_live_at = _price_event["last_at"]

    try:
        _sio = _get_socketio()
        _sio.emit(
            "price_update",
            _json_safe(snapshot) if snapshot is not None else None,
            callback=on_price_update_ack,
            namespace="/",
        )
    except Exception:
        log.exception("price event broadcast failed")

def on_price_update_ack(client_id, *args):
    """Called by the Socket.IO server when the client acks `price_update`.

    ``client_id`` is the socket ID that acknowledged the message.  The
    payload (snapshot) is intentionally ignored here: the server's job is
    only to prove delivery.  The client owns reconnection/retry and later
    pushes live price deltas back with the same protocol.
    """
    log.debug("price_update ack from socket=%s payload=%r", client_id, args)
    # Register the Socket.IO event that the dashboard uses to push live price
    # deltas back up to the server (the dashboard is read-write, not just a
    # one-way consumer).
    _register_live_price_events(_get_socketio())
    try:
        _nd = _get_notification_dispatcher()
        _nd.record_live_price_update(socket_id, payload)
        log.debug(
            "received live price update from socket=%s",
            socket_id,
        )
    except Exception:
        log.exception(
            "failed to record live price update from socket=%s",
            socket_id,
        )


def _register_live_price_events(socketio):
    """Register the Socket.IO events used by the bidirectional live stream.

    Bound at app startup (when ``socketio`` exists) so the handler decorates
    the same Socket.IO instance the broadcast uses.
    """
    socketio.on("live_price_update", on_price_update_from_client)


def source_family(source) -> str:
    """Spot and estimate histories from earlier versions are kept apart from MCX rows."""
    s = (source or "").lower()
    if s.startswith("mcx"):
        return "mcx"
    return "estimate" if "estimate" in s else "spot"

_FAMILY_SQL = {
    "mcx": "m.provider LIKE 'MCX%%'",
    "estimate": "m.provider LIKE '%%(estimate)'",
    "spot": "m.provider NOT LIKE 'MCX%%' AND m.provider NOT LIKE '%%(estimate)'",
}


def _live_quote() -> dict | None:
    quote = metals_tradingview.fetch_mcx()
    if not quote:
        return None

    fx = Decimal(str(quote["fx"]))
    ounce = Decimal(str(Config.TROY_OUNCE_IN_GRAMS))
    metals = {}
    for symbol, key, per_gram_divisor, spot_key in (
        ("XAU", "gold", 10, "XAU"),
        ("XAG", "silver", 1000, "XAG"),
    ):
        gram = Decimal(str(quote[key]["price"])) / per_gram_divisor  # gold per 10 g, silver per kg
        spot_gram = Decimal(str(quote["spot"][spot_key])) * fx / ounce
        ratio = gram / spot_gram
        if not (Decimal("0.95") <= ratio <= Decimal("1.6")):
            log.warning("MCX %s price rejected: %.2fx the converted spot price", key, ratio)
            return None
        metals[symbol] = {
            "inr_per_gram": gram,
            "source": f"MCX {key.upper()} front-month futures",
            "updated_at": quote["fetched_at"],
            "spot_inr_per_10g": spot_gram * Decimal("10"),
            "usd_per_oz": quote["spot"][spot_key],
        }
    return {"metals": metals, "fx": quote["fx"]}


def feed_health(now: datetime | None = None) -> dict:
    """How long the market feed has been unable to serve a live quote.

    Measured from the last successful live quote, or from process start when
    there has not been one yet. ``stale`` turns true after
    ``Config.FEED_STALE_SECONDS`` (5 minutes by default).
    """
    now = now or datetime.now(timezone.utc)
    last = _last_live_at
    reference = last or _BOOT_AT
    age = max(0, int((now - reference).total_seconds()))
    threshold = Config.FEED_STALE_SECONDS
    return {
        "stale": age >= threshold,
        "last_success_at": last.isoformat() if last else None,
        "age_seconds": age,
        "threshold_seconds": threshold,
    }


def _market_open_now() -> bool:
    """True during IST market hours (09:00-23:55 Mon-Fri)."""
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    t = time(9, 0)
    t_close = time(23, 55)
    wd = now.isoweekday()
    if wd > 5:
        return False
    now_time = now.time().replace(tzinfo=None)
    return t <= now_time <= t_close


def get_latest_snapshot() -> dict:
    global _last_live_at
    live = _live_quote()
    if live:
        snapshot = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "base_currency": "USD",
            "output_currency": "INR",
            "market_open": _market_open_now(),
            "metals": {
                "XAU": {**live["metals"]["XAU"], "live": True},
                "XAG": {**live["metals"]["XAG"], "live": True},
            },
            "fx": {
                "USD_INR": float(live["fx"]),
                "FX_SOURCE": "TradingView",
            },
        }
        set_price_event(snapshot)
        return snapshot

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT s.id, s.captured_at, m.symbol, m.inr_per_gram, m.usd_per_oz, m.provider "
            "FROM goldbot.price_snapshots s "
            "JOIN goldbot.metal_prices m ON s.id = m.snapshot_id "
            "WHERE s.id = (SELECT id FROM goldbot.price_snapshots ORDER BY captured_at DESC LIMIT 1)"
        )
        rows = cur.fetchall()
        if not rows:
            return {
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "base_currency": "USD",
                "output_currency": "INR",
                "market_open": _market_open_now(),
                "metals": {"XAU": {}, "XAG": {}},
                "fx": {"USD_INR": 0.0},
                "fx_source": "db",
            }

        metals = {"XAU": {}, "XAG": {}}
        fx = {"USD_INR": 0.0}
        fx_source = "db"
        captured_at = rows[0][1].isoformat() if rows[0][1] else None

        for row in rows:
            symbol = row[2]
            inr_per_gram = row[3]
            usd_per_oz = row[4]
            provider = row[5] if row[5] else "db"
            updated_at = row[1].isoformat() if row[1] else None

            per_10g = (inr_per_gram * Decimal("10")) if inr_per_gram is not None else None

            entry = {
                "inr_per_gram": float(inr_per_gram) if inr_per_gram is not None else None,
                "inr_per_10g": float(per_10g) if per_10g is not None else None,
                "usd_per_oz": float(usd_per_oz) if usd_per_oz is not None else None,
                "open_per_10g": float(per_10g) if per_10g is not None else None,
                "updated_at": updated_at,
                "source": provider,
                "live": False,
                "estimated": source_family(provider) == "estimate",
                "snapshot_id": None,
            }
            if symbol in metals:
                metals[symbol] = entry

        cur.execute(
            "SELECT rate, provider FROM goldbot.fx_rates "
            "WHERE snapshot_id = %s AND base = 'USD' AND quote = 'INR'",
            (snapshot_id,),
        )
        fx_row = cur.fetchone()
        if fx_row and fx_row[0] is not None:
            fx["USD_INR"] = float(fx_row[0])
            fx_source = fx_row[1] if fx_row[1] else "db"

        return {
            "captured_at": captured_at,
            "base_currency": "USD",
            "output_currency": "INR",
            "market_open": _market_open_now(),
            "metals": metals,
            "fx": fx,
            "fx_source": fx_source,
            "snapshot_id": None,
        }
    finally:
        conn.close()

def get_open_close_delta(metal: str, family: str | None = None) -> dict:
    """Open/close delta for a metal symbol (XAU or XAG).

    Since the schema has no open_per_gram column, the open is taken
    as the oldest reading of the day (or the latest reading as a
    fallback), and the close is the latest reading.
    """
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT m.inr_per_gram "
            "FROM goldbot.metal_prices m "
            "JOIN goldbot.price_snapshots s ON m.snapshot_id = s.id "
            "WHERE m.symbol = %s " + (f"AND {_FAMILY_SQL[family]} " if family else "") +
            "ORDER BY s.captured_at DESC "
            "LIMIT 1",
            (metal,),
        )
        row = cur.fetchone()
        if not row or row[0] is None:
            return {"open": 0, "close": 0, "delta": 0, "delta_pct": 0}

        close = Decimal(str(row[0]))
        cur.execute(
            "SELECT m.inr_per_gram "
            "FROM goldbot.metal_prices m "
            "JOIN goldbot.price_snapshots s ON m.snapshot_id = s.id "
            "WHERE m.symbol = %s "
            "AND DATE(s.captured_at AT TIME ZONE 'Asia/Kolkata') "
            "= (NOW() AT TIME ZONE 'Asia/Kolkata')::date " + (f"AND {_FAMILY_SQL[family]} " if family else "") +
            "ORDER BY s.captured_at ASC "
            "LIMIT 1",
            (metal,),
        )
        row_open = cur.fetchone()
        open_ = Decimal(str(row_open[0])) if row_open and row_open[0] is not None else close
        delta = close - open_
        delta_pct = (delta / open_ * Decimal("100")) if open_ != 0 else Decimal("0")
        return {
            "open": float(open_),
            "close": float(close),
            "delta": float(delta),
            "delta_pct": float(delta_pct),
        }
    finally:
        conn.close()


def _get_daily_open(symbol: str) -> Decimal | None:
    """Get the first price reading from DB for a metal.

    Used as a proxy for the day's open price.
    """
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT inr_per_gram FROM goldbot.metal_prices m "
            "JOIN goldbot.price_snapshots s ON m.snapshot_id = s.id "
            "WHERE m.symbol = %s "
            "ORDER BY s.captured_at ASC LIMIT 1",
            (symbol,),
        )
        row = cur.fetchone()
        if row and row[0]:
            return Decimal(str(row[0])) * Decimal("10")
    finally:
        conn.close()
