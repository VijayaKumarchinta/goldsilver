import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import Mock, patch

import requests

from app.providers import metals_xaus
from app.services import market_data


class XausProviderTests(unittest.TestCase):
    def setUp(self):
        self.cache_snapshot = patch.object(metals_xaus, "_cached_snapshot", None)
        self.cache_time = patch.object(metals_xaus, "_last_attempt_at", None)
        self.cache_snapshot.start()
        self.cache_time.start()
        self.addCleanup(self.cache_snapshot.stop)
        self.addCleanup(self.cache_time.stop)

    def _response(self):
        response = Mock()
        response.json.return_value = {
            "xau": {"price": 2600, "currency": "USD", "unit": "troy_oz"},
            "spot_usd_oz": 2600,
            "silver_usd_oz": 30,
            "fx_rates": {"INR": 80},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        return response

    def test_one_provider_response_supplies_both_metals_and_fx(self):
        with (
            patch("app.providers.metals_xaus.requests.get", return_value=self._response()) as get,
            patch("app.providers.metals_xaus.monotonic", side_effect=[10, 10]),
        ):
            snapshot = metals_xaus.fetch_market_data()
            cached_snapshot = metals_xaus.fetch_market_data()

        self.assertEqual(get.call_count, 1)
        self.assertIs(snapshot, cached_snapshot)
        self.assertEqual(snapshot["fx_rate"], 80)
        self.assertEqual(snapshot["metals"]["XAU"]["provider"], "xaus.com")
        self.assertEqual(snapshot["metals"]["XAG"]["provider"], "xaus.com")

    def test_silver_quote_conversion_matches_usd_ounce_and_inr_rate(self):
        response = self._response()
        response.json.return_value = {
            "xau": {"price": 3607.55, "currency": "USD", "unit": "troy_oz"},
            "spot_usd_oz": 3607.55,
            "silver_usd_oz": 42.153,
            "fx_rates": {"INR": 92.753491},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        with (
            patch("app.providers.metals_xaus.requests.get", return_value=response),
            patch("app.providers.metals_xaus.monotonic", return_value=10),
        ):
            snapshot = metals_xaus.fetch_market_data()

        expected = Decimal("42.153") * Decimal("92.753491") / Decimal("31.1035")
        self.assertEqual(snapshot["metals"]["XAG"]["inr_per_gram"], expected)
        self.assertEqual(expected.quantize(Decimal("0.01")), Decimal("125.70"))

    def test_provider_failure_returns_last_quote_as_stale(self):
        with (
            patch(
                "app.providers.metals_xaus.requests.get",
                side_effect=[self._response(), requests.ConnectionError("offline")],
            ),
            patch("app.providers.metals_xaus.monotonic", side_effect=[0, 6, 6.1]),
        ):
            fresh_snapshot = metals_xaus.fetch_market_data()
            stale_snapshot = metals_xaus.fetch_market_data()
            cached_stale_snapshot = metals_xaus.fetch_market_data()

        self.assertFalse(fresh_snapshot["stale"])
        self.assertTrue(stale_snapshot["stale"])
        self.assertIs(stale_snapshot, cached_stale_snapshot)
        self.assertEqual(stale_snapshot["metals"]["XAU"], fresh_snapshot["metals"]["XAU"])

    def test_stale_provider_response_does_not_replace_last_fresh_cache(self):
        stale_response = self._response()
        stale_response.json.return_value = {
            **self._response().json.return_value,
            "spot_usd_oz": 9000,
            "updated_at": (datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat(),
        }
        with (
            patch(
                "app.providers.metals_xaus.requests.get",
                side_effect=[self._response(), stale_response],
            ) as get,
            patch("app.providers.metals_xaus.monotonic", side_effect=[0, 6]),
        ):
            fresh_snapshot = metals_xaus.fetch_market_data()
            stale_snapshot = metals_xaus.fetch_market_data()

        self.assertFalse(fresh_snapshot["stale"])
        self.assertTrue(stale_snapshot["stale"])
        self.assertEqual(
            stale_snapshot["metals"]["XAU"]["usd_per_oz"],
            fresh_snapshot["metals"]["XAU"]["usd_per_oz"],
        )
        self.assertEqual(get.call_count, 2)

    def test_live_snapshot_uses_both_prices_from_one_provider_snapshot(
        self,
    ):
        provider_snapshot = {
            "metals": {
                "XAU": {
                    "inr_per_gram": Decimal("100"),
                    "usd_per_oz": Decimal("2600"),
                    "provider": "xaus.com",
                    "updated_at": market_data.datetime.now(market_data.timezone.utc),
                },
                "XAG": {
                    "inr_per_gram": Decimal("1"),
                    "usd_per_oz": Decimal("30"),
                    "provider": "xaus.com",
                    "updated_at": market_data.datetime.now(market_data.timezone.utc),
                },
            },
            "fx_rate": Decimal("80"),
            "fx_source": "xaus.com",
            "stale": False,
        }

        with (
            patch("app.services.market_data.metals_xaus.fetch_market_data", return_value=provider_snapshot) as fetch,
            patch("app.services.market_data.get_latest", return_value=None),
            patch("app.services.market_data.get_open_close_delta", return_value={"open": 2500}) as get_delta,
        ):
            snapshot = market_data.get_latest_snapshot()

        fetch.assert_called_once_with()
        self.assertEqual(snapshot["metals"]["XAU"]["source"], "xaus.com")
        self.assertEqual(snapshot["metals"]["XAG"]["source"], "xaus.com")
        self.assertEqual(snapshot["metals"]["XAU"]["inr_per_10g"], 1000)
        self.assertEqual(snapshot["metals"]["XAG"]["inr_per_10g"], 10)
        self.assertEqual(get_delta.call_count, 2)

    def test_outlier_uses_saved_snapshot_instead_of_returning_bad_quote(self):
        provider_snapshot = {
            "metals": {
                "XAU": {"inr_per_gram": Decimal("116")},
                "XAG": {"inr_per_gram": Decimal("1")},
            },
            "stale": False,
        }
        saved = {"metals": {"XAU": {"inr_per_gram": 100}}}
        previous = {
            "captured_at": datetime.now(timezone.utc),
            "metals": {
                "XAU": {"inr_per_gram": Decimal("100")},
                "XAG": {"inr_per_gram": Decimal("1")},
            }
        }

        with (
            patch("app.services.market_data.metals_xaus.fetch_market_data", return_value=provider_snapshot),
            patch("app.services.market_data.get_latest", return_value=previous),
            patch("app.services.market_data._saved_snapshot", return_value=saved) as get_saved,
        ):
            snapshot = market_data.get_latest_snapshot()

        self.assertIs(snapshot, saved)
        get_saved.assert_called_once_with()

    def test_old_reference_does_not_block_a_recovered_market_quote(self):
        provider_snapshot = {
            "metals": {
                "XAU": {
                    "inr_per_gram": Decimal("116"),
                    "usd_per_oz": Decimal("3000"),
                    "provider": "xaus.com",
                    "updated_at": datetime.now(timezone.utc),
                },
                "XAG": {
                    "inr_per_gram": Decimal("1.16"),
                    "usd_per_oz": Decimal("30"),
                    "provider": "xaus.com",
                    "updated_at": datetime.now(timezone.utc),
                },
            },
            "fx_rate": Decimal("80"),
            "fx_source": "xaus.com",
            "stale": False,
        }
        previous = {
            "captured_at": datetime.now(timezone.utc) - timedelta(hours=2),
            "metals": {
                "XAU": {"inr_per_gram": Decimal("100")},
                "XAG": {"inr_per_gram": Decimal("1")},
            },
        }

        with (
            patch("app.services.market_data.metals_xaus.fetch_market_data", return_value=provider_snapshot),
            patch("app.services.market_data.get_latest", return_value=previous),
            patch("app.services.market_data.get_open_close_delta", return_value={"open": 100}),
        ):
            snapshot = market_data.get_latest_snapshot()

        self.assertTrue(snapshot["metals"]["XAU"]["live"])

    def test_stale_provider_uses_saved_snapshot(self):
        provider_snapshot = {"stale": True}
        saved = {"metals": {"XAU": {"inr_per_gram": 100}}}

        with (
            patch("app.services.market_data.metals_xaus.fetch_market_data", return_value=provider_snapshot),
            patch("app.services.market_data._saved_snapshot", return_value=saved) as get_saved,
        ):
            snapshot = market_data.get_latest_snapshot()

        self.assertIs(snapshot, saved)
        get_saved.assert_called_once_with()

    def test_open_close_delta_uses_current_spot_close_and_saved_ist_open(self):
        conn = Mock()
        cursor = Mock()
        conn.cursor.return_value = cursor
        cursor.fetchone.return_value = (Decimal("100"),)

        with patch("app.services.market_data.get_db", return_value=conn):
            delta = market_data.get_open_close_delta(
                "XAU",
                current_close=Decimal("120"),
            )

        self.assertEqual(delta, {
            "open": 100.0,
            "close": 120.0,
            "delta": 20.0,
            "delta_pct": 20.0,
        })
        self.assertEqual(cursor.execute.call_count, 1)
        self.assertIn("Asia/Kolkata", cursor.execute.call_args.args[0])

if __name__ == "__main__":
    unittest.main()
