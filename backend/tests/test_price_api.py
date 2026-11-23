import pytest
from unittest.mock import patch
from app.api.prices import prices_bp
from app.config import Config


class FakeResponse:
    def __init__(self, status_code, json_data):
        self.status_code = status_code
        self._json = json_data

    def json(self):
        return self._json

    def text(self):
        return str(self._json)


class PriceApiTests:
    def test_latest_endpoint_identifies_global_spot_basis(self, client):
        resp = client.get("/prices/latest")
        assert resp.status_code in (200, 503)
        if resp.status_code == 200:
            data = resp.get_json()
            assert data["quote_type"] == "global_spot"

    def test_delta_uses_current_validated_spot_as_close(self, client):
        resp = client.get("/prices/delta/XAU")
        assert resp.status_code in (200, 400, 503)

    def test_states_endpoint_reports_unavailable_when_not_configured(self, client, monkeypatch):
        monkeypatch.setattr(Config, "FREEAPI_BASE", "")
        resp = client.get("/prices/states")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["provider"] == "FreeAPI"
        assert data["local_rates_available"] is False
        assert isinstance(data["states"], list)

    def test_states_endpoint_returns_searchable_cities(self, client, monkeypatch):
        monkeypatch.setattr(Config, "FREEAPI_BASE", "https://example.test")
        resp = client.get("/prices/states?q=Del")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["local_rates_available"] is True
        assert "Delhi" in data["states"]
        assert "Mumbai" not in data["states"]

    def test_local_market_endpoint_requires_freeapi_base(self, client, monkeypatch):
        monkeypatch.setattr(Config, "FREEAPI_BASE", "")
        resp = client.get("/prices/local-market")
        assert resp.status_code == 503
        data = resp.get_json()
        assert data["error"] == "FreeAPI is not configured"

    def test_local_market_endpoint_accepts_city_param(self, client, monkeypatch):
        monkeypatch.setattr(Config, "FREEAPI_BASE", "https://example.test")

        def fake_get(url, timeout):
            assert url == "https://example.test/prices"
            return FakeResponse(200, {
                "statusCode": 200,
                "data": {
                    "gold": {"buy": "7280", "sell": "7310", "gst": "0", "currency": "INR", "unit": "gram"},
                    "silver": {"buy": "87", "sell": "88", "gst": "0", "currency": "INR", "unit": "gram"},
                    "timestamp": "2026-02-14T10:30:00Z",
                },
            })

        with patch("app.services.local_rates.requests.get", fake_get):
            resp = client.get("/prices/local-market?city=Delhi")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["provider"] == "FreeAPI"
            assert data["city"] == "Delhi"
            assert data["gold"]["buy_per_gram"] == 7280.0
            assert data["silver"]["buy_per_gram"] == 87.0

    def test_local_market_endpoint_returns_freeapi_reference(self, client, monkeypatch):
        monkeypatch.setattr(Config, "FREEAPI_BASE", "https://example.test")

        def fake_get(url, timeout):
            return FakeResponse(200, {
                "statusCode": 200,
                "data": {
                    "gold": {"buy": "7280.50", "sell": "7310.00", "gst": "5.00", "currency": "INR", "unit": "gram"},
                    "silver": {"buy": "87.25", "sell": "87.75", "gst": "0.50", "currency": "INR", "unit": "gram"},
                    "timestamp": "2026-02-14T10:30:00Z",
                },
            })

        with patch("app.services.local_rates.requests.get", fake_get):
            resp = client.get("/prices/local-market")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["provider"] == "FreeAPI"
            assert data["city"] == "India"
            assert data["gold"]["buy_per_gram"] == 7280.50
            assert data["gold"]["sell_per_gram"] == 7310.0
            assert data["gold"]["gst_per_gram"] == 5.0
            assert data["silver"]["buy_per_gram"] == 87.25
            assert data["silver"]["sell_per_gram"] == 87.75
            assert data["silver"]["gst_per_gram"] == 0.5
