import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app.services import market_data


def _quote(gold_per_10g=126021.0, silver_per_kg=154205.0, xau=3625.0, xag=42.24, fx=92.995):
    return {
        "gold": {"price": gold_per_10g, "expiry": None},
        "silver": {"price": silver_per_kg, "expiry": None},
        "fx": fx,
        "spot": {"XAU": xau, "XAG": xag},
        "fetched_at": datetime.now(timezone.utc),
        "provider": "TradingView",
    }


class MarketDataTests(unittest.TestCase):
    @patch("app.services.market_data.get_open_close_delta", return_value={"open": 0})
    @patch("app.services.market_data.metals_tradingview.fetch_mcx")
    def test_prices_come_from_mcx_futures_with_correct_units(self, fetch_mcx, _delta):
        fetch_mcx.return_value = _quote()

        snapshot = market_data.get_latest_snapshot()
        gold, silver = snapshot["metals"]["XAU"], snapshot["metals"]["XAG"]

        self.assertEqual(gold["source"], "MCX GOLD front-month futures")
        self.assertEqual(silver["source"], "MCX SILVER front-month futures")
        self.assertEqual(gold["inr_per_10g"], 126021.0)      # MCX gold is already per 10 g
        self.assertEqual(silver["inr_per_10g"], 1542.05)     # MCX silver is per kg: 154205 / 100
        self.assertEqual(silver["inr_per_gram"], 154.205)
        self.assertTrue(gold["live"] and silver["live"])
        self.assertFalse(gold["estimated"])
        self.assertEqual(gold["usd_per_oz"], 3625.0)         # COMEX reference kept for display
        self.assertEqual(snapshot["fx"]["USD_INR"], 92.995)
        self.assertEqual(snapshot["fx"]["FX_SOURCE"], "TradingView")

    @patch("app.services.market_data.get_open_close_delta", return_value={"open": 0})
    @patch("app.services.market_data.metals_tradingview.fetch_mcx")
    def test_spot_reference_is_converted_to_rupees(self, fetch_mcx, _delta):
        fetch_mcx.return_value = _quote()

        gold = market_data.get_latest_snapshot()["metals"]["XAU"]
        expected_per_gram = 3625.0 * 92.995 / 31.1035

        self.assertAlmostEqual(gold["spot_inr_per_10g"], expected_per_gram * 10, places=1)
        self.assertLess(gold["spot_inr_per_10g"], gold["inr_per_10g"])  # futures include import duty

    @patch("app.services.market_data.metals_tradingview.fetch_mcx")
    def test_implausible_futures_price_is_rejected(self, fetch_mcx):
        fetch_mcx.return_value = _quote(gold_per_10g=5000.0)  # half of spot: unit or parsing error
        self.assertIsNone(market_data._live_quote())

    @patch("app.services.market_data.metals_tradingview.fetch_mcx", return_value=None)
    def test_unavailable_provider_yields_no_live_quote(self, _fetch):
        self.assertIsNone(market_data._live_quote())

    def test_source_family_keeps_price_histories_apart(self):
        self.assertEqual(market_data.source_family("MCX GOLD front-month futures"), "mcx")
        self.assertEqual(market_data.source_family("MCX GOLD 05DEC2026 futures"), "mcx")
        self.assertEqual(market_data.source_family("xaus.com spot + duty (estimate)"), "estimate")
        self.assertEqual(market_data.source_family("xaus.com"), "spot")


if __name__ == "__main__":
    unittest.main()
