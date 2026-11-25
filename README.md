# GoldSilver Dashboard

A Telegram-driven price dashboard for gold and silver (India). The backend
fetches live MCX gold/silver futures, USD/INR and COMEX spot quotes, stores
them in PostgreSQL, and pushes them to the dashboard over Socket.IO. Telegram
sends a 30-minute delivery of the same data to configured groups, and the
dashboard shows live charts plus delivery logs.

The service is a single Flask + Flask-SocketIO process. It serves the built
frontend SPA, exposes REST APIs, and runs one APScheduler job: the 30-minute
Telegram update. There is no browser-side polling for live prices.

---

## Stack

- **Backend:** Python 3.14, Flask, Flask-SocketIO, Flask-CORS, APScheduler,
  SQLAlchemy-less PostgreSQL access via `psycopg2`, `requests`.
- **Database:** PostgreSQL (`goldbot` schema) for snapshots, metal prices,
  FX rates, destinations and delivery logs.
- **Frontend:** Vue 3 (Composition API), Socket.IO client, ECharts, Vite.
- **Deployment:** Render (Python + `requirements.txt`, `gunicorn`).

---

## Requirements

- PostgreSQL (12+ recommended)
- `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` for Telegram delivery
- Frontend build output at `frontend/dist` (committed to the repo)

---

## Environment variables

| Variable | Required | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `TELEGRAM_BOT_TOKEN` | Yes | Bot token used to send updates |
| `TELEGRAM_CHAT_ID` | Yes | Destination chat id for delivery |
| `SECRET_KEY` | No | Flask secret key (default `dev`) |
| `TROY_OUNCE_IN_GRAMS` | No | Default `31.1035` |
| `FEED_STALE_SECONDS` | No | Default `300`; seconds before the feed is flagged stale |
| `MIN_USD_INR` / `MAX_USD_INR` | No | Legacy validation bounds |
| `MAX_PRICE_STALENESS_SECONDS` | No | Default `300` |
| `MAX_SINGLE_TICK_JUMP_PCT` | No | Default `15` |
| `FREEAPI_BASE` | No | Legacy FreeAPI endpoint |

---

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
export DATABASE_URL=postgresql://...
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_CHAT_ID=...
cd backend
python run.py
```

The app listens on `http://0.0.0.0:5000`. Request the dashboard at `/`, or
`/api/prices/latest`, `/api/prices/chart/7D`, `/api/logs`, `/api/health` etc.

---

## Run on Render

Render runs `python run.py` from the `backend/` directory. The `render.yaml`
build step is `pip install -r requirements.txt`; the `frontend/dist` static
directory is served directly by the backend's `/` route. Set the required
environment variables in the Render dashboard before deploying.

---

## Project layout

```text
backend/
  run.py                # Entry point: create_app + socketio.run
  app/
    __init__.py         # Flask factory, SocketIO, blueprints, connect handler
    config.py           # Settings loaded from environment
    extensions.py       # DB connection helper
    api/
      prices.py         # /latest, /chart/<range>, /delta/<metal>, /purity, /states, /schedule, /destinations, /health
      health.py         # /api/health
      logs.py           # /api/logs (delivery status)
      destinations.py   # /api/destinations
    services/
      market_data.py    # Live quote source, broadcast, feed_health()
      notification_dispatcher.py  # dispatch_pending(), create_sender()
      message_formatter.py        # MarkdownV2 Telegram message builder
      snapshot.py       # (kept as a marker)
      message_formatter.py        # (kept as a marker)
      rates.py          # Purity/state rate rows
      conversion.py     # (kept as a marker)
      fx_service.py     # (kept as a marker)
      local_rates.py    # (kept as a marker)
      validation.py     # (kept as a marker)
    repositories/
      prices.py         # save_snapshot(), get_latest()
      history.py        # get_chart_history()
      destinations.py   # list_enabled(), ensure_telegram_destination()
      notifications.py  # (kept as a marker)
      __init__.py
    scheduler/
      manager.py        # start_scheduler()/shutdown_scheduler()
      jobs.py           # scheduled_periodic_update(), clear_all(), scheduled_capture()
    messaging/
      telegram.py       # TelegramSender
      base.py           # Sender ABC
    sockets/
      events.py         # (kept as a marker)
      auth.py           # (kept as a marker)
    providers/
      metals_tradingview.py
    static/             # Built frontend assets
    templates/          # (none used; SPA is served from dist)
frontend/
  src/                  # Vue 3 source
  dist/                 # Built SPA (committed to the repo)
  index.html
  vite.config.js
  package.json
  render.yaml
  README.md
```

---

## Technology notes

- **Live prices**: `backend/app/services/market_data.py` calls
  `metals_tradingview.fetch_mcx()` and, when a valid quote arrives, calls
  `set_price_event(snapshot)` which broadcasts `price_update` over Socket.IO to
  every connected dashboard client. The frontend reads the stream; it does not
  poll.
- **30-minute delivery**: `backend/app/scheduler/manager.py` registers a single
  APScheduler job (`CronTrigger(minute="*/30", second=0, timezone="Asia/Kolkata")`)
  running `scheduled_periodic_update()` from `backend/app/scheduler/jobs.py`.
  That function ensures the notification schema, dispatches pending delivery
  jobs, and respects `FEED_STALE_SECONDS`, `TELEGRAM_BOT_TOKEN` and enabled
  destinations.
- **Chart data**: served from the database via `get_chart_history()` in
  `backend/app/repositories/history.py`. The frontend requests
  `/api/prices/chart/<range>` (1D / 7D / 30D).
- **Delivery logs**: `backend/app/api/logs.py` reads
  `get_notification_status()` and the last 50 rows from `notification_jobs`.

---

## Known limitations

- The live price quote comes from a single source (TradingView scanner). If the
  endpoint is unreachable, the dashboard falls back to the last saved snapshot
  and flags the feed stale after `FEED_STALE_SECONDS`.
- Telegram delivery is not guaranteed-delivery: each job is retried up to
  `MAX_ATTEMPTS` times with backoff, then marked `failed`.
- The frontend `dist/` is committed. The backend serves it; without a build the
  SPA shows a placeholder page.

---

## Files to review / improve

- `backend/app/services/market_data.py` — single live quote source; consider
  multiple providers and a stronger fallback.
- `backend/app/services/notification_dispatcher.py` — retry/backoff behaviour;
  consider per-destination status aggregation.
- `backend/app/services/message_formatter.py` — MarkdownV2 escaping is the
  reason Telegram renders correctly; keep it committed and validated.
- `backend/app/api/prices.py` — legacy `GET /latest` still exists; it is used
  by the dashboard for the initial snapshot but not for live updates.
- `backend/app/api/schedule.py` — empty; it used to serve the notification
  schedule and should be populated or removed once the UI no longer needs it.
- `backend/app/repositories/history.py` — chart series; verify the per-metal
  rounding and the `estimated`/`open_per_10g` handling matches the frontend
  range selections.
