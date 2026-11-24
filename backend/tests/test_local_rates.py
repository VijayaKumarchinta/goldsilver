import pytest
from app.services import local_rates
from app.config import Config


class FakeResponse:
    def __init__(self, status_code, json_data):
        self.status_code = status_code
        self._json = json_data

    def json(self):
        return self._json

    @property
    def text(self):
        return str(self._json)


class TestLocalRates:
    def setup_method(self):
        # Clear the cache before each test
        local_rates._cache.clear()

    def test_is_configured_returns_true_when_base_set(self, monkeypatch):
        monkeypatch.setattr(Config, "FREEAPI_BASE", "https://api.oropocket.com/public", raising=False)
        assert local_rates.is_configured() is True

    def test_is_configured_returns_false_when_base_empty(self, monkeypatch):
        monkeypatch.setattr(Config, "FREEAPI_BASE", "", raising=False)
        assert local_rates.is_configured() is False

    def test_get_local_market_reference_returns_parsed_rates(self, monkeypatch):
        monkeypatch.setattr(Config, "FREEAPI_BASE", "https://example.test", raising=False)

        def fake_get(url, timeout):
            assert url == "https://example.test/prices"
            return FakeResponse(200, {
                "statusCode": 200,
                "data": {
                    "gold": {
                        "buy": "7280.50",
                        "sell": "7310.00",
                        "gst": "0.00",
                        "currency": "INR",
                        "unit": "gram",
                        "change24h": {"buy": 0.14, "sell": 0.12},
                    },
                    "silver": {
                        "buy": "87.25",
                        "sell": "87.75",
                        "gst": "0.00",
                        "currency": "INR",
                        "unit": "gram",
                        "change24h": {"buy": -0.08, "sell": -0.05},
                    },
                    "timestamp": "2026-02-14T10:30:00Z",
                },
            })

        monkeypatch.setattr(local_rates.requests, "get", fake_get)
        result = local_rates.get_local_market_reference("Delhi")

        assert result["provider"] == "FreeAPI"
        assert result["city"] == "Delhi"
        assert result["gold"]["buy_per_gram"] == 7280.50
        assert result["gold"]["sell_per_gram"] == 7310.0
        assert result["gold"]["buy_per_10g"] == 72805.0
        assert result["gold"]["sell_per_10g"] == 73100.0
        assert result["silver"]["buy_per_gram"] == 87.25
        assert result["silver"]["sell_per_gram"] == 87.75
        assert result["silver"]["buy_per_10g"] == 872.5
        assert result["silver"]["sell_per_10g"] == 877.5
        assert result["gold"]["change24h"] == {"buy": 0.14, "sell": 0.12}
        assert result["silver"]["change24h"] == {"buy": -0.08, "sell": -0.05}

    def test_get_local_market_reference_passes_city_to_result(self, monkeypatch):
        monkeypatch.setattr(Config, "FREEAPI_BASE", "https://example.test", raising=False)

        def fake_get(url, timeout):
            return FakeResponse(200, {
                "statusCode": 200,
                "data": {
                    "gold": {"buy": "7280", "sell": "7310", "gst": "0", "currency": "INR", "unit": "gram"},
                    "silver": {"buy": "87", "sell": "88", "gst": "0", "currency": "INR", "unit": "gram"},
                    "timestamp": "2026-02-14T10:30:00Z",
                },
            })

        monkeypatch.setattr(local_rates.requests, "get", fake_get)
        result = local_rates.get_local_market_reference("Mumbai")
        assert result["city"] == "Mumbai"

    def test_get_local_market_reference_uses_india_when_no_city(self, monkeypatch):
        monkeypatch.setattr(Config, "FREEAPI_BASE", "https://example.test", raising=False)

        def fake_get(url, timeout):
            return FakeResponse(200, {
                "statusCode": 200,
                "data": {
                    "gold": {"buy": "7280", "sell": "7310", "gst": "0", "currency": "INR", "unit": "gram"},
                    "silver": {"buy": "87", "sell": "88", "gst": "0", "currency": "INR", "unit": "gram"},
                    "timestamp": "2026-02-14T10:30:00Z",
                },
            })

        monkeypatch.setattr(local_rates.requests, "get", fake_get)
        result = local_rates.get_local_market_reference()
        assert result["city"] == "India"

    def test_get_local_market_reference_raises_on_non_200(self, monkeypatch):
        monkeypatch.setattr(Config, "FREEAPI_BASE", "https://example.test", raising=False)

        def fake_get(url, timeout):
            return FakeResponse(500, {"error": "server error"})

        monkeypatch.setattr(local_rates.requests, "get", fake_get)
        with pytest.raises(local_rates.LocalRatesProviderError, match="status 500"):
            local_rates.get_local_market_reference()

    def test_get_local_market_reference_raises_on_non_200_status_code(self, monkeypatch):
        monkeypatch.setattr(Config, "FREEAPI_BASE", "https://example.test", raising=False)

        def fake_get(url, timeout):
            return FakeResponse(200, {"statusCode": 400, "message": "bad request"})

        monkeypatch.setattr(local_rates.requests, "get", fake_get)
        with pytest.raises(local_rates.LocalRatesProviderError, match="bad request"):
            local_rates.get_local_market_reference()

    def test_get_local_market_reference_rejects_missing_data(self, monkeypatch):
        monkeypatch.setattr(Config, "FREEAPI_BASE", "https://example.test", raising=False)

        def fake_get(url, timeout):
            return FakeResponse(200, {"statusCode": 200, "data": {}})

        monkeypatch.setattr(local_rates.requests, "get", fake_get)
        with pytest.raises(local_rates.LocalRatesProviderError, match="missing gold/silver"):
            local_rates.get_local_market_reference()

    def test_get_local_market_reference_rejects_bad_payload_shape(self, monkeypatch):
        monkeypatch.setattr(Config, "FREEAPI_BASE", "https://example.test", raising=False)

        def fake_get(url, timeout):
            return FakeResponse(200, {"statusCode": 200})

        monkeypatch.setattr(local_rates.requests, "get", fake_get)
        with pytest.raises(local_rates.LocalRatesProviderError, match="unexpected payload shape"):
            local_rates.get_local_market_reference()

    def _set_freeapi_base(self, monkeypatch, base):
        monkeypatch.setattr(Config, "FREEAPI_BASE", base, raising=False)

    def test_list_states_returns_all_cities_without_query(self):
        self._set_freeapi_base(pytest.MonkeyPatch(), "https://api.oropocket.com/public")

        states = local_rates.list_states()
        assert "Delhi" in states
        assert "Mumbai" in states
        assert "Bengaluru" in states
        assert len(states) > 20

    def test_search_returns_filtered_cities(self):
        self._set_freeapi_base(pytest.MonkeyPatch(), "https://api.oropocket.com/public")

        states = local_rates.list_states("Del")
        assert "Delhi" in states
        assert "New Delhi" in states
        assert "Mumbai" not in states

    def test_search_returns_empty_list_for_no_matches(self):
        self._set_freeapi_base(pytest.MonkeyPatch(), "https://api.oropocket.com/public")

        states = local_rates.list_states("XyzCity")
        assert states == []

    def test_local_market_reference_requires_freeapi_base(self, monkeypatch):
        monkeypatch.setattr(Config, "FREEAPI_BASE", "https://invalid.test", raising=False)

        def fake_get(url, timeout):
            from requests.exceptions import ConnectionError
            raise ConnectionError("Connection refused")

        monkeypatch.setattr(local_rates.requests, "get", fake_get)
        with pytest.raises(local_rates.LocalRatesProviderError):
            local_rates.get_local_market_reference()
