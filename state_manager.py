"""
Download state manager.
Tracks per-stock fetch progress and persists to JSON for crash recovery.
"""

import json
import logging
import time
from datetime import date, datetime
from pathlib import Path
from enum import Enum

from config import config

log = logging.getLogger(__name__)


class StockStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class StateManager:
    def __init__(self):
        self.stocks: dict[str, dict] = {}
        self.download_start_time: float | None = None
        self.download_end_time: float | None = None
        self._date_from: str | None = None
        self._date_to: str | None = None
        self.total_chunks: int = 0
        self.completed_chunks: int = 0

    def initialize(self, symbols: list[str], date_from: str, date_to: str):
        """Set up state for a new download run, preserving completed entries."""
        self._date_from = date_from
        self._date_to = date_to
        self.download_start_time = time.time()
        self.download_end_time = None
        self.total_chunks = 0
        self.completed_chunks = 0

        for sym in symbols:
            if sym not in self.stocks or self.stocks[sym]["status"] != StockStatus.COMPLETED:
                self.stocks[sym] = {
                    "status": StockStatus.PENDING,
                    "last_fetched_date": None,
                    "candles_fetched": 0,
                    "error": None,
                    "retries": 0,
                    "updated_at": datetime.now().isoformat(),
                }

    def mark_in_progress(self, symbol: str):
        if symbol in self.stocks:
            self.stocks[symbol]["status"] = StockStatus.IN_PROGRESS
            self.stocks[symbol]["updated_at"] = datetime.now().isoformat()
            self._persist()

    def mark_completed(self, symbol: str, candles: int):
        if symbol in self.stocks:
            self.stocks[symbol]["status"] = StockStatus.COMPLETED
            self.stocks[symbol]["candles_fetched"] += candles
            self.stocks[symbol]["last_fetched_date"] = self._date_to
            self.stocks[symbol]["error"] = None
            self.stocks[symbol]["updated_at"] = datetime.now().isoformat()
            self._persist()

    def mark_failed(self, symbol: str, error: str):
        if symbol in self.stocks:
            self.stocks[symbol]["status"] = StockStatus.FAILED
            self.stocks[symbol]["error"] = str(error)[:500]
            self.stocks[symbol]["retries"] += 1
            self.stocks[symbol]["updated_at"] = datetime.now().isoformat()
            self._persist()

    def update_progress(self, symbol: str, last_date: str, candles: int):
        if symbol in self.stocks:
            self.stocks[symbol]["last_fetched_date"] = last_date
            self.stocks[symbol]["candles_fetched"] += candles
            self.stocks[symbol]["updated_at"] = datetime.now().isoformat()
            
    def set_total_chunks(self, total: int):
        self.total_chunks = total
        
    def increment_chunk(self):
        self.completed_chunks += 1

    def get_resume_date(self, symbol: str) -> str | None:
        entry = self.stocks.get(symbol)
        if entry and entry.get("last_fetched_date"):
            return entry["last_fetched_date"]
        return None

    def get_failed_symbols(self) -> list[str]:
        return [
            sym for sym, data in self.stocks.items()
            if data["status"] == StockStatus.FAILED
        ]

    def reset_failed(self):
        for sym, data in self.stocks.items():
            if data["status"] == StockStatus.FAILED:
                data["status"] = StockStatus.PENDING
                data["error"] = None
                data["retries"] = 0
        self._persist()

    def get_summary(self) -> dict:
        total = len(self.stocks)
        if total == 0:
            return {
                "total": 0, "pending": 0, "in_progress": 0,
                "completed": 0, "failed": 0, "progress_pct": 0,
                "total_candles": 0, "elapsed_sec": 0, "eta_sec": 0,
            }

        counts = {"pending": 0, "in_progress": 0, "completed": 0, "failed": 0, "skipped": 0}
        total_candles = 0
        for data in self.stocks.values():
            counts[data["status"]] = counts.get(data["status"], 0) + 1
            total_candles += data.get("candles_fetched", 0)

        done = counts["completed"]
        if self.total_chunks > 0:
            progress = (self.completed_chunks / self.total_chunks * 100)
        else:
            progress = (done / total * 100) if total > 0 else 0

        elapsed = 0.0
        eta = 0.0
        if self.download_start_time:
            elapsed = time.time() - self.download_start_time
            if self.completed_chunks > 0 and self.total_chunks > 0:
                rate = elapsed / self.completed_chunks
                remaining = self.total_chunks - self.completed_chunks
                eta = rate * remaining
            elif done > 0:
                rate = elapsed / done
                remaining = total - done - counts["failed"]
                eta = rate * remaining

        return {
            "total": total,
            **counts,
            "progress_pct": round(progress, 1),
            "total_candles": total_candles,
            "elapsed_sec": round(elapsed),
            "eta_sec": round(eta),
            "date_from": self._date_from,
            "date_to": self._date_to,
        }

    def get_stock_states(self) -> list[dict]:
        return [
            {"symbol": sym, **data}
            for sym, data in sorted(self.stocks.items())
        ]

    def _persist(self):
        try:
            payload = {
                "date_from": self._date_from,
                "date_to": self._date_to,
                "download_start_time": self.download_start_time,
                "stocks": self.stocks,
            }
            config.STATE_FILE.write_text(
                json.dumps(payload, indent=2, default=str), encoding="utf-8"
            )
        except Exception as exc:
            log.warning("Failed to persist state: %s", exc)

    def restore(self) -> bool:
        """Restore state from disk. Returns True if state was loaded."""
        if not config.STATE_FILE.exists():
            return False
        try:
            payload = json.loads(config.STATE_FILE.read_text(encoding="utf-8"))
            self._date_from = payload.get("date_from")
            self._date_to = payload.get("date_to")
            self.download_start_time = payload.get("download_start_time")
            self.stocks = payload.get("stocks", {})
            log.info("Restored state: %d stocks tracked", len(self.stocks))
            return True
        except Exception as exc:
            log.warning("Failed to restore state: %s", exc)
            return False


state_manager = StateManager()
