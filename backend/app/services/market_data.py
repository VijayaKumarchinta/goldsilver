import logging
from datetime import datetime, timezone, time
from decimal import Decimal

from app.config import Config
from app.extensions import get_db
from app.repositories.prices import get_latest
from app.providers import metals_xaus
from app.services.conversion import to_10g
from app.services.validation import validate_price_jump

log = logging.getLogger(__name__)


def _market_open_now() -> bool:
    """True during IST market hours (09:00-23:55 Mon-Fri)."""
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    t = time(9, 0)
    t_close = time(23, 55)
    wd = now.isoweekday()
    if wd > 5:
        return False
    now_time = now.time().replace(tzinfo=None)
    return t <= now_time <= t_close


def _empty_snapshot() -> dict:
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "base_currency": "USD",
        "output_currency": "INR",
        "market_open": _market_open_now(),
        "metals": {"XAU": {}, "XAG": {}},
        "fx": {"USD_INR": None, "FX_SOURCE": "xaus.com"},
        "quote_type": "global_spot",
    }


def _saved_snapshot() -> dict:
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT s.id, s.captured_at, m.symbol, m.inr_per_gram, m.usd_per_oz, m.provider, m.provider_updated_at "
            "FROM goldbot.price_snapshots s "
            "JOIN goldbot.metal_prices m ON s.id = m.snapshot_id "
            "WHERE s.id = (SELECT id FROM goldbot.price_snapshots ORDER BY captured_at DESC LIMIT 1)"
        )
        rows = cur.fetchall()
        if not rows:
            return _empty_snapshot()

        metals = {"XAU": {}, "XAG": {}}
        fx = {"USD_INR": 0.0}
        fx_source = "db"
        captured_at = rows[0][1].isoformat() if rows[0][1] else None
        snapshot_id = rows[0][0]

        for row in rows:
            symbol = row[2]
            inr_per_gram = row[3]
            usd_per_oz = row[4]
            provider = row[5] if row[5] else "db"
            updated_at = row[6].isoformat() if row[6] else None

            per_10g = to_10g(Decimal(str(inr_per_gram))) if inr_per_gram is not None else None

            entry = {
                "inr_per_gram": float(inr_per_gram) if inr_per_gram is not None else None,
                "inr_per_10g": float(per_10g) if per_10g is not None else None,
                "usd_per_oz": float(usd_per_oz) if usd_per_oz is not None else None,
                "open_per_10g": float(per_10g) if per_10g is not None else None,
                "updated_at": updated_at,
                "source": provider,
                "live": False,
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
            "quote_type": "global_spot",
        }
    finally:
        conn.close()


def _provider_snapshot(provider_snapshot: dict, live: bool) -> dict:
    metals = {}
    for symbol, quote in provider_snapshot["metals"].items():
        delta = get_open_close_delta(
            symbol,
            current_close=quote["inr_per_gram"],
        )
        inr_per_gram = Decimal(str(quote["inr_per_gram"]))
        metals[symbol] = {
            "inr_per_gram": float(inr_per_gram),
            "inr_per_10g": float(to_10g(inr_per_gram)),
            "usd_per_oz": float(quote["usd_per_oz"]),
            "open_per_10g": float(to_10g(Decimal(str(delta["open"])))),
            "updated_at": quote["updated_at"].isoformat(),
            "source": quote["provider"],
            "live": live,
        }
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "base_currency": "USD",
        "output_currency": "INR",
        "market_open": _market_open_now(),
        "metals": metals,
        "fx": {
            "USD_INR": float(provider_snapshot["fx_rate"]),
            "FX_SOURCE": provider_snapshot["fx_source"],
        },
        "quote_type": "global_spot",
    }


def _validate_price_changes(provider_snapshot: dict) -> None:
    previous = get_latest()
    if not previous:
        return
    captured_at = previous.get("captured_at")
    if isinstance(captured_at, str):
        try:
            captured_at = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
        except ValueError:
            log.warning("Skipping price-jump checks because saved timestamp is invalid")
            return
    if not isinstance(captured_at, datetime):
        log.warning("Skipping price-jump checks because saved timestamp is missing")
        return
    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=timezone.utc)
    reference_age = (datetime.now(timezone.utc) - captured_at.astimezone(timezone.utc)).total_seconds()
    if reference_age < 0 or reference_age > Config.MAX_JUMP_REFERENCE_AGE_SECONDS:
        log.info("Skipping price-jump checks because the saved reference is too old")
        return
    for symbol, quote in provider_snapshot["metals"].items():
        previous_quote = previous.get("metals", {}).get(symbol, {})
        previous_value = previous_quote.get("inr_per_gram")
        if previous_value is None:
            continue
        previous_value = Decimal(str(previous_value))
        if not previous_value.is_finite() or previous_value <= 0:
            log.warning("Skipping jump comparison for invalid saved %s quote", symbol)
            continue
        validate_price_jump(
            Decimal(str(quote["inr_per_gram"])),
            previous_value,
        )


def get_latest_snapshot() -> dict:
    """Return a validated Xaus snapshot or the latest saved quote."""
    provider_snapshot = metals_xaus.fetch_market_data()
    if provider_snapshot and not provider_snapshot["stale"]:
        try:
            _validate_price_changes(provider_snapshot)
        except ValueError as exc:
            log.error("Rejected Xaus snapshot: %s", exc)
            return _saved_snapshot()
        return _provider_snapshot(provider_snapshot, live=True)
    if provider_snapshot:
        saved = _saved_snapshot()
        if any(saved["metals"].get(symbol) for symbol in ("XAU", "XAG")):
            return saved
        return _provider_snapshot(provider_snapshot, live=False)
    return _saved_snapshot()


def get_open_close_delta(
    metal: str,
    current_close: Decimal | float | None = None,
) -> dict:
    """Compare the first IST-day reading with a live or latest saved quote."""
    conn = get_db()
    try:
        cur = conn.cursor()
        if current_close is None:
            cur.execute(
                "SELECT m.inr_per_gram "
                "FROM goldbot.metal_prices m "
                "JOIN goldbot.price_snapshots s ON m.snapshot_id = s.id "
                "WHERE m.symbol = %s "
                "ORDER BY s.captured_at DESC "
                "LIMIT 1",
                (metal,),
            )
            row = cur.fetchone()
            if not row or row[0] is None:
                return {"open": 0, "close": 0, "delta": 0, "delta_pct": 0}
            close = Decimal(str(row[0]))
        else:
            close = Decimal(str(current_close))
            if not close.is_finite() or close <= 0:
                return {"open": 0, "close": 0, "delta": 0, "delta_pct": 0}

        cur.execute(
            "SELECT m.inr_per_gram "
            "FROM goldbot.metal_prices m "
            "JOIN goldbot.price_snapshots s ON m.snapshot_id = s.id "
            "WHERE m.symbol = %s "
            "AND DATE(s.captured_at AT TIME ZONE 'Asia/Kolkata') "
            "= (NOW() AT TIME ZONE 'Asia/Kolkata')::date "
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
    return None
