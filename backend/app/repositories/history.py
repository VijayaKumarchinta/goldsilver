from decimal import Decimal, ROUND_HALF_UP
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

        ranges = {
            "1D": ("1 day", 180),
            "7D": ("7 days", 750),
            "30D": ("30 days", 3000),
        }
        interval, limit = ranges.get(range_val, ranges["7D"])

        cur.execute(
            """
            WITH recent AS (
                SELECT id, captured_at
                FROM goldbot.price_snapshots
                WHERE captured_at >= NOW() - (%s)::interval
                ORDER BY captured_at DESC
                LIMIT %s
            )
            SELECT recent.captured_at, m.symbol, m.inr_per_gram
            FROM recent
            JOIN goldbot.metal_prices m ON recent.id = m.snapshot_id
            WHERE m.inr_per_gram > 0
            ORDER BY recent.captured_at ASC, m.symbol ASC
            """,
            (interval, limit),
        )

        rows = cur.fetchall()

        if not rows:
            return {"labels": [], "gold": [], "silver": [], "live": False}

        grouped = {}
        for r in rows:
            t = r["captured_at"]
            if t not in grouped:
                grouped[t] = {"time": t, "XAU": None, "XAG": None}
            if r["symbol"] in {"XAU", "XAG"} and r["inr_per_gram"] is not None:
                grouped[t][r["symbol"]] = Decimal(str(r["inr_per_gram"]))

        sorted_items = sorted(grouped.values(), key=lambda x: x["time"])

        labels = []
        gold_series = []
        silver_series = []

        for item in sorted_items:
            labels.append(item["time"].isoformat())
            gold_series.append(
                float((item["XAU"] * Decimal("10")).quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                ))
                if item["XAU"] is not None
                else None
            )
            silver_series.append(
                float(item["XAG"].quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                ))
                if item["XAG"] is not None
                else None
            )

        return {
            "labels": labels,
            "gold": gold_series,
            "silver": silver_series,
            "live": bool(rows),
        }
    finally:
        conn.close()
