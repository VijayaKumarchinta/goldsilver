# Backend

Backend code for the GoldSilver Bot dashboard.

This directory is the Flask + Flask-SocketIO process. It serves the built
frontend SPA at `/`, exposes the `/api/prices`, `/api/health`, and
`/api/logs` endpoints, and runs one APScheduler job: the 30-minute Telegram
delivery tick.

## Run locally

```bash
cd backend
python run.py
```

The app listens on `http://0.0.0.0:5000`. Request the dashboard at `/`, or
`/api/prices/latest`, `/api/prices/chart/7D`, `/api/logs`, `/api/health` etc.
