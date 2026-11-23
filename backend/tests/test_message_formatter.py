import unittest

from app.services.message_formatter import format_price_message


class PriceMessageFormatterTests(unittest.TestCase):
    def test_price_message_uses_inr_only_and_explains_units_and_ist_time(self):
        snapshot = {
            "captured_at": "2026-11-23T09:00:00+00:00",
            "metals": {
                "XAU": {
                    "inr_per_gram": "10800.00",
                    "usd_per_oz": "3600.00",
                    "updated_at": "2026-11-23T09:00:00+00:00",
                },
                "XAG": {
                    "inr_per_gram": "125.00",
                    "usd_per_oz": "42.00",
                },
            },
            "fx": {"USD_INR": "93.25"},
        }

        message = format_price_message(snapshot, "periodic_update")

        self.assertIn("Gold & Silver Global Spot Update (India)", message)
        self.assertIn("Gold 24K global spot: ₹10,800.00 per gram (₹108,000.00 per 10 grams)", message)
        self.assertIn("Silver 999 global spot: ₹125.00 per gram (₹1,250.00 per 10 grams)", message)
        self.assertNotIn("$", message)
        self.assertNotIn("USD", message)
        self.assertIn("23 Nov 2026, 02:30 PM IST", message)
        self.assertIn("Checked:", message)
        self.assertNotIn("not Hyderabad retail quotes", message)


if __name__ == "__main__":
    unittest.main()
