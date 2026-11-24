from decimal import Decimal
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def _ist_time(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(IST).strftime("%d %b %Y, %I:%M %p IST")
    except (AttributeError, TypeError, ValueError):
        return iso


def _number(value) -> str:
    return f"{Decimal(str(value)):,.2f}"


def format_price_message(snapshot: dict, event_label: str) -> str:
    gold = snapshot["metals"]["XAU"]
    silver = snapshot["metals"]["XAG"]
    gold_gram = Decimal(str(gold["inr_per_gram"]))
    silver_gram = Decimal(str(silver["inr_per_gram"]))
    gold_oz = gold.get("usd_per_oz")
    silver_oz = silver.get("usd_per_oz")
    usd_inr = snapshot["fx"].get("USD_INR", "—")
    updated = _ist_time(snapshot.get("captured_at") or gold.get("updated_at", ""))
    labels = {
        "periodic_update": "Gold & Silver Price Update (India)",
        "hourly_update": "Gold & Silver Price Update (India)",
        "hourly": "Gold & Silver Price Update (India)",
        "market_open": "Gold & Silver Market Open Update (India)",
        "market_close": "Gold & Silver Market Close Update (India)",
        "weekly_close": "Gold & Silver Weekly Close Update (India)",
    }
    title = labels.get(event_label, "Gold & Silver Price Update (India)")
    gold_10g = gold_gram * Decimal("10")
    silver_10g = silver_gram * Decimal("10")

    return (
        f"{title}\n\n"
        f"Gold 24K: ₹{_number(gold_gram)} per gram "
        f"(₹{_number(gold_10g)} per 10 grams)\n"
        f"Silver 999: ₹{_number(silver_gram)} per gram "
        f"(₹{_number(silver_10g)} per 10 grams)\n"
        f"Source: {gold.get('source') or 'MCX futures'}; {silver.get('source') or 'MCX futures'}\n"
        f"USD/INR: {_number(usd_inr)}\n"
        f"International spot (reference): Gold ${_number(gold_oz)}/oz; "
        f"Silver ${_number(silver_oz)}/oz\n"
        f"Checked: {updated}\n\n"
        "MCX futures prices exclude GST and making charges; local retail rates differ."
    )