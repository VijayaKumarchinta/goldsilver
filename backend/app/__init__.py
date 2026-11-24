import logging
from pathlib import Path
from flask import Flask, abort, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO
from app.config import Config
from app.api.prices import prices_bp
from app.api.health import health_bp
from app.api.logs import logs_bp
from app.scheduler.manager import start_scheduler
from app.repositories.destinations import ensure_telegram_destination

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

# Quiet noisy third-party loggers: APScheduler per-job logs + werkzeug HTTP request logs
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.WARNING)

socketio = SocketIO()


def create_app(start_sched: bool = True):
    app = Flask(__name__)
    app.config.from_object(Config)
    CORS(app)  # Allow Vue to connect

    socketio.init_app(
        app,
        cors_allowed_origins="*",
        ping_timeout=10,
        ping_interval=15,
    )

    app.register_blueprint(health_bp, url_prefix="/api/health")
    app.register_blueprint(prices_bp, url_prefix="/api/prices")
    app.register_blueprint(logs_bp, url_prefix="/api/logs")

    # Serve the built dashboard (frontend/dist) from the same origin when it exists.
    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if dist.is_dir():
        @app.route("/", defaults={"path": ""})
        @app.route("/<path:path>")
        def dashboard(path):
            if path.startswith(("api/", "socket.io")):
                abort(404)
            if path and (dist / path).is_file():
                return send_from_directory(dist, path)
            return send_from_directory(dist, "index.html")

    # Ensure the Telegram destination exists from TELEGRAM_CHAT_ID
    ensure_telegram_destination()

    # Real-time price push
    from app.services.market_data import get_latest_snapshot
    @socketio.on("connect")
    def on_connect():
        try:
            snap = get_latest_snapshot()
            socketio.emit("price_update", snap)
        except Exception as e:
            logging.exception("Failed to send initial price on connect: %s", e)

    if start_sched:
        start_scheduler()

    return app