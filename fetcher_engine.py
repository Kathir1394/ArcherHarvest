"""
Core download engine.
Iterates over stocks × date-chunks, respects rate limits,
implements retry with exponential backoff, and supports pause/resume.
"""

import asyncio
import logging
import random
import time
from datetime import date, datetime, timedelta
from typing import Callable, Awaitable

from kiteconnect import KiteConnect

from config import config
from auth_manager import auth_manager
from instrument_loader import instrument_loader
from state_manager import state_manager, StockStatus
from storage_handler import save_candles, get_downloaded_date_range
from holiday_calendar import generate_date_chunks

log = logging.getLogger(__name__)

EventCallback = Callable[[dict], Awaitable[None]]


class FetcherEngine:
    def __init__(self):
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # starts unpaused
        self._cancel_flag = False
        self._running = False
        self._task: asyncio.Task | None = None
        self._event_callback: EventCallback | None = None
        self._current_symbol: str | None = None

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
            log.info("Download resumed")

    def stop(self):
        self._cancel_flag = True
        self._pause_event.set()  # unblock if paused so loop can exit
        if self._task and not self._task.done():
            self._task.cancel()
        log.info("Download stop requested")

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
        self._pause_event.set()
        self._running = True

        self._task = asyncio.create_task(
            self._run_loop(failed, date_from, date_to, timeframe, continuous)
        )
        self._task.add_done_callback(self._on_done)
        return True

    def _on_done(self, task: asyncio.Task):
        self._running = False
        self._current_symbol = None
        exc = task.exception() if not task.cancelled() else None
        if exc:
            log.error("Fetcher loop crashed: %s", exc)

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
        kite: KiteConnect = auth_manager.kite
        total = len(symbols)

        await self._emit("download_started", {
            "total_stocks": total,
            "date_from": date_from,
            "date_to": date_to,
        })

        queue = asyncio.Queue()
        for idx, symbol in enumerate(symbols):
            queue.put_nowait((idx, symbol))

        self._rate_limit_lock = asyncio.Lock()
        self._completed_count = 0
        self._total_count = total

        workers = [
            asyncio.create_task(
                self._worker_task(queue, start_d, end_d, timeframe, continuous, kite)
            )
            for _ in range(config.CONCURRENT_WORKERS)
        ]

        await asyncio.gather(*workers)

        state_manager.download_end_time = time.time()
        state_manager._persist()
        await self._emit("download_finished", state_manager.get_summary())
        log.info("Download loop finished")

    async def _worker_task(self, queue: asyncio.Queue, start_d: date, end_d: date, timeframe: str, continuous: bool, kite: KiteConnect):
        while not queue.empty():
            if self._cancel_flag:
                break
            await self._pause_event.wait()
            if self._cancel_flag:
                break

            idx, symbol = queue.get_nowait()

            try:
                entry = state_manager.stocks.get(symbol, {})
                if entry.get("status") == StockStatus.COMPLETED:
                    continue

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

                resume_date = state_manager.get_resume_date(symbol)
                effective_start = start_d
                if resume_date:
                    resumed = date.fromisoformat(resume_date) + timedelta(days=1)
                    if resumed > effective_start:
                        effective_start = resumed

                if effective_start > end_d:
                    state_manager.mark_completed(symbol, 0)
                    await self._emit("stock_completed", {"symbol": symbol, "candles": 0})
                    continue
                    
                dl_min, dl_max = get_downloaded_date_range(symbol)

                chunk_days = config.CHUNK_DAYS
                if timeframe == "day": chunk_days = 2000
                elif timeframe in ("5minute", "10minute", "15minute"): chunk_days = 100
                
                chunks = generate_date_chunks(effective_start, end_d, chunk_days)
                symbol_candles = 0
                symbol_failed = False

                for chunk_start, chunk_end in chunks:
                    if self._cancel_flag:
                        break
                    await self._pause_event.wait()
                    if self._cancel_flag:
                        break
                        
                    if dl_min and dl_max and chunk_start >= dl_min and chunk_end <= dl_max:
                        log.info("Smart sync: Skipping %s [%s → %s] (already downloaded)", symbol, chunk_start, chunk_end)
                        state_manager.update_progress(symbol, chunk_end.isoformat(), 0)
                        continue

                    candles = await self._fetch_chunk_with_retry(
                        kite, token, symbol, chunk_start, chunk_end, timeframe, continuous
                    )

                    if candles is None:
                        symbol_failed = True
                        break

                    if candles:
                        written = save_candles(symbol, candles)
                        symbol_candles += len(candles)
                        state_manager.update_progress(
                            symbol, chunk_end.isoformat(), len(candles)
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

            finally:
                queue.task_done()

    async def _fetch_chunk_with_retry(
        self,
        kite: KiteConnect,
        token: int,
        symbol: str,
        chunk_start: date,
        chunk_end: date,
        timeframe: str,
        continuous: bool = False,
    ) -> list | None:
        """
        Fetch a single date chunk with exponential backoff retry.
        Returns candle list on success, None on exhausted retries.
        """
        delay = config.RETRY_BASE_DELAY
        for attempt in range(1, config.MAX_RETRIES + 1):
            try:
                # Global rate limit lock across all workers
                async with self._rate_limit_lock:
                    await asyncio.sleep(config.REQUEST_DELAY)

                candles = await asyncio.to_thread(
                    kite.historical_data,
                    token,
                    chunk_start,
                    chunk_end,
                    timeframe,
                    continuous=continuous,
                    oi=True,
                )

                # Convert dict rows to lists if needed
                if candles and isinstance(candles[0], dict):
                    candles = [
                        [c["date"], c["open"], c["high"], c["low"], c["close"], c["volume"], c.get("oi", 0)]
                        for c in candles
                    ]

                return candles

            except Exception as exc:
                error_msg = str(exc)
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
