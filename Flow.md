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

## 2. Scheduler: register the recurring jobs

`backend/app/scheduler/manager.py` (`start_scheduler`):

1. Creates one `BackgroundScheduler` with `timezone="UTC"`.
2. Registers two jobs:
   - `id="chart_snapshot"`
   - `CronTrigger(minute="*/5", second=0, timezone="Asia/Kolkata")`
   - `scheduled_capture` with `"chart_update"` as the argument; it saves a
     history snapshot every 5 minutes and queues no notifications.
   - `id="periodic_update"`
   - `CronTrigger(minute="*/30", second=0, timezone="Asia/Kolkata")`
   - `scheduled_periodic_update` as the callback
3. Starts the scheduler.
4. Logs each registered job.

Telegram delivery stays on the 30-minute CronTrigger; the 5-minute job only
records chart history. The browser requests the chart on the same 5-minute
cadence and does not poll for live prices.

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

`frontend/src/composables/useSocket.js` opens one shared Socket.IO connection
and stores each `price_update` in a `latest` ref.
`frontend/src/composables/useApi.js` consumes that ref:

1. `useApi` watches `latest` and updates the quote cards, market-open flag and
   feed status.
2. It loads the REST snapshot, chart, logs and purity on mount, and reloads
   them when the socket reconnects.
3. The chart loads history with `fetch('<apiBase>/prices/chart/<range>')`
   because chart series come from the database, not the live broadcast, and is
   refetched every 5 minutes to match the `chart_snapshot` job. The same tick
   refetches `/prices/latest` so the feed-stale banner stays current.

There is no polling of `/api/prices/latest` for live prices.

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
[Flask-SocketIO broadcast: price_update] --> [Browser dashboard watches useSocket().latest]
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

## 10. Connection, sockets, data passing, and storage

### 10.1 Frontend ↔ backend connection (WebSocket)

`frontend/src/composables/useSocket.js` opens the Socket.IO connection.
`frontend/src/App.vue` (and `useApi`) consumes it.

`frontend/src/composables/useSocket.js`:

| What | Detail |
| --- | --- |
| `apiBase` / `socketOrigin` | origin the client connects to (`VITE_API_BASE`, then the current origin) |
| `io(...)` | Socket.IO client; `transports: ['websocket', 'polling']`, `reconnection: true`, `reconnectionAttempts: 10` |
| listeners | `connect`, `disconnect`, `price_update`, `connect_error`, registered once at module load |
| return value | `{ socket, latest, connected, error }` |

`frontend/src/composables/useApi.js`:

| What | Detail |
| --- | --- |
| `useSocket()` | reads the shared `latest` / `connected` refs |
| `watch(connected)` | reloads data when the socket comes up |
| `normalizeSnapshot()` | maps both the REST `gold`/`silver` and socket `metals.XAU`/`XAG` payloads onto one quote shape |
| `refreshChart(range)` | fetches chart history and assigns it to `chart` |
| `loadAll()` | loads `/prices/latest`, chart, `/logs`, `/prices/purity` |

Key socket protocol:

- The server broadcasts `socketio.emit("price_update", snapshot)`; the client receives it as the
  `price_update` Socket.IO event, stored in `latest`.
- The chart is **not** part of the broadcast. It is fetched over plain HTTP:
  `fetch('<apiBase>/prices/chart/<range>')`, because chart series come from PostgreSQL, not the live broadcast.

### 10.2 Where the data is stored

| Store | Used for |
| --- | --- |
| PostgreSQL `goldbot` schema | `price_snapshots` (each captured price set + `live` flag), `metal_prices` (per-metal rows for a snapshot), `fx_rates`, `notification_jobs` (30-minute delivery schedule + retry), `destinations` (enabled Telegram channels) |
| `backend/app/config.py` (`Config.DATABASE_URL`) and `backend/app/extensions.py:get_db()` | Connection string + `SET search_path TO goldbot, public` (`extensions.py:6`) |
| TradingView scanner (HTTP) | Live gold/silver/USD-INR/COMEX quotes fetched by `metals_tradingview.fetch_mcx()` (`providers/metals_tradingview.py`) |
| Telegram API | Delivery target; `TelegramSender` POSTs to `https://api.telegram.org/bot<TOKEN>/sendMessage` (`messaging/telegram.py`) |

Storage flow:

1. `market_data.get_latest_snapshot()` — live path builds a snapshot from
   `metals_tradingview.fetch_mcx()` results, marks `XAU`/`XAG` `live: true`,
   calls `set_price_event()` (`market_data.py:132`), and *optionally* writes it to PostgreSQL
   (`repositories/prices.save_snapshot`).
2. The same snapshot object is what `set_price_event()` broadcasts, so clients and the scheduler
   read exactly one source of truth.
3. `scheduled_periodic_update()` (every 30 minutes, `manager.py:13-16`) calls
   `ensure_hourly_notification_schema()`, then `create_jobs()` inserts one
   `notification_jobs` row per enabled destination (`repositories/notifications.py`), then
   `dispatch_pending()` sends it.
4. `dispatch_pending()` SELECTs the pending/failed rows with `SKIP LOCKED` (`notification_dispatcher.py:203-207`),
   loads the snapshot, formats `format_price_message()` (`message_formatter.py`),
   and `sender.send()`es it through `TelegramSender` (`telegram.py:8`).

### 10.3 How the data passes from backend → frontend (live price)

```text
market_data._live_quote()                       <- TradingView fetch_mcx
        |
        v
market_data.set_price_event(snapshot)           <- stores _price_event (dict)
        |
        v
socketio.emit("price_update", snapshot)         <- Flask-SocketIO broadcast to all clients
        |
        v
useSocket.js -> socket.on("price_update", ...) -> latest.value = snapshot
        |
        v
useApi.js -> watch(connected) + watch(latest)
        |
        v
App.vue updates the quote cards / market-open flag / feed status
```

Notes:

- The server does **not** wait for a client acknowledgment (`socketio.emit` is fire-and-forget;
  `useSocket.js` owns reconnection/retry).
- The client only *listens*; it never POSTs live prices back to the server.

### 10.4 How the data passes from frontend → backend (HTTP, read-only queries)

| Client call | Endpoint | Purpose |
| --- | --- | --- |
| `loadChart()` (`useApi.js:38`) | `GET /api/prices/chart/<range>` | ECharts series from PostgreSQL `price_snapshots`/`metal_prices` |
| `loadLogs()` (`useApi.js:64`) | `GET /api/logs` | `notification_jobs` statuses for the delivery panel |
| `loadPurity()` (`useApi.js:70`) | `GET /api/prices/purity` | Purity / rates rows |
| On `connect` (`useSocket.js:32`) | server `on_connect` → `price_update` broadcast | New browser lands on last known snapshot |

### 10.5 Socket.IO server config

`backend/app/__init__.py`:

| Lines | Config |
| --- | --- |
| 8,14-16 | `socketio = SocketIO()` (module-level instance) |
| 19-21 | `socketio.init_app(app, cors_allowed_origins="*", ping_timeout=10, ping_interval=15)` |
| 23-25 | blueprints registered at `/api/health`, `/api/prices`, `/api/logs` |
| 43-45 | serves `frontend/dist` at `/`, and aborts (404) for `/api/*` and `/socket.io/*` |

`backend/app/scheduler/manager.py`:

| Lines | Config |
| --- | --- |
| `BackgroundScheduler(timezone="UTC")` | scheduler instance |
| `id="chart_snapshot"` | `CronTrigger(minute="*/5", second=0, timezone="Asia/Kolkata")` → `scheduled_capture("chart_update")` |
| `id="periodic_update"` | `CronTrigger(minute="*/30", second=0, timezone="Asia/Kolkata")` → `scheduled_periodic_update` |
| `start()` | logs each registered job |

### 10.6 Startup order (what runs, in what sequence)

```text
1. python run.py
   |
   v
2. create_app(start_sched=True)
   +-- Config (env)
   +-- Flask-SocketIO init (cors=*)
   +-- /api/health, /api/prices, /api/logs blueprints
   +-- frontend/dist mounted at /
   +-- ensure_telegram_destination() (idempotent)
   +-- @socketio.on("connect") -> sends current snapshot to new client
   +-- start_scheduler()
   |     +-- BackgroundScheduler
   |     +-- CronTrigger */5 Asia/Kolkata -> chart history snapshot
   |     +-- CronTrigger */30 Asia/Kolkata -> Telegram delivery
   |     +-- start()
   |     +-- scheduled_periodic_update()  <- one-time first delivery at startup
   |
   v
3. Browser connects -> on_connect -> price_update (last state)
   |
   v
4. Live quote arrives -> set_price_event -> price_update broadcast
   +-- browser watch(latest) re-renders the dashboard
   |
   v
5. Every 5 minutes -> scheduled_capture("chart_update") -> snapshot saved for history
   |
   v
6. Every 30 minutes -> scheduled_periodic_update -> dispatch_pending -> Telegram
   +-- /api/logs shows sent/failed + retry status
```
