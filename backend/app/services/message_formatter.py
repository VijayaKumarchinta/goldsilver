from datetime import datetime, timezone
from decimal import Decimal
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


def _next_ist_load() -> str:
    """Next time the dashboard or Telegram update regenerates prices, in IST.

    The chart, the live feed refresh and the 30-minute delivery all regenerate
    from the same schedule, so every slot the user waits for should use the
    same reference. ``next_send_at`` is the next real scheduler tick while a
    public UI refresh means the next 5-minute tick.
    """
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    minute = (now.minute // 5) * 5
    return now.replace(minute=minute, second=0, microsecond=0).astimezone(
        ZoneInfo("Asia/Kolkata")
    ).strftime("%d %b %Y, %I:%M %p IST")


def _number(value) -> str:
    # Coerce numeric inputs to Decimal. ``Decimal(str(value))`` is unsafe for
    # binary floats (1999.25 renders as "1999.2500000000001") and for plain
    # ints (which are always integral). Convert once here, where the input is
    # still just a Python value, then format the rounded Decimal.
    try:
        return f"{Decimal(value):,.2f}"
    except Exception:
        return str(value)


def format_price_message(snapshot: dict, event_label: str) -> str:
    gold = snapshot["metals"]["XAU"]
    silver = snapshot["metals"]["XAG"]
    gold_gram = Decimal(str(gold["inr_per_gram"]))
    silver_gram = Decimal(str(silver["inr_per_gram"]))
    usd_inr = snapshot["fx"].get("USD_INR", "—")
    updated = _ist_time(snapshot.get("captured_at") or gold.get("updated_at", ""))

    # The *next* regeneration time, not the retry time: the user should never
    # see a clock that already passed, and it has to line up with what the
    # dashboard shows as the next load.
    next_update = _next_ist_load()

    labels = {
        "periodic_update": "Gold & Silver Update",
        "hourly_update": "Gold & Silver Update",
        "hourly": "Gold & Silver Update",
        "market_open": "Market Open: Gold & Silver",
        "market_close": "Market Close: Gold & Silver",
        "weekly_close": "Weekly Close: Gold & Silver",
    }
    title = labels.get(event_label, "Gold & Silver Update")
    gold_10g = gold_gram * Decimal("10")
    silver_10g = silver_gram * Decimal("10")

    # Telegram uses MarkdownV2, so literal punctuation is escaped here.
    return _escape_markdown_v2(
        f"{title}\n\n"
        f"Gold 24K: ₹{_number(gold_gram)}/g (₹{_number(gold_10g)}/10g)\n"
        f"Silver 999: ₹{_number(silver_gram)}/g (₹{_number(silver_10g)}/10g)\n"
        f"USD/INR: {_number(usd_inr)}\n"
        f"Next update at: {next_update}"
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


# Telegram MarkdownV2 treats the rupee sign and em dash as special characters
# that must be escaped even though they are not ASCII. The bot formats rates
# with these symbols, so they are added here to avoid the "can't parse entities"
# / "Character '-' is reserved" errors.
for _ch in "₹—‘’“”–—…·":
    if _ch not in _TELEGRAM_MD_V2_ESCAPE:
        _TELEGRAM_MD_V2_ESCAPE[_ch] = "\\" + _ch


def _escape_markdown_v2(text: str) -> str:
    # Telegram's MarkdownV2 requires many ASCII punctuation characters to be
    # escaped with a backslash. Escaping is applied once at message-build time.
    result = []
    for ch in text:
        replacement = _TELEGRAM_MD_V2_ESCAPE.get(ch)
        if replacement is None:
            result.append(ch)
        else:
            result.append(replacement)
    return "".join(result)
