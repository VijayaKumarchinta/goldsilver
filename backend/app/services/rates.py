from decimal import Decimal, ROUND_HALF_UP
from flask import current_app

KARAT_FACTORS = {
    "24K": Decimal("1.000"),
    "22K": Decimal("0.916"),
    "18K": Decimal("0.750"),
}

STATE_DATA = [
    ("Andhra Pradesh", "Vijayawada"),
    ("Arunachal Pradesh", "Itanagar"),
    ("Assam", "Guwahati"),
    ("Bihar", "Patna"),
    ("Chhattisgarh", "Raipur"),
    ("Delhi (NCT)", "Delhi"),
    ("Goa", "Panaji"),
    ("Gujarat", "Ahmedabad"),
    ("Haryana", "Gurugram"),
    ("Himachal Pradesh", "Shimla"),
    ("Jharkhand", "Ranchi"),
    ("Karnataka", "Bengaluru"),
    ("Kerala", "Kochi"),
    ("Madhya Pradesh", "Bhopal"),
    ("Maharashtra", "Mumbai"),
    ("Manipur", "Imphal"),
    ("Meghalaya", "Shillong"),
    ("Mizoram", "Aizawl"),
    ("Nagaland", "Kohima"),
    ("Odisha", "Bhubaneswar"),
    ("Punjab", "Ludhiana"),
    ("Rajasthan", "Jaipur"),
    ("Sikkim", "Gangtok"),
    ("Tamil Nadu", "Chennai"),
    ("Telangana", "Hyderabad"),
    ("Tripura", "Agartala"),
    ("Uttar Pradesh", "Lucknow"),
    ("Uttarakhand", "Dehradun"),
    ("West Bengal", "Kolkata"),
]


def purity_rows(gold_per_10g, silver_per_10g) -> list[dict]:
    """Return purity breakdown rows derived from the 24K gold rate.

    ``gold_per_10g``/``silver_per_10g`` may be ``int``, ``float``, ``str`` or
    ``Decimal``: JSON serialisation (and a DB that returns an integer column)
    can hand us any of them. Convert once at the door so every subsequent
    ``Decimal`` operation and every test assertion that compares to ``str``
    stays deterministic.
    """
    gold = _to_decimal(gold_per_10g)
    silver = _to_decimal(silver_per_10g)
    rows = []
    for label, factor in KARAT_FACTORS.items():
        per_gram = (gold * factor / Decimal("10")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        per_lot = (gold * factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        rows.append(
            {
                "label": f"Gold {label}",
                "per_gram": str(per_gram),
                "per_lot": str(per_lot),
                "unit": "/10 g",
            }
        )
    # Silver 999
    rows.append(
        {
            "label": "Silver 999",
            "per_gram": str(
                (silver / Decimal("10")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            ),
            "per_lot": str(silver.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "unit": "/10 g",
        }
    )
    return rows


def _to_decimal(value) -> Decimal:
    """Coerce a numeric input (int, float, str, or Decimal) to a Decimal.

    A plain int is accepted so downstream callers that receive a JSON number
    (which Flask may render as an int when the DB returns an integer column)
    do not raise ``AttributeError: 'int' object has no attribute 'quantize'``.
    """
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):  # bool is a subclass of int; reject it explicitly
        return Decimal("0")
    if isinstance(value, int):
        return Decimal(value)
    return Decimal(str(value))


def state_rows(gold_per_10g, silver_per_10g) -> list[dict]:
    """Return national spot references for each state, without invented premiums.

    Inputs may arrive as ``int``/``float``/``str``/``Decimal`` (the REST
    boundary hands all four). ``diff_pct`` is computed from the actual
    24K-and-22K spreads, rounded to two decimals, instead of a hardcoded
    ``"0.00"`` that no longer reflects the data.
    """
    gold = _to_decimal(gold_per_10g)
    silver = _to_decimal(silver_per_10g)
    state_gold = gold.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    state_gold_22k = (state_gold * Decimal("0.916")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    state_silver = silver.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    diff_pct = ((state_gold - state_gold_22k) / state_gold * Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    rows = []
    for state, city in STATE_DATA:
        rows.append(
            {
                "state": state,
                "city": city,
                "gold_24k": str(state_gold),
                "gold_22k": str(state_gold_22k),
                "silver": str(state_silver),
                "diff_pct": str(diff_pct),
            }
        )
    return rows
