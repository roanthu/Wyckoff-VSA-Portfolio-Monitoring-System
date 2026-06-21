from __future__ import annotations
import datetime
import os
import time
import pandas as pd
from typing import Any

from .market_api_adapter import create_market_data_provider
from .wyckoff import (
    calculate_trading_range,
    calculate_virtual_candle,
    is_wyckoff_buy_setup,
    is_wyckoff_sell_setup,
    H1_SLOTS,
    H4_SLOTS,
    _parse_time,
)


class WyckoffBacktester:
    """Historical backtester for the Wyckoff/VSA Monitoring System."""

    def __init__(self, provider_name: str = "vnstock", source: str = "VCI") -> None:
        self.adapter = create_market_data_provider(provider_name, source=source)

    def run_backtest(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        status: str = "WATCH",
        sl_manual: float | None = None,
        tr_lookback: int = 60,
        use_cache: bool = True,
        timeframe_mode: str = "ALL",
    ) -> list[dict[str, Any]]:
        """Run backtest for a ticker over a date range.

        Args:
            ticker: Stock symbol (e.g. "TCB")
            start_date: Start date of simulation (YYYY-MM-DD)
            end_date: End date of simulation (YYYY-MM-DD)
            status: "WATCH" (test buy setup) or "HOLD" (test sell/SL setup)
            sl_manual: Optional manual Stop Loss level
            tr_lookback: Lookback days for baseline Trading Range calculation
            use_cache: If True, caches raw API calls to CSV files locally.

        Returns:
            List of detected signals.
        """
        print(f"=== Starting Backtest for {ticker} ({start_date} to {end_date}) ===")
        print(f"Mode: {status} | TR Lookback: {tr_lookback} days | Cache: {use_cache}")

        # Ensure ticker-specific cache directory exists
        cache_dir = "data_cache"
        ticker_cache_dir = os.path.join(cache_dir, ticker)
        if use_cache and not os.path.exists(ticker_cache_dir):
            os.makedirs(ticker_cache_dir)

        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        daily_cache_path = os.path.join(ticker_cache_dir, "daily.csv")
        daily_full = pd.DataFrame()

        # 1. Fetch daily D1 history
        if use_cache and os.path.exists(daily_cache_path):
            try:
                df = pd.read_csv(daily_cache_path)
                df["time"] = pd.to_datetime(df["time"])
                # Check if cache covers our target end date
                if not df.empty and df["time"].max() >= end_dt:
                    print(f"Loading daily D1 history from local cache: {daily_cache_path}")
                    daily_full = df
            except Exception as exc:
                print(f"Failed to read daily cache {daily_cache_path}: {exc}")

        if daily_full.empty:
            total_lookback_days = tr_lookback + int((end_dt - start_dt).days) + 30
            print(f"Fetching daily D1 history from live API (lookback {total_lookback_days} days)...")
            daily_full = self.adapter.get_daily_history(ticker, lookback_days=total_lookback_days)
            if daily_full.empty:
                print("Error: Could not retrieve D1 history.")
                return []
            
            # Convert daily_full time to datetime
            daily_full["time"] = pd.to_datetime(daily_full["time"])
            if use_cache:
                try:
                    daily_full.to_csv(daily_cache_path, index=False)
                    print(f"Saved daily D1 history to local cache: {daily_cache_path}")
                except Exception as exc:
                    print(f"Failed to write daily cache: {exc}")
            time.sleep(3.5)  # Respect free tier rate limits (20 req/min)

        daily_full = daily_full.sort_values("time").reset_index(drop=True)

        # Find trading days in our backtest range
        all_dates = pd.date_range(start=start_date, end=end_date, freq="B") # Business days
        trading_days = [d.strftime("%Y-%m-%d") for d in all_dates]

        signals_triggered = []

        # 2. Iterate day by day
        for current_day_str in trading_days:
            current_day_dt = pd.to_datetime(current_day_str)

            # Check if this day actually has trading data
            daily_history_before = daily_full[daily_full["time"] < current_day_dt]
            if len(daily_history_before) < 20:
                continue

            day_bar = daily_full[daily_full["time"].dt.strftime("%Y-%m-%d") == current_day_str]
            if day_bar.empty:
                continue

            print(f"\nProcessing {current_day_str}...")

            # Calculate Trading Range baseline at the start of this day
            try:
                tr = calculate_trading_range(daily_history_before, n=tr_lookback)
            except Exception as exc:
                print(f"  Failed to calculate TR for {current_day_str}: {exc}")
                continue

            # 3. Evaluate D1 timeframe setup independently
            d1_candle = {
                "timeframe": "D1",
                "slot_id": "D1",
                "slot_start": "09:15",
                "slot_end": "14:45",
                "slot_duration_minutes": 240,
                "elapsed_minutes": 240,
                "open": float(day_bar.iloc[0]["open"]),
                "high": float(day_bar.iloc[0]["high"]),
                "low": float(day_bar.iloc[0]["low"]),
                "close": float(day_bar.iloc[0]["close"]),
                "volume": int(day_bar.iloc[0]["volume"]),
            }

            d1_signal = None
            if status == "WATCH":
                d1_signal = is_wyckoff_buy_setup(
                    virtual_candle=d1_candle,
                    tr_low=tr["tr_low"],
                    tr_low_range=tr["tr_low_range"],
                    daily_history=daily_history_before,
                    tr_high=tr["tr_high"],
                )
            elif status == "HOLD":
                d1_signal = is_wyckoff_sell_setup(
                    virtual_candle=d1_candle,
                    tr_high=tr["tr_high"],
                    tr_high_range=tr["tr_high_range"],
                    daily_history=daily_history_before,
                    sl_manual=sl_manual,
                    tr_low=tr["tr_low"],
                )

            if d1_signal is not None:
                d1_signal["date"] = current_day_str
                d1_signal["ticker"] = ticker
                signals_triggered.append(d1_signal)
                print(f"  [SIGNAL] D1 at 14:45 - {d1_signal['type']} | Price: {d1_signal['current_price']}")

            # 4. Fetch 1m candles for H1/H4 simulation
            if timeframe_mode == "D1":
                continue

            minute_candles = pd.DataFrame()
            minute_cache_path = os.path.join(ticker_cache_dir, f"minute_{current_day_str}.csv")

            if use_cache and os.path.exists(minute_cache_path):
                try:
                    minute_candles = pd.read_csv(minute_cache_path)
                    if "time" in minute_candles.columns:
                        minute_candles["time"] = pd.to_datetime(minute_candles["time"])
                except Exception as exc:
                    print(f"  Failed to read minute cache {minute_cache_path}: {exc}")

            if minute_candles.empty:
                try:
                    minute_candles = self.adapter.get_minute_candles(ticker, date=current_day_str)
                    if not minute_candles.empty and use_cache:
                        minute_candles.to_csv(minute_cache_path, index=False)
                    time.sleep(3.5)  # Respect free tier rate limits (20 req/min)
                except Exception as exc:
                    print(f"  Warning: Failed to fetch minute candles from live API: {exc}")

            if minute_candles.empty:
                # Skip H1/H4 if 1m data is missing, but continue since D1 was already evaluated
                continue

            # 5. Simulate H1 and H4 slots of the day
            for tf in ("H1", "H4"):
                slots = H1_SLOTS if tf == "H1" else H4_SLOTS
                for slot in slots:
                    slot_end_time = _parse_time(slot["end"])

                    candle = calculate_virtual_candle(
                        minute_candles,
                        timeframe=tf,
                        current_time=slot_end_time,
                    )
                    if candle is None:
                        continue

                    # Evaluate signal
                    signal = None
                    if status == "WATCH":
                        signal = is_wyckoff_buy_setup(
                            virtual_candle=candle,
                            tr_low=tr["tr_low"],
                            tr_low_range=tr["tr_low_range"],
                            daily_history=daily_history_before,
                            tr_high=tr["tr_high"],
                        )
                    elif status == "HOLD":
                        signal = is_wyckoff_sell_setup(
                            virtual_candle=candle,
                            tr_high=tr["tr_high"],
                            tr_high_range=tr["tr_high_range"],
                            daily_history=daily_history_before,
                            sl_manual=sl_manual,
                            tr_low=tr["tr_low"],
                        )

                    if signal is not None:
                        signal["date"] = current_day_str
                        signal["ticker"] = ticker
                        signals_triggered.append(signal)

                        print(f"  [SIGNAL] {tf} {slot['id']} at {slot['end']} - {signal['type']} "
                              f"| Price: {signal['current_price']} | Vol ratio: {signal.get('vol_ratio_pct')}%")

        print(f"\n=== Backtest Complete. Total signals found: {len(signals_triggered)} ===")
        return signals_triggered


if __name__ == "__main__":
    tester = WyckoffBacktester()
    signals = tester.run_backtest(
        ticker="HPG",
        start_date="2026-06-01",
        end_date="2026-06-19",
        status="WATCH",
    )
