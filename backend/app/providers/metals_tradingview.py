"""Live MCX gold / silver, USD/INR and COMEX references in one request.

The live source is TradingView's public scanner. The scanner returns one
report per requested ticker:

    * ``MCX:GOLD1!`` / ``MCX:SILVER1!``  -> the MCX front-month index in
      its native currency: ``gold.price`` is INR per 10 g, ``silver.price``
      is INR per kg.

    * ``FX_IDC:USDINR``                  -> the rupee reference.

    * ``COMEX:GC1!`` / ``COMEX:SI1!``    -> the USD/oz COMEX spot reference,
      quoted in USD per troy ounce.

Every numeric field is kept exactly as the scanner returned it, so a price can
never be re-denominated and displayed in the wrong currency. ``market_data``
then derives per-gram rules from those raw numbers; the two levels never get
mixed.
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
# The front-month contracts carry the MCX price in the metal's own currency
# (INR for gold/silver, USD for COMEX). The price is read from exactly these
# symbols, so a scanner reply that happens to repeat a USD/oz quote under
# another symbol can never leak into the rupee price.
GOLD_MCX = "MCX:GOLD1!"
SILVER_MCX = "MCX:SILVER1!"
USD_INR = "FX_IDC:USDINR"
GOLD_SPOT = "COMEX:GC1!"
SILVER_SPOT = "COMEX:SI1!"
TICKERS = (GOLD_MCX, SILVER_MCX, USD_INR, GOLD_SPOT, SILVER_SPOT)

# One scanner call a minute is plenty for a dashboard and keeps the scanner's
# shared-egress rate limit (HTTP 429) away from the normal request path.
CACHE_SECONDS = 60

# While the scanner is failing, keep serving the last good quote instead of
# dropping the dashboard straight to saved prices: a 429 usually clears in
# seconds. The quote keeps its original fetched_at, and it is dropped at the
# same threshold the feed-health banner is measured against, so a cached
# quote is never presented as newly fetched.
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


def _into_quote(
    gold_price: float,
    silver_price: float,
    fx: float,
    gold_spot: float,
    silver_spot: float,
    fetched_at,
) -> dict:
    """Assemble the quote from the scanner reply, in raw currencies."""
    return {
        "gold": {"price": gold_price, "expiry": None},
        "silver": {"price": silver_price, "expiry": None},
        "fx": fx,
        "spot": {"XAU": gold_spot, "XAG": silver_spot},
        "fetched_at": fetched_at,
        "provider": "TradingView",
        "cached": False,
    }


def parse_scan(payload: dict) -> dict:
    """Normalise a scanner response into the quote shape the app expects.

    The scanner is asked for the front-month MCX contracts plus the FX and
    COMEX references in one call. Only the front-month symbols are trusted
    for the rupee price, and COMEX spot plus USD/INR always come from their
    own symbols, so a quote can never mix currencies.
    """
    rows = {}
    for row in (payload or {}).get("data") or []:
        if isinstance(row, dict) and row.get("d"):
            rows[row["s"]] = row["d"]

    gold = rows.get(GOLD_MCX)
    silver = rows.get(SILVER_MCX)
    if gold is None:
        raise ValueError(f"scanner omitted {GOLD_MCX}")
    if silver is None:
        raise ValueError(f"scanner omitted {SILVER_MCX}")
    if USD_INR not in rows:
        raise ValueError(f"scanner omitted {USD_INR}")

    gold = float(gold[0])
    silver = float(silver[0])

    # The rupee level is the metal's own currency. The COMEX reference and the
    # USD/INR rate are always taken from their own tickers, so a spot quote
    # that the scanner repeats under another symbol can never leak into the
    # rupee price.
    xau_spot = Decimal(str(rows[GOLD_SPOT][0]))
    xag_spot = Decimal(str(rows[SILVER_SPOT][0]))
    fx = Decimal(str(rows[USD_INR][0]))

    return _into_quote(gold, silver, float(fx), float(xau_spot), float(xag_spot), None)


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
