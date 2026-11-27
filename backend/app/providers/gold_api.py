"""Live gold / silver + USD/INR in one request.

Source: https://gold-api.com  (free, no key, unlimited live prices)

gold-api.com serves the spot price of each symbol in the currency asked for,
``/price/{symbol}/{currency}``, and keeps the timestamp of the reading it
held itself (``updatedAt``). The app needs one live reading of gold AND
silver plus the currency reference, so this provider calls the two symbol
endpoints (``XAU`` / ``XAG``) in INR and normalises them into the exact
shape every other provider returns:

    {\"gold\": {\"price\": INR per 10 g}, \"silver\": {\"price\": INR per kg},
     \"fx\": USD/INR, \"spot\": {\"XAU\": USD/oz, \"XAG\": USD/oz},
     \"provider\": \"gold_api\", \"fetched_at\": <UTC now>, \"cached\": bool}

The rupee-level fields are derived from the troy-ounce spot price, so the
displayed gold and silver numbers are spot-INR prices, not MCX futures.

The provider also carries ``fetched_at``, already aware so it can be handed
straight to the dashboard feed-health and the Telegram/update timestamps.

Provider choice: the user asked for a single live feeder and gold-api.com is
the only free, keyless, no-rate-limit endpoint in the project that exposes
BOTH XAU and XAG at once, in INR. The TradingView scanner is therefore no
longer part of the live path.
"""

import logging
import random
from datetime import datetime, timezone
from threading import Lock
from time import monotonic

import requests

from app.config import Config

log = logging.getLogger(__name__)

# One request a minute is plenty for a dashboard and keeps gold-api's
# shared-egress limits away from the normal request path.
CACHE_SECONDS = 60

# Retry quickly at first. A flaky connection should not knock the feed onto
# saved prices: the feed keeps its last good quote and is refreshed within
# the same threshold as the feed banner.
RETRY_BASE_SECONDS = 10
RETRY_MAX_SECONDS = 60
RETRY_JITTER = 0.2

HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}

# troy oz -> grams, from app config (default 31.1035 g)
_ounce = Config.TROY_OUNCE_IN_GRAMS

# perf_counter is monotonic and thread-safe, so two concurrent callers
# cannot read the same stale value; the lock serialises state updates.
_state_lock = Lock()

# Guards "one request in flight" so dashboard requests never queue behind
# another request's HTTP timeout.
_fetch_lock = Lock()

_cache = {"data": None, "data_at": None, "retry_at": None, "failures": 0}


def _into_quote(
    gold_per_10g: float,
    silver_per_kg: float,
    fx: float,
    gold_usd_per_oz: float,
    silver_usd_per_oz: float,
    fetched_at: datetime,
    cached: bool,
) -> dict:
    """Assemble the provider quote into the app's shared shape."""
    return {
        "gold": {"price": gold_per_10g, "expiry": None},
        "silver": {"price": silver_per_kg, "expiry": None},
        "fx": fx,
        "spot": {"XAU": gold_usd_per_oz, "XAG": silver_usd_per_oz},
        "fetched_at": fetched_at,
        "provider": "gold_api",
        "cached": cached,
    }


def _request_quote() -> dict:
    """One pair of gold-api calls. Raises on any failure so the caller owns backoff."""
    gold = _get_price("XAU", "INR")
    silver = _get_price("XAG", "INR")

    # raw prices are per troy ounce
    # gold.price is per troy ounce in INR. Troy ounce = 31.1035 g, so price
    # per 10 g is price x 10 / ounce. (Silver is priced per kg: price x 1000
    # / ounce. The gold conversion here was once written backwards as /
    # ounce / 10, which multiplied the per-gram result by 10 x 10 and pushed
    # the displayed gold 100x too low.)

    # raw prices are per troy ounce
    # gold.price is per troy ounce in INR. Troy ounce = 31.1035 g, so the
    # price per 10 g is price x 10 / ounce. Silver is priced per kg:
    # price x 1000 / ounce. The gold conversion is price x 10 / ounce,
    # NOT price / ounce / 10 (the latter multiplies the per-gram result
    # by 10 x 10 and pushes the displayed gold 100x too low).
    gold_per_10g = gold["price"] * 10 / _ounce
    silver_per_kg = silver["price"] * 1000 / _ounce

    # USD/oz spot (what this app's COMEX reference and the Telegram message
    # display) = INR/oz / USD/INR.
    fx = gold["exchangeRate"]
    gold_usd = gold["price"] / fx
    silver_usd = silver["price"] / fx

    return _into_quote(
        gold_per_10g,
        silver_per_kg,
        fx,
        gold_usd,
        silver_usd,
        datetime.now(timezone.utc),
        cached=False,
    )


def _get_price(symbol: str, currency: str) -> dict:
    url = f"https://api.gold-api.com/price/{symbol}/{currency}"
    response = requests.get(url, headers=HEADERS, timeout=15)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("symbol") != symbol:
        raise ValueError(f"gold-api returned an unusable payload: {payload!r}")
    if not isinstance(payload.get("price"), (int, float)):
        raise ValueError(f"gold-api returned a non-numeric price: {payload!r}")
    return payload


def _cached_quote_locked(now: float) -> dict | None:
    """Last good quote, marked cached, while it is still worth serving.

    Caller must hold ``_state_lock``.
    """
    data = _cache["data"]
    data_at = _cache["data_at"]
    if data is None or data_at is None:
        return None
    if now - data_at > Config.FEED_STALE_SECONDS:
        return None
    return {**data, "cached": True}


def _retry_delay(failures: int) -> float:
    """Exponential backoff with jitter, capped so recovery is never slow."""
    delay = min(RETRY_BASE_SECONDS * 2 ** max(failures - 1, 0), RETRY_MAX_SECONDS)
    return delay * (1 + random.uniform(-RETRY_JITTER, RETRY_JITTER))


def fetch_mcx() -> dict | None:
    """Latest quote, a still-usable cached one, or ``None`` when none is usable.

    A ``cached`` quote keeps its original ``fetched_at`` so callers show the
    real reading time instead of the retry time.
    """
    with _state_lock:
        now = monotonic()
        if (
            _cache["data"] is not None
            and _cache["data_at"] is not None
            and now - _cache["data_at"] < CACHE_SECONDS
        ):
            return _cache["data"]
        if _cache["retry_at"] is not None and now < _cache["retry_at"]:
            return _cached_quote_locked(now)
        if not _fetch_lock.acquire(blocking=False):
            return _cached_quote_locked(now)

    try:
        quote = _request_quote()
    except Exception as exc:  # network, 429, malformed payload
        with _state_lock:
            _cache["failures"] += 1
            delay = _retry_delay(_cache["failures"])
            _cache["retry_at"] = monotonic() + delay
            log.warning(
                "gold-api quote failed (retrying in %.0fs): %s: %s",
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
    print(f"GOLD  {quote['gold']['price']:,.2f} Rs per 10 g")
    print(f"SILVER {quote['silver']['price']:,.2f} Rs per kg")
    print(f"USD/INR {quote['fx']:.4f}")
    print(
        f"COMEX gold {quote['spot']['XAU']:,.2f} USD/oz, "
        f"silver {quote['spot']['XAG']:,.2f} USD/oz"
    )
