import logging
import threading
from datetime import datetime, timezone, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.config import Config
from app.extensions import get_db
from app.messaging.base import Sender
from app.providers import fetch_mcx as fetch_mcx_provider

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
    Socket.IO client. The decimal fields come out of PostgreSQL raw, so each
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


def set_price_event(snapshot: dict | None, fresh: bool = True):
    """Record the newest live market snapshot and notify every Socket.IO client.

    ``fresh`` is False when the snapshot replays a provider's cached quote. It
    is broadcast either way, but only a real provider fetch moves feed health.

    The snapshot is serialised to JSON first so Decimal values (which come
    straight out of PostgreSQL) are converted to float and can be sent over
    the Socket.IO payload.
    """
    with _broadcast_lock:
        _price_event["last"] = snapshot
        _price_event["last_at"] = datetime.now(timezone.utc)
        global _last_live_at
        # A provider replaying its last good quote must not make the feed look
        # healthier than it is: feed health is measured from real fetches.
        if fresh:
            _last_live_at = _price_event["last_at"]

    try:
        from app import socketio as _socketio

        _sio = _socketio
        _sio.emit(
            "price_update",
            _json_safe(snapshot) if snapshot is not None else None,
            namespace="/",
        )
    except Exception:
        log.exception("price event broadcast failed")


def source_family(source) -> str:
    """Classify a price source into *mcx*, *estimate* or *spot* for chart filtering.

    ``source`` is the ``source`` field stamped onto a metal entry. Live quotes
    from the TradingView scanner carry a friendly name such as
    ``"TradingView - MCX GOLD front-month futures"`` and must sort into *mcx*;
    rows stored by the database carry ``"db"`` (the DB fallback) and are also
    *mcx* so the chart is not filtered to an empty set. Anything carrying an
    ``(estimate)`` tag stays *estimate*; everything else is *spot*.
    """
    s = (source or "").lower()
    if "mcx" in s or s in {"db", "database"}:
        return "mcx"
    if "estimate" in s:
        return "estimate"
    return "spot"


_FAMILY_SQL = {
    # The provider field is free text: the live TradingView row is stamped with
    # a friendly name such as "TradingView - MCX GOLD front-month futures", and
    # the DB fallback is stamped "db". Match both, plus the legacy "MCX..."
    # prefix, and keep estimate rows separate so a spot-history never leaks
    # into an MCX trace.
    #
    # Every clause is parenthesised because callers append it after an AND.
    # Without the parentheses SQL binds the AND to the first OR term only, so
    # the live '%MCX GOLD%' rows bypassed the caller's time window and 1D, 7D
    # and 30D all returned the entire history.
    "mcx": "(m.provider ILIKE 'MCX%%' OR m.provider ILIKE '%%MCX GOLD%%' OR m.provider ILIKE '%%MCX SILVER%%' OR m.provider = 'db')",
    "estimate": "(m.provider LIKE '%%(estimate)')",
    "spot": "(m.provider NOT ILIKE 'MCX%%' AND m.provider NOT ILIKE '%%MCX GOLD%%' AND m.provider NOT ILIKE '%%MCX SILVER%%' AND m.provider <> 'db' AND m.provider NOT LIKE '%%(estimate)')",
}


def _live_quote() -> dict | None:
    # TradingView is the only live MCX source: it returns the rupee prices and
    # the currency/DEX references in one call. Nothing else on this list emits
    # a INR MCX quote, so when the scanner eventually returns we have the full
    # feed and no further enrichment is required.
    quote = fetch_mcx_provider()
    if not quote:
        return None

    fx = Decimal(str(quote["fx"]))
    ounce = Decimal(str(Config.TROY_OUNCE_IN_GRAMS))
    metals = {}
    for symbol, key, per_gram_divisor, spot_key in (
        ("XAU", "gold", 10, "XAU"),
        ("XAG", "silver", 1000, "XAG"),
    ):
        gram = (
            Decimal(str(quote[key]["price"])) / per_gram_divisor
        )  # gold per 10 g, silver per kg
        spot_price = (quote.get("spot") or {}).get(spot_key)
        if not spot_price or spot_price <= 0:
            log.warning(
                "MCX %s quote rejected: the quote carries no COMEX %s reference",
                key,
                spot_key,
            )
            return None
        spot_gram = Decimal(str(spot_price)) * fx / ounce
        ratio = gram / spot_gram
        # Keep the comparison as a diagnostic only. If the live scanner ever
        # begins to report a misaligned quote, the ratio moves and the log
        # surfaces it so the mismatch can be triaged. The dashboard stays up
        # either way.
        if not (Decimal("0.6") <= ratio <= Decimal("2.5")):
            log.warning(
                "MCX %s price diverges %.2fx from the converted spot price (flagging, not rejecting)",
                key, ratio,
            )
        metals[symbol] = {
            # The live feed is global spot converted to INR (gold-api.com
            # returns the spot price; the old TradingView path reported the
            # MCX front-month contract). Keep the label honest so the chart
            # family and any downstream message carry the right source.
            "inr_per_gram": gram,
            "source": f"{quote['provider']} - spot",
            "updated_at": quote["fetched_at"],
            "spot_inr_per_10g": spot_gram * Decimal("10"),
            "usd_per_oz": Decimal(str(quote["spot"][spot_key])),
        }
    return {
        "metals": metals,
        "fx": Decimal(str(quote["fx"])),
        "provider": quote["provider"],
        # The reading time of the quote itself: a cached quote keeps the time it
        # was actually fetched, so the dashboard never claims a stale price is new.
        "fetched_at": quote["fetched_at"],
        "fresh": not quote.get("cached", False),
    }


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


def _today_open_per_10g() -> dict[str, Decimal]:
    """First saved reading of the current IST day, per 10 g.

    The dashboard compares the live close with this value to show the day's
    move. A failure here must never take the live quote down, so it is
    best-effort and returns an empty mapping when the DB is unavailable.
    """
    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT DISTINCT ON (m.symbol) m.symbol, m.inr_per_gram "
                "FROM goldbot.metal_prices m "
                "JOIN goldbot.price_snapshots s ON s.id = m.snapshot_id "
                "WHERE DATE(s.captured_at AT TIME ZONE 'Asia/Kolkata') "
                "= (NOW() AT TIME ZONE 'Asia/Kolkata')::date "
                "ORDER BY m.symbol, s.captured_at ASC"
            )
            return {
                symbol: Decimal(str(rate)) * 10
                for symbol, rate in cur.fetchall()
                if rate is not None
            }
        finally:
            conn.close()
    except Exception:
        log.exception("Could not load today's opening readings")
        return {}


def get_latest_snapshot() -> dict:
    global _last_live_at
    live = _live_quote()
    if live:
        opens = _today_open_per_10g()
        snapshot = {
            "captured_at": live["fetched_at"].isoformat(),
            "base_currency": "USD",
            "output_currency": "INR",
            "market_open": _market_open_now(),
            "metals": {
                "XAU": {
                    **live["metals"]["XAU"],
                    "live": True,
                    "open_per_10g": (
                        Decimal(str(opens.get("XAU")))
                        if opens.get("XAU") is not None
                        else None
                    ),
                },
                "XAG": {
                    **live["metals"]["XAG"],
                    "live": True,
                    "open_per_10g": (
                        Decimal(str(opens.get("XAG")))
                        if opens.get("XAG") is not None
                        else None
                    ),
                },
            },
            "fx": {
                "USD_INR": live["fx"],
                "FX_SOURCE": live["provider"],
            },
        }
        set_price_event(snapshot, fresh=live["fresh"])
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
                "fx": {"USD_INR": Decimal("0")},
                "fx_source": "db",
            }

        metals = {"XAU": {}, "XAG": {}}
        fx = {"USD_INR": Decimal("0")}
        fx_source = "db"
        snapshot_id = rows[0][0]
        opens = _today_open_per_10g()
        captured_at = rows[0][1].isoformat() if rows[0][1] else None

        for row in rows:
            symbol = row[2]
            inr_per_gram = row[3]
            usd_per_oz = row[4]
            provider = row[5] if row[5] else "db"
            updated_at = row[1].isoformat() if row[1] else None

            per_10g = (
                (Decimal(str(inr_per_gram)) * Decimal("10"))
                if inr_per_gram is not None
                else None
            )

            entry = {
                "inr_per_gram": (
                    Decimal(str(inr_per_gram)) if inr_per_gram is not None else None
                ),
                "inr_per_10g": per_10g,
                "usd_per_oz": (
                    Decimal(str(usd_per_oz)) if usd_per_oz is not None else None
                ),
                "open_per_10g": (
                    Decimal(str(opens.get(symbol)))
                    if opens.get(symbol) is not None
                    else per_10g
                ),
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
            fx["USD_INR"] = Decimal(str(fx_row[0]))
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
            "WHERE m.symbol = %s "
            + (f"AND {_FAMILY_SQL[family]} " if family else "")
            + "ORDER BY s.captured_at DESC "
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
            "= (NOW() AT TIME ZONE 'Asia/Kolkata')::date "
            + (f"AND {_FAMILY_SQL[family]} " if family else "")
            + "ORDER BY s.captured_at ASC "
            "LIMIT 1",
            (metal,),
        )
        row_open = cur.fetchone()
        open_ = (
            Decimal(str(row_open[0])) if row_open and row_open[0] is not None else close
        )
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
