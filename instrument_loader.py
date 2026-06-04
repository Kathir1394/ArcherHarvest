"""
NSE instrument list loader.
Downloads the Kite instrument dump, filters for NSE equities,
and provides lookup helpers.
"""

import csv
import io
import logging
from datetime import date, datetime
from pathlib import Path

import httpx

from config import config

log = logging.getLogger(__name__)


class InstrumentLoader:
    KITE_INSTRUMENTS_URL = "https://api.kite.trade/instruments"

    def __init__(self):
        self.instruments: list[dict] = []
        self._by_token: dict[int, dict] = {}
        self._by_symbol: dict[str, dict] = {}

    @property
    def count(self) -> int:
        return len(self.instruments)

    def _cache_is_fresh(self) -> bool:
        cache = config.INSTRUMENT_CACHE
        if not cache.exists():
            return False
        mtime = datetime.fromtimestamp(cache.stat().st_mtime).date()
        return mtime == date.today()

    async def load(self, force_refresh: bool = False):
        """Load instruments from cache or download fresh from Kite."""
        cache = config.INSTRUMENT_CACHE
        if not force_refresh and self._cache_is_fresh():
            log.info("Loading instruments from cache: %s", cache)
            self._parse_csv(cache.read_text(encoding="utf-8"))
            return

        log.info("Downloading instrument list from Kite...")
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(self.KITE_INSTRUMENTS_URL)
            resp.raise_for_status()
            raw_csv = resp.text

        cache.write_text(raw_csv, encoding="utf-8")
        log.info("Instrument list cached to %s", cache)
        self._parse_csv(raw_csv)

    def _parse_csv(self, raw_csv: str):
        reader = csv.DictReader(io.StringIO(raw_csv))
        all_instruments = list(reader)

        filtered = []
        for row in all_instruments:
            exch = row.get("exchange")
            itype = row.get("instrument_type")
            symbol = row.get("tradingsymbol", "")
            
            # Equities & Indices
            if exch in ("NSE", "BSE") and itype == "EQ":
                # Filter out bonds/NCDs
                has_digit = any(c.isdigit() for c in symbol)
                has_hyphen = "-" in symbol
                starts_ends_digit = bool(symbol and symbol[0].isdigit() and symbol[-1].isdigit())
                if (has_digit and has_hyphen) or starts_ends_digit:
                    continue
                    
                if row.get("segment") == "INDICES":
                    row["ui_segment"] = "Index"
                else:
                    row["ui_segment"] = "Equity"
                filtered.append(row)
            
            # Futures
            elif exch == "NFO" and itype in ("FUTIDX", "FUTSTK"):
                row["ui_segment"] = "Future"
                filtered.append(row)
                
            # Options
            elif exch == "NFO" and itype in ("OPTIDX", "OPTSTK"):
                row["ui_segment"] = "Option"
                filtered.append(row)
                
            # Commodities
            elif exch == "MCX":
                if row.get("segment") == "INDICES":
                    row["ui_segment"] = "Index"
                else:
                    row["ui_segment"] = "Commodity"
                filtered.append(row)

        self.instruments = filtered

        self._by_token = {}
        self._by_symbol = {}
        for inst in self.instruments:
            token = int(inst["instrument_token"])
            symbol = f"{inst['exchange']}:{inst['tradingsymbol']}"
            inst["instrument_token_int"] = token
            inst["unique_symbol"] = symbol
            self._by_token[token] = inst
            self._by_symbol[symbol] = inst

        log.info(
            "Loaded %d instruments (out of %d total)",
            len(self.instruments), len(all_instruments),
        )

    def get_by_token(self, token: int) -> dict | None:
        return self._by_token.get(token)

    def get_by_symbol(self, symbol: str) -> dict | None:
        return self._by_symbol.get(symbol)

    def all_symbols(self) -> list[str]:
        return sorted(self._by_symbol.keys())

    def all_tokens(self) -> list[int]:
        return sorted(self._by_token.keys())

    def get_instrument_list(self) -> list[dict]:
        """Return simplified instrument dicts for the frontend."""
        return [
            {
                "token": int(inst["instrument_token"]),
                "symbol": inst["unique_symbol"],
                "raw_symbol": inst["tradingsymbol"],
                "exchange": inst["exchange"],
                "name": inst.get("name", ""),
                "isin": inst.get("isin", ""),
                "segment": inst.get("ui_segment", ""),
            }
            for inst in self.instruments
        ]


instrument_loader = InstrumentLoader()
