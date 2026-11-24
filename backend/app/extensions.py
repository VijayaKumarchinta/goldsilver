import psycopg2
from psycopg2.extras import RealDictCursor
from app.config import Config


def get_db():
    conn = psycopg2.connect(Config.DATABASE_URL)
    conn.autocommit = False
    with conn.cursor() as cur:
        cur.execute("SET search_path TO goldbot, public")
    return conn


def db_cursor(conn):
    return conn.cursor(cursor_factory=RealDictCursor)