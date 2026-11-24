import logging
from datetime import datetime, timezone
from math import isfinite
from threading import Lock
from time import monotonic

import requests

from app.config import Config

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

            fx_rate = float(payload["fx_rates"]["INR"])
            gold = payload["xau"]
            gold_usd_per_oz = float(payload["spot_usd_oz"])
            silver_usd_per_oz = float(payload["silver_usd_oz"])
            if not all(
                isfinite(value) and value > 0
                for value in (fx_rate, gold_usd_per_oz, silver_usd_per_oz)
            ):
                raise ValueError("provider returned a non-positive market rate")

            if gold.get("currency") == "INR":
                gold_inr_per_gram = float(gold["price"])
            else:
                gold_inr_per_gram = (
                    gold_usd_per_oz * fx_rate / Config.TROY_OUNCE_IN_GRAMS
                )
            silver_inr_per_gram = (
                silver_usd_per_oz * fx_rate / Config.TROY_OUNCE_IN_GRAMS
            )
            if not all(
                isfinite(value) and value > 0
                for value in (gold_inr_per_gram, silver_inr_per_gram)
            ):
                raise ValueError("provider returned a non-positive converted rate")

            updated_at_raw = payload.get("updated_at") or payload.get("price_as_of")
            try:
                updated_at = datetime.fromisoformat(
                    updated_at_raw.replace("Z", "+00:00")
                ) if updated_at_raw else datetime.now(timezone.utc)
            except (TypeError, ValueError):
                updated_at = datetime.now(timezone.utc)
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)

            _cached_snapshot = {
                "metals": {
                    "XAU": {
                        "inr_per_gram": gold_inr_per_gram,
                        "usd_per_oz": gold_usd_per_oz,
                        "provider": "xaus.com",
                        "updated_at": updated_at,
                    },
                    "XAG": {
                        "inr_per_gram": silver_inr_per_gram,
                        "usd_per_oz": silver_usd_per_oz,
                        "provider": "xaus.com",
                        "updated_at": updated_at,
                    },
                },
                "fx_rate": fx_rate,
                "fx_source": "xaus.com",
                "stale": False,
            }
            return _cached_snapshot
        except (
            requests.RequestException,
            AttributeError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            log.warning("Market data provider failed: %s", exc)
            if _cached_snapshot is not None:
                _cached_snapshot = {**_cached_snapshot, "stale": True}
                return _cached_snapshot
            return None
