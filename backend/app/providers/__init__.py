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
# Only the TradingView scanner is listed as a live MCX source. The previous AMC
# fallback pointed at https://www.amc.in, a domain that does not resolve
# (NXDOMAIN), so every request paid for a failed DNS lookup and logged a
# warning. mcxindia.com, the only other publisher of MCX front-month prices,
# answers HTTP 403 to datacentre IPs, so it cannot stand behind this source
# either.
#
# forex_black is also registered as an MCX fallback candidate on the live path,
# but it does not yet satisfy the MCX quote contract: it returns COMEX USD/oz
# spot plus USD/INR, not INR MCX prices, so ``market_data._live_quote`` still
# rejects its payload through the INR/spot ratio gate. It is kept in the import
# and in PROVIDERS so the intended fallback wiring is explicit and is the next
# change behind this one; see ``app.providers.forex_black.fetch_mcx``.
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
