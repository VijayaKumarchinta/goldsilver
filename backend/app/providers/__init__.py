"""Live gold / silver + USD/INR, single feeder.

A provider must expose ``fetch_mcx() -> dict | None`` and return one quote::

    {
        "gold": {"price": <INR per 10 g>, "expiry": None},
        "silver": {"price": <INR per kg>, "expiry": None},
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

# The live feeder. gold-api.com is the only free, keyless endpoint on this
# machine that returns both XAU and XAG at the same time, in INR, with
# the USD/INR cross-rate, so a single two-request call replaces the whole
# multi-provider path. Its fields are the only ones the dashboard consumes;
# the old scanner and the spot/FX source are no longer part of the live
# request path.
from app.providers import gold_api

PROVIDERS = (gold_api,)

log = logging.getLogger(__name__)

__all__ = ["PROVIDERS", "fetch_mcx"]


def fetch_mcx() -> dict | None:
    """Try every provider in order and return the first usable quote.

    Under the current configuration the list holds a single entry, so this is
    a one-step chain: gold-api.com either returns a full gold/silver quote or
    nothing. The loop is kept so a future provider can be prepended without
    touching the caller of this function, and so the existing unit tests
    (which monkeypatch the PROVIDERS list) keep their current behaviour.
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
