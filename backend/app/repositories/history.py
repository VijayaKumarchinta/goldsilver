from datetime import timedelta
from decimal import Decimal
from psycopg2.extras import RealDictCursor
from app.extensions import get_db


def get_chart_history(range_val: str = "7D") -> dict:
    """Return chart time-series from the database.

    range_val: "1D", "7D", or "30D"
    Returns { labels: [...], gold: [...], silver: [...], live: bool }

    Gold is reported per 10 g (inr_per_gram * 10) and silver is
    reported per gram (inr_per_gram). Series are raw readings,
    one point per snapshot timestamp, only where that metal was
    actually recorded.
    """
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if range_val == "1D":
            interval = "1 day"
            limit = 180
        elif range_val == "7D":
            interval = "7 days"
            limit = 420
        else:
            interval = "30 days"
            limit = 900

        from app.services.market_data import _FAMILY_SQL, source_family

        # Pick the same family the current view is built from so the
        # chart never mixes two different providers into one trace.
        cur.execute(
            """
            SELECT m.provider FROM goldbot.metal_prices m
            JOIN goldbot.price_snapshots s ON s.id = m.snapshot_id
            ORDER BY s.captured_at DESC LIMIT 1
            """
        )
        newest = cur.fetchone()
        family_sql = _FAMILY_SQL[source_family(newest["provider"] if newest else None)]
        cur.execute(
            f"""
            SELECT s.captured_at, m.symbol, m.inr_per_gram
            FROM goldbot.price_snapshots s
            JOIN goldbot.metal_prices m ON s.id = m.snapshot_id
            WHERE s.captured_at >= NOW() - (%s)::interval AND {family_sql}
            ORDER BY s.captured_at ASC
            LIMIT %s
            """,
            (interval, limit),
        )

        rows = cur.fetchall()

        if not rows:
            return {"labels": [], "gold": [], "silver": [], "live": False}

        # Build one point per snapshot, with separate per-metal values.
        by_time: dict[str, dict] = {}
        for r in rows:
            t = r["captured_at"].isoformat().replace("T", " ")
            point = by_time.setdefault(
                t,
                {"time": t, "XAU": None, "XAG": None},
            )
            point[r["symbol"]] = float(r["inr_per_gram"])

        # Chronological order.
        sorted_items = sorted(by_time.values(), key=lambda x: x["time"])

        labels = []
        gold_series = []
        silver_series = []

        for item in sorted_items:
            labels.append(item["time"])
            gold_series.append(
                round(item["XAU"] * 10, 2) if item["XAU"] is not None else None
            )
            silver_series.append(
                round(item["XAG"], 2) if item["XAG"] is not None else None
            )

        return {
            "labels": labels,
            "gold": gold_series,
            "silver": silver_series,
            "live": bool(rows),
        }

    finally:
        conn.close()
