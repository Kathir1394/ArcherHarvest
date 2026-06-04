"""
Configuration loader for the Market Data Downloader.
Reads .env and exposes validated settings.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

if getattr(sys, 'frozen', False):
    APP_DIR = Path(sys._MEIPASS)
    CWD_DIR = Path(sys.executable).parent
else:
    APP_DIR = Path(__file__).resolve().parent
    CWD_DIR = APP_DIR

load_dotenv(CWD_DIR / ".env")


class Config:
    KITE_API_KEY: str = os.getenv("KITE_API_KEY", "")
    KITE_API_SECRET: str = os.getenv("KITE_API_SECRET", "")

    DATA_DIR: Path = CWD_DIR / os.getenv("DATA_DIR", "data")
    STATE_FILE: Path = CWD_DIR / os.getenv("STATE_FILE", "download_state.json")
    INSTRUMENT_CACHE: Path = CWD_DIR / "instruments_cache.csv"

    REDIRECT_URL: str = os.getenv("REDIRECT_URL", "http://127.0.0.1:8000/api/auth/callback")
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))

    # Kite rate-limit: 3 req/s → sleep 0.35s between requests for safety
    REQUEST_DELAY: float = float(os.getenv("REQUEST_DELAY", "0.35"))
    CONCURRENT_WORKERS: int = int(os.getenv("CONCURRENT_WORKERS", "3"))
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "5"))
    RETRY_BASE_DELAY: float = float(os.getenv("RETRY_BASE_DELAY", "1.0"))
    RETRY_MAX_DELAY: float = float(os.getenv("RETRY_MAX_DELAY", "60.0"))

    # 1-min candle → max 60 calendar days per API call
    CHUNK_DAYS: int = 60

    # Market hours IST
    MARKET_OPEN_HOUR: int = 9
    MARKET_OPEN_MINUTE: int = 15
    MARKET_CLOSE_HOUR: int = 15
    MARKET_CLOSE_MINUTE: int = 30

    @classmethod
    def validate(cls) -> list[str]:
        errors = []
        if not cls.KITE_API_KEY:
            errors.append("KITE_API_KEY is missing in .env")
        if not cls.KITE_API_SECRET:
            errors.append("KITE_API_SECRET is missing in .env")
        return errors

    @classmethod
    def ensure_dirs(cls):
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)


config = Config()
