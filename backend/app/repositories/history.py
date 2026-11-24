from datetime import timedelta
from decimal import Decimal
from psycopg2.extras import RealDictCursor
from app.extensions import get_db


def get_chart_history(range_val: str = "7D") -> dict:
    """Return chart time-series from the database.

    range_val: "1D", "7D", or "30D"
    Returns { labels: [...], gold: [...], silver: [...], live: bool }
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

        # Group by timestamp
        grouped = {}
        for r in rows:
            t = r["captured_at"].isoformat()
            if t not in grouped:
                grouped[t] = {"time": t, "XAU": None, "XAG": None}
            grouped[t][r["symbol"]] = float(r["inr_per_gram"])

        # Sort chronologically and build series
        sorted_items = sorted(grouped.values(), key=lambda x: x["time"])

        labels = []
        gold_series = []
        silver_series = []
        last_gold = None
        last_silver = None

        cur.execute(
            """
            SELECT m.symbol, m.inr_per_gram
            FROM goldbot.price_snapshots s
            JOIN goldbot.metal_prices m ON s.id = m.snapshot_id
            WHERE s.id = (SELECT id FROM goldbot.price_snapshots ORDER BY captured_at DESC LIMIT 1)
            """
        )
        for latest in cur.fetchall():
            if latest["symbol"] == "XAU":
                last_gold = round(float(latest["inr_per_gram"]) * 10, 2)
            elif latest["symbol"] == "XAG":
                last_silver = round(float(latest["inr_per_gram"]), 2)

        if last_gold is None or last_silver is None:
            try:
                from app.services.market_data import get_latest_snapshot
                snap = get_latest_snapshot()
                if last_gold is None and snap["metals"].get("XAU"):
                    last_gold = round(float(snap["metals"]["XAU"]["inr_per_10g"]), 2)
                if last_silver is None and snap["metals"].get("XAG"):
                    last_silver = round(float(snap["metals"]["XAG"]["inr_per_10g"]) / 10, 2)
            except Exception:
                pass

        for item in sorted_items:
            dt = item["time"].replace("T", " ")
            labels.append(dt)
            if item["XAU"] is not None:
                last_gold = round(item["XAU"] * 10, 2)
            if item["XAG"] is not None:
                last_silver = round(item["XAG"], 2)
            gold_series.append(last_gold if last_gold is not None else 0)
            silver_series.append(last_silver if last_silver is not None else 0)

        return {
            "labels": labels,
            "gold": gold_series,
            "silver": silver_series,
            "live": bool(rows),
        }
    finally:
        conn.close()
