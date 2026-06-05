"""
Migration script: Add 'symbol' column to all existing parquet files.
Derives the symbol from the folder name (e.g., NSE_RELIANCE → RELIANCE).
Safe to run multiple times — skips files that already have the column.
Uses multiprocessing to speed up processing of thousands of files.
"""

import sys
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


def process_file(pf_str: str) -> tuple[str, str, str]:
    pf = Path(pf_str)
    try:
        df = pd.read_parquet(pf)
        if "symbol" in df.columns:
            return (pf_str, "skipped", "")

        folder_name = pf.parent.name
        # NSE_RELIANCE → RELIANCE, BSE_TCS → TCS, MCX_CRUDEOIL → CRUDEOIL
        parts = folder_name.split("_", 1)
        raw_symbol = parts[1] if len(parts) > 1 else folder_name

        df.insert(0, "symbol", raw_symbol)

        schema = pa.schema([
            ("symbol", pa.string()),
            ("timestamp", pa.timestamp("s", tz="Asia/Kolkata")),
            ("open", pa.float64()),
            ("high", pa.float64()),
            ("low", pa.float64()),
            ("close", pa.float64()),
            ("volume", pa.float64()),
            ("open_interest", pa.float64()),
        ])

        table = pa.Table.from_pandas(df, schema=schema, preserve_index=False)
        pq.write_table(table, pf, compression="snappy")
        return (pf_str, "migrated", "")
    except Exception as exc:
        return (pf_str, "error", str(exc))


def migrate_data_dir(data_dir: Path):
    if not data_dir.exists():
        print(f"Data directory not found: {data_dir}")
        return

    print("Scanning for parquet files...")
    parquet_files = [str(p) for p in data_dir.rglob("*.parquet")]
    total = len(parquet_files)
    if total == 0:
        print("No parquet files found.")
        return

    print(f"Found {total} files. Starting migration using {multiprocessing.cpu_count()} cores...")

    migrated = 0
    skipped = 0
    errors = 0

    start_time = time.time()

    with ProcessPoolExecutor(max_workers=multiprocessing.cpu_count()) as executor:
        futures = {executor.submit(process_file, pf): pf for pf in parquet_files}
        
        for idx, future in enumerate(as_completed(futures), 1):
            pf, status, err_msg = future.result()
            
            if status == "migrated":
                migrated += 1
            elif status == "skipped":
                skipped += 1
            else:
                errors += 1
                print(f"\nERROR on {pf}: {err_msg}")

            if idx % 100 == 0 or idx == total:
                elapsed = time.time() - start_time
                rate = idx / elapsed if elapsed > 0 else 0
                remaining = (total - idx) / rate if rate > 0 else 0
                print(f"\r  [{idx}/{total}] Migrated: {migrated} | Skipped: {skipped} | Errors: {errors} | {rate:.1f} files/s | ETA: {remaining:.0f}s", end="")

    total_time = time.time() - start_time
    print(f"\n\nMigration complete in {total_time:.1f}s: {migrated} migrated, {skipped} already had symbol, {errors} errors")


if __name__ == "__main__":
    # Windows requires multiprocessing spawn protection
    multiprocessing.freeze_support()
    data_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data")
    print(f"Migrating parquet files in: {data_path.resolve()}")
    migrate_data_dir(data_path)
