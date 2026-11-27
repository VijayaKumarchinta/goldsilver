"""Live price providers for MCX gold / silver.

Each provider must expose ``fetch_mcx() -> dict | None`` and return one quote::

    {
        "gold": {"price": <MCX gold, INR per 10 g>, "expiry": None},
        "silver": {"price": <MCX silver, INR per kg>, "expiry": None},
        "fx": <USD/INR>,
        "spot": {"XAU": <gold USD/oz>, "XAG": <silver USD/oz>},
        "provider": "<provider id>",
        "fetched_at": <aware datetime of the reading>,
        "cached": <True when the provider is replaying its last good quote>,
    }

``None`` means "no quote right now"; an exception is treated as the same and
is logged, so the loop in ``market_data._live_quote`` keeps trying the next
source instead of taking the process down.

/MCX quote contract/: ``gold.price`` and ``silver.price`` are INR per the
exchange unit for that metal (gold per 10 g, silver per kg). A provider that
only returns COMEX USD/oz spot does not satisfy this contract, even when it
also returns USD/INR, because ``market_data._live_quote`` validates the INR
quote against the converted COMEX reference before it accepts the reading.
"""

import logging

from app.providers import metals_tradingview, forex_black

# Ordered list of sources. The first one that returns a quote wins.
#
# The TradingView scanner is the only live price source for this app: it
# reports the MCX rupee prices (gold per 10 g, silver per kg), the USD/INR
# rate and the USD/oz COMEX spot in a single call. The xaus spot/FX source
# is registered to carry the currency reference, but its fields are volatile
# and it could return only the spot/wholesale band if the INR-level fields
# were ever missing.
PROVIDERS = (metals_tradingview, forex_black)

log = logging.getLogger(__name__)

__all__ = ["PROVIDERS", "fetch_mcx"]


def fetch_mcx() -> dict | None:
    """Try every provider in order and return the first usable quote.

    ``market_data._live_quote`` treats the first non-``None`` quote as *the*
    live feed, so keep the order disciplined: the scanner first, then any
    future fallback behind it.
    """
    failures = []
    for provider in PROVIDERS:
        name = provider.__name__.rsplit(".", 1)[-1]
        try:
            quote = provider.fetch_mcx()
        except Exception as exc:  # network, timeout, changed payload
            failures.append(f"{name}: {type(exc).__name__}")
            provider.log.warning(
                "Provider %s failed: %s: %s", name, type(exc).__name__, exc
            )
            continue
        if quote is None:
            failures.append(f"{name}: no quote")
            continue
        return quote

    # Name the source that failed. The old message printed
    # "last error: NoneType" because providers report failure by returning
    # None, which hid the actual cause from the deploy logs.
    log.warning(
        "No price provider returned a usable quote (%s)",
        "; ".join(failures) or "no providers configured",
    )
    return None
