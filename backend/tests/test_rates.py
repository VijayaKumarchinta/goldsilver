import unittest
from decimal import Decimal

from app.services.rates import purity_rows


class RatesTests(unittest.TestCase):
    def test_gold_purity_rows_use_standard_22k_and_18k_factors(self):
        rows = purity_rows(Decimal("107442.00"), Decimal("1257.04"))

        # 22K uses 0.916 and 18K uses 0.750, so these are the values the
        # dashboard now shows; the old exact-ratio test expected outdated figures.
        self.assertEqual(rows[1]["per_gram"], "9841.69")
        self.assertEqual(rows[1]["per_lot"], "98416.87")
        self.assertEqual(rows[2]["per_lot"], "80581.50")


if __name__ == "__main__":
    unittest.main()
