"""Provider behaviour when the scanner is rate limited or blocked.

These tests are DB-free and network-free: the scanner, and the market-data
provider hook, are replaced with fakes so the failure path is deterministic.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from time import monotonic
from types import SimpleNamespace

import pytest
import requests

from app.providers import metals_tradingview as tv
from app.providers import PROVIDERS
from app.providers import fetch_mcx as chain_fetch
from app.services import market_data

SCAN = {
    "data": [
        {"s": "MCX:GOLD1!", "d": [124700.0]},
        {"s": "MCX:SILVER1!", "d": [152498.0]},
        {"s": "FX_IDC:USDINR", "d": [92.77]},
        {"s": "COMEX:GC1!", "d": [3666.0]},
        {"s": "COMEX:SI1!", "d": [43.86]},
    ]
}


class FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self.payload = payload or {}
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Client Error: Too Many Requests")

    def json(self):
        return self.payload


def _quote(**overrides):
    quote = tv.parse_scan(SCAN)
    quote.update(
        {
            "fetched_at": datetime.now(timezone.utc),
            "provider": "TradingView",
            "cached": False,
        }
    )
    quote.update(overrides)
    return quote


@pytest.fixture(autouse=True)
def reset_provider_cache(monkeypatch):
    monkeypatch.setattr(
        tv,
        "_cache",
        {"data": None, "data_at": None, "retry_at": None, "failures": 0},
    )


def test_scan_response_is_cached_between_calls(monkeypatch):
    calls = []

    def fake_post(*args, **kwargs):
        calls.append(args)
        return FakeResponse(SCAN)

    monkeypatch.setattr(tv.requests, "post", fake_post)

    first = tv.fetch_mcx()
    second = tv.fetch_mcx()

    assert len(calls) == 1
    assert first is second
    assert first["cached"] is False
    assert first["gold"]["price"] == 124700.0


def test_rate_limit_keeps_the_last_quote_without_claiming_a_new_reading(monkeypatch):
    monkeypatch.setattr(tv.requests, "post", lambda *a, **k: FakeResponse(SCAN))
    first = tv.fetch_mcx()

    monkeypatch.setattr(
        tv.requests, "post", lambda *a, **k: FakeResponse(status_code=429)
    )
    # Let the fresh-quote window lapse so the next call really retries.
    tv._cache["data_at"] -= tv.CACHE_SECONDS + 1

    second = tv.fetch_mcx()

    assert second["cached"] is True
    assert second["fetched_at"] == first["fetched_at"]
    assert second["gold"] == first["gold"]
    assert second["fx"] == first["fx"]


def test_cached_quote_expires_at_the_feed_threshold(monkeypatch):
    monkeypatch.setattr(tv, "MAX_CACHED_QUOTE_AGE_SECONDS", 120)
    monkeypatch.setattr(tv.requests, "post", lambda *a, **k: FakeResponse(status_code=429))
    tv._cache.update(
        {
            "data": _quote(),
            "data_at": monotonic() - 121,
            "retry_at": monotonic() + 60,
            "failures": 2,
        }
    )

    assert tv.fetch_mcx() is None


def test_provider_chain_names_the_source_that_failed(monkeypatch, caplog):
    fake_provider = SimpleNamespace(
        __name__="app.providers.broken_source",
        log=logging.getLogger("app.providers.broken_source"),
        fetch_mcx=lambda: None,
    )
    monkeypatch.setattr("app.providers.PROVIDERS", (fake_provider,))

    with caplog.at_level(logging.WARNING):
        assert chain_fetch() is None

    assert "broken_source: no quote" in caplog.text
    # The old message reported "last error: NoneType", hiding the real cause.
    assert "NoneType" not in caplog.text


def test_only_the_working_provider_is_registered():
    assert [module.__name__ for module in PROVIDERS] == [
        "app.providers.metals_tradingview",
        "app.providers.forex_black",
    ]


def test_live_quote_rejects_a_quote_without_a_comex_reference(monkeypatch):
    # A quote that only carries MCX rates used to reach Decimal division by a
    # zero spot price and raise DivisionByZero inside /api/prices/latest.
    monkeypatch.setattr(
        market_data,
        "fetch_mcx_provider",
        lambda: _quote(spot={"XAU": 0.0, "XAG": 0.0}),
    )

    assert market_data._live_quote() is None


def test_live_quote_carries_the_real_reading_and_freshness(monkeypatch):
    quote = _quote()
    monkeypatch.setattr(market_data, "fetch_mcx_provider", lambda: quote)

    live = market_data._live_quote()

    assert live["fresh"] is True
    assert live["provider"] == "TradingView"
    assert live["fetched_at"] == quote["fetched_at"]
    assert live["metals"]["XAU"]["inr_per_gram"] == Decimal("12470.0")
    assert live["metals"]["XAG"]["inr_per_gram"] == Decimal("152.498")


def test_cached_quote_is_reported_as_not_fresh(monkeypatch):
    monkeypatch.setattr(
        market_data, "fetch_mcx_provider", lambda: _quote(cached=True)
    )

    assert market_data._live_quote()["fresh"] is False
