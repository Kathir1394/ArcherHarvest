"""
FastAPI application entry point for the Market Data Downloader.
"""

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from config import config, APP_DIR
from api_routes import router
from state_manager import state_manager
from fetcher_engine import fetcher_engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)-20s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──
    errors = config.validate()
    if errors:
        for e in errors:
            log.error("Config error: %s", e)
        log.error("Fix .env and restart.")
    else:
        config.ensure_dirs()
        restored = state_manager.restore()
        if restored:
            # Clear stale state from previous sessions to prevent count inflation
            has_active = any(
                s.get("status") in ("in_progress", "pending")
                for s in state_manager.stocks.values()
            )
            if not has_active:
                state_manager.stocks.clear()
                log.info("Cleared stale download state from previous session")
        log.info("Archer Harvest started on http://%s:%d", config.HOST, config.PORT)

    yield

    # ── Shutdown ──
    if fetcher_engine.is_running:
        log.info("Shutting down — stopping active download...")
        fetcher_engine.stop()
    state_manager._persist()
    log.info("Shutdown complete")


app = FastAPI(
    title="Archer Harvest",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# Serve frontend static files
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
app.mount("/Logo", StaticFiles(directory=str(APP_DIR / "Logo")), name="Logo")


@app.get("/")
async def serve_index():
    return FileResponse(str(APP_DIR / "static" / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=config.HOST,
        port=config.PORT,
        reload=True,
    )
