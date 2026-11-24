# Gold and Silver Price Bot

## Where the prices come from
Prices are **MCX gold and silver futures** (nearest contract; gold per 10 g, silver per kg shown per 10 g), read from
MCX's public market-watch page. International spot (xaus.com) and USD/INR are shown only as a reference.
The old version converted international spot to rupees, which left out India's 15% import duty (since 13 May 2026)
and was 14-20% below MCX. If MCX cannot be reached the dashboard shows a value marked "Estimate"; nothing is saved
or sent to Telegram in that case.

Check the MCX connection from the machine that runs the bot:

    cd backend && python -m app.providers.metals_mcx

MCX sits behind a bot filter and often blocks cloud/datacentre IP addresses, so this may work on a home PC and
fail on Render or other hosts. This reads a public website; it is not a licensed MCX data feed.

## Running on a server (Render and similar)
- Build: `pip install -r backend/requirements.txt && cd frontend && npm ci && npm run build`
- Start: `cd backend && gunicorn -w 1 --threads 8 -b 0.0.0.0:$PORT run:app` (one worker only: it runs the scheduler)
- Flask serves the built dashboard from `frontend/dist`, so no separate frontend host is needed.
- Free web services sleep when idle, which stops the in-process scheduler and the Telegram posts. Use an always-on plan.

## Market data

The dashboard refreshes its backend data every five seconds. Gold, silver, and
USD/INR are read together from the Xaus spot endpoint; the five-second refresh
does not guarantee that the provider publishes a new quote every five seconds.
Values are global spot references, not local retail quotes, so local taxes,
premiums, and jeweller charges can differ.

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