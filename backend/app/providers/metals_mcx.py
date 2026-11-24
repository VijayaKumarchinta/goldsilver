"""MCX gold and silver futures from MCX's public market-watch page.

Units used by MCX: GOLD is quoted in rupees per 10 g, SILVER in rupees per kg.
This is an unofficial use of the public website, not a licensed data feed. MCX sits behind
a bot filter (Akamai), so requests go through curl_cffi with a browser fingerprint.
Run `python -m app.providers.metals_mcx` to test the connection from your machine.
"""
import logging
import re
import time
from datetime import date, datetime, timedelta, timezone
from math import isfinite
from threading import Lock

from app.config import Config

log = logging.getLogger(__name__)

PAGE_URL = "https://www.mcxindia.com/market-data/market-watch"
DATA_URL = "https://www.mcxindia.com/backpage.aspx/GetMarketWatch"
CACHE_SECONDS = 15
HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/json",
    "Origin": "https://www.mcxindia.com",
    "Referer": PAGE_URL,
    "X-Requested-With": "XMLHttpRequest",
}
# MCX does not document its field names, so several spellings are accepted.
SYMBOL_KEYS = ("Symbol", "Commodity", "CommodityName", "Product", "ProductName")
INSTRUMENT_KEYS = ("InstrumentName", "Instrument", "InstrumentType")
PRICE_KEYS = ("LTP", "LastTradedPrice", "LastPrice", "Last", "ClosePrice")
EXPIRY_KEYS = ("ExpiryDate", "Expiry", "ExpiryDt")
EXPIRY_FORMATS = ("%d%b%Y", "%d %b %Y", "%d-%b-%Y", "%Y-%m-%d", "%d/%m/%Y", "%d%B%Y", "%d %B %Y")

_lock = Lock()
_cache: dict = {"t": None, "data": None}
_session = None


def _first(row: dict, keys):
    for key in keys:
        if row.get(key) not in (None, ""):
            return row[key]
    return None


def _number(value):
    try:
        number = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) and number > 0 else None


def parse_expiry(value) -> date | None:
    text = str(value or "").strip()
    match = re.search(r"/Date\((\d+)\)/", text)  # ASP.NET style
    if match:
        return datetime.fromtimestamp(int(match.group(1)) / 1000, timezone.utc).date()
    for fmt in EXPIRY_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def pick_contract(rows: list, symbol: str, today: date, roll_days: int) -> dict | None:
    """Nearest futures contract for `symbol`, skipping ones about to expire."""
    candidates = []
    for row in rows:
        if str(_first(row, SYMBOL_KEYS) or "").strip().upper() != symbol:
            continue
        instrument = _first(row, INSTRUMENT_KEYS)
        if instrument and not str(instrument).upper().startswith("FUT"):
            continue  # options
        price, expiry = _number(_first(row, PRICE_KEYS)), parse_expiry(_first(row, EXPIRY_KEYS))
        if price and expiry:
            candidates.append({"price": price, "expiry": expiry})
    eligible = [c for c in candidates if (c["expiry"] - today).days >= roll_days] or candidates
    return min(eligible, key=lambda c: c["expiry"]) if eligible else None


def parse_market_watch(payload: dict, today: date | None = None, roll_days: int | None = None) -> dict:
    """{'gold': {'price': INR/10 g, 'expiry': date}, 'silver': {'price': INR/kg, 'expiry': date}}"""
    rows = payload["d"]["Data"]
    today = today or datetime.now(timezone.utc).date()
    roll = Config.MCX_ROLL_DAYS if roll_days is None else roll_days
    gold = pick_contract(rows, "GOLD", today, roll)
    silver = pick_contract(rows, "SILVER", today, roll)
    if not gold or not silver:
        keys = sorted(rows[0].keys()) if rows else []
        raise ValueError(f"no GOLD/SILVER futures found in {len(rows)} rows; fields seen: {keys}")
    return {"gold": gold, "silver": silver}


def _new_session():
    from curl_cffi import requests as curl_requests

    session = curl_requests.Session(impersonate="chrome124")
    session.get(PAGE_URL, timeout=20)  # picks up the cookies the data call expects
    time.sleep(1.5)
    return session


def fetch_mcx() -> dict | None:
    """Latest MCX GOLD and SILVER futures, or None. A failed call is never served from cache."""
    global _session
    if not Config.MCX_ENABLED:
        return None
    with _lock:
        now = time.monotonic()
        if _cache["t"] is not None and now - _cache["t"] < CACHE_SECONDS:
            return _cache["data"]
        _cache["t"] = now
        try:
            _session = _session or _new_session()
            response = _session.post(DATA_URL, headers=HEADERS, data={}, timeout=20)
            if response.status_code in (401, 403):
                _session = None
                raise RuntimeError(f"blocked by MCX (HTTP {response.status_code})")
            response.raise_for_status()
            quote = parse_market_watch(response.json())
            quote["fetched_at"] = datetime.now(timezone.utc)
            _cache["data"] = quote
            return quote
        except Exception as exc:  # network, bot filter, changed page format
            log.warning("MCX fetch failed: %s: %s", type(exc).__name__, str(exc)[:200])
            _cache["data"] = None
            return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = fetch_mcx()
    if result is None:
        raise SystemExit("MCX fetch failed - see the warning above.")
    g, s = result["gold"], result["silver"]
    print(f"GOLD   {g['expiry']}  Rs {g['price']:,.2f} per 10 g")
    print(f"SILVER {s['expiry']}  Rs {s['price']:,.2f} per kg  (Rs {s['price'] / 100:,.2f} per 10 g)")
