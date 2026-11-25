"""Focused tests for the dashboard's intended contracts.

These tests are deliberately DB-free: they cover deterministic calculations and
the scheduler health contract that regressed when the blueprint imported
``_scheduler`` by value.
"""

from decimal import Decimal

from flask import Flask

from app.api.health import health_bp
from app.repositories.history import MAX_POINTS, _downsample
from app.scheduler import manager
from app.services.rates import KARAT_FACTORS, STATE_DATA, purity_rows, state_rows


def test_downsample_keeps_newest_and_respects_cap():
    items = [{"time": str(i)} for i in range(1000)]
    sampled = _downsample(items, MAX_POINTS["1D"])
    assert len(sampled) <= MAX_POINTS["1D"]
    assert sampled[-1] == items[-1]


def test_downsample_is_identity_below_cap():
    items = [{"time": str(i)} for i in range(10)]
    assert _downsample(items, 288) == items


def test_purity_rows_match_karat_factors():
    rows = purity_rows(Decimal("120000"), Decimal("1400"))
    by_label = {row["label"]: row for row in rows}

    assert by_label["Gold 24K"]["per_lot"] == "120000.00"
    assert by_label["Gold 24K"]["per_gram"] == "12000.00"
    expected_22k = (Decimal("120000") * KARAT_FACTORS["22K"]).quantize(Decimal("0.01"))
    assert by_label["Gold 22K"]["per_lot"] == str(expected_22k)
    assert by_label["Silver 999"]["per_lot"] == "1400.00"
    assert by_label["Silver 999"]["per_gram"] == "140.00"


def test_state_rows_cover_every_configured_state():
    rows = state_rows(Decimal("120000"), Decimal("1400"))
    assert len(rows) == len(STATE_DATA)
    assert {row["state"] for row in rows} == {state for state, _ in STATE_DATA}
    assert all(row["diff_pct"] == "0.00" for row in rows)


def test_scheduler_health_reports_the_running_scheduler():
    class FakeJob:
        id = "chart_snapshot"
        next_run_time = "2026-11-25 13:25:00+00:00"
        trigger = "cron[minute='*/5']"

    class FakeScheduler:
        running = True

        def get_jobs(self):
            return [FakeJob()]

    app = Flask(__name__)
    app.register_blueprint(health_bp, url_prefix="/api/health")
    client = app.test_client()

    original = manager._scheduler
    manager._scheduler = FakeScheduler()
    try:
        response = client.get("/api/health/scheduler")
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["running"] is True
        assert payload["jobs"][0]["id"] == "chart_snapshot"
    finally:
        manager._scheduler = original
