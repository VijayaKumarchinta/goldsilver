import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.services.validation import (
    validate_price_jump,
    validate_snapshot_for_persistence,
    validate_xaus_payload,
)


class ValidationTests(unittest.TestCase):
    def _payload(self, updated_at):
        return {
            "xau": {"price": 3607.55, "currency": "USD", "unit": "troy_oz"},
            "spot_usd_oz": 3607.55,
            "silver_usd_oz": 42.153,
            "fx_rates": {"INR": 92.753491},
            "updated_at": updated_at,
        }

    def test_valid_xaus_payload_is_normalized_and_fresh(self):
        now = datetime.now(timezone.utc)
        result = validate_xaus_payload(
            self._payload(now.isoformat()),
            now=now,
        )

        self.assertEqual(result["gold_usd_per_oz"], Decimal("3607.55"))
        self.assertEqual(result["silver_usd_per_oz"], Decimal("42.153"))
        self.assertEqual(result["usd_inr"], Decimal("92.753491"))
        self.assertFalse(result["stale"])

    def test_old_provider_timestamp_is_stale(self):
        now = datetime.now(timezone.utc)
        result = validate_xaus_payload(
            self._payload((now - timedelta(minutes=6)).isoformat()),
            now=now,
        )

        self.assertTrue(result["stale"])

    def test_missing_timestamp_and_invalid_fx_are_rejected(self):
        now = datetime.now(timezone.utc)
        with self.assertRaisesRegex(ValueError, "timestamp"):
            validate_xaus_payload(self._payload(None), now=now)

        payload = self._payload(now.isoformat())
        payload["fx_rates"]["INR"] = "NaN"
        with self.assertRaisesRegex(ValueError, "USD/INR"):
            validate_xaus_payload(payload, now=now)

    def test_excessive_price_jump_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "jump"):
            validate_price_jump(Decimal("116"), Decimal("100"))

        validate_price_jump(Decimal("115"), Decimal("100"))

    def test_persistence_requires_fresh_live_prices_and_valid_fx(self):
        now = datetime.now(timezone.utc)
        snapshot = {
            "captured_at": now.isoformat(),
            "metals": {
                "XAU": {
                    "live": True,
                    "inr_per_gram": "10000",
                    "usd_per_oz": "3600",
                    "updated_at": now.isoformat(),
                },
                "XAG": {
                    "live": True,
                    "inr_per_gram": "125",
                    "usd_per_oz": "42",
                    "updated_at": now.isoformat(),
                },
            },
            "fx": {"USD_INR": "92.75"},
        }

        validate_snapshot_for_persistence(snapshot)

        snapshot["metals"]["XAG"]["updated_at"] = (
            now - timedelta(minutes=6)
        ).isoformat()
        with self.assertRaisesRegex(ValueError, "stale"):
            validate_snapshot_for_persistence(snapshot)


if __name__ == "__main__":
    unittest.main()
