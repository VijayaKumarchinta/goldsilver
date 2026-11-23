from decimal import Decimal, ROUND_HALF_UP

from app.config import Config

_CENT = Decimal("0.01")


def oz_to_gram(usd_per_oz: Decimal, usd_inr: Decimal) -> Decimal:
    return Decimal(str(usd_per_oz)) * Decimal(str(usd_inr)) / Config.TROY_OUNCE_IN_GRAMS


def to_10g(inr_per_gram: Decimal) -> Decimal:
    return (Decimal(str(inr_per_gram)) * Decimal("10")).quantize(
        _CENT,
        rounding=ROUND_HALF_UP,
    )


def to_kg(inr_per_gram: Decimal) -> Decimal:
    return (Decimal(str(inr_per_gram)) * Decimal("1000")).quantize(
        _CENT,
        rounding=ROUND_HALF_UP,
    )


def karat_rate(gold_24k_per_10g: Decimal, karat: int) -> Decimal:
    if not isinstance(karat, int) or isinstance(karat, bool) or not 1 <= karat <= 24:
        raise ValueError("karat must be an integer from 1 through 24")
    rate = Decimal(str(gold_24k_per_10g)) * Decimal(karat) / Decimal("24")
    return rate.quantize(_CENT, rounding=ROUND_HALF_UP)