# STATE — NSE Market Data Downloader

## Architecture
- **Backend**: FastAPI (Python) serving REST API + SSE real-time events.
- **Frontend**: Single-page HTML/CSS/JS with a Glassmorphism "Futuristic Minimalist" theme. Custom DatePicker logic integrated.
- **Data Source**: Kite Connect API (Zerodha) — Historical data (Minute to Daily).
- **Storage**: Parquet files, partitioned per-symbol per-year in `data/`. Extremely fast read/writes using PyArrow.
- **State & Recovery**: `download_state.json` tracks progress per stock/chunk for pause/resume and crash recovery.
- **Concurrency & Rate Limiting**: Asynchronous `fetcher_engine` leveraging a `TokenBucket` for optimal parallel execution while strictly respecting 3 requests/second rate limits.
- **Desktop Launcher**: `start_app.py` + `launcher_visuals.py` — CustomTkinter animated dark theme window with embedded terminal, server lifecycle management, DPI awareness, and browser auto-launch. Compiled into a standalone executable (`ArcherHarvest.exe`).

## Completed Features
- [x] Full backend architecture (FastAPI, auth, SSE, storage, API routes).
- [x] Full frontend dashboard (glassmorphism UI, stats, progress bar, real-time activity log).
- [x] Segment Filtering (Equity, Index, Future, Option, Commodity) and Exchange Filtering.
- [x] Native integration with Kite API's continuous data feature for stitched near-month derivative contracts.
- [x] Asynchronous multi-threaded worker engine (`fetcher_engine.py`) efficiently handling up to 20 concurrent tasks.
- [x] Smart TokenBucket rate-limiting gracefully hiding 429 errors from the UI unless fatal.
- [x] "Graceful Stop" mechanic that allows currently downloading tasks to write out Parquet files to prevent corruption.
- [x] Enhanced Activity Log with dedicated "Errors" tab featuring clipboard and file export support.
- [x] Continuous Futures data fetching support.
- [x] High-precision chunked ETA calculation algorithm for realistic wait times.
- [x] Retry logic with exponential backoff (5 retries, 1s→60s).
- [x] Pause/resume mechanics using `asyncio.Event`.
- [x] Crash recovery and smart sync (skips already downloaded date ranges).
- [x] Maximum speed concurrency with a custom Token Bucket rate limiter to eliminate worker starvation.
- [x] PyInstaller standalone compilation with DPI awareness, embedded web server, and transparent high-res taskbar icons.
- [x] Custom Glassmorphism calendar DatePicker.

## Pending
- [ ] Production testing of large-scale (5-10 year) continuous downloads.
- [ ] Add support for downloading specific Option/Futures symbols by exact trading symbol.
