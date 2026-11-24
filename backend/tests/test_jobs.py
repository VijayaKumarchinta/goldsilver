import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.scheduler.jobs import scheduled_capture, scheduled_periodic_update


class ScheduledCaptureTests(unittest.TestCase):
    @patch(
        "app.scheduler.jobs.get_latest_snapshot",
        side_effect=RuntimeError("provider unavailable"),
    )
    def test_capture_failure_is_reraised(self, get_snapshot):
        with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
            scheduled_capture("market_capture")

        get_snapshot.assert_called_once_with()

    @patch("app.scheduler.jobs.scheduled_periodic_update", return_value={"due": True})
    def test_legacy_hourly_capture_uses_due_check(self, periodic_update):
        result = scheduled_capture("hourly_update")

        self.assertEqual(result, {"due": True})
        periodic_update.assert_called_once_with()


class ScheduledHourlyUpdateTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.due_status = {
            "last_sent_at": self.now - timedelta(hours=2),
            "last_periodic_attempt_at": self.now - timedelta(hours=2),
            "last_periodic_status": "sent",
        }
        self.live_snapshot = {
            "metals": {
                "XAU": {"live": True},
                "XAG": {"live": True},
            }
        }

    def test_due_update_saves_one_snapshot_and_dispatches(self):
        with (
            patch("app.scheduler.jobs.ensure_hourly_notification_schema"),
            patch("app.scheduler.jobs.dispatch_pending", return_value={"sent": 1}) as dispatch,
            patch("app.scheduler.jobs.get_notification_status", return_value=self.due_status),
            patch("app.scheduler.jobs.Config.TELEGRAM_BOT_TOKEN", "token"),
            patch("app.scheduler.jobs.list_enabled", return_value=[{"id": 1}]),
            patch("app.scheduler.jobs.has_scheduled_slot", return_value=False),
            patch("app.scheduler.jobs.get_latest_snapshot", return_value=self.live_snapshot),
            patch("app.scheduler.jobs.save_snapshot", return_value=42) as save_snapshot,
            patch("app.scheduler.jobs.create_jobs", return_value=1) as create_jobs,
        ):
            result = scheduled_periodic_update()

        self.assertTrue(result["due"])
        save_snapshot.assert_called_once_with(self.live_snapshot, event_type="periodic_update")
        create_jobs.assert_called_once()
        self.assertEqual(create_jobs.call_args.args[:2], (42, "periodic_update"))
        self.assertEqual(create_jobs.call_args.kwargs["scheduled_for"].second, 0)
        self.assertEqual(dispatch.call_count, 2)

    def test_backend_start_respects_recent_delivery_interval(self):
        recent_status = {
            **self.due_status,
            "last_sent_at": self.now - timedelta(minutes=10),
            "last_periodic_attempt_at": self.now - timedelta(minutes=10),
        }
        with (
            patch("app.scheduler.jobs.ensure_hourly_notification_schema"),
            patch("app.scheduler.jobs.dispatch_pending") as dispatch,
            patch("app.scheduler.jobs.get_notification_status", return_value=recent_status),
            patch("app.scheduler.jobs.list_enabled") as destinations,
            patch("app.scheduler.jobs.get_latest_snapshot") as get_snapshot,
        ):
            result = scheduled_periodic_update()

        self.assertFalse(result["due"])
        dispatch.assert_called_once_with()
        destinations.assert_not_called()
        get_snapshot.assert_not_called()

    def test_stale_market_data_is_not_sent(self):
        stale_snapshot = {
            "metals": {
                "XAU": {"live": False},
                "XAG": {"live": False},
            }
        }
        with (
            patch("app.scheduler.jobs.ensure_hourly_notification_schema"),
            patch("app.scheduler.jobs.dispatch_pending"),
            patch("app.scheduler.jobs.get_notification_status", return_value=self.due_status),
            patch("app.scheduler.jobs.Config.TELEGRAM_BOT_TOKEN", "token"),
            patch("app.scheduler.jobs.list_enabled", return_value=[{"id": 1}]),
            patch("app.scheduler.jobs.has_scheduled_slot", return_value=False),
            patch("app.scheduler.jobs.get_latest_snapshot", return_value=stale_snapshot),
            patch("app.scheduler.jobs.save_snapshot") as save_snapshot,
            patch("app.scheduler.jobs.create_jobs") as create_jobs,
        ):
            result = scheduled_periodic_update()

        self.assertFalse(result["due"])
        self.assertEqual(result["reason"], "live_market_data_unavailable")
        save_snapshot.assert_not_called()
        create_jobs.assert_not_called()

    def test_existing_interval_slot_prevents_duplicate_jobs(self):
        with (
            patch("app.scheduler.jobs.ensure_hourly_notification_schema"),
            patch("app.scheduler.jobs.dispatch_pending"),
            patch("app.scheduler.jobs.get_notification_status", return_value=self.due_status),
            patch("app.scheduler.jobs.Config.TELEGRAM_BOT_TOKEN", "token"),
            patch("app.scheduler.jobs.list_enabled", return_value=[{"id": 1}]),
            patch("app.scheduler.jobs.has_scheduled_slot", return_value=True),
            patch("app.scheduler.jobs.get_latest_snapshot") as get_snapshot,
            patch("app.scheduler.jobs.save_snapshot") as save_snapshot,
        ):
            result = scheduled_periodic_update()

        self.assertEqual(result["reason"], "interval_already_processed")
        get_snapshot.assert_not_called()
        save_snapshot.assert_not_called()

if __name__ == "__main__":
    unittest.main()
