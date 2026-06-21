from __future__ import annotations
import os
import time
import datetime
from typing import Any
from zoneinfo import ZoneInfo

from src.market_api_adapter import create_market_data_provider
from src.monitor import MarketMonitor
import pandas as pd

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def read_watchlist_from_csv(url: str) -> list[dict[str, Any]]:
    """Read watchlist from public Google Sheets CSV.

    Expected columns: Ticker, Entry, SL_Manual, Status.
    Returns list of dicts with keys: ticker, entry, sl_manual, status.
    """
    try:
        df = pd.read_csv(url)
        # Normalize column names to lowercase for robust matching
        col_map = {c: c.strip().lower() for c in df.columns}
        df = df.rename(columns=col_map)

        # Find the ticker column (try 'ticker' first, then 'symbol', then first column)
        ticker_col = None
        for candidate in ["ticker", "symbol"]:
            if candidate in df.columns:
                ticker_col = candidate
                break
        if ticker_col is None:
            ticker_col = df.columns[0]

        result = []
        for _, row in df.iterrows():
            ticker = str(row.get(ticker_col, "")).strip().upper()
            if not ticker:
                continue

            # Parse entry price
            entry_raw = row.get("entry", None)
            try:
                entry = float(entry_raw) if pd.notna(entry_raw) else None
            except (TypeError, ValueError):
                entry = None

            # Parse SL_Manual
            sl_raw = row.get("sl_manual", None)
            try:
                sl_manual = float(sl_raw) if pd.notna(sl_raw) else None
            except (TypeError, ValueError):
                sl_manual = None

            # Parse Status (default to WATCH)
            status_raw = str(row.get("status", "WATCH")).strip().upper()
            status = status_raw if status_raw in ("WATCH", "HOLD") else "WATCH"

            result.append({
                "ticker": ticker,
                "entry": entry,
                "sl_manual": sl_manual,
                "status": status,
            })
        return result
    except Exception as exc:
        print(f"Failed to read watchlist CSV {url}: {exc}")
        return []


def _is_market_hours() -> bool:
    """Check if current time is within VN market hours (09:00 - 15:00)."""
    now = datetime.datetime.now(tz=VN_TZ)
    market_open = now.replace(hour=9, minute=0, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=0, second=0, microsecond=0)
    # Skip weekends
    if now.weekday() >= 5:
        return False
    return market_open <= now <= market_close


def run_loop(interval_seconds: int = 60) -> None:
    provider = create_market_data_provider()
    monitor = MarketMonitor(provider)

    try:
        while True:
            if _is_market_hours():
                cycle_start = time.time()
                monitor.run_cycle()
                elapsed = time.time() - cycle_start
                sleep_time = max(0, interval_seconds - elapsed)
                if sleep_time > 0:
                    time.sleep(sleep_time)
            else:
                # Outside market hours, check every 5 minutes
                print(f"Outside market hours. Next check in 5 minutes...")
                time.sleep(300)
    except KeyboardInterrupt:
        print("Scheduler stopped by user")


if __name__ == "__main__":
    run_loop()
