import logging
from threading import Lock
from time import monotonic

import requests

from app.config import Config
from app.services.conversion import oz_to_gram
from app.services.validation import validate_xaus_payload

log = logging.getLogger(__name__)

REFRESH_SECONDS = 5
_cache_lock = Lock()
_cached_snapshot = None
_last_attempt_at = None


def fetch_market_data() -> dict | None:
    global _cached_snapshot, _last_attempt_at

    with _cache_lock:
        now = monotonic()
        if (
            _last_attempt_at is not None
            and now - _last_attempt_at < REFRESH_SECONDS
        ):
            return _cached_snapshot
        _last_attempt_at = now

        try:
            response = requests.get(
                f"{Config.XAUS_BASE}/api/v1/spot",
                timeout=10,
            )
            response.raise_for_status()
            payload = response.json()
            quote = validate_xaus_payload(payload)
            fx_rate = quote["usd_inr"]
            gold_usd_per_oz = quote["gold_usd_per_oz"]
            silver_usd_per_oz = quote["silver_usd_per_oz"]
            snapshot = {
                "metals": {
                    "XAU": {
                        "inr_per_gram": oz_to_gram(gold_usd_per_oz, fx_rate),
                        "usd_per_oz": gold_usd_per_oz,
                        "provider": "xaus.com",
                        "updated_at": quote["updated_at"],
                    },
                    "XAG": {
                        "inr_per_gram": oz_to_gram(silver_usd_per_oz, fx_rate),
                        "usd_per_oz": silver_usd_per_oz,
                        "provider": "xaus.com",
                        "updated_at": quote["updated_at"],
                    },
                },
                "fx_rate": fx_rate,
                "fx_source": "xaus.com",
                "stale": quote["stale"],
            }
            if quote["stale"]:
                log.warning("Xaus returned a quote older than the configured freshness limit")
                if _cached_snapshot is not None:
                    return {**_cached_snapshot, "stale": True}
                return snapshot
            _cached_snapshot = snapshot
            return snapshot
        except (
            requests.RequestException,
            ValueError,
        ) as exc:
            log.warning("Market data provider failed: %s", exc)
            if _cached_snapshot is not None:
                _cached_snapshot = {**_cached_snapshot, "stale": True}
                return _cached_snapshot
            return None
