from decimal import Decimal, ROUND_HALF_UP
from flask import Blueprint, jsonify
from app.services.market_data import (
    feed_health,
    get_latest_snapshot,
    get_open_close_delta,
)
from app.repositories.history import get_chart_history
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

    return jsonify({
        "gold": {
            "open": gold["open_per_10g"],
            "close": gold["inr_per_10g"],
            "usd_per_oz": gold["usd_per_oz"],
            "inr_per_gram": gold["inr_per_gram"],
            "updated_at": gold["updated_at"],
            "source": gold["source"],
            "live": gold["live"],
            "estimated": gold.get("estimated", False),
            "spot_inr_per_10g": gold.get("spot_inr_per_10g"),
        },
        "silver": {
            "open": silver["open_per_10g"],
            "close": silver["inr_per_10g"],
            "usd_per_oz": silver["usd_per_oz"],
            "inr_per_gram": silver["inr_per_gram"],
            "updated_at": silver["updated_at"],
            "source": silver["source"],
            "live": silver["live"],
            "estimated": silver.get("estimated", False),
            "spot_inr_per_10g": silver.get("spot_inr_per_10g"),
        },
        "fx": {"USD_INR": usd_inr},
        "market_open": snap["market_open"],
        "captured_at": snap["captured_at"],
        "feed": feed_health(),
    }), 200


@prices_bp.route("/chart/<range_val>", methods=["GET"])
def chart_range(range_val):
    """Chart data for a specific range: 1D, 7D, or 30D.
    Uses real historical data from the database."""
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
    gold_10g = Decimal(snap["metals"]["XAU"]["inr_per_10g"])
    silver_10g = Decimal(snap["metals"]["XAG"]["inr_per_10g"])
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
    gold_10g = Decimal(snap["metals"]["XAU"]["inr_per_10g"])
    silver_10g = Decimal(snap["metals"]["XAG"]["inr_per_10g"])
    return jsonify({
        "states": state_rows(gold_10g, silver_10g),
        "gold_24k_per_10g": str(gold_10g.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "silver_per_10g": str(silver_10g.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
    }), 200


@prices_bp.route("/schedule", methods=["GET"])
def schedule():
    """Notification schedule matching HTML reference."""
    return jsonify([
        {
            "name": "Market open",
            "time": "09:00",
            "tz": "Asia/Kolkata",
            "zone": "IST",
            "days": "Mon–Fri",
            "enabled": True,
        },
        {
            "name": "Market close",
            "time": "23:55",
            "tz": "Asia/Kolkata",
            "zone": "IST",
            "days": "Mon–Thu",
            "enabled": True,
        },
        {
            "name": "Weekly close",
            "time": "23:55",
            "tz": "Asia/Kolkata",
            "zone": "IST",
            "days": "Fri",
            "enabled": True,
        },
    ]), 200


@prices_bp.route("/destinations", methods=["GET"])
def destinations():
    """Telegram notification destinations."""
    return jsonify([
        {"name": "Metals Watch", "platform": "Telegram", "enabled": True},
        {"name": "Test group", "platform": "Telegram", "enabled": False},
    ]), 200


@prices_bp.route("/health", methods=["GET"])
def health_check():
    """Lightweight health check. Matches HTML reference market status."""
    from app.services.market_data import _market_open_now
    return jsonify({
        "status": "ok",
        "market_open": _market_open_now(),
    }), 200
