"""
Core download engine.
Iterates over stocks × date-chunks, respects rate limits,
implements retry with exponential backoff, and supports pause/resume.
Supports multiple API keys for parallel rate-limit scaling.
"""

import asyncio
import logging
import math
import random
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Callable, Awaitable

import aiohttp
import orjson
from kiteconnect import KiteConnect

from config import config
from auth_manager import auth_manager
from instrument_loader import instrument_loader
from state_manager import state_manager, StockStatus
from storage_handler import save_candles, get_downloaded_date_range
from holiday_calendar import generate_date_chunks

log = logging.getLogger(__name__)

EventCallback = Callable[[dict], Awaitable[None]]

_SENTINEL = None  # Poison pill for queue termination


class _TokenBucket:
    """Async token bucket: releases one token every `interval` seconds.
    Workers acquire a scheduled slot, then sleep OUTSIDE the lock
    so their API calls overlap freely.
    """
    def __init__(self, interval: float):
        self._interval = interval
        self._lock = asyncio.Lock()
        self._next_time: float = 0.0

    async def acquire(self):
        async with self._lock:
            now = asyncio.get_event_loop().time()
            if self._next_time <= now:
                self._next_time = now + self._interval
                wait = 0.0
            else:
                wait = self._next_time - now
                self._next_time += self._interval
        if wait > 0:
            await asyncio.sleep(wait)


class FetcherEngine:
    def __init__(self):
        self._pause_event = asyncio.Event()
        self._pause_event.set()
        self._cancel_flag = False
        self._stopping = False
        self._running = False
        self._task: asyncio.Task | None = None
        self._event_callback: EventCallback | None = None
        self._current_symbol: str | None = None
        self._queue: asyncio.Queue | None = None
        self._total_workers: int = 0

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_paused(self) -> bool:
        return not self._pause_event.is_set()

    @property
    def status(self) -> str:
        if not self._running:
            return "idle"
        if self._stopping:
            return "stopping"
        if self.is_paused:
            return "paused"
        return "running"

    def set_event_callback(self, cb: EventCallback):
        self._event_callback = cb

    async def _emit(self, event_type: str, data: dict):
        if self._event_callback:
            try:
                await self._event_callback({"type": event_type, **data})
            except Exception:
                pass

    def start(
        self,
        date_from: str,
        date_to: str,
        symbols: list[str] | None = None,
        timeframe: str = "minute",
        continuous: bool = False,
    ) -> bool:
        if self._running:
            return False
        if not auth_manager.is_authenticated:
            raise RuntimeError("Not authenticated. Please log in via Kite first.")

        all_symbols = symbols or instrument_loader.all_symbols()
        if not all_symbols:
            raise ValueError("No instruments loaded. Refresh the instrument list.")

        self._last_timeframe = timeframe
        self._last_continuous = continuous

        state_manager.initialize(all_symbols, date_from, date_to)
        self._cancel_flag = False
        self._pause_event.set()
        self._running = True

        self._task = asyncio.create_task(
            self._run_loop(all_symbols, date_from, date_to, timeframe, continuous)
        )
        self._task.add_done_callback(self._on_done)
        return True

    def pause(self):
        if self._running:
            self._pause_event.clear()
            log.info("Download paused")

    def resume(self):
        if self._running:
            self._pause_event.set()
    def stop(self):
        log.info("Download stop requested")
        self._cancel_flag = True
        self._stopping = True
        self._pause_event.set()
        
        # Clear the queue gracefully so workers exit after current chunk
        if self._queue:
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                    
            for _ in range(self._total_workers * 2):
                self._queue.put_nowait(_SENTINEL)
        
        # DO NOT cancel the task here. Let workers finish their current chunk 
        # and write the Parquet file to avoid data corruption or loss.
        log.info("Engine transitioning to STOPPED state, waiting for parquet writes...")

    def retry_failed(self) -> bool:
        if self._running:
            return False
        failed = state_manager.get_failed_symbols()
        if not failed:
            return False
        state_manager.reset_failed()
        date_from = state_manager._date_from
        date_to = state_manager._date_to
        if not date_from or not date_to:
            return False

        timeframe = getattr(self, '_last_timeframe', 'minute')
        continuous = getattr(self, '_last_continuous', False)

        self._cancel_flag = False
        self._stopping = False
        self._pause_event.set()
        self._running = True

        self._task = asyncio.create_task(
            self._run_loop(failed, date_from, date_to, timeframe, continuous)
        )
        self._task.add_done_callback(self._on_done)
        return True

    def _on_done(self, task: asyncio.Task):
        self._running = False
        self._stopping = False
        self._current_symbol = None
        exc = task.exception() if not task.cancelled() else None
        if exc:
            log.error("Fetcher loop crashed: %s", exc)
        else:
            log.info("Fetcher loop stopped cleanly.")
        
        # Fire and forget an event to notify frontend that we are fully idle
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(self._emit("status_change", {"status": "idle"}))
        except RuntimeError:
            pass

    async def _run_loop(
        self,
        symbols: list[str],
        date_from: str,
        date_to: str,
        timeframe: str = "minute",
        continuous: bool = False,
    ):
        start_d = date.fromisoformat(date_from)
        end_d = date.fromisoformat(date_to)
        total = len(symbols)

        await self._emit("download_started", {
            "total_stocks": total,
            "date_from": date_from,
            "date_to": date_to,
        })

        chunk_days = config.CHUNK_DAYS
        if timeframe == "day":
            chunk_days = 2000
        elif timeframe in ("5minute", "10minute", "15minute"):
            chunk_days = 100
        est_chunks_per_stock = max(1, math.ceil((end_d - start_d).days / chunk_days))
        state_manager.set_total_chunks(total * est_chunks_per_stock)

        queue: asyncio.Queue = asyncio.Queue()
        for idx, symbol in enumerate(symbols):
            queue.put_nowait((idx, symbol))

        all_kites = auth_manager.get_all_kites()
        num_keys = len(all_kites)

        buckets = [_TokenBucket(config.REQUEST_DELAY) for _ in range(num_keys)]

        workers_per_key = config.CONCURRENT_WORKERS
        total_workers = workers_per_key * num_keys
        # We still need an executor for save_candles (Parquet I/O)
        executor = ThreadPoolExecutor(max_workers=4)
        loop = asyncio.get_event_loop()

        log.info(
            "Starting AIOHTTP download: %d stocks, %d API key(s), %d workers, %.3fs delay",
            total, num_keys, total_workers, config.REQUEST_DELAY,
        )

        for _ in range(total_workers):
            queue.put_nowait(_SENTINEL)

        self._completed_count = 0
        self._total_count = total

        # Create one aiohttp.ClientSession per API key
        tcp_connector = aiohttp.TCPConnector(limit=total_workers)
        sessions = [
            aiohttp.ClientSession(
                connector=tcp_connector if i == 0 else aiohttp.TCPConnector(limit=total_workers),
                json_serialize=lambda x: orjson.dumps(x).decode(),
            )
            for i in range(num_keys)
        ]

        try:
            workers = []
            for key_idx in range(num_keys):
                kite = all_kites[key_idx]
                bucket = buckets[key_idx]
                session = sessions[key_idx]
                
                # Pre-compute headers for this API key
                headers = {
                    "X-Kite-Version": "3",
                    "Authorization": f"token {kite.api_key}:{kite.access_token}",
                    "User-Agent": "Kiteconnect-python/5.0.1"
                }

                for _ in range(workers_per_key):
                    workers.append(
                        asyncio.create_task(
                            self._worker_task(
                                queue, start_d, end_d, timeframe, continuous,
                                session, kite, bucket, executor, loop,
                            )
                        )
                    )

            await asyncio.gather(*workers)
        finally:
            # Clean up all sessions
            for session in sessions:
                await session.close()
            executor.shutdown(wait=False)

        state_manager.download_end_time = time.time()
        state_manager._persist()
        await self._emit("download_finished", state_manager.get_summary())
        log.info("Download loop finished")

    async def _worker_task(
        self,
        queue: asyncio.Queue,
        start_d: date,
        end_d: date,
        timeframe: str,
        continuous: bool,
        session: aiohttp.ClientSession,
        kite,
        bucket: _TokenBucket,
        executor: ThreadPoolExecutor,
        loop: asyncio.AbstractEventLoop,
    ):
        while True:
            if self._cancel_flag:
                break
            await self._pause_event.wait()
            if self._cancel_flag:
                break

            item = await queue.get()
            if item is _SENTINEL:
                break
            idx, symbol = item

            try:
                self._current_symbol = symbol
                state_manager.mark_in_progress(symbol)
                await self._emit("stock_started", {
                    "symbol": symbol,
                    "index": idx + 1,
                    "total": self._total_count,
                })

                inst = instrument_loader.get_by_symbol(symbol)
                if not inst:
                    state_manager.mark_failed(symbol, "Instrument not found")
                    await self._emit("stock_error", {
                        "symbol": symbol, "error": "Instrument not found",
                    })
                    continue

                token = inst["instrument_token_int"]
                effective_start = start_d

                if effective_start > end_d:
                    state_manager.mark_completed(symbol, 0)
                    await self._emit("stock_completed", {"symbol": symbol, "candles": 0})
                    continue

                dl_min, dl_max = get_downloaded_date_range(symbol)

                chunk_days = config.CHUNK_DAYS
                if timeframe == "day":
                    chunk_days = 2000
                elif timeframe in ("5minute", "10minute", "15minute"):
                    chunk_days = 100

                chunks = generate_date_chunks(effective_start, end_d, chunk_days)
                symbol_candles = 0
                symbol_failed = False
                all_symbol_candles = []

                for chunk_start, chunk_end in chunks:
                    if self._cancel_flag:
                        break
                    await self._pause_event.wait()
                    if self._cancel_flag:
                        break

                    if dl_min and dl_max and chunk_start >= dl_min and chunk_end <= dl_max:
                        state_manager.update_progress(symbol, chunk_end.isoformat(), 0)
                        state_manager.increment_chunk()
                        continue

                    candles = await self._fetch_chunk_with_retry(
                        session, kite, token, symbol, chunk_start, chunk_end,
                        timeframe, continuous, bucket
                    )

                    if candles is None:
                        symbol_failed = True
                        break

                    if candles:
                        all_symbol_candles.extend(candles)
                        symbol_candles += len(candles)
                        state_manager.update_progress(
                            symbol, chunk_end.isoformat(), len(candles)
                        )
                    state_manager.increment_chunk()

                    if state_manager.completed_chunks % 10 == 0:
                        await self._emit("progress_update", state_manager.get_summary())

                if all_symbol_candles:
                    await loop.run_in_executor(
                        executor, save_candles, symbol, all_symbol_candles
                    )

                if self._cancel_flag:
                    break

                if symbol_failed:
                    state_manager.mark_failed(
                        symbol,
                        state_manager.stocks.get(symbol, {}).get("error", "Unknown"),
                    )
                    await self._emit("stock_failed", {
                        "symbol": symbol,
                        "error": state_manager.stocks[symbol].get("error"),
                    })
                else:
                    state_manager.mark_completed(symbol, 0)
                    await self._emit("stock_completed", {
                        "symbol": symbol,
                        "candles": symbol_candles,
                    })

                self._completed_count += 1
                if self._completed_count % 10 == 0 or self._completed_count == self._total_count:
                    await self._emit("progress_update", state_manager.get_summary())

            except Exception as exc:
                log.error("Unhandled exception for %s: %s", symbol, exc, exc_info=True)
                state_manager.mark_failed(symbol, str(exc))
                await self._emit("stock_error", {"symbol": symbol, "error": str(exc)})

    async def _fetch_chunk_with_retry(
        self,
        session: aiohttp.ClientSession,
        kite,
        token: int,
        symbol: str,
        chunk_start: date,
        chunk_end: date,
        timeframe: str,
        continuous: bool,
        bucket: _TokenBucket,
    ) -> list | None:
        delay = config.RETRY_BASE_DELAY
        url = f"https://api.kite.trade/instruments/historical/{token}/{timeframe}"
        
        exch = symbol.split(":")[0] if ":" in symbol else ""
        actual_continuous = continuous and exch not in ("NSE", "BSE")
        
        params = {
            "from": chunk_start.strftime("%Y-%m-%d %H:%M:%S"),
            "to": chunk_end.strftime("%Y-%m-%d %H:%M:%S"),
            "continuous": "1" if actual_continuous else "0",
            "oi": "1"
        }

        for attempt in range(1, config.MAX_RETRIES + 1):
            try:
                await bucket.acquire()
                
                headers = {
                    "X-Kite-Version": "3",
                    "Authorization": f"token {kite.api_key}:{kite.access_token}",
                    "User-Agent": "Kiteconnect-python/5.0.1"
                }

                async with session.get(url, headers=headers, params=params) as resp:
                    resp_text = await resp.text()
                    
                    if resp.status != 200:
                        raise Exception(f"HTTP {resp.status}: {resp_text}")
                    
                    # Ultra-fast GIL-free JSON parsing
                    data = orjson.loads(resp_text)
                    
                    if data.get("status") == "error":
                        raise Exception(data.get("message", "Unknown API Error"))
                    
                    raw_candles = data.get("data", {}).get("candles", [])
                    
                    candles = []
                    for c in raw_candles:
                        # [date, open, high, low, close, volume, oi]
                        candles.append([c[0], c[1], c[2], c[3], c[4], c[5], c[6] if len(c) > 6 else 0])

                    return candles

            except Exception as exc:
                error_msg = str(exc)

                if "TokenException" in error_msg:
                    log.warning("API Token expired! Pausing engine. Please re-authenticate.")
                    self.pause()
                    await self._emit("status_change", {"status": "paused"})
                    await self._emit("token_expired", {"message": "API Token expired. Please connect to Kite again and click Resume."})
                    
                    # Wait for the user to resume
                    await self._pause_event.wait()
                    # Re-loop with the exact same attempt index so it retries with the new token
                    continue

                # Non-retryable errors — skip immediately
                non_retryable = ("invalid token", "InputException", "No data", "instrument is not available")
                if any(phrase in error_msg for phrase in non_retryable):
                    log.info(
                        "Skipping %s [%s → %s]: non-retryable error: %s",
                        symbol, chunk_start, chunk_end, error_msg[:150],
                    )
                    await self._emit("retry", {
                        "symbol": symbol,
                        "attempt": attempt,
                        "max_retries": config.MAX_RETRIES,
                        "error": f"SKIPPED (non-retryable): {error_msg[:150]}",
                    })
                    state_manager.stocks[symbol]["error"] = error_msg[:500]
                    return None

                is_rate_limit = "Too many requests" in error_msg or "429" in error_msg
                
                # Only log and emit if it's the final attempt OR it's not a rate limit error
                if attempt == config.MAX_RETRIES or not is_rate_limit:
                    log.warning(
                        "Attempt %d/%d for %s [%s → %s] failed: %s",
                        attempt, config.MAX_RETRIES, symbol,
                        chunk_start, chunk_end, error_msg,
                    )
                    await self._emit("retry", {
                        "symbol": symbol,
                        "attempt": attempt,
                        "max_retries": config.MAX_RETRIES,
                        "error": error_msg[:200],
                    })

                if attempt < config.MAX_RETRIES:
                    jitter = random.uniform(0, delay * 0.3)
                    wait = min(delay + jitter, config.RETRY_MAX_DELAY)
                    await asyncio.sleep(wait)
                    delay = min(delay * 2, config.RETRY_MAX_DELAY)
                else:
                    state_manager.stocks[symbol]["error"] = error_msg[:500]
                    return None

        return None


fetcher_engine = FetcherEngine()
