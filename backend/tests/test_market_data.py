import unittest
from unittest.mock import patch
import requests

from app.services import market_data


class MarketDataTests(unittest.TestCase):
    def _mcx(self, gold_per_10g=1160, silver_per_kg=1150):
        return {
            "gold": {"price": gold_per_10g, "expiry": market_data.datetime(2026, 12, 5).date()},
            "silver": {"price": silver_per_kg, "expiry": market_data.datetime(2026, 12, 4).date()},
            "fetched_at": market_data.datetime.now(market_data.timezone.utc),
        }

    @patch("app.services.market_data.metals_mcx.fetch_mcx")
    @patch("app.services.market_data.metals_xaus.fetch_market_data")
    def test_prices_come_from_mcx_with_correct_units(self, fetch_spot, fetch_mcx):
        fetch_spot.return_value = {
            "metals": {
                "XAU": {"inr_per_gram": 100, "usd_per_oz": 2600, "provider": "xaus.com"},
                "XAG": {"inr_per_gram": 1, "usd_per_oz": 30, "provider": "xaus.com"},
            },
            "fx_rate": 80,
            "fx_source": "xaus.com",
            "stale": False,
        }
        fetch_mcx.return_value = self._mcx()

        snapshot = market_data.get_latest_snapshot()
        gold, silver = snapshot["metals"]["XAU"], snapshot["metals"]["XAG"]

        self.assertEqual(gold["source"], "MCX GOLD 05DEC2026 futures")
        self.assertEqual(silver["source"], "MCX SILVER 04DEC2026 futures")
        self.assertEqual(gold["inr_per_10g"], 1160)      # MCX gold is already per 10 g
        self.assertEqual(silver["inr_per_10g"], 11.5)    # MCX silver is per kg: 1150 / 100
        self.assertEqual(silver["inr_per_gram"], 1.15)
        self.assertTrue(gold["live"] and silver["live"])
        self.assertFalse(gold["estimated"])
        self.assertEqual(gold["usd_per_oz"], 2600)       # international spot kept as a reference

    @patch("app.services.market_data.metals_mcx.fetch_mcx", return_value=None)
    @patch("app.services.market_data.metals_xaus.fetch_market_data")
    def test_without_mcx_the_dashboard_shows_a_flagged_estimate(self, fetch_spot, _mcx):
        now = market_data.datetime.now(market_data.timezone.utc)
        fetch_spot.return_value = {
            "metals": {
                "XAU": {"inr_per_gram": 100, "usd_per_oz": 2600, "provider": "xaus.com", "updated_at": now},
                "XAG": {"inr_per_gram": 1, "usd_per_oz": 30, "provider": "xaus.com", "updated_at": now},
            },
            "fx_rate": 80,
            "fx_source": "xaus.com",
            "stale": False,
        }
        snapshot = market_data.get_latest_snapshot()
        gold = snapshot["metals"]["XAU"]
        self.assertEqual(gold["inr_per_10g"], 1150)      # 100/g x 10 x 1.15 import duty
        self.assertTrue(gold["estimated"])
        self.assertFalse(gold["live"])
        self.assertIn("estimate", gold["source"])
        self.assertTrue(snapshot["metals"]["XAG"]["estimated"])
        self.assertFalse(snapshot["metals"]["XAG"]["live"])

    @patch("app.services.market_data.metals_mcx.fetch_mcx")
    @patch("app.services.market_data.metals_xaus.fetch_market_data")
    def test_implausible_mcx_price_is_rejected(self, fetch_spot, fetch_mcx):
        fetch_spot.return_value = {
            "metals": {
                "XAU": {"inr_per_gram": 100, "usd_per_oz": 2600, "provider": "xaus.com", "updated_at": market_data.datetime.now(market_data.timezone.utc)},
                "XAG": {"inr_per_gram": 1, "usd_per_oz": 30, "provider": "xaus.com", "updated_at": market_data.datetime.now(market_data.timezone.utc)},
            },
            "fx_rate": 80,
            "fx_source": "xaus.com",
            "stale": False,
        }
        fetch_mcx.return_value = self._mcx(gold_per_10g=5000)   # half of spot: parsing or unit error
        self.assertTrue(market_data.get_latest_snapshot()["metals"]["XAU"]["estimated"])

    def test_source_family_keeps_price_histories_apart(self):
        self.assertEqual(market_data.source_family("MCX GOLD 05DEC2026 futures"), "mcx")
        self.assertEqual(market_data.source_family("xaus.com spot + duty (estimate)"), "estimate")
        self.assertEqual(market_data.source_family("xaus.com"), "spot")


if __name__ == "__main__":
    unittest.main()
