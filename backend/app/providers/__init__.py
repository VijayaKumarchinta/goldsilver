"""Live price providers for MCX gold / silver.

Each provider must expose ``fetch_mcx() -> dict | None`` and return one quote::

    {
        "gold": {"price": <MCX gold, INR per 10 g>, "expiry": None},
        "silver": {"price": <MCX silver, INR per kg>, "expiry": None},
        "fx": <USD/INR>,
        "spot": {"XAU": <gold USD/oz>, "XAG": <silver USD/oz>},
        "provider": "<provider id>",
    }

``None`` means "no quote right now"; an exception is treated as the same and
is logged, so the loop in ``market_data._live_quote`` keeps trying the next
source instead of taking the process down.
"""

import logging

from app.providers import metals_tradingview
from app.providers.bullion_desk import fetch_mcx as fetch_bullion_desk

# Ordered list of sources. The first one that returns a quote wins.
PROVIDERS = (metals_tradingview, bullion_desk)

log = logging.getLogger(__name__)

__all__ = ["PROVIDERS", "fetch_mcx"]


def fetch_mcx() -> dict | None:
    """Try every provider in order and return the first usable quote.

    ``market_data._live_quote`` treats the first non-``None`` quote as *the*
    live feed, so keep the order disciplined: the scanner first, then the
    fallback that sits behind it.
    """
    last_error = None
    for provider in PROVIDERS:
        try:
            quote = provider.fetch_mcx()
        except Exception as exc:  # network, timeout, changed payload
            last_error = exc
            provider.log.warning(
                "Provider %s failed: %s: %s", provider.__name__, type(exc).__name__, exc
            )
            continue
        if quote is None:
            continue
        return quote

    log.warning(
        "All price providers unavailable (last error: %s)", type(last_error).__name__
    )
    return None
