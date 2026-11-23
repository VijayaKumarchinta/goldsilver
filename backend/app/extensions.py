import logging
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from app.config import Config

logger = logging.getLogger(__name__)
_db_init_done = False


def get_db():
    global _db_init_done
    conn = psycopg2.connect(Config.DATABASE_URL)
    conn.autocommit = False
    with conn.cursor() as cur:
        cur.execute("SET search_path TO goldbot, public")
    if not _db_init_done:
        _db_init_done = True
        _init_schema(conn)
    return conn


def _init_schema(conn):
    """Run the project schema.sql on first connection so tables exist before any query."""
    schema_path = os.path.join(os.path.dirname(__file__), "..", "database", "schema.sql")
    with open(schema_path) as f:
        sql = f.read()
    with conn.cursor() as cur:
        for statement in sql.split(";"):
            stmt = statement.strip()
            if stmt:
                try:
                    cur.execute(stmt)
                except Exception:
                    logger.warning("Schema statement skipped: %s", stmt[:120])
    conn.commit()


def db_cursor(conn):
    return conn.cursor(cursor_factory=RealDictCursor)