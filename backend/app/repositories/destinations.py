from psycopg2.extras import RealDictCursor
from app.extensions import get_db
from app.config import Config


def list_enabled() -> list[dict]:
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "SELECT id, channel, identifier, label FROM destinations WHERE enabled = TRUE"
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def ensure_telegram_destination() -> int | None:
    """Create or retrieve the Telegram destination from TELEGRAM_CHAT_ID.
    Returns the destination id, or None if TELEGRAM_CHAT_ID is not configured."""
    if not Config.TELEGRAM_CHAT_ID:
        return None
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO destinations (channel, identifier, label, enabled)
            VALUES ('telegram', %s, 'Telegram Gold Updates', TRUE)
            ON CONFLICT (channel, identifier) DO UPDATE SET enabled = TRUE
            RETURNING id
            """,
            (Config.TELEGRAM_CHAT_ID,),
        )
        destination_id = cur.fetchone()[0]
        conn.commit()
        return destination_id
    finally:
        conn.close()