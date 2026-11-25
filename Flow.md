# Flow — how the project executes

This document describes what happens from the moment the process starts to the
moment a dashboard client sees a fresh gold/silver price, and on every 30
minutes when Telegram receives a delivery.

---

## 1. Start the process

`backend/run.py` calls `create_app(start_sched=True)`.

`backend/app/__init__.py` (`create_app`):

1. Creates a Flask app and loads `Config` from environment variables.
2. Initializes `Flask-SocketIO` with `cors_allowed_origins="*"`.
3. Registers the blueprints:
   - `/api/health`
   - `/api/prices`
   - `/api/logs`
4. Mounts the built frontend (`frontend/dist`) at `/`. Requests to `/api/*`
   and `/socket.io/*` are not intercepted.
5. Registers the Socket.IO `connect` handler: on every new browser client
   connection it fetches the latest snapshot from PostgreSQL and emits
   `price_update` so the new client lands on the last known state.
6. If `start_sched=True` (the default), calls `start_scheduler()`.

---

## 2. Scheduler: register the single recurring job

`backend/app/scheduler/manager.py` (`start_scheduler`):

1. Creates one `BackgroundScheduler` with `timezone="UTC"`.
2. Registers exactly one job:
   - `id="periodic_update"`
   - `CronTrigger(minute="*/30", second=0, timezone="Asia/Kolkata")`
   - `scheduled_periodic_update` as the callback
3. Starts the scheduler.
4. Logs `Registered job: periodic_update -> cron[minute='*/30', second='0']`.

There is no 5-minute REST polling job and no browser-side `setInterval` for
live prices. The only recurring process is this 30-minute CronTrigger.

---

## 3. Every 30 minutes — the delivery tick

`backend/app/scheduler/jobs.py` (`scheduled_periodic_update`):

1. Calls `ensure_hourly_notification_schema()` so the
   `notification_jobs` table has `scheduled_for` / `next_attempt_at` columns
   and the unique schedule slot index exists.
2. Calls `dispatch_pending(sender=create_sender())`:
   - Opens a DB transaction.
   - SELECTs `notification_jobs` rows with `status IN ('pending','sending','failed')`
     and `attempts < 3` and `next_attempt_at <= NOW()`, using `SKIP LOCKED`.
   - For each row, it loads the snapshot, builds the message with
     `format_price_message()`, and sends it through `sender.send()`.
   - On success, marks the job `sent`. On exhaustion, `failed`. Otherwise it
     reschedules with backoff `[30, 120, 480]` seconds and marks `pending`.
   - Commits only when the whole batch is processed.
3. Reads `get_notification_status()` to learn the last send attempt.
4. Returns early with `{"due": False, "reason": "notification_pending"}` if a
   delivery for this period is already in progress.
5. Returns early with `missing_bot_token` or `no_destinations` if Telegram is
   not configured or no destination is enabled.
6. Returns early with `interval_already_processed` if a slot for this timestamp
   already exists.
7. Checks whether the live price feed is usable:
   - `get_latest_snapshot()` tries `market_data._live_quote()` first. If that
     returns a valid quote (gold, silver, USD/INR, and the ratio guard passes),
     the snapshot is saved with `event_type="periodic_update"`, `create_jobs()`
     inserts one row per enabled destination, and `dispatch_pending()` sends the
     message.
   - If the live feed is not usable, the function returns
     `{"due": False, "reason": "live_market_data_unavailable"}` and nothing is
     sent. No fake price is sent.
8. Returns `{"due": True, ...}` so the scheduler can log the outcome.

---

## 4. Startup cadence: first delivery

On boot, after the scheduler starts, `start_scheduler()` calls
`scheduled_periodic_update()` directly:

1. The periodic update runs once at startup, not repeatedly.
2. If Telegram and a valid snapshot are available, it posts the first 30-minute
   delivery immediately and sets the `notification_jobs` schedule slots so the
   next run cannot reprocess this slot.
3. If the feed is stale or Telegram is misconfigured, the startup call logs the
   failure and returns gracefully.

---

## 5. Live price path (the dashboard, not the scheduler)

`backend/app/services/market_data.py`:

1. `_live_quote()` calls `metals_tradingview.fetch_mcx()`, which POSTs to the
   TradingView scanner endpoint and parses gold, silver, USD/INR and COMEX spot
   into a quote.
2. The ratio guard (`0.95` to `1.6`) rejects a quote if gold or silver is
   implausible; the feed then falls back to the last saved snapshot.
3. `get_latest_snapshot()` either:
   - returns a live snapshot with `metals.XAU.live = true` and
     `metals.XAG.live = true`, calling `set_price_event()`; or
   - falls back to the latest PostgreSQL snapshot with `live: false`.
4. `set_price_event()` emits `socketio.emit("price_update", snapshot)` to all
   connected Socket.IO clients. This is a fire-and-forget broadcast; the
   client owns reconnect and retry.

---

## 6. Browser receives the live price

`frontend/src/composables/useSocket.js` connects to the Socket.IO server.
`frontend/src/composables/useApi.js` consumes `socket.latest`:

1. On `connect`, it emits `reconnect()` (an HTTP fallback refresh).
2. `watch(socket.latest)` updates the dashboard quote cards, market-open flag
   and feed status.
3. The chart still loads history with `fetch('/api/prices/chart/<range>')`
   because chart series come from the database, not the live broadcast.

The old 5-second REST polling of `/api/prices/latest` was removed at
`frontend/src/composables/useApi.js`.

---

## 7. Telegram delivery path (the scheduler side)

1. `scheduled_periodic_update()` inserts one `notification_jobs` row per enabled
   destination, each with `status='pending'`.
2. `dispatch_pending()` processes those rows in a single DB transaction.
3. `TelegramSender.send()` POSTs to
   `https://api.telegram.org/bot<TOKEN>/sendMessage` with `parse_mode: MarkdownV2`.
4. The API returns `{ok: true, ...}` → job becomes `sent`.
5. The API rejects or the network fails → the job is retried up to 3 times with
   backoff `[30, 120, 480]` seconds, then marked `failed`.
6. `backend/app/api/logs.py` reads those statuses and exposes them at
   `/api/logs` for the delivery panel.

---

## 8. End-to-end summary

```text
[TradingView scanner] -> [metals_tradingview.fetch_mcx]
        |
        v
[market_data._live_quote] -> [market_data.set_price_event]
        |
        v
[Flask-SocketIO broadcast: price_update] --> [Browser dashboard uses socket.latest]
        |
        v
[scheduler manager: CronTrigger */30] -> [scheduled_periodic_update]
        |
        v
[ensure_hourly_notification_schema] -> [create_jobs: insert notification_jobs rows]
        |
        v
[dispatch_pending: sender.send per destination]
        |
        v
[TelegramSender.send] -> [Telegram group receives MarkdownV2 message]
        |
        v
[/api/logs shows sent/failed with retry status]
```

---

## 9. Startup sequence (full order)

```text
1. python run.py
   |
   v
2. create_app(start_sched=True)
   |
   +-- load Config
   +-- init Flask-SocketIO
   +-- register /api/health, /api/prices, /api/logs
   +-- mount frontend/dist at /
   +-- ensure_telegram_destination() (idempotent)
   +-- register Socket.IO connect handler
   +-- start_scheduler()
   |     |
   |     +-- BackgroundScheduler(timezone="UTC")
   |     +-- add_job(periodic_update, CronTrigger */30 Asia/Kolkata)
   |     +-- start()
   |     +-- scheduled_periodic_update()  <- first delivery (one-time)
   |
   v
3. Browser connects -> on_connect -> price_update broadcast (last known state)
   |
   v
4. Live quote arrives (every <cache> seconds from TradingView)
   +-- set_price_event -> socketio.emit("price_update", snapshot)
   +-- browser watch(socket.latest) updates the UI
   |
   v
5. Every 30 minutes: scheduled_periodic_update()
   +-- ensure schema
   +-- dispatch_pending
   +-- send to Telegram groups
   +-- log status to /api/logs
```

---

## 10. Responsibilities of each source file

| File | Responsibility |
| --- | --- |
| `backend/run.py` | Entry point; `create_app` + `socketio.run` |
| `backend/app/__init__.py` | Flask factory, SocketIO, blueprints, connect handler |
| `backend/app/config.py` | Environment-driven configuration |
| `backend/app/extensions.py` | `get_db()` connection helper |
| `backend/app/services/market_data.py` | Live quote fetch, broadcast, feed health |
| `backend/app/services/market_data.py` | `_get_daily_open` (legacy proxy, not used by the delivery path) |
| `backend/app/providers/metals_tradingview.py` | TradingView scanner HTTP client and parse |
| `backend/app/services/notification_dispatcher.py` | `dispatch_pending`, `create_sender`, schema helpers |
| `backend/app/services/message_formatter.py` | MarkdownV2 Telegram message text |
| `backend/app/messaging/telegram.py` | `TelegramSender` HTTP send |
| `backend/app/services/snapshot.py` | (empty marker) |
| `backend/app/services/rates.py` | Purity and state rate rows |
| `backend/app/services/validation.py` | (legacy validation, not on the delivery path) |
| `backend/app/services/conversion.py` | (legacy, not on the delivery path) |
| `backend/app/services/fx_service.py` | (legacy FX, not on the delivery path) |
| `backend/app/services/local_rates.py` | (legacy local rates, not on the delivery path) |
| `backend/app/repositories/prices.py` | `save_snapshot`, `get_latest` |
| `backend/app/repositories/history.py` | `get_chart_history` (chart series) |
| `backend/app/repositories/destinations.py` | `list_enabled`, `ensure_telegram_destination` |
| `backend/app/repositories/notifications.py` | (empty marker) |
| `backend/app/repositories/__init__.py` | Package marker |
| `backend/app/scheduler/manager.py` | APScheduler setup and the single 30-minute job |
| `backend/app/scheduler/jobs.py` | `scheduled_periodic_update`, `scheduled_capture`, `clear_all` |
| `backend/app/api/prices.py` | `/latest`, `/chart/<range>`, `/delta/<metal>`, `/purity`, `/states`, `/schedule`, `/destinations`, `/health` |
| `backend/app/api/health.py` | `/api/health` |
| `backend/app/api/logs.py` | `/api/logs` delivery status |
| `backend/app/api/destinations.py` | (empty marker) |
| `backend/app/api/schedule.py` | (empty marker) |
| `backend/app/templates/` | (not used) |
| `frontend/src/` | Vue 3 + Socket.IO + ECharts SPA |
| `frontend/dist/` | Built SPA, served by the backend |
