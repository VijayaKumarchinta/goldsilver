import requests
from flask import Blueprint, jsonify
from app.config import Config
from app.extensions import get_db
from app.scheduler import manager as scheduler_manager

health_bp = Blueprint("health", __name__)

@health_bp.route("", methods=["GET"])
def health():
    db_ok = True
    db_err = None
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        conn.close()
    except Exception as e:
        db_ok = False
        db_err = str(e)

    return jsonify({"status": "ok" if db_ok else "degraded",
                    "db": db_ok, "db_error": db_err}), 200 if db_ok else 503

@health_bp.route("/scheduler", methods=["GET"])
def scheduler_status():
    # Read the module attribute at request time: start_scheduler() assigns it
    # after this blueprint is imported, so a from-import would stay None.
    scheduler = scheduler_manager._scheduler
    if not scheduler:
        return jsonify({"running": False, "jobs": []}), 200
    jobs = [
        {"id": j.id, "next_run_time": str(j.next_run_time), "trigger": str(j.trigger)}
        for j in scheduler.get_jobs()
    ]
    return jsonify({"running": scheduler.running, "jobs": jobs}), 200


@health_bp.route("/telegram", methods=["GET"])
def telegram_status():
    """Validate the configured bot and chat without exposing secrets.

    Telegram returns "chat not found" both when the id is wrong and when the
    bot is not a member of the chat, so this separates token validity from
    chat reachability and reports the stored destinations.
    """
    token = Config.TELEGRAM_BOT_TOKEN
    chat_id = Config.TELEGRAM_CHAT_ID
    result = {
        "token_configured": bool(token),
        "chat_configured": bool(chat_id),
        "configured_chat_suffix": chat_id[-4:] if chat_id else None,
    }

    if token:
        try:
            me = requests.get(
                f"https://api.telegram.org/bot{token}/getMe", timeout=10
            ).json()
            result["bot_ok"] = bool(me.get("ok"))
            result["bot_username"] = (me.get("result") or {}).get("username")
            if not me.get("ok"):
                result["bot_error"] = me.get("description")
        except Exception as exc:
            result["bot_ok"] = False
            result["bot_error"] = type(exc).__name__

    if token and chat_id:
        try:
            body = requests.get(
                f"https://api.telegram.org/bot{token}/getChat",
                params={"chat_id": chat_id},
                timeout=10,
            ).json()
            result["chat_reachable"] = bool(body.get("ok"))
            if body.get("ok"):
                info = body.get("result") or {}
                result["chat_type"] = info.get("type")
                result["resolved_chat_suffix"] = str(info.get("id"))[-4:]
            else:
                result["chat_error"] = body.get("description")
        except Exception as exc:
            result["chat_reachable"] = False
            result["chat_error"] = type(exc).__name__

    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT label, enabled, RIGHT(identifier, 4) "
                "FROM goldbot.destinations WHERE channel = 'telegram' ORDER BY id"
            )
            result["destinations"] = [
                {"label": label, "enabled": enabled, "id_suffix": suffix}
                for label, enabled, suffix in cur.fetchall()
            ]
        finally:
            conn.close()
    except Exception as exc:
        result["destinations_error"] = type(exc).__name__

    result["deliverable"] = bool(result.get("bot_ok") and result.get("chat_reachable"))
    return jsonify(result), 200