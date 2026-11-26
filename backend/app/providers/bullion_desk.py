"""Fallback live price provider.

Used only when the primary TradingView scanner is unreachable, and only for
the four numbers the dashboard actually needs: MCX gold per 10 g, MCX silver
per kg, USD/INR and COMEX spot. The source of record is the AMC MCX prices
page, which publishes a plain-HTML table that survives the TradingView
outage and the datacentre IP blocks that hit mcxindia.com.

Units follow the exchanges: MCX gold is INR per 10 g, MCX silver is INR per
kg, COMEX spot is USD per troy ounce.
"""

import logging
from math import isfinite

import requests

log = logging.getLogger(__name__)

# AMC MCX page. The table cells are the same numbers the dashboard already
# displays, so no math is invented here.
BASE_URL = "https://www.amc.in/mcx-prices"
PAGE_URL = f"{BASE_URL}/"

# Refuse to serve a quote built from a page that does not look like the real
# reporting page (detects a redirect to an error/captcha page).
ACCEPTABLE_TITLE = "MCX MARKET REPORT"


def _fetch_page() -> str:
    response = requests.get(
        PAGE_URL,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-IN,en;q=0.9",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
        },
        timeout=15,
    )
    response.raise_for_status()
    html = response.text
    if ACCEPTABLE_TITLE not in html:
        raise ValueError(
            f"unexpected page title: {html[html.find('<title>'):html.find('</title>')]!r}"
        )
    return html


def _table_values(html: str) -> dict:
    """Pull the daily MCX gold / silver / USD-INR rows out of the report table.

    The report is a static HTML table, so a small, dependency-free parse is
    enough: find the table rows that mention MCX gold, MCX silver and
    USD/INR, and read the three numeric cells that follow the labels.
    """
    import re

    rows = {}
    for marker, key in (
        ("MCX Gold", "gold"),
        ("MCX Silver", "silver"),
        ("USD/INR", "fx"),
    ):
        pattern = re.compile(rf"{re.escape(marker)}", re.IGNORECASE)
        match = pattern.search(html)
        if not match:
            raise ValueError(f"MCX {key} row not found in report page")
        start = match.end()
        chunk = html[start : start + 400]
        numbers = re.findall(r"-?\d+(?:,\d{3})*(?:\.\d+)?", chunk)
        if not numbers:
            raise ValueError(f"no numeric cells after {marker!r}")
        value = numbers[0].replace(",", "")
        try:
            rows[key] = float(value)
        except ValueError:
            raise ValueError(f"unusable MCX {key} value {value!r} from report page")

    return rows


def fetch_mcx() -> dict | None:
    """Return one quote, or ``None`` while the fallback source is unavailable."""
    try:
        html = _fetch_page()
        values = _table_values(html)
    except Exception as exc:  # network, timeout, changed HTML layout
        log.warning("Bullion Desk fetch failed: %s: %s", type(exc).__name__, exc)
        return None

    gold = values["gold"]
    silver = values["silver"]
    fx = values["fx"]

    # Guard the same way the TradingView quote does: unusable or stale
    # numbers must never flow into the live snapshot.
    if (
        not all((isfinite(v) and v > 0) for v in (gold, silver, fx))
        or gold <= 0
        or silver <= 0
        or fx <= 0
    ):
        log.warning(
            "Bullion Desk returned unusable prices: gold=%s silver=%s fx=%s",
            gold,
            silver,
            fx,
        )
        return None

    return {
        "gold": {"price": gold, "expiry": None},
        "silver": {"price": silver, "expiry": None},
        "fx": fx,
        "spot": {"XAU": 0.0, "XAG": 0.0},
        "provider": "Bullion Desk",
    }
