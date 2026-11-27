"""COMEX spot + FX provider with no key.

Source: https://xaus.com (free, keyless, unlimited JSON API)

The active spot feed can throttle Render's egress IP on a burst, so the
provider caches a single good reading and serves it until the cache lapses.
``gold.price`` and ``silver.price`` are the raw USD-per-oz spot price and
``fx`` is USD/INR; they are NOT INR MCX prices, so nothing in this provider
claims to emit them.
"""

import logging
import random
import time
from datetime import datetime, timezone
from time import monotonic

import requests

log = logging.getLogger(__name__)

# https://xaus.com
# GET https://xaus.com/api/v1/spot?compact=1  -> live spot price + USD/INR
SPOT_URL = "https://xaus.com/api/v1/spot?compact=1"

# One request per minute is plenty to keep the dashboard live; the free tier
# serves unlimited calls and a short cache keeps a throttled blip from knocking
# the whole feed offline.
CACHE_SECONDS = 60

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}

_cache: dict = {"t": None, "data": None}


def _get_json(url: str, *, retries: int = 2) -> dict:
    """Fetch a JSON endpoint, up to ``retries`` times, then raise."""
    last_error = None
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=HEADERS, timeout=15)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict) and "xau" in payload:
                return payload
            last_error = ValueError(f"unexpected payload: {payload!r}")
        except Exception as exc:
            last_error = exc
            log.warning(
                "Xaus spot request failed (attempt %d/%d): %s: %s",
                attempt + 1,
                retries,
                type(exc).__name__,
                str(exc)[:200],
            )

        # Back off slightly (with a small random jitter) instead of hammering a
        # throttled endpoint.
        time.sleep((1 + random.random() * 0.5) * (2**attempt))

    raise last_error or RuntimeError("unreachable")


def parse_spot(payload: dict) -> dict:
    """Normalise a compact spot payload into the provider quote shape."""

    def _get(path: str, *, default=None):
        cur = payload
        for key in path.split("."):
            if not isinstance(cur, dict):
                return default
            cur = cur.get(key)
        return cur if cur is not None else default

    def _safe_number(value) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    xau_usd = _get("xau.price")
    xag_usd = _get("silver_usd_oz")
    fx = _get("fx_rate")

    if xau_usd is None or xag_usd is None or fx is None:
        raise ValueError(
            f"Xaus returned an unusable spot payload: xau={xau_usd!r}, "
            f"silver={xag_usd!r}, fx={fx!r}"
        )

    if (
        _safe_number(xau_usd) is None
        or _safe_number(xag_usd) is None
        or _safe_number(fx) is None
    ):
        raise ValueError(
            f"Xaus returned non-numeric spot values: xau={xau_usd!r}, "
            f"silver={xag_usd!r}, fx={fx!r}"
        )

    return {
        # The rupee-levels (gold/silver INR) are deliberately omitted: they are
        # provided by the TradingView scanner, not by this spot source.
        "spot": {"XAU": xau_usd, "XAG": xag_usd},
        "fx": fx,
        "gold": {"price": xau_usd},
        "silver": {"price": xag_usd},
    }


def fetch_mcx() -> dict | None:
    """Return one live spot/FX reading, or ``None`` while the endpoint is unusable.

    The caller owns the feed: ``market_data._live_quote`` uses this only as the
    currency reference (USD/INR and COMEX spot), never as the INR MCX price.
    """
    now = monotonic()
    if _cache["t"] is not None and now - _cache["t"] < CACHE_SECONDS:
        # Serve the last good quote while the cache is still valid so the
        # dashboard does not drop to saved prices on a throttling blip.
        return {**_cache["data"], "cached": True}

    try:
        payload = _get_json(SPOT_URL)
        quote = parse_spot(payload)
        quote["fetched_at"] = datetime.now(timezone.utc)
        quote["provider"] = "Xaus"
        quote["cached"] = False
    except Exception as exc:  # network, 429, changed payload
        log.warning(
            "Xaus spot feed failed: %s: %s", type(exc).__name__, str(exc)[:200]
        )
        if _cache["data"] is not None:
            return {**_cache["data"], "cached": True}
        return None

    _cache["data"] = quote
    _cache["t"] = now
    return quote


if __name__ == "__main__":
    quote = fetch_mcx()
    if not quote:
        raise SystemExit("Xaus spot feed unavailable")
    print(f"USD/INR     {quote['fx']:.4f}")
    print(f"COMEX gold  {quote['spot']['XAU']:,.2f} USD/oz")
    print(f"COMEX silver {quote['spot']['XAG']:,.2f} USD/oz")
