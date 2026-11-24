import unittest

from app.services.message_formatter import format_price_message, _escape_markdown_v2


class PriceMessageFormatterTests(unittest.TestCase):
    def test_price_message_explains_units_and_ist_capture_time(self):
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

        # Telegram now sends MarkdownV2, so literal punctuation is escaped.
        from app.services.message_formatter import _escape_markdown_v2

        # Build the exact expected lines the module produces, so the test
        # stays aligned with the formatter instead of hardcoding escape counts.
        expected_title = _escape_markdown_v2("Gold & Silver Price Update (India)")
        self.assertIn(expected_title, message)

        expected_silver_line = _escape_markdown_v2(
            "Silver 999: ₹125.00 per gram (₹1,250.00 per 10 grams)"
        )
        self.assertIn(expected_silver_line, message)

        expected_usd_line = _escape_markdown_v2("USD/INR: 93.25")
        self.assertIn(expected_usd_line, message)

        self.assertIn("23 Nov 2026, 02:30 PM IST", message)
        self.assertIn("Checked:", message)

    def test_markdown_v2_escapes_telegram_punctuation(self):
        raw = "Hello world! (test) 1.23 USD $42.00"
        expected = "Hello world\\! \\(test\\) 1\\.23 USD \\$42\\.00"
        self.assertEqual(_escape_markdown_v2(raw), expected)

    def test_markdown_v2_escapes_dash_dot_exclamation(self):
        raw = "A-B.C!D"
        expected = "A\\-B\\.C\\!D"
        self.assertEqual(_escape_markdown_v2(raw), expected)


if __name__ == "__main__":
    unittest.main()
