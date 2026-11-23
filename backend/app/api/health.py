from flask import Blueprint, jsonify
from app.extensions import get_db

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
    from app.scheduler.manager import _scheduler
    if not _scheduler:
        return jsonify({"running": False, "jobs": []}), 200
    jobs = [
        {"id": j.id, "next_run_time": str(j.next_run_time), "trigger": str(j.trigger)}
        for j in _scheduler.get_jobs()
    ]
    return jsonify({"running": _scheduler.running, "jobs": jobs}), 200