"""
Parquet-based storage handler for OHLCV candle data.
Writes one file per symbol per year, supports append + dedup.
"""

import logging
from datetime import datetime, date
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from config import config

log = logging.getLogger(__name__)

OHLCV_SCHEMA = pa.schema([
    ("timestamp", pa.timestamp("s", tz="Asia/Kolkata")),
    ("open", pa.float64()),
    ("high", pa.float64()),
    ("low", pa.float64()),
    ("close", pa.float64()),
    ("volume", pa.int64()),
    ("open_interest", pa.int64()),
])


def _symbol_dir(symbol: str) -> Path:
    safe_symbol = symbol.replace(":", "_")
    d = config.DATA_DIR / safe_symbol
    d.mkdir(parents=True, exist_ok=True)
    return d


def _parquet_path(symbol: str, year: int) -> Path:
    safe_symbol = symbol.replace(":", "_")
    return _symbol_dir(symbol) / f"{safe_symbol}_{year}.parquet"


def save_candles(symbol: str, candles: list[list]) -> int:
    """
    Save OHLCV candles for a symbol. Candles come from Kite as:
        [[datetime, open, high, low, close, volume], ...]
    Returns the number of new rows written (after dedup).
    """
    if not candles:
        return 0

    rows = []
    for c in candles:
        ts = c[0] if isinstance(c[0], datetime) else datetime.fromisoformat(str(c[0]))
        rows.append({
            "timestamp": ts,
            "open": float(c[1]),
            "high": float(c[2]),
            "low": float(c[3]),
            "close": float(c[4]),
            "volume": int(c[5]),
            "open_interest": int(c[6]) if len(c) > 6 else 0,
        })

    new_df = pd.DataFrame(rows)
    new_df["timestamp"] = pd.to_datetime(new_df["timestamp"], utc=True).dt.tz_convert("Asia/Kolkata")

    total_written = 0
    for year, year_df in new_df.groupby(new_df["timestamp"].dt.year):
        path = _parquet_path(symbol, int(year))

        if path.exists():
            existing = pd.read_parquet(path)
            combined = pd.concat([existing, year_df], ignore_index=True)
            combined.drop_duplicates(subset=["timestamp"], keep="last", inplace=True)
            combined.sort_values("timestamp", inplace=True)
        else:
            combined = year_df.sort_values("timestamp")

        combined.reset_index(drop=True, inplace=True)
        table = pa.Table.from_pandas(combined, schema=OHLCV_SCHEMA, preserve_index=False)
        pq.write_table(table, path, compression="snappy")

        new_count = len(combined) - (len(pd.read_parquet(path)) if False else 0)
        total_written += len(year_df)
        log.debug("Wrote %d candles → %s (total %d)", len(year_df), path.name, len(combined))

    # Save a CSV preview of the last 10 records
    try:
        safe_symbol = symbol.replace(":", "_")
        preview_path = _symbol_dir(symbol) / f"{safe_symbol}_preview.csv"
        # Re-read all to get global last 10? No, just the last batch is enough, but to be safe, get from the last year updated
        last_year = new_df["timestamp"].dt.year.max()
        last_path = _parquet_path(symbol, int(last_year))
        if last_path.exists():
            last_df = pd.read_parquet(last_path)
            last_df.tail(10).to_csv(preview_path, index=False)
    except Exception as exc:
        log.warning("Failed to write CSV preview for %s: %s", symbol, exc)

    return total_written


def get_downloaded_date_range(symbol: str) -> tuple[date | None, date | None]:
    """Return the absolute min and max date currently downloaded for a symbol."""
    sym_dir = _symbol_dir(symbol)
    if not sym_dir.exists():
        return None, None
        
    safe_symbol = symbol.replace(":", "_")
    parquets = sorted(sym_dir.glob(f"{safe_symbol}_*.parquet"))
    if not parquets:
        return None, None
        
    try:
        # Min date from first file
        first_meta = pq.read_metadata(parquets[0])
        min_ts = None
        if first_meta.num_row_groups > 0:
            first_df = pd.read_parquet(parquets[0], columns=["timestamp"])
            if not first_df.empty:
                min_ts = first_df["timestamp"].min().date()
                
        # Max date from last file
        last_meta = pq.read_metadata(parquets[-1])
        max_ts = None
        if last_meta.num_row_groups > 0:
            last_df = pd.read_parquet(parquets[-1], columns=["timestamp"])
            if not last_df.empty:
                max_ts = last_df["timestamp"].max().date()
                
        return min_ts, max_ts
    except Exception as exc:
        log.warning("Error reading date range for %s: %s", symbol, exc)
        return None, None


def read_candles(symbol: str, year: int | None = None) -> pd.DataFrame:
    """Read stored candles for a symbol, optionally filtered by year."""
    sym_dir = _symbol_dir(symbol)
    if not sym_dir.exists():
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume", "open_interest"])

    if year:
        path = _parquet_path(symbol, year)
        if path.exists():
            return pd.read_parquet(path)
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume", "open_interest"])

    frames = []
    for p in sorted(sym_dir.glob(f"{symbol}_*.parquet")):
        frames.append(pd.read_parquet(p))

    if not frames:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume", "open_interest"])
    return pd.concat(frames, ignore_index=True).sort_values("timestamp").reset_index(drop=True)


def get_storage_stats() -> dict:
    """Return aggregate storage statistics."""
    data_dir = config.DATA_DIR
    if not data_dir.exists():
        return {"total_files": 0, "total_bytes": 0, "total_symbols": 0}

    total_files = 0
    total_bytes = 0
    symbols = set()
    for p in data_dir.rglob("*.parquet"):
        total_files += 1
        total_bytes += p.stat().st_size
        symbols.add(p.parent.name)

    return {
        "total_files": total_files,
        "total_bytes": total_bytes,
        "total_bytes_display": _format_bytes(total_bytes),
        "total_symbols": len(symbols),
    }


def _format_bytes(b: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"
