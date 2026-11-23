from decimal import Decimal, ROUND_HALF_UP

from app.services.conversion import karat_rate

KARATS = {
    "24K": 24,
    "22K": 22,
    "18K": 18,
}


def purity_rows(gold_per_10g: Decimal, silver_per_10g: Decimal) -> list[dict]:
    """Return purity breakdown rows derived from the 24K gold rate."""
    rows = []
    for label, karat in KARATS.items():
        per_lot = karat_rate(gold_per_10g, karat)
        per_gram = (per_lot / Decimal("10")).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        rows.append({
            "label": f"Gold {label}",
            "per_gram": str(per_gram),
            "per_lot": str(per_lot),
            "unit": "/10 g",
        })
    # Silver 999
    rows.append({
        "label": "Silver 999",
        "per_gram": str((silver_per_10g / Decimal("10")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "per_lot": str(silver_per_10g.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "unit": "/10 g",
    })
    return rows
