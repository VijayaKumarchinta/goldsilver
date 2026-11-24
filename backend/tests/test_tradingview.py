import unittest

from app.providers import metals_tradingview as tv


def _payload():
    return {
        "totalCount": 5,
        "data": [
            {"s": "MCX:GOLD1!", "d": [125996, 3.46]},
            {"s": "MCX:SILVER1!", "d": [154217, 4.33]},
            {"s": "FX_IDC:USDINR", "d": [92.9, 0]},
            {"s": "COMEX:GC1!", "d": [3625.4, -0.71]},
            {"s": "COMEX:SI1!", "d": [42.26, -2.12]},
        ],
    }


class ScannerParserTests(unittest.TestCase):
    def test_maps_exchange_units(self):
        quote = tv.parse_scan(_payload())
        self.assertEqual(quote["gold"]["price"], 125996.0)   # INR per 10 g
        self.assertEqual(quote["silver"]["price"], 154217.0)  # INR per kg
        self.assertEqual(quote["fx"], 92.9)
        self.assertEqual(quote["spot"], {"XAU": 3625.4, "XAG": 42.26})

    def test_missing_symbol_is_an_error_not_a_guess(self):
        payload = _payload()
        payload["data"] = [row for row in payload["data"] if row["s"] != "MCX:SILVER1!"]
        with self.assertRaisesRegex(ValueError, "MCX:SILVER1!"):
            tv.parse_scan(payload)

    def test_zero_or_non_numeric_price_is_rejected(self):
        for bad in (0, None, "125996"):
            payload = _payload()
            payload["data"][0]["d"] = [bad, 3.46]
            with self.assertRaises(ValueError):
                tv.parse_scan(payload)

    def test_empty_payload_is_rejected(self):
        with self.assertRaises(ValueError):
            tv.parse_scan({})


if __name__ == "__main__":
    unittest.main()
