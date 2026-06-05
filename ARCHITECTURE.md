# Market Data Engine — Complete System Blueprint

This document contains the complete functional, technical, architectural, and visual specifications for the **Market Data Engine** project. It is designed to act as a comprehensive blueprint so that an AI/LLM can perfectly recreate the application from scratch.

---

## 1. Project Overview
The Market Data Engine is a full-stack desktop/web hybrid application designed to bulk-download 1-minute OHLCV (Open, High, Low, Close, Volume) historical candlestick data for all NSE-listed equities (approx. 2000+ stocks) in India. It fetches data primarily using the **Zerodha Kite Connect API**.

### Core Capabilities:
- **Authentication**: OAuth 2.0 flow with Kite Connect.
- **Data Fetching**: Asynchronous fetching looping through all NSE equities and downloading historical data in max 60-day chunks (API limit).
- **Resilience**: Implements pause/resume capabilities, crash recovery via state persistence, and exponential backoff for API rate-limiting (HTTP 429).
- **Storage**: Highly compressed, partitioned Parquet file storage.
- **Frontend Dashboard**: A responsive, real-time Glassmorphic web UI powered by Server-Sent Events (SSE).
- **Desktop Launcher**: A premium dark-themed Python GUI launcher (using `customtkinter`) that handles server lifecycle, embedded terminal logs, and browser auto-launch.

---

## 2. Technology Stack
- **Backend**: Python 3.12, FastAPI, Uvicorn, asyncio.
- **APIs**: `kiteconnect` (Zerodha API), `httpx` (async HTTP requests).
- **Data Processing & Storage**: `pandas`, `pyarrow` (Parquet).
- **Frontend**: Vanilla HTML5, Vanilla JavaScript, Vanilla CSS3 (No heavy frameworks like React/Tailwind).
- **Desktop Launcher**: `customtkinter`, `Pillow` (PIL) for graphics.
- **Configuration**: `python-dotenv`.

---

## 3. Architecture & Data Flow

### 3.1 System Architecture
```mermaid
graph TB
    subgraph Desktop GUI ["Desktop Launcher (Python/Tkinter)"]
        Launcher["start_app.py (Visual Engine & Terminal)"]
    end
    
    subgraph FastAPI Backend ["Backend (FastAPI)"]
        Routes["API Routes (/api/*)"]
        Auth["Auth Manager (OAuth)"]
        Fetcher["Fetcher Engine (Asyncio)"]
        State["State Manager (State persistence)"]
        Store["Storage Handler (Parquet)"]
        Instr["Instrument Loader"]
    end
    
    subgraph Web UI ["Browser Frontend (HTML/JS/CSS)"]
        Dashboard["Dashboard UI"]
    end
    
    Launcher -->|Spawns & Monitors| Routes
    Dashboard -->|REST (Control) & SSE (Real-time)| Routes
    Routes --> Auth & Fetcher
    Fetcher -->|Reads/Updates| State
    Fetcher -->|Writes Data| Store
    Fetcher -->|Queries API| KiteConnect["Kite Connect API"]
    Store --> Disk[(Parquet Files)]
    State --> JSON[(download_state.json)]
```

### 3.2 State Management & Crash Recovery
- The `StateManager` tracks every stock's status (`pending`, `in_progress`, `completed`, `failed`).
- State is continuously flushed to `download_state.json`.
- On startup, the backend loads this file. If a download was interrupted, clicking "Resume" or "Start" will pick up exactly where it left off, avoiding duplicate API calls.

---

## 4. UI/UX Design System (Strict Enforcement)
The application adheres strictly to a **Futuristic Minimalist Glassmorphism** aesthetic.

### 4.1 Web Dashboard (CSS/HTML)
- **Palette**: Deep dark background (`#020208`), neon accents (Cyan `#00E8D4`, Violet `#A855F7`, Teal `#14B8A6`).
- **Background**: Absolute-positioned floating CSS orbs with high `blur()` filters to create an ambient glowing background.
- **Panels**: `backdrop-filter: blur(18px)`, semi-transparent dark backgrounds (`hsla(225, 20%, 12%, 0.55)`), subtle glowing borders.
- **Typography**: `Inter` for UI text, `JetBrains Mono` for numbers/logs.
- **Interactivity**: Hover micro-animations on all buttons and stock chips. An animated, shimmering progress bar.
- **Components**:
  - Stat Cards (Total, Completed, Failed, Data Volume).
  - Control Panel (Date pickers, symbol filters, Start/Pause/Stop/Retry buttons).
  - Progress Panel (ETA, Speed, Progress Bar).
  - Stock Grid (Scrollable grid of chips showing individual stock statuses).
  - Live Log Console.

### 4.2 Desktop Launcher (`customtkinter`)
- **Theme**: Dark mode, frameless embedded terminal.
- **Visuals**: Animated gradient background using PIL, floating particle simulation, and a "Plasma Separator" (a color-cycling shimmer line).
- **Controls**: "Start Server" (spins up Uvicorn on a background thread), "Open Browser", and "Close".
- **Terminal**: A custom `CTkTextbox` that intercepts `sys.stdout` and `sys.stderr` via a thread-safe queue. It syntax-highlights logs in real-time (Cyan for success, Red for errors, Violet for info).

---

## 5. File Structure & Detailed Specifications

### 5.1 Project Root Files
- **`.env` / `.env.example`**: Contains `KITE_API_KEY`, `KITE_API_SECRET`, and rate-limiting configs (`REQUEST_DELAY=0.35`, `MAX_RETRIES=5`).
- **`requirements.txt`**: Pinned versions for `fastapi`, `uvicorn`, `kiteconnect`, `pandas`, `pyarrow`, `customtkinter`, `Pillow`, `sse-starlette`, etc.
- **`.gitignore`**: Ignores `venv`, `__pycache__`, `data/`, `.env`, and `download_state.json`.

### 5.2 Desktop Launcher Modules
- **`launcher_visuals.py`**:
  - `LauncherVisualEngine`: Generates the animated gradient and handles the `ParticleField`.
  - `ParticleField` & `FloatingParticle`: Math-driven floating dots that pulse.
  - `PlasmaSeparator`: A horizontal Canvas line that cycles HSV colors to simulate a neon plasma burn.
- **`start_app.py`**:
  - Main `customtkinter.CTk` window.
  - `LogQueue` and `StreamRedirector`: Safely pipes terminal output to the GUI.
  - `EmbeddedTerminal`: The glassmorphic terminal panel that slides out smoothly when the server starts.
  - Handles the `threading.Thread` to run `uvicorn.run(main:app)` so the GUI remains responsive.

### 5.3 Backend Modules (Python)
- **`config.py`**: 
  - Loads `.env`. Validates presence of Kite credentials.
  - Defines directories (`data/`) and API constraints (60 days max per chunk, 3 req/sec).
- **`holiday_calendar.py`**:
  - Hardcoded `set` of NSE trading holidays (2020-2026).
  - `is_trading_day()` and `generate_date_chunks(start, end, max_days=60)` functions to split date ranges while skipping weekends and holidays.
- **`instrument_loader.py`**:
  - Downloads the daily `instruments.csv` from Zerodha.
  - Caches to disk. Filters for `exchange == "NSE"` and `instrument_type == "EQ"`.
  - Provides O(1) lookups by symbol or token.
- **`auth_manager.py`**:
  - Wraps `KiteConnect`.
  - Generates the login URL and handles the OAuth callback token exchange.
  - Stores `access_token`.
- **`storage_handler.py`**:
  - Converts raw OHLCV arrays to `pandas.DataFrame`.
  - Uses `pyarrow.parquet` to save data to `data/{SYMBOL}/{SYMBOL}_{YEAR}.parquet`.
  - Implements **upsert/deduplication**: If a file exists, it concatenates, drops duplicates by timestamp keeping the last, and overwrites the Parquet file.
- **`state_manager.py`**:
  - Maintains a dictionary of tracking data per stock (`status`, `last_fetched_date`, `candles_fetched`, `error`).
  - Serializes to `download_state.json` synchronously upon state changes.
- **`fetcher_engine.py`**:
  - The core async loop.
  - Uses `asyncio.Event` for Pause/Resume functionality (clearing the event pauses the loop).
  - Uses exponential backoff for the Kite historical API call to gracefully handle rate limits.
  - Emits real-time progress dictionaries to a registered callback (which wires to SSE).
- **`api_routes.py`**:
  - FastAPI router.
  - `/api/auth/login-url`, `/api/auth/callback` for login.
  - `/api/download/start`, `pause`, `resume`, `stop`, `retry-failed`.
  - `/api/events`: `sse_starlette` endpoint that maintains a list of `asyncio.Queue` objects to broadcast events to all connected browser clients.
- **`main.py`**:
  - FastAPI app definition.
  - `lifespan` context manager: Validates config, restores state on startup, and cleanly cancels running tasks on shutdown.
  - Mounts the `static/` directory.

### 5.4 Frontend Modules (HTML/JS/CSS)
- **`static/index.html`**:
  - Semantic HTML grid. Contains background orbs, header, stats row, controls panel, progress panel, and a two-column bottom layout for the stock grid and activity log.
- **`static/styles.css`**:
  - Implements the strict Glassmorphism aesthetic.
  - Defines CSS variables for exact neon colors.
  - Defines `@keyframes` for shimmering progress bars and sliding log entries.
  - Custom scrollbars for grids.
- **`static/app.js`**:
  - `EventSource` connection to `/api/events`.
  - Event loop `switch(type)` that handles `download_started`, `stock_started`, `stock_completed`, `stock_failed`, `progress_update`, `retry`.
  - Dynamically builds HTML elements for the stock grid and updates CSS classes (`badge--pending`, `badge--in_progress`, etc.) to change colors instantly.
  - Maintains an auto-scrolling log array (max 300 entries).
  - REST `fetch()` calls mapped to the UI buttons.

---

## 6. Execution Flow (End-to-End)

1. User runs `start_app.py`. The Python GUI opens.
2. User clicks "Start Server". A background thread boots Uvicorn on port 8000. The GUI expands to reveal live server logs.
3. The GUI automatically opens the default web browser to `http://127.0.0.1:8000`.
4. User clicks "Connect Kite" on the web UI. It hits `/api/auth/login-url` and redirects to Zerodha.
5. User logs in. Zerodha redirects to `http://127.0.0.1:8000/api/auth/callback?request_token=...`.
6. Backend exchanges the token, marks as authenticated, and redirects back to the main dashboard.
7. User selects a date range and clicks "Start Download".
8. `fetcher_engine.py` initializes `state_manager.py` for all NSE stocks.
9. For each stock, it calculates 60-day date chunks using `holiday_calendar.py`.
10. It calls Kite API. If HTTP 429 occurs, it sleeps and retries.
11. Data is passed to `storage_handler.py`, converted to a DataFrame, and saved as Parquet.
12. The `fetcher_engine.py` emits an SSE event. The `app.js` updates the web UI instantly.
13. If the user clicks "Pause", the `asyncio.Event` is cleared, and the loop pauses at the next chunk boundary.

---
**End of Document**
