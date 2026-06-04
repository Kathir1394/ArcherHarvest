"""
NSE Trading Holiday Calendar (2020–2026).
Provides helpers to check trading days and generate trading-day date ranges.
"""

from datetime import date, timedelta

NSE_HOLIDAYS: set[date] = {
    # 2020
    date(2020, 1, 26), date(2020, 2, 21), date(2020, 3, 10),
    date(2020, 4, 2), date(2020, 4, 6), date(2020, 4, 10),
    date(2020, 4, 14), date(2020, 5, 1), date(2020, 5, 25),
    date(2020, 8, 15), date(2020, 10, 2), date(2020, 10, 29),
    date(2020, 11, 14), date(2020, 11, 16), date(2020, 11, 30),
    date(2020, 12, 25),
    # 2021
    date(2021, 1, 26), date(2021, 3, 11), date(2021, 3, 29),
    date(2021, 4, 2), date(2021, 4, 14), date(2021, 4, 21),
    date(2021, 5, 13), date(2021, 7, 21), date(2021, 8, 19),
    date(2021, 9, 10), date(2021, 10, 15), date(2021, 10, 19),
    date(2021, 11, 4), date(2021, 11, 5), date(2021, 11, 19),
    date(2021, 12, 25),
    # 2022
    date(2022, 1, 26), date(2022, 3, 1), date(2022, 3, 18),
    date(2022, 4, 14), date(2022, 4, 15), date(2022, 5, 3),
    date(2022, 8, 9), date(2022, 8, 15), date(2022, 8, 31),
    date(2022, 10, 5), date(2022, 10, 24), date(2022, 10, 26),
    date(2022, 11, 8),
    # 2023
    date(2023, 1, 26), date(2023, 3, 7), date(2023, 3, 30),
    date(2023, 4, 4), date(2023, 4, 7), date(2023, 4, 14),
    date(2023, 4, 22), date(2023, 5, 1), date(2023, 6, 28),
    date(2023, 8, 15), date(2023, 9, 19), date(2023, 9, 28),
    date(2023, 10, 2), date(2023, 10, 24), date(2023, 11, 14),
    date(2023, 11, 27), date(2023, 12, 25),
    # 2024
    date(2024, 1, 22), date(2024, 1, 26), date(2024, 3, 8),
    date(2024, 3, 25), date(2024, 3, 29), date(2024, 4, 11),
    date(2024, 4, 14), date(2024, 4, 17), date(2024, 4, 21),
    date(2024, 5, 1), date(2024, 5, 20), date(2024, 5, 23),
    date(2024, 6, 17), date(2024, 7, 17), date(2024, 8, 15),
    date(2024, 9, 16), date(2024, 10, 2), date(2024, 10, 12),
    date(2024, 11, 1), date(2024, 11, 15), date(2024, 12, 25),
    # 2025
    date(2025, 2, 26), date(2025, 3, 14), date(2025, 3, 31),
    date(2025, 4, 10), date(2025, 4, 14), date(2025, 4, 18),
    date(2025, 5, 1), date(2025, 8, 15), date(2025, 8, 27),
    date(2025, 10, 2), date(2025, 10, 21), date(2025, 10, 22),
    date(2025, 11, 5), date(2025, 11, 26), date(2025, 12, 25),
    # 2026 (tentative — update when NSE publishes official list)
    date(2026, 1, 26), date(2026, 3, 5), date(2026, 3, 19),
    date(2026, 3, 20), date(2026, 4, 3), date(2026, 4, 14),
    date(2026, 5, 1), date(2026, 5, 14), date(2026, 7, 7),
    date(2026, 8, 15), date(2026, 8, 17), date(2026, 9, 8),
    date(2026, 10, 2), date(2026, 10, 12), date(2026, 10, 26),
    date(2026, 11, 16), date(2026, 12, 25),
}


def is_trading_day(d: date) -> bool:
    """Weekend or listed holiday → not a trading day."""
    if d.weekday() >= 5:
        return False
    return d not in NSE_HOLIDAYS


def generate_date_chunks(
    start: date, end: date, chunk_days: int = 60
) -> list[tuple[date, date]]:
    """
    Break [start, end] into chunks of at most `chunk_days` calendar days.
    Each chunk is (chunk_start, chunk_end) inclusive.
    """
    chunks: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=chunk_days - 1), end)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return chunks


def count_trading_days(start: date, end: date) -> int:
    count = 0
    cursor = start
    while cursor <= end:
        if is_trading_day(cursor):
            count += 1
        cursor += timedelta(days=1)
    return count
