"""COMEX spot FX + gold/silver provider with no key.

Source: https://xaus.com (free, keyless, unlimited JSON API)

The active Marketplace spot feed throttles Render's egress IP (HTTP 429 on
GET /spot), while the raw spot endpoint stays reachable. Cached responses are
served for CACHE_SECONDS and only refreshed after that, which keeps the
incident window to a single request and drops back to the last good quote
afterward so the dashboard never goes to saved prices on a one-off throttling
blip.

Returned quote shape (same envelope as metals_tradingview.py, but not the same
price contract):

    {
        "gold":   {"price": <COMEX gold, USD per oz>},
        "silver": {"price": <COMEX silver, USD per oz>},
        "fx":     <USD/INR>,
        "spot":   {"XAU": <gold USD/oz>, "XAG": <silver USD/oz>},
        "provider": "Xaus",
        "fetched_at": <aware datetime>,
        "cached":   <bool>,
    }

Note this is a spot/FX source, not an MCX futures source. ``gold.price`` and
``silver.price`` are USD per troy ounce, not INR per 10 g / INR per kg. That
means ``app.providers`` can list this module in PROVIDERS and
``market_data._live_quote`` can try it, but the existing INR/spot ratio gate
will reject its payload until a spot-aware enrichment path is wired on top of
it.
"""

import logging
from datetime import datetime, timezone
from time import monotonic

import requests

log = logging.getLogger(__name__)

# https://xaus.com
# Free, keyless, unlimited JSON API:
#   GET https://xaus.com/api/v1/spot?compact=1   -> live spot price + USD/INR
#   GET https://xaus.com/api/v1/history?days=N   -> daily OHLC history
#   GET https://xaus.com/api/v1/intraday?symbol=xau&hours=N -> 1-min intraday
SPOT_URL = "https://xaus.com/api/v1/spot?compact=1"
HISTORY_URL = "https://xaus.com/api/v1/history?days=7"
INTRADAY_URL = "https://xaus.com/api/v1/intraday?symbol=xau&hours=24"

# One request per minute is plenty to keep the dashboard live; the free tier
# serves unlimited calls and a short cache keeps a throttled blip from
# knocking the whole feed offline.
CACHE_SECONDS = 60

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}


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
                "Xaus %s request failed (attempt %d/%d): %s",
                url,
                attempt + 1,
                retries,
                type(exc).__name__,
                exc,
            )
        # Back off slightly (with a small random jitter) instead of hammering a
        # throttled endpoint.
        import random
        import time

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

    # Return COMEX spot in USD/oz and the FX reference. The INR MCX prices are
    # not provided by this source and are not derived here.
    return {
        "gold": {"price": xau_usd},
        "silver": {"price": xag_usd},
        "fx": fx,
        "spot": {"XAU": xau_usd, "XAG": xag_usd},
    }


def fetch_mcx() -> dict | None:
    """Return one live spot/FX reading, or ``None`` while the endpoint is unusable.

    ``market_data._live_quote`` will try this provider if it is listed in
    PROVIDERS, but it will reject the returned quote through the INR/spot ratio
    gate because this source does not return INR MCX prices.
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
        log.warning("Xaus spot feed failed: %s: %s", type(exc).__name__, str(exc)[:200])
        if _cache["data"] is not None:
            return {**_cache["data"], "cached": True}
        return None

    _cache["data"] = quote
    _cache["t"] = now
    return quote


_cache: dict = {"t": None, "data": None}


if __name__ == "__main__":
    quote = fetch_mcx()
    if not quote:
        raise SystemExit("Xaus spot feed unavailable")
    print(f"FX/INR      {quote['fx']:.4f}")
    print(f"COMEX gold  {quote['spot']['XAU']:,.2f} USD/oz")
    print(f"COMEX silver {quote['spot']['XAG']:,.2f} USD/oz")
