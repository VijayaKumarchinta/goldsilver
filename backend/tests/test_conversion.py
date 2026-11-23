import unittest
from decimal import Decimal

from app.services.conversion import karat_rate, oz_to_gram, to_10g, to_kg


class ConversionTests(unittest.TestCase):
    def test_troy_ounce_conversion_uses_decimal_arithmetic(self):
        usd_per_oz = Decimal("42.153")
        usd_inr = Decimal("92.753491")

        result = oz_to_gram(usd_per_oz, usd_inr)

        self.assertEqual(
            result,
            usd_per_oz * usd_inr / Decimal("31.1035"),
        )
        self.assertEqual(to_10g(result), Decimal("1257.04"))
        self.assertEqual(to_kg(result), Decimal("125704.11"))

    def test_22k_rate_uses_exact_karat_ratio(self):
        self.assertEqual(
            karat_rate(Decimal("107442.00"), 22),
            Decimal("98488.50"),
        )


if __name__ == "__main__":
    unittest.main()
