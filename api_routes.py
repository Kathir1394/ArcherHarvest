"""
FastAPI REST + SSE API routes for the Market Data Downloader.
"""

import asyncio
import json
import logging
from datetime import date, datetime

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sse_starlette.sse import EventSourceResponse

from auth_manager import auth_manager
from instrument_loader import instrument_loader
from state_manager import state_manager
from fetcher_engine import fetcher_engine
from storage_handler import get_storage_stats

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

# ── SSE event queue shared across clients ──
_sse_queues: list[asyncio.Queue] = []


async def broadcast_event(data: dict):
    """Push an event to all connected SSE clients."""
    payload = json.dumps(data, default=str)
    dead: list[asyncio.Queue] = []
    for q in _sse_queues:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        _sse_queues.remove(q)


# Wire the fetcher's event callback to SSE broadcast
fetcher_engine.set_event_callback(broadcast_event)


# ─────────────── Auth ───────────────

@router.get("/auth/login-url")
async def get_login_url():
    url = auth_manager.get_login_url()
    return {"login_url": url}


@router.get("/auth/callback")
async def auth_callback(request_token: str = Query(...), action: str = Query(default="login")):
    """Kite OAuth redirect lands here."""
    try:
        result = auth_manager.handle_callback(request_token)
        # After successful auth, try loading instruments
        try:
            await instrument_loader.load()
        except Exception as exc:
            log.warning("Failed to load instruments after auth: %s", exc)
        return RedirectResponse(url="/?auth=success")
    except Exception as exc:
        log.error("Auth callback failed: %s", exc)
        return RedirectResponse(url=f"/?auth=failed&error={str(exc)[:100]}")


@router.get("/auth/status")
async def auth_status():
    status = auth_manager.get_status()
    status["instruments_loaded"] = instrument_loader.count
    return status


@router.post("/auth/logout")
async def logout():
    auth_manager.logout()
    return {"status": "logged_out"}


# ─────────────── Instruments ───────────────

@router.get("/instruments")
async def list_instruments():
    return {
        "count": instrument_loader.count,
        "instruments": instrument_loader.get_instrument_list(),
    }


@router.post("/instruments/refresh")
async def refresh_instruments():
    await instrument_loader.load(force_refresh=True)
    return {"count": instrument_loader.count}


# ─────────────── Download Control ───────────────

@router.post("/download/start")
async def start_download(
    date_from: str = Query(default="2020-01-01"),
    date_to: str = Query(default=None),
    symbols: str = Query(default=None),
    timeframe: str = Query(default="minute"),
    segment: str = Query(default="ALL"),
    exchange_filter: str = Query(default="NSE_BSE"),
    continuous_data: bool = Query(default=False),
):
    if not auth_manager.is_authenticated:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    if date_to is None:
        date_to = date.today().isoformat()

    symbol_list = None
    if symbols:
        # If user provides explicit list, format it
        symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    else:
        # If no explicit symbols, filter by segment and exchange
        all_inst = instrument_loader.get_instrument_list()
        
        # 1. Segment filter
        if segment and segment != "ALL":
            allowed_segments = [s.strip() for s in segment.split(",") if s.strip()]
            filtered_inst = [i for i in all_inst if i.get("segment") in allowed_segments]
        else:
            filtered_inst = all_inst

        # 2. Exchange & Deduplication filter (applies mostly to Equities)
        final_inst = []
        nse_symbols = {i["raw_symbol"] for i in filtered_inst if i["exchange"] == "NSE"}
        
        for i in filtered_inst:
            exch = i["exchange"]
            raw_sym = i["raw_symbol"]
            
            if exchange_filter == "NSE_ONLY" and exch == "BSE":
                continue
            if exchange_filter == "BSE_ONLY" and exch == "NSE":
                continue
            if exchange_filter == "NSE_BSE" and exch == "BSE" and raw_sym in nse_symbols:
                # Deduplicate: Skip BSE if NSE equivalent exists
                continue
                
            final_inst.append(i["symbol"])
            
        symbol_list = final_inst

    try:
        started = fetcher_engine.start(date_from, date_to, symbol_list, timeframe, continuous_data)
        if started:
            return {"status": "started", "date_from": date_from, "date_to": date_to}
        return JSONResponse({"error": "Download already in progress"}, status_code=409)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@router.post("/download/pause")
async def pause_download():
    fetcher_engine.pause()
    await broadcast_event({"type": "status_change", "status": "paused"})
    return {"status": "paused"}


@router.post("/download/resume")
async def resume_download():
    fetcher_engine.resume()
    await broadcast_event({"type": "status_change", "status": "running"})
    return {"status": "resumed"}


@router.post("/download/stop")
async def stop_download():
    fetcher_engine.stop()
    await broadcast_event({"type": "status_change", "status": "stopped"})
    return {"status": "stopped"}


@router.post("/download/retry-failed")
async def retry_failed():
    if not auth_manager.is_authenticated:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    started = fetcher_engine.retry_failed()
    if started:
        return {"status": "retrying_failed"}
    return JSONResponse({"error": "No failed stocks to retry or download in progress"}, status_code=400)


@router.get("/download/status")
async def download_status():
    return {
        "engine": fetcher_engine.status,
        "summary": state_manager.get_summary(),
        "storage": get_storage_stats(),
    }


@router.get("/download/stocks")
async def download_stocks():
    return {"stocks": state_manager.get_stock_states()}


# ─────────────── SSE Stream ───────────────

@router.get("/events")
async def sse_events(request: Request):
    queue: asyncio.Queue = asyncio.Queue(maxsize=200)
    _sse_queues.append(queue)

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield {"event": "message", "data": data}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
        finally:
            if queue in _sse_queues:
                _sse_queues.remove(queue)

    return EventSourceResponse(event_generator())
