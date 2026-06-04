# STATE — NSE Market Data Downloader

## Architecture
- **Backend**: FastAPI (Python) serving REST API + SSE real-time events
- **Frontend**: Single-page HTML/CSS/JS with glassmorphism theme
- **Data Source**: Kite Connect API (Zerodha) — 1-min OHLCV candles
- **Storage**: Parquet files, partitioned per-symbol per-year in `data/`
- **State**: `download_state.json` for crash recovery

## Completed
- [x] Full backend: config, auth (OAuth), instrument loader, fetcher engine, state manager, storage handler, holiday calendar, API routes
- [x] Full frontend: dashboard with stats, controls (start/pause/resume/stop/retry), progress bar, stock grid, activity log
- [x] Desktop launcher: start_app.py + launcher_visuals.py — animated dark theme window with embedded terminal, server lifecycle, browser auto-launch
- [x] SSE real-time event stream
- [x] Retry logic with exponential backoff (5 retries, 1s→60s)
- [x] Pause/resume via asyncio.Event
- [x] Crash recovery via JSON state persistence
- [x] Virtual environment with all dependencies installed
- [x] Server verified running at http://127.0.0.1:8000

## Pending
- [ ] User needs to authenticate with Kite Connect to begin actual downloads
- [ ] First real data download run
- [ ] Kite redirect URL in developer dashboard must be set to `http://127.0.0.1:8000/api/auth/callback`
