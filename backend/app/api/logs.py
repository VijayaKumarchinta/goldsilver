import re
from flask import Blueprint, jsonify
from psycopg2.extras import RealDictCursor
from app.config import Config
from app.extensions import get_db
from app.services.notification_dispatcher import get_notification_status

logs_bp = Blueprint("logs", __name__)


def _iso(value):
    return value.isoformat() if value else None


def _safe_error(value):
    if not value:
        return None
    message = str(value)
    if Config.TELEGRAM_BOT_TOKEN:
        message = message.replace(Config.TELEGRAM_BOT_TOKEN, "[redacted]")
    message = re.sub(r"https?://api\.telegram\.org/bot[^\s/]+", "Telegram API", message)
    return message[:240]


@logs_bp.route("", methods=["GET"])
def list_logs():
    delivery = get_notification_status()
    delivery = {key: _iso(value) if key.endswith("_at") else value for key, value in delivery.items()}
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            SELECT j.id, j.event_type, j.status, j.attempts, j.last_error,
                   j.created_at, j.updated_at, j.scheduled_for,
                   d.channel, d.identifier, d.label
            FROM notification_jobs j
            JOIN destinations d ON d.id = j.destination_id
            ORDER BY j.id DESC
            LIMIT 50
            """
        )
        rows = cur.fetchall()

        if not rows:
            return jsonify({"logs": [], "source": "db", **delivery}), 200

        logs = []
        for r in rows:
            note = ""
            if r["status"] == "failed" and r["attempts"] >= 3:
                note = f"Delivery failed after {r['attempts']} attempts"
            elif r["attempts"] > 1:
                note = f"{r['attempts'] - 1} retry"
            logs.append({
                "id": r["id"],
                "event_type": r["event_type"],
                "destination": r["label"] or r["identifier"],
                "platform": r["channel"],
                "status": r["status"],
                "attempts": r["attempts"],
                "created_at": _iso(r["created_at"]),
                "updated_at": _iso(r["updated_at"]),
                "scheduled_for": _iso(r["scheduled_for"]),
                "sent_at": _iso(r["updated_at"]) if r["status"] == "sent" else None,
                "note": note,
                "last_error": _safe_error(r["last_error"]),
            })
        return jsonify({"logs": logs, "source": "db", **delivery}), 200
    finally:
        conn.close()
