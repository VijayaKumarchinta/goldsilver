from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from app.config import Config


def _positive_decimal(value, label: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a positive finite number") from exc
    if not number.is_finite() or number <= 0:
        raise ValueError(f"{label} must be a positive finite number")
    return number


def _parse_timestamp(value) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("provider timestamp is missing")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("provider timestamp is invalid") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def validate_xaus_payload(payload: dict, now: datetime | None = None) -> dict:
    if not isinstance(payload, Mapping):
        raise ValueError("provider payload must be an object")

    gold = payload.get("xau")
    if not isinstance(gold, Mapping):
        raise ValueError("provider gold quote is missing")
    currency = str(gold.get("currency", "")).upper()
    if currency != "USD":
        raise ValueError("provider gold quote must be denominated in USD")
    unit = gold.get("unit")
    if str(unit).lower() not in {
        "troy_oz",
        "troy ounce",
        "troy ounces",
    }:
        raise ValueError("provider gold quote must use troy ounces")

    gold_usd_per_oz = _positive_decimal(payload.get("spot_usd_oz"), "gold USD/oz")
    silver_usd_per_oz = _positive_decimal(payload.get("silver_usd_oz"), "silver USD/oz")
    fx_rates = payload.get("fx_rates")
    if not isinstance(fx_rates, Mapping):
        raise ValueError("provider USD/INR rate is missing")
    usd_inr = _positive_decimal(fx_rates.get("INR"), "USD/INR")
    if not Config.MIN_USD_INR <= usd_inr <= Config.MAX_USD_INR:
        raise ValueError("provider USD/INR rate is outside configured bounds")

    updated_at = _parse_timestamp(payload.get("updated_at") or payload.get("price_as_of"))
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    age_seconds = (now.astimezone(timezone.utc) - updated_at).total_seconds()
    if age_seconds < -60:
        raise ValueError("provider timestamp is in the future")

    return {
        "gold_usd_per_oz": gold_usd_per_oz,
        "silver_usd_per_oz": silver_usd_per_oz,
        "usd_inr": usd_inr,
        "updated_at": updated_at,
        "stale": age_seconds > Config.MAX_PRICE_STALENESS_SECONDS,
    }


def validate_price_jump(
    current: Decimal,
    previous: Decimal,
    max_jump_pct: Decimal | None = None,
) -> None:
    current = _positive_decimal(current, "current price")
    previous = _positive_decimal(previous, "previous price")
    if max_jump_pct is None:
        max_jump_pct = Config.MAX_SINGLE_TICK_JUMP_PCT
    max_jump_pct = Decimal(str(max_jump_pct))
    if not max_jump_pct.is_finite() or max_jump_pct <= 0:
        raise ValueError("maximum price jump must be a positive finite number")
    change_pct = abs(current - previous) / previous * Decimal("100")
    if change_pct > max_jump_pct:
        raise ValueError("market price jump exceeds configured limit")


def validate_snapshot_for_persistence(snapshot: dict) -> None:
    if not isinstance(snapshot, Mapping):
        raise ValueError("market snapshot must be an object")
    _parse_timestamp(snapshot.get("captured_at"))
    now = datetime.now(timezone.utc)
    metals = snapshot.get("metals")
    if not isinstance(metals, Mapping):
        raise ValueError("market snapshot metals are missing")
    for symbol in ("XAU", "XAG"):
        quote = metals.get(symbol)
        if not isinstance(quote, Mapping) or quote.get("live") is not True:
            raise ValueError(f"{symbol} quote is not live")
        _positive_decimal(quote.get("inr_per_gram"), f"{symbol} INR/gram")
        _positive_decimal(quote.get("usd_per_oz"), f"{symbol} USD/oz")
        quote_time = _parse_timestamp(quote.get("updated_at"))
        age_seconds = (now - quote_time).total_seconds()
        if age_seconds < -60 or age_seconds > Config.MAX_PRICE_STALENESS_SECONDS:
            raise ValueError(f"{symbol} provider quote is stale")
    fx = snapshot.get("fx")
    if not isinstance(fx, Mapping):
        raise ValueError("market snapshot USD/INR rate is missing")
    usd_inr = _positive_decimal(fx.get("USD_INR"), "USD/INR")
    if not Config.MIN_USD_INR <= usd_inr <= Config.MAX_USD_INR:
        raise ValueError("market snapshot USD/INR rate is outside configured bounds")
