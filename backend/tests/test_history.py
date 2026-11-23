import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import Mock, patch

from app.repositories.history import get_chart_history


class ChartHistoryTests(unittest.TestCase):
    def test_returns_latest_observations_in_order_and_keeps_symbol_gaps(self):
        first = datetime(2026, 11, 23, 8, 0, tzinfo=timezone.utc)
        latest = first + timedelta(minutes=15)
        conn = Mock()
        cursor = Mock()
        conn.cursor.return_value = cursor
        cursor.fetchall.return_value = [
            {"captured_at": latest, "symbol": "XAU", "inr_per_gram": Decimal("10800")},
            {"captured_at": first, "symbol": "XAG", "inr_per_gram": Decimal("125.5")},
            {"captured_at": first, "symbol": "XAU", "inr_per_gram": Decimal("10700")},
        ]

        with patch("app.repositories.history.get_db", return_value=conn):
            history = get_chart_history("1D")

        self.assertEqual(history["labels"], [first.isoformat(), latest.isoformat()])
        self.assertEqual(history["gold"], [107000.0, 108000.0])
        self.assertEqual(history["silver"], [125.5, None])
        sql = cursor.execute.call_args.args[0]
        self.assertIn("ORDER BY captured_at DESC", sql)
        self.assertIn("ORDER BY recent.captured_at ASC", sql)
        conn.close.assert_called_once_with()

    def test_no_history_does_not_fetch_live_prices(self):
        conn = Mock()
        cursor = Mock()
        conn.cursor.return_value = cursor
        cursor.fetchall.return_value = []

        with (
            patch("app.repositories.history.get_db", return_value=conn),
            patch("app.services.market_data.get_latest_snapshot") as get_latest,
        ):
            history = get_chart_history("7D")

        self.assertEqual(history, {"labels": [], "gold": [], "silver": [], "live": False})
        get_latest.assert_not_called()
        conn.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
