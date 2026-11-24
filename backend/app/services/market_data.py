from datetime import datetime, timezone, time
from decimal import Decimal

from app.extensions import get_db
import logging

from app.config import Config
from app.providers import metals_mcx, metals_xaus

log = logging.getLogger(__name__)


def source_family(source) -> str:
    """Prices from different sources must never be mixed in history or open/close."""
    s = (source or "").lower()
    if s.startswith("mcx"):
        return "mcx"
    return "estimate" if "estimate" in s else "spot"


_FAMILY_SQL = {
    "mcx": "m.provider LIKE 'MCX%%'",
    "estimate": "m.provider LIKE '%%(estimate)'",
    "spot": "m.provider NOT LIKE 'MCX%%' AND m.provider NOT LIKE '%%(estimate)'",
}


def _usable_mcx(spot: dict) -> dict | None:
    """MCX prices as {symbol: (inr_per_gram, source, fetched_at, live)}, or None if missing or implausible."""
    quote = metals_mcx.fetch_mcx()
    if not quote:
        return None
    out = {}
    for symbol, key, per_gram_divisor in (("XAU", "gold", 10), ("XAG", "silver", 1000)):
        gram = Decimal(str(quote[key]["price"])) / per_gram_divisor  # gold: per 10 g, silver: per kg
        spot_gram = Decimal(str(spot["metals"][symbol]["inr_per_gram"]))
        ratio = gram / spot_gram
        if not (Decimal("0.95") <= ratio <= Decimal("1.6")):
            log.warning("MCX %s price rejected: %.2fx the converted spot price", key, ratio)
            return None
        expiry = quote[key]["expiry"].strftime("%d%b%Y").upper()
        out[symbol] = (gram, f"MCX {key.upper()} {expiry} futures", quote["fetched_at"], True)
    return out


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


def get_latest_snapshot() -> dict:
    """Return a single-provider snapshot or the latest saved snapshot."""
    provider_snapshot = metals_xaus.fetch_market_data()
    if provider_snapshot:
        usd_inr = provider_snapshot["fx_rate"]
        mcx = _usable_mcx(provider_snapshot)
        metals_live = {}
        for symbol, provider in provider_snapshot["metals"].items():
            spot_gram = Decimal(str(provider["inr_per_gram"]))
            if mcx:
                inr_per_gram, source, updated_at, live = mcx[symbol]
            else:  # MCX unreachable: show an honest estimate, flagged and never posted to Telegram
                premium = Config.ESTIMATE_PREMIUM_GOLD if symbol == "XAU" else Config.ESTIMATE_PREMIUM_SILVER
                inr_per_gram = spot_gram * (Decimal("1") + Decimal(str(premium)))
                source, updated_at, live = "xaus.com spot + duty (estimate)", provider["updated_at"], False
            delta = get_open_close_delta(symbol, family=source_family(source))
            open_gram = Decimal(str(delta["open"])) or inr_per_gram
            metals_live[symbol] = {
                "inr_per_gram": float(inr_per_gram),
                "inr_per_10g": float(inr_per_gram * Decimal("10")),
                "usd_per_oz": provider["usd_per_oz"],
                "spot_inr_per_10g": float(spot_gram * Decimal("10")),
                "open_per_10g": float(open_gram * Decimal("10")),
                "updated_at": updated_at.isoformat(),
                "source": source,
                "live": live,
                "estimated": not mcx,
            }
        return {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "base_currency": "USD",
            "output_currency": "INR",
            "market_open": _market_open_now(),
            "metals": metals_live,
            "fx": {
                "USD_INR": float(usd_inr),
                "FX_SOURCE": provider_snapshot["fx_source"],
            },
        }

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
        snapshot_id = rows[0][0]

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
    return None
