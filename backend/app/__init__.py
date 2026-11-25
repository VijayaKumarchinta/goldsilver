import logging
from pathlib import Path
from flask import Flask, Response, abort, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO
from app.config import Config
from app.api.prices import prices_bp
from app.api.health import health_bp
from app.api.logs import logs_bp
from app.api.prices import prices_bp
from app.repositories.destinations import ensure_telegram_destination
from app.scheduler.manager import start_scheduler
from app.services.market_data import _json_safe, get_latest_snapshot, _register_live_price_events

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logging.getLogger("apscheduler").setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.WARNING)

socketio = SocketIO()

def create_app(start_sched: bool = True):
    app = Flask(__name__)
    app.config.from_object(Config)
    CORS(app) 

    socketio.init_app(
        app,
        cors_allowed_origins="*",
        ping_timeout=10,
        ping_interval=15,
    )

    app.register_blueprint(health_bp, url_prefix="/api/health")
    app.register_blueprint(prices_bp, url_prefix="/api/prices")
    app.register_blueprint(logs_bp, url_prefix="/api/logs")

    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if dist.is_dir():
        index_html = dist / "index.html"
        if index_html.is_file():
            @app.route("/", defaults={"path": ""})
            @app.route("/<path:path>")
            def dashboard(path):
                if path.startswith(("api/", "socket.io")):
                    abort(404)
                if path and (dist / path).is_file():
                    return send_from_directory(dist, path)
                return send_from_directory(dist, "index.html")
        else:
            @app.route("/")
            def frontend_missing():
                return (
                    "<!doctype html>\r\n"
                    "<html lang=\"en\"><head><meta charset=\"utf-8\">\r\n"
                    "<title>GoldSilver Dashboard</title></head><body>\r\n"
                    "<h1>GoldSilver Dashboard</h1>\r\n"
                    "<p>The frontend build is not present yet.</p>\r\n"
                    "<p>Once <code>frontend/dist/index.html</code> exists, this page will serve the dashboard.</p>\r\n"
                    "</body></html>",
                    200,
                    {"Content-Type": "text/html; charset=utf-8"},
                )

        @app.route("/_debug/dist")
        def debug_dist():
            return Response(
                f"dist={dist}\n"
                f"is_dir={dist.is_dir()}\n"
                f"index_html={dist / 'index.html'}\n"
                f"index_exists={ (dist / 'index.html').is_file() }\n",
                mimetype="text/plain",
            )

    ensure_telegram_destination()

    def _initial_price(snap):
        try:
            socketio.emit("price_update", _json_safe(snap), namespace="/")
        except Exception:
            logging.exception("Failed to send initial price on connect")

    @socketio.on("connect")
    def on_connect(socket_id, auth=None):
        """Flask-SocketIO calls the connect handler with (socket_id, auth); accept both."""
        try:
            snap = get_latest_snapshot()
            _initial_price(snap)
        except Exception:
            logging.exception("Failed to send initial price on connect")
    _register_live_price_events(socketio)

    if start_sched:
        start_scheduler()

    return app