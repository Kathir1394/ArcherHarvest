# Archer Harvest — Market Data Downloader

Archer Harvest is an advanced, high-performance historical market data downloader built for the NSE (National Stock Exchange of India). It interfaces with the Kite Connect API (Zerodha) to bulk-download historical OHLCV candles (from minute to daily timeframes) for equities, indices, futures, options, and commodities. 

It is designed with maximum concurrency, robust error recovery, and an ultra-modern aesthetic UI.

## 🎯 Key Features

1.  **High-Performance Fetching Engine**
    *   **Token Bucket Rate Limiting**: Ensures strict compliance with Kite Connect's rate limits (3 requests per second) while allowing maximum worker concurrency. 
    *   **High Concurrency**: Defaults to 20 concurrent workers, completely saturating the allowed API bandwidth for blazing-fast downloads.
    *   **Smart Sync (Delta Downloads)**: Automatically detects previously downloaded date ranges for a symbol and skips them, allowing rapid incremental updates of databases without re-downloading years of data.
    *   **Chunked Downloads**: Breaks down massive multi-year data requests into optimal chunks based on the requested timeframe (e.g., 60 days per chunk for 1-minute data) to prevent API timeouts.

2.  **Resilience & State Management**
    *   **State Persistence**: Writes download progress continuously to a `download_state.json` file. If the app crashes or is closed abruptly, it instantly resumes exactly where it left off.
    *   **Exponential Backoff Retries**: Automatically retries failed chunks up to 5 times, starting with a 1-second delay and backing off up to 60 seconds.
    *   **Pause / Resume**: Ability to halt network activity instantly and resume without losing partial progress.

3.  **Data Storage**
    *   **Apache Parquet Format**: Stores data in highly compressed, columnar Parquet format using `PyArrow`.
    *   **Automatic Partitioning**: Data is automatically partitioned by Symbol and Year (`data/NSE_RELIANCE/year=2023/data.parquet`), ensuring lightning-fast localized reads for backtesting engines.

4.  **Modern UI / UX**
    *   **Glassmorphism Dashboard**: A futuristic, single-page web dashboard with frosted glass effects, neon accents, and smooth micro-animations.
    *   **Real-time SSE Tracking**: The backend streams live progress, logs, and stock status directly to the frontend via Server-Sent Events (SSE).
    *   **Custom Date Picker**: Replaces native browser elements with a fully themed, animated Glassmorphism calendar component.
    *   **Accurate ETA Engine**: Calculates estimated time remaining based on active *data chunks* processed rather than entire stocks, ensuring a highly stable and realistic ETA.

5.  **Desktop Launcher (Standalone Executable)**
    *   **CustomTkinter GUI**: The application ships as a standalone Windows executable. When launched, it presents an animated, DPI-aware dark-mode launcher.
    *   **Embedded Server**: The launcher automatically spins up the `uvicorn` FastAPI server in a subprocess.
    *   **Webview / Browser Auto-launch**: It automatically opens the dashboard in the user's default browser or handles an embedded webview gracefully.

## 🏗️ Architecture & Tech Stack

### Backend Stack
*   **Python 3.11+**
*   **FastAPI**: Provides the REST API and the asynchronous SSE (Server-Sent Events) stream.
*   **Uvicorn**: High-performance ASGI server.
*   **Kite Connect**: Official python wrapper for Zerodha's trading API.
*   **PyArrow / Pandas**: Used for converting JSON API responses into dataframes and saving them rapidly to disk in Parquet format.
*   **Asyncio**: Core asynchronous event loop managing the fetcher engine, task queues, and locking mechanisms.

### Frontend Stack
*   **Vanilla HTML5 / CSS3 / JavaScript (ES6)**: Built without heavy frameworks to ensure minimal overhead and maximum performance.
*   **CSS Custom Properties (Variables)**: Used extensively for theme management and glassmorphism styling.
*   **Server-Sent Events (EventSource)**: Maintains a persistent connection to the backend for zero-latency UI updates.

## 📂 Project Structure

```text
📁 Archer Harvest/
├── 📄 main.py                 # FastAPI application definition, SSE routes, and endpoints
├── 📄 start_app.py            # Desktop Launcher (CustomTkinter) + subprocess manager
├── 📄 launcher_visuals.py     # UI class definitions for the Desktop Launcher
├── 📄 config.py               # Environment variables and configuration loader
├── 📄 auth_manager.py         # Kite Connect OAuth lifecycle management
├── 📄 fetcher_engine.py       # Core asynchronous download engine and TokenBucket limiter
├── 📄 instrument_loader.py    # Fetches and caches the latest active instrument list from Kite
├── 📄 state_manager.py        # Manages download_state.json and calculates ETA/Progress
├── 📄 storage_handler.py      # PyArrow logic for reading/writing Parquet files and directories
├── 📄 holiday_calendar.py     # Generator for breaking date ranges into chunks
├── 📄 build.py                # PyInstaller compilation script
├── 📁 static/                 # Frontend Assets
│   ├── 📄 index.html          # Main Dashboard HTML
│   ├── 📄 styles.css          # Core Glassmorphism CSS
│   ├── 📄 app.js              # Frontend logic and SSE handling
│   ├── 📄 datepicker.css      # Custom Calendar Styles
│   ├── 📄 datepicker.js       # Custom Calendar Logic
│   └── 📄 logo.png            # Transparent App Logo
├── 📁 Logo/                   # Source logo and icon assets
├── 📁 data/                   # Target directory where Parquet files are saved
└── 📄 .env                    # Secrets and configuration overrides
```

## ⚙️ Configuration (`.env`)

The application expects a `.env` file in the root directory (or next to the `.exe`):

```env
KITE_API_KEY=your_api_key_here
KITE_API_SECRET=your_api_secret_here
CONCURRENT_WORKERS=20       # Number of simultaneous API requests (Default: 20)
REQUEST_DELAY=0.35          # Delay between requests in seconds to respect Kite 3 req/s limit
DATA_DIR=data               # Output directory for downloaded files
```

## 🚀 Building the Executable

The application can be compiled into a single-file executable using PyInstaller. A custom build script (`build.py`) handles hook injections, hidden imports, and icon attachment.

```bash
python build.py
```

The resulting artifact `ArcherHarvest.exe` will be located in the `dist/` directory.

## 🛠️ API Endpoints (FastAPI)

*   `GET /api/auth/status` — Returns current Kite authentication status.
*   `GET /api/auth/login-url` — Generates the Kite OAuth login URL.
*   `GET /api/auth/callback` — Handles the redirect from Kite and generates the access token.
*   `POST /api/download/start` — Initializes the `fetcher_engine` with parameters (dates, timeframe, segments).
*   `POST /api/download/pause` — Halts the `asyncio.Event` flag in the fetcher engine.
*   `POST /api/download/resume` — Sets the `asyncio.Event` flag to resume workers.
*   `POST /api/download/stop` — Triggers the cancellation flag and terminates tasks.
*   `POST /api/download/retry-failed` — Re-queues only the stocks marked as `failed` in the state manager.
*   `GET /api/events` — Server-Sent Events (SSE) endpoint providing real-time streaming JSON payloads to the frontend.

## 🧠 Internal Mechanics: Worker Starvation & Token Bucket

**The Problem Solved:**
Initially, rate-limiting was handled by an `asyncio.Lock()`. A worker would acquire the lock, `await asyncio.sleep(0.35)`, make the API call, and release the lock. 
This caused *worker starvation*. Because the lock was held *during* the sleep, the entire engine became serialized. Workers were forced to wait in line for the sleep to finish, preventing them from overlapping their actual 2-to-5 second network requests. 

**The Solution:**
A custom `_TokenBucket` class was implemented. It records the timestamp of the last request. When a worker calls `acquire()`, it calculates the delta needed to ensure exactly 0.35 seconds have passed since the *last* request. It sleeps only that delta, updates the timestamp, and releases the lock *before* making the API call. This allows all 20 workers to overlap their network latency seamlessly while strictly emitting exactly 3 requests per second to the Kite servers.
