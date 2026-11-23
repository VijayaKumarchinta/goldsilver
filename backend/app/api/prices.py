from decimal import Decimal, ROUND_HALF_UP
from flask import Blueprint, jsonify, request
from app.services.market_data import (
    get_latest_snapshot,
    get_open_close_delta,
)
from app.repositories.history import get_chart_history
from app.services.rates import purity_rows
from app.services import local_rates
from app.config import Config

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
        },
        "silver": {
            "open": silver["open_per_10g"],
            "close": silver["inr_per_10g"],
            "usd_per_oz": silver["usd_per_oz"],
            "inr_per_gram": silver["inr_per_gram"],
            "updated_at": silver["updated_at"],
            "source": silver["source"],
            "live": silver["live"],
        },
        "fx": {"USD_INR": usd_inr},
        "quote_type": "global_spot",
        "market_open": snap["market_open"],
        "captured_at": snap["captured_at"],
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
    snapshot = get_latest_snapshot()
    quote = snapshot["metals"].get(metal, {})
    if not quote:
        return jsonify({"error": "No current or saved market prices are available"}), 503
    d = get_open_close_delta(metal, current_close=quote.get("inr_per_gram"))
    d["name"] = name
    d["metal"] = metal
    d["quote_type"] = "global_spot"
    return jsonify(d), 200


@prices_bp.route("/purity", methods=["GET"])
@prices_bp.route("/purity/", methods=["GET"])
def purity():
    """Gold by purity: 24K, 22K, 18K, and Silver 999."""
    snap = get_latest_snapshot()
    gold = snap["metals"].get("XAU", {})
    silver = snap["metals"].get("XAG", {})
    if not gold or not silver:
        return jsonify({"error": "No current or saved market prices are available"}), 503
    gold_10g = Decimal(str(gold["inr_per_10g"]))
    silver_10g = Decimal(str(silver["inr_per_10g"]))
    return jsonify({
        "purity": purity_rows(gold_10g, silver_10g),
        "gold_24k_per_10g": str(gold_10g.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "silver_per_10g": str(silver_10g.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "quote_type": "global_spot",
    }), 200


@prices_bp.route("/states", methods=["GET"])
@prices_bp.route("/states/", methods=["GET"])
def states():
    """Return searchable Indian cities for local market reference.

    FreeAPI provides India-wide rates, not city-specific quotes.
    This returns the list of major cities for display/search purposes.
    """
    return jsonify({
        "provider": "FreeAPI",
        "local_rates_available": bool(local_rates.is_configured()),
        "states": local_rates.list_states(request.args.get("q", "")),
        "message": (
            "Local market reference is India-wide from FreeAPI, not city-specific. "
            "GST treatment is indicative. Rates are tradeable references, not guaranteed retail quotes."
        ),
    }), 200


@prices_bp.route("/local-market", methods=["GET"])
def local_market():
    """Current local market gold and silver reference from FreeAPI.

    Returns tradeable buy/sell rates in INR per gram with GST and 24h changes.
    Query param `city` is optional and informational only; FreeAPI returns India-wide rates.
    """
    if not Config.FREEAPI_BASE:
        return jsonify({"error": "FreeAPI is not configured"}), 503
    city = request.args.get("city", "India")
    try:
        quote = local_rates.get_local_market_reference(city)
    except local_rates.LocalRatesProviderError as exc:
        return jsonify({"error": str(exc)}), 502
    return jsonify(quote), 200


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
