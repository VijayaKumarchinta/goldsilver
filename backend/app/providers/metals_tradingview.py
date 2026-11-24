"""Live MCX gold/silver futures, USD/INR and COMEX references in one request.

mcxindia.com answers HTTP 403 to datacentre IPs, which is every Render instance.
TradingView's public scanner serves the same MCX front-month continuous contract
from an ordinary HTTPS call, so it is the single price source for this app.

Units follow the exchanges: MCX gold is INR per 10 g, MCX silver is INR per kg,
COMEX spot is USD per troy ounce.

Run `python -m app.providers.metals_tradingview` to check the connection.
"""

import logging
from datetime import datetime, timezone
from math import isfinite
from threading import Lock
from time import monotonic

import requests

log = logging.getLogger(__name__)

SCAN_URL = "https://scanner.tradingview.com/global/scan"
GOLD_MCX = "MCX:GOLD1!"
SILVER_MCX = "MCX:SILVER1!"
USD_INR = "FX_IDC:USDINR"
GOLD_SPOT = "COMEX:GC1!"
SILVER_SPOT = "COMEX:SI1!"
TICKERS = (GOLD_MCX, SILVER_MCX, USD_INR, GOLD_SPOT, SILVER_SPOT)

CACHE_SECONDS = 15
# Short enough that Telegram updates recover quickly, long enough to stop a
# failing endpoint from being hit on every dashboard poll.
FAILURE_BACKOFF_SECONDS = 60

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

_lock = Lock()
_cache: dict = {"t": None, "data": None, "retry_at": None}


def parse_scan(payload: dict) -> dict:
    """Normalise a scanner response into the quote shape the app expects."""
    rows = {}
    for row in (payload or {}).get("data") or []:
        if isinstance(row, dict) and row.get("s") in TICKERS and row.get("d"):
            rows[row["s"]] = row["d"]

    missing = [ticker for ticker in TICKERS if ticker not in rows]
    if missing:
        raise ValueError(f"scanner omitted {', '.join(missing)}")

    values = {}
    for ticker in TICKERS:
        value = rows[ticker][0]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"scanner returned a non-numeric price for {ticker}: {value!r}")
        if not isfinite(value) or value <= 0:
            raise ValueError(f"scanner returned an unusable price for {ticker}: {value!r}")
        values[ticker] = float(value)

    return {
        "gold": {"price": values[GOLD_MCX], "expiry": None},
        "silver": {"price": values[SILVER_MCX], "expiry": None},
        "fx": values[USD_INR],
        "spot": {"XAU": values[GOLD_SPOT], "XAG": values[SILVER_SPOT]},
    }


def fetch_mcx() -> dict | None:
    """Latest quote, or None while the endpoint is unavailable."""
    with _lock:
        now = monotonic()
        if _cache["t"] is not None and now - _cache["t"] < CACHE_SECONDS:
            return _cache["data"]
        if _cache["retry_at"] is not None and now < _cache["retry_at"]:
            return None
        _cache["t"] = now

        try:
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
            _cache["data"] = quote
            _cache["retry_at"] = None
            return quote
        except Exception as exc:  # network, timeout, changed payload
            log.warning(
                "Market data fetch failed (retrying in %ss): %s: %s",
                FAILURE_BACKOFF_SECONDS,
                type(exc).__name__,
                str(exc)[:200],
            )
            _cache["data"] = None
            _cache["retry_at"] = now + FAILURE_BACKOFF_SECONDS
            return None


if __name__ == "__main__":
    quote = fetch_mcx()
    if not quote:
        raise SystemExit("Market data unavailable")
    print(f"GOLD   MCX front month  Rs {quote['gold']['price']:,.2f} per 10 g")
    print(f"SILVER MCX front month  Rs {quote['silver']['price']:,.2f} per kg")
    print(f"USD/INR {quote['fx']:.4f}")
    print(f"COMEX gold {quote['spot']['XAU']:,.2f} USD/oz, silver {quote['spot']['XAG']:,.2f} USD/oz")
