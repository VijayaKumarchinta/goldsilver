# Gold and Silver Price Bot

## Where the prices come from
Prices are **MCX gold and silver futures** (front-month continuous contract; gold per 10 g, silver per kg shown
per 10 g), read from TradingView's public scanner (`MCX:GOLD1!`, `MCX:SILVER1!`). The same request also returns
COMEX spot (`COMEX:GC1!`, `COMEX:SI1!`) and USD/INR (`FX_IDC:USDINR`), which the dashboard shows for reference and
which the backend uses to sanity-check the futures price. There is a single market-data provider.

Check the connection from the machine that runs the bot:

    cd backend && python -m app.providers.metals_tradingview

Why not mcxindia.com directly: MCX answers HTTP 403 to cloud/datacentre IP addresses, including Render. The
TradingView scanner serves the same MCX contract from an ordinary HTTPS call. It is a public, undocumented
endpoint with no SLA, not a licensed MCX data feed; if it is unreachable the dashboard falls back to the last
saved reading and Telegram updates pause until live prices return.

## Running on a server (Render and similar)
- Build from the repository root: `pip install -r backend/requirements.txt && cd frontend && npm ci && npm run build`
- Start: `cd backend && gunicorn -w 1 --threads 8 -b 0.0.0.0:$PORT run:app` (one worker only: it runs the scheduler)
- The Render backend build installs Python dependencies and builds `frontend/dist` before starting Flask.
- Flask serves the built dashboard from `frontend/dist`, so no separate frontend host is needed.
- Free web services sleep when idle, which stops the in-process scheduler and the Telegram posts. Use an always-on plan.

## Market data

The dashboard refreshes its backend data every five seconds. Gold, silver,
USD/INR, and the COMEX spot reference are read together from one scanner request
and cached for 15 seconds, so the five-second refresh does not hit the provider
five times. A failed fetch backs off for 60 seconds. Values are exchange futures,
not local retail quotes, so GST, making charges, and jeweller premiums differ.

## Telegram updates on Windows

Telegram updates run as a Windows Scheduled Task and do not require the Flask
backend or Vue frontend to be running. Install the backend requirements and
configure `DATABASE_URL`, `TELEGRAM_BOT_TOKEN`, and at least one enabled
Telegram destination (via `TELEGRAM_CHAT_ID` or the database) in the root `.env`
file.

From PowerShell in this project folder, register the task once:

```powershell
.\install_hourly_task.ps1
```

If you use a virtual environment, pass its Python executable:

```powershell
.\install_hourly_task.ps1 -PythonPath ".\backend\.venv\Scripts\python.exe"
```

The task checks every five minutes and sends when a 30-minute update is due.
On backend startup, the saved send time is checked; an update is sent only if
the 30-minute interval has elapsed. The standalone task keeps updates running
without Flask or Vue. After downtime, the system sends one catch-up update
rather than replaying every missed interval. Historical data contains only
snapshots that were actually captured; a quote from an hour when the computer
was off cannot be reconstructed.

The task runs under your Windows account, so the computer must be on and you
must be signed in. Windows can start a missed run when it becomes available
again. PostgreSQL must be reachable, and the machine needs internet access for
the price provider and Telegram.