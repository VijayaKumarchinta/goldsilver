import logging
from flask import Flask
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

    # Initialize DB tables on first connection, then ensure the Telegram destination exists
    from app.repositories.destinations import ensure_telegram_destination
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