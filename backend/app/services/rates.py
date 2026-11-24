from decimal import Decimal, ROUND_HALF_UP

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


def purity_rows(gold_per_10g: Decimal, silver_per_10g: Decimal) -> list[dict]:
    """Return purity breakdown rows derived from the 24K gold rate."""
    rows = []
    for label, factor in KARAT_FACTORS.items():
        per_gram = (gold_per_10g * factor / Decimal("10")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        per_lot = (gold_per_10g * factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
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


def state_rows(gold_per_10g: Decimal, silver_per_10g: Decimal) -> list[dict]:
    """Return national spot references for each state, without invented premiums."""
    rows = []
    for state, city in STATE_DATA:
        state_gold = gold_per_10g.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        state_gold_22k = (state_gold * Decimal("0.916")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        state_silver = silver_per_10g.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        rows.append({
            "state": state,
            "city": city,
            "gold_24k": str(state_gold),
            "gold_22k": str(state_gold_22k),
            "silver": str(state_silver),
            "diff_pct": "0.00",
        })
    return rows
