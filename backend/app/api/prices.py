from decimal import Decimal, ROUND_HALF_UP
from flask import Blueprint, jsonify
from app.repositories.history import get_chart_history
from app.services.market_data import (
    _market_open_now,
    feed_health,
    get_latest_snapshot,
    get_open_close_delta,
)
from app.services.rates import purity_rows, state_rows

prices_bp = Blueprint("prices", __name__)


@prices_bp.route("/latest", methods=["GET"])
def latest():
    """Current price snapshot. Matches HTML preview `D` object structure."""
    snap = get_latest_snapshot()
    gold = snap["metals"]["XAU"]
    silver = snap["metals"]["XAG"]
    if not gold or not silver:
        return jsonify({"error": "No current or saved market prices are available"}), 503
    usd_inr = snap["fx"]["USD_INR"]

    # Both the live provider and the DB fallback store the rate per gram. The
    # dashboard always displays a per-10 g number, so expose ``close`` as that
    # value and keep ``inr_per_gram`` for the per-gram detail. ``Decimal``
    # (straight out of PostgreSQL and the live provider) is not JSON-safe in
    # older Flask, so coerce to float here — the frontend expects a number.
    def _to_number(value):
        try:
            return float(Decimal(str(value)))
        except Exception:
            return value

    return jsonify({
        "gold": {
            "open": gold.get("open_per_10g"),
            "close": _to_number(gold["inr_per_gram"]) * 10 if gold.get("inr_per_gram") is not None else None,
            "usd_per_oz": _to_number(gold["usd_per_oz"]),
            "inr_per_gram": _to_number(gold["inr_per_gram"]),
            "updated_at": gold["updated_at"],
            "source": gold["source"],
            "live": gold.get("live", False),
            "estimated": gold.get("estimated", False),
            "spot_inr_per_10g": _to_number(gold.get("spot_inr_per_10g")),
        },
        "silver": {
            "open": silver.get("open_per_10g"),
            "close": _to_number(silver["inr_per_gram"]) * 10 if silver.get("inr_per_gram") is not None else None,
            "usd_per_oz": _to_number(silver["usd_per_oz"]),
            "inr_per_gram": _to_number(silver["inr_per_gram"]),
            "live": silver.get("live", False),
            "updated_at": silver["updated_at"],
            "source": silver["source"],
            "estimated": silver.get("estimated", False),
            "spot_inr_per_10g": _to_number(silver.get("spot_inr_per_10g")),
        },
        "fx": {"USD_INR": _to_number(usd_inr)},
        "market_open": snap["market_open"],
        "captured_at": snap["captured_at"],
        "feed": feed_health(),
    }), 200


@prices_bp.route("/chart/<range_val>", methods=["GET"])
def chart_range(range_val):
    """Chart data for a specific range: 1D, 7D, or 30D.
    Uses real historical data from the database.
    """
    if range_val not in ("1D", "7D", "30D"):
        range_val = "7D"
    history = get_chart_history(range_val)
    return jsonify(history), 200


@prices_bp.route("/delta/<metal>", methods=["GET"])
def delta(metal):
    """Open/close delta for a metal (gold or silver)."""
    if metal not in ("XAU", "XAG"):
        return jsonify({"error": "invalid metal"}), 400
    name = "Gold" if metal == "XAU" else "Silver"
    d = get_open_close_delta(metal)
    d["name"] = name
    d["metal"] = metal
    return jsonify(d), 200


@prices_bp.route("/purity", methods=["GET"])
@prices_bp.route("/purity/", methods=["GET"])
def purity():
    """Gold by purity: 24K, 22K, 18K, and Silver 999."""
    snap = get_latest_snapshot()
    gold = snap["metals"]["XAU"]
    silver = snap["metals"]["XAG"]
    gold_10g = Decimal(str(gold["inr_per_gram"])) * 10
    silver_10g = Decimal(str(silver["inr_per_gram"])) * 10
    return jsonify({
        "purity": purity_rows(gold_10g, silver_10g),
        "gold_24k_per_10g": str(gold_10g.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "silver_per_10g": str(silver_10g.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
    }), 200


@prices_bp.route("/states", methods=["GET"])
@prices_bp.route("/states/", methods=["GET"])
def states():
    """Rates by state with local premiums."""
    snap = get_latest_snapshot()
    gold = snap["metals"]["XAU"]
    silver = snap["metals"]["XAG"]
    gold_10g = Decimal(str(gold["inr_per_gram"])) * 10
    silver_10g = Decimal(str(silver["inr_per_gram"])) * 10
    return jsonify({
        "states": state_rows(gold_10g, silver_10g),
        "gold_24k_per_10g": str(gold_10g.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "silver_per_10g": str(silver_10g.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
    }), 200
