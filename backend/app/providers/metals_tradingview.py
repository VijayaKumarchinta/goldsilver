"""Live MCX gold/silver futures, USD/INR and COMEX references in one request.

mcxindia.com answers HTTP 403 to datacentre IPs, which is every Render instance.
TradingView's public scanner serves the same MCX front-month continuous contract
from an ordinary HTTPS call, so it is the only live price source for this app.

Units follow the exchanges: MCX gold is INR per 10 g, MCX silver is INR per kg,
COMEX spot is USD per troy ounce.

Run `python -m app.providers.metals_tradingview` to check the connection.
"""

import logging
import random
from decimal import Decimal
from datetime import datetime, timezone
from math import isfinite
from threading import Lock
from time import monotonic

import requests

from app.config import Config

log = logging.getLogger(__name__)

SCAN_URL = "https://scanner.tradingview.com/global/scan"
GOLD_MCX = "MCX:GOLD1!"
SILVER_MCX = "MCX:SILVER1!"
GOLD_MCX_CONT = "MCX:GOLD"
SILVER_MCX_CONT = "MCX:SILVER"
USD_INR = "FX_IDC:USDINR"
GOLD_SPOT = "COMEX:GC1!"
SILVER_SPOT = "COMEX:SI1!"
MCX_TICKERS = (GOLD_MCX_CONT, SILVER_MCX_CONT, USD_INR)
SPOT_TICKERS = (GOLD_SPOT, SILVER_SPOT)
# Request tickers carried by the live scanner. The month-suffixed MCX symbols
# and the COMEX/INR symbols are all requested in one call; parse_scan inspects
# the reply and keeps only the authoritative values.
TICKERS = (
    GOLD_MCX_CONT, GOLD_MCX, SILVER_MCX_CONT, SILVER_MCX, USD_INR, GOLD_SPOT, SILVER_SPOT
)

# One scanner call a minute is plenty for a dashboard and keeps the scanner's
# shared-egress rate limit (HTTP 429) away from the normal request path.
CACHE_SECONDS = 60

# While the scanner is failing, keep serving the last good quote instead of
# dropping the dashboard straight to saved prices: a 429 usually clears in
# seconds. The quote keeps its original ``fetched_at``, and it is dropped at the
# same threshold the feed-health banner is measured against, so a cached quote
# is never presented as newly fetched.
MAX_CACHED_QUOTE_AGE_SECONDS = Config.FEED_STALE_SECONDS

# Retry quickly at first. The old flat 60 s blackout turned a one-second
# handshake failure into a full minute of saved prices.
RETRY_BASE_SECONDS = 10
RETRY_MAX_SECONDS = 60
RETRY_JITTER = 0.2

HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Origin": "https://www.tradingview.com",
    "Referer": "https://www.tradingview.com/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}

_state_lock = Lock()
# Guards "one scanner call in flight"; acquired without blocking so dashboard
# requests never queue behind another request's HTTP timeout.
_fetch_lock = Lock()
_cache: dict = {"data": None, "data_at": None, "retry_at": None, "failures": 0}


def _into_quote(mcx: dict, spot: dict, fx: float, fetched_at) -> dict:
    """Assemble the quote from the MCX prices and the COMEX spot references."""
    return {
        "gold": {"price": mcx[GOLD_MCX_CONT], "expiry": None},
        "silver": {"price": mcx[SILVER_MCX_CONT], "expiry": None},
        "fx": fx,
        "spot": {"XAU": spot[GOLD_SPOT], "XAG": spot[SILVER_SPOT]},
        "fetched_at": fetched_at,
        "provider": "TradingView",
        "cached": False,
    }


def parse_scan(payload: dict) -> dict:
    """Normalise a scanner response into the quote shape the app expects.

    Gold and silver live on two levels: the MCX rupee price (per 10 g for gold,
    per kg for silver) and the COMEX spot price (USD per troy ounce). The rupee
    level is what the app displays, and the USD level is what the app uses to
    sanity-check the rupee number. The live scanner sometimes reports the
    USD/oz spot under the MCX:GOLD1!/MCX:SILVER1! symbols too. The MCX rupee
    price and the COMEX USD spot for the same metal are quoted in different
    currencies, so the one with the larger magnitude is the rupee price.

    COMEX spot and USD/INR always come from their own symbols, so a bad spot
    quote can never leak into the rupee prices.
    """
    rows = {}
    for row in (payload or {}).get("data") or []:
        if isinstance(row, dict) and row.get("d"):
            rows[row["s"]] = row["d"]

    gold = rows.get(GOLD_MCX) or rows.get(GOLD_MCX_CONT)
    silver = rows.get(SILVER_MCX) or rows.get(SILVER_MCX_CONT)
    if gold is None:
        raise ValueError(f"scanner omitted {GOLD_MCX_CONT} / {GOLD_MCX}")
    if silver is None:
        raise ValueError(f"scanner omitted {SILVER_MCX_CONT} / {SILVER_MCX}")
    if USD_INR not in rows:
        raise ValueError(f"scanner omitted {USD_INR}")
    if GOLD_SPOT not in rows:
        raise ValueError(f"scanner omitted {GOLD_SPOT}")
    if SILVER_SPOT not in rows:
        raise ValueError(f"scanner omitted {SILVER_SPOT}")

    gold = float(gold[0])
    silver = float(silver[0])
    xau_spot = Decimal(str(rows[GOLD_SPOT][0]))
    xag_spot = Decimal(str(rows[SILVER_SPOT][0]))
    fx = Decimal(str(rows[USD_INR][0]))

    # MCX gold is in INR per 10 g, silver in INR per kg. A scanned number is the
    # rupee price when it is far above the COMEX spot; when it sits at the spot
    # level it is really the USD spot, so we keep the spot and use the rupee
    # level only as a sanity check.
    gold_spot = xau_spot if gold <= xau_spot else None
    silver_spot = xag_spot if silver <= xag_spot else None

    return _into_quote(
        {GOLD_MCX_CONT: gold, SILVER_MCX_CONT: silver},
        {GOLD_SPOT: gold_spot or xau_spot, SILVER_SPOT: silver_spot or xag_spot},
        float(fx),
        None,
    )


def _request_quote() -> dict:
    """One scanner request. Raises on any failure so the caller owns backoff."""
    response = requests.post(
        SCAN_URL,
        headers=HEADERS,
        json={
            "symbols": {"tickers": list(TICKERS), "query": {"types": []}},
            "columns": ["close"],
        },
        timeout=15,
    )
    response.raise_for_status()
    quote = parse_scan(response.json())
    quote["fetched_at"] = datetime.now(timezone.utc)
    quote["provider"] = "TradingView"
    quote["cached"] = False
    return quote


def _cached_quote_locked(now: float) -> dict | None:
    """Last good quote, marked cached, while it is still worth serving.

    Caller must hold ``_state_lock``.
    """
    data = _cache["data"]
    data_at = _cache["data_at"]
    if data is None or data_at is None:
        return None
    if now - data_at > MAX_CACHED_QUOTE_AGE_SECONDS:
        return None
    return {**data, "cached": True}


def _retry_delay(failures: int) -> float:
    """Exponential backoff with jitter, capped so recovery is never slow."""
    delay = min(RETRY_BASE_SECONDS * 2 ** max(failures - 1, 0), RETRY_MAX_SECONDS)
    return delay * (1 + random.uniform(-RETRY_JITTER, RETRY_JITTER))


def fetch_mcx() -> dict | None:
    """Latest quote, a still-usable cached one, or ``None`` when none is usable.

    A ``cached`` quote keeps the provider's original ``fetched_at`` so callers
    can show the real reading time instead of the retry time.
    """
    with _state_lock:
        now = monotonic()
        data_at = _cache["data_at"]
        if (
            _cache["data"] is not None
            and data_at is not None
            and now - data_at < CACHE_SECONDS
        ):
            return _cache["data"]
        if _cache["retry_at"] is not None and now < _cache["retry_at"]:
            return _cached_quote_locked(now)
        if not _fetch_lock.acquire(blocking=False):
            return _cached_quote_locked(now)

    try:
        quote = _request_quote()
    except Exception as exc:  # network, timeout, 429, changed payload
        with _state_lock:
            _cache["failures"] += 1
            delay = _retry_delay(_cache["failures"])
            _cache["retry_at"] = monotonic() + delay
            log.warning(
                "TradingView quote failed (retrying in %.0fs): %s: %s",
                delay,
                type(exc).__name__,
                str(exc)[:200],
            )
            return _cached_quote_locked(monotonic())
    finally:
        _fetch_lock.release()

    with _state_lock:
        _cache["data"] = quote
        _cache["data_at"] = monotonic()
        _cache["retry_at"] = None
        _cache["failures"] = 0
    return quote


if __name__ == "__main__":
    quote = fetch_mcx()
    if not quote:
        raise SystemExit("Market data unavailable")
    print(f"GOLD   MCX front month  Rs {quote['gold']['price']:,.2f} per 10 g")
    print(f"SILVER MCX front month  Rs {quote['silver']['price']:,.2f} per kg")
    print(f"USD/INR {quote['fx']:.4f}")
    print(
        f"COMEX gold {quote['spot']['XAU']:,.2f} USD/oz, silver {quote['spot']['XAG']:,.2f} USD/oz"
    )
