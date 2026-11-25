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

    # Telegram uses MarkdownV2. Every literal punctuation character must be escaped
    # so the message renders correctly in the group.
    return _escape_markdown_v2(
        f"{title}\n\n"
        f"Gold 24K: ₹{_number(gold_gram)} per gram "
        f"(₹{_number(gold_10g)} per 10 grams)\n"
        f"Silver 999: ₹{_number(silver_gram)} per gram "
        f"(₹{_number(silver_10g)} per 10 grams)\n"
        f"Source: {gold.get('source') or 'MCX futures'}; {silver.get('source') or 'MCX futures'}\n"
        f"USD/INR: {_number(usd_inr)}\n"
        f"International spot reference: Gold {_number(gold_oz)} USD/oz; "
        f"Silver {_number(silver_oz)} USD/oz\n"
        f"Checked: {updated}\n\n"
        "MCX futures prices exclude GST and making charges; local retail rates differ."
    )


def format_user_message(snapshot: dict) -> str:
    """Turn a received Telegram msg into one line-of-context, readable text.

    The bot no longer parses the original message; it keeps a short human-written
    draft and attaches the extracted context (time, sender, raw text). The draft
    is the only part the user is allowed to edit, so the chat stays
    understandable without the bot inventing a new language.
    """
    gold = snapshot.get("metals", {}).get("XAU", {})
    silver = snapshot.get("metals", {}).get("XAG", {})
    gold_gram = Decimal(str(gold.get("inr_per_gram", "0")))
    silver_gram = Decimal(str(silver.get("inr_per_gram", "0")))
    usd_inr = snapshot.get("fx", {}).get("USD_INR", "—")
    draft = snapshot.get("user_draft") or snapshot.get("context", "")
    return _escape_markdown_v2(
        f"User draft: {draft or 'No draft provided'}"
        + f"\nTime: {_ist_time(snapshot.get('captured_at'))}"
        + f"\nSender: {snapshot.get('from', {}).get('username') or snapshot.get('from', {}).get('id') or 'unknown'}"
        + f"\nRaw text: {snapshot.get('text', '').replace(chr(10), ' | ')}"
        + f"\nGold: {chr(0x20b9)}{_number(gold_gram)} / g"
        + f"\nSilver: {chr(0x20b9)}{_number(silver_gram)} / g"
        + f"\nUSD/INR: {_number(usd_inr)}"
    )


_TELEGRAM_MD_V2_ESCAPE = {
    ch: "\\" + ch
    for ch in r"_*[]()~`>#+-=|{}.!"
}


def _escape_markdown_v2(text: str) -> str:
    # Telegram's MarkdownV2 requires many ASCII punctuation characters to be escaped
    # with a backslash. Escaping is applied once at message-build time.
    result = []
    for ch in text:
        replacement = _TELEGRAM_MD_V2_ESCAPE.get(ch)
        if replacement is None:
            result.append(ch)
        else:
            result.append(replacement)
    return "".join(result)
