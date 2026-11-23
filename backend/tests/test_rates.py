import unittest
from decimal import Decimal

from app.services.rates import purity_rows


class RatesTests(unittest.TestCase):
    def test_gold_purity_rows_use_exact_karat_ratio(self):
        rows = purity_rows(Decimal("107442.00"), Decimal("1257.04"))

        self.assertEqual(rows[1]["per_gram"], "9848.85")
        self.assertEqual(rows[1]["per_lot"], "98488.50")
        self.assertEqual(rows[2]["per_lot"], "80581.50")


if __name__ == "__main__":
    unittest.main()
