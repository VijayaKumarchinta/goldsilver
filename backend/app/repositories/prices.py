from psycopg2.extras import RealDictCursor
from app.extensions import get_db

def save_snapshot(snapshot: dict, event_type: str) -> int:
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute(
            """
            INSERT INTO price_snapshots (event_type, captured_at, base_currency, output_currency)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (
                event_type,
                snapshot["captured_at"],
                snapshot["base_currency"],
                snapshot["output_currency"],
            ),
        )
        snapshot_id = cur.fetchone()["id"]

        for symbol, m in snapshot["metals"].items():
            cur.execute(
                """
                INSERT INTO metal_prices
                    (snapshot_id, symbol, usd_per_oz, inr_per_gram, provider, provider_updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    snapshot_id,
                    symbol,
                    m["usd_per_oz"],
                    m["inr_per_gram"],
                    m["source"],
                    m["updated_at"],
                ),
            )

        usd_inr = snapshot["fx"]["USD_INR"]
        fx_provider_name = snapshot["fx"].get("FX_SOURCE", "xaus.com")
        cur.execute(
            """
            INSERT INTO fx_rates (snapshot_id, base, quote, rate, provider)
            VALUES (%s, 'USD', 'INR', %s, %s)
            """,
            (snapshot_id, usd_inr, fx_provider_name),
        )

        conn.commit()
        return snapshot_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def get_latest() -> dict | None:
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            SELECT s.id, s.event_type, s.captured_at, s.base_currency, s.output_currency
            FROM price_snapshots s
            ORDER BY s.captured_at DESC
            LIMIT 1
            """
        )
        snap = cur.fetchone()
        if not snap:
            return None

        cur.execute(
            "SELECT symbol, usd_per_oz, inr_per_gram, provider, provider_updated_at "
            "FROM metal_prices WHERE snapshot_id = %s",
            (snap["id"],),
        )
        metals = {row["symbol"]: dict(row) for row in cur.fetchall()}

        cur.execute(
            "SELECT base, quote, rate, provider FROM fx_rates WHERE snapshot_id = %s",
            (snap["id"],),
        )
        fx = {f'{r["base"]}_{r["quote"]}': str(r["rate"]) for r in cur.fetchall()}

        snap["metals"] = metals
        snap["fx"] = fx
        return snap
    finally:
        conn.close()