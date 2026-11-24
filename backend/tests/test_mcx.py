import unittest
from datetime import date, datetime, timezone

from app.providers import metals_mcx as mcx

ROWS = [
    {"Symbol": "GOLD", "InstrumentName": "FUTCOM", "ExpiryDate": "05DEC2026", "LTP": 124760},
    {"Symbol": "GOLD", "InstrumentName": "FUTCOM", "ExpiryDate": "05FEB2027", "LTP": 126100},
    {"Symbol": "GOLD", "InstrumentName": "OPTFUT", "ExpiryDate": "27NOV2026", "LTP": 900},   # option: ignored
    {"Symbol": "GOLDM", "InstrumentName": "FUTCOM", "ExpiryDate": "05DEC2026", "LTP": 124700},  # other product
    {"Symbol": "SILVER", "InstrumentName": "FUTCOM", "ExpiryDate": "04DEC2026", "LTP": "1,52,090"},
    {"Symbol": "SILVER", "InstrumentName": "FUTCOM", "ExpiryDate": "05MAR2027", "LTP": 155000},
    {"Symbol": "CRUDEOIL", "InstrumentName": "FUTCOM", "ExpiryDate": "18DEC2026", "LTP": 5300},
]


class McxParserTests(unittest.TestCase):
    def test_picks_nearest_gold_and_silver_futures(self):
        result = mcx.parse_market_watch({"d": {"Data": ROWS}}, today=date(2026, 11, 23), roll_days=5)
        self.assertEqual(result["gold"], {"price": 124760.0, "expiry": date(2026, 12, 5)})
        self.assertEqual(result["silver"], {"price": 152090.0, "expiry": date(2026, 12, 4)})

    def test_rolls_to_the_next_contract_close_to_expiry(self):
        result = mcx.parse_market_watch({"d": {"Data": ROWS}}, today=date(2026, 12, 2), roll_days=5)
        self.assertEqual(result["gold"]["expiry"], date(2027, 2, 5))
        self.assertEqual(result["silver"]["expiry"], date(2027, 3, 5))

    def test_accepts_other_field_spellings(self):
        rows = [
            {"Commodity": "GOLD", "Instrument": "FUTCOM", "Expiry": "2026-12-05", "LastTradedPrice": "1,24,760.00"},
            {"Product": "SILVER", "InstrumentType": "FUTCOM", "ExpiryDt": "04 Dec 2026", "Last": 152090},
        ]
        result = mcx.parse_market_watch({"d": {"Data": rows}}, today=date(2026, 11, 23), roll_days=5)
        self.assertEqual(result["gold"]["price"], 124760.0)
        self.assertEqual(result["silver"]["expiry"], date(2026, 12, 4))

    def test_aspnet_date_format(self):
        ms = int(datetime(2026, 12, 5, tzinfo=timezone.utc).timestamp() * 1000)
        self.assertEqual(mcx.parse_expiry(f"/Date({ms})/"), date(2026, 12, 5))
        self.assertIsNone(mcx.parse_expiry("not a date"))

    def test_changed_page_format_fails_loudly_and_names_the_fields(self):
        rows = [{"Foo": "GOLD", "Bar": 1}]
        with self.assertRaises(ValueError) as ctx:
            mcx.parse_market_watch({"d": {"Data": rows}}, today=date(2026, 11, 23))
        self.assertIn("Foo", str(ctx.exception))

    def test_zero_or_missing_prices_are_ignored(self):
        rows = [{"Symbol": "GOLD", "InstrumentName": "FUTCOM", "ExpiryDate": "05DEC2026", "LTP": 0}]
        self.assertIsNone(mcx.pick_contract(rows, "GOLD", date(2026, 11, 23), 5))


if __name__ == "__main__":
    unittest.main()
