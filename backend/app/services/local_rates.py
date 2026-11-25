import time
import requests
from app.config import Config


_cache = {}
_cache_lock: object | None = None  # set lazily


def _cache_lock_for() -> object:
    global _cache_lock
    if _cache_lock is None:
        import threading
        _cache_lock = threading.Lock()
    return _cache_lock


def _now_epoch() -> float:
    return time.time()


def is_configured() -> bool:
    """FreeAPI base URL is configured and non-empty."""
    return bool(Config.FREEAPI_BASE)


def get_local_market_reference(city: str | None = None) -> dict:
    """Fetch current India gold/silver buy/sell reference from FreeAPI.

    FreeAPI returns a single India-wide market reference, not city-specific
    quotes. The `city` parameter is accepted for interface parity but does
    not change the returned rates.
    """
    key = ("local", city or "India")
    now = _now_epoch()

    with _cache_lock_for():
        entry = _cache.get(key)
        if entry and (now - entry["fetched_at"]) < Config.FREEAPI_CACHE_SECONDS:
            return entry["data"]

    url = f"{Config.FREEAPI_BASE}/prices"
    try:
        resp = requests.get(url, timeout=15)
    except requests.RequestException as exc:
        raise LocalRatesProviderError(f"FreeAPI request failed: {exc}") from exc
    if resp.status_code != 200:
        raise LocalRatesProviderError(
            f"FreeAPI returned status {resp.status_code}: {resp.text[:200]}"
        )

    payload = resp.json()
    if payload.get("statusCode") != 200:
        raise LocalRatesProviderError(
            f"FreeAPI error payload: {payload.get('message') or payload}"
        )

    data = payload.get("data")
    if not isinstance(data, dict):
        raise LocalRatesProviderError("FreeAPI returned an unexpected payload shape")

    gold = data.get("gold", {})
    silver = data.get("silver", {})
    if not gold or not silver:
        raise LocalRatesProviderError("FreeAPI payload missing gold/silver data")

    def _num(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _change(block):
        inner = block.get("change24h") if isinstance(block, dict) else None
        if not isinstance(inner, dict):
            return None
        return {
            "buy": _num(inner.get("buy")),
            "sell": _num(inner.get("sell")),
        }

    parsed = {
        "provider": "FreeAPI",
        "city": city or "India",
        "timestamp": data.get("timestamp"),
        "gold": {
            "buy_per_gram": _num(gold.get("buy")),
            "sell_per_gram": _num(gold.get("sell")),
            "buy_per_10g": _num(gold.get("buy")) * 10 if _num(gold.get("buy")) is not None else None,
            "sell_per_10g": _num(gold.get("sell")) * 10 if _num(gold.get("sell")) is not None else None,
            "gst_per_gram": _num(gold.get("gst")),
            "gst_per_10g": _num(gold.get("gst")) * 10 if _num(gold.get("gst")) is not None else None,
            "currency": gold.get("currency", "INR"),
            "unit": gold.get("unit", "gram"),
            "change24h": _change(gold),
        },
        "silver": {
            "buy_per_gram": _num(silver.get("buy")),
            "sell_per_gram": _num(silver.get("sell")),
            "buy_per_10g": _num(silver.get("buy")) * 10 if _num(silver.get("buy")) is not None else None,
            "sell_per_10g": _num(silver.get("sell")) * 10 if _num(silver.get("sell")) is not None else None,
            "gst_per_gram": _num(silver.get("gst")),
            "gst_per_10g": _num(silver.get("gst")) * 10 if _num(silver.get("gst")) is not None else None,
            "currency": silver.get("currency", "INR"),
            "unit": silver.get("unit", "gram"),
            "change24h": _change(silver),
        },
    }

    with _cache_lock_for():
        _cache[key] = {"data": parsed, "fetched_at": now}
    return parsed


def list_states(query: str = "") -> list[str]:
    """Return searchable list of major Indian cities for display.

    FreeAPI does not expose a city list endpoint; this returns a curated list
    of major Indian cities/metros for the search UI.
    """
    cities = [
        "India", "Delhi", "Mumbai", "Chennai", "Kolkata", "Bengaluru",
        "Hyderabad", "Ahmedabad", "Pune", "Jaipur", "Lucknow", "Kanpur",
        "Nagpur", "Indore", "Thane", "Bhopal", "Visakhapatnam", "Prayagraj",
        "Vadodara", "Ghaziabad", "Ludhiana", "Agra", "Nashik", "Faridabad",
        "Meerut", "Rajkot", "Kalyan-Dombivli", "Vasai-Virar", "Varanasi",
        "Surat", "Mumbai Suburbs", "New Delhi", "North Delhi", "South Delhi",
        "East Delhi", "West Delhi", "Central Delhi",
    ]
    if query:
        q = query.lower()
        cities = [c for c in cities if q in c.lower()]
    return cities


class LocalRatesProviderError(Exception):
    """FreeAPI request or response error."""
