from __future__ import annotations
import datetime
import os
import traceback
from typing import Any

import pandas as pd

from .market_api_adapter import MarketDataProvider, create_market_data_provider
from .telegram_alerts import send_telegram
from .wyckoff import (
    calculate_trading_range,
    calculate_virtual_candle,
    is_wyckoff_buy_setup,
    is_wyckoff_sell_setup,
)


class MonitorState:
    """In-memory anti-spam state. Resets daily.

    Anti-spam key format: {ticker}:{timeframe}:{slot_id}
    E.g. "TCB:H1:H1_1" — ensures only 1 alert per ticker per candle slot.
    """

    def __init__(self) -> None:
        self.date = datetime.date.today()
        self.alerts_sent: dict[str, set[str]] = {}
        self.consecutive_failures = 0
        self.admin_alert_sent = False

    def reset_if_new_day(self) -> None:
        today = datetime.date.today()
        if today != self.date:
            self.date = today
            self.alerts_sent.clear()
            self.consecutive_failures = 0
            self.admin_alert_sent = False

    def has_alerted(self, key: str) -> bool:
        return key in self.alerts_sent.get(self.date.isoformat(), set())

    def mark_alerted(self, key: str) -> None:
        self.alerts_sent.setdefault(self.date.isoformat(), set()).add(key)


class MarketMonitor:
    def __init__(self, adapter: MarketDataProvider | None = None) -> None:
        self.adapter = adapter or create_market_data_provider()
        self.state = MonitorState()
        self.watchlist_url = os.environ.get("WATCHLIST_CSV_URL")
        self.telegram_chat_id = os.environ.get("TELEGRAM_ALERT_CHAT_ID") or os.environ.get("TELEGRAM_ADMIN_CHAT_ID")
        self.admin_chat_id = os.environ.get("TELEGRAM_ADMIN_CHAT_ID") or self.telegram_chat_id
        self.tr_lookback = int(os.environ.get("TR_LOOKBACK", "60"))
        self.default_watchlist: list[dict[str, Any]] = [
            {"ticker": t, "entry": None, "sl_manual": None, "status": "WATCH"}
            for t in ["TCB", "HPG", "SSI", "VHM", "VCB"]
        ]
        # Caches (reset daily via MonitorState)
        self.history_cache: dict[str, pd.DataFrame] = {}
        self.tr_cache: dict[str, dict] = {}

    # -- Watchlist ----------------------------------------------------------

    def load_watchlist(self) -> list[dict[str, Any]]:
        """Load watchlist as list of dicts with ticker/entry/sl_manual/status."""
        if not self.watchlist_url:
            return self.default_watchlist

        from .scheduler import read_watchlist_from_csv
        items = read_watchlist_from_csv(self.watchlist_url)
        return items if items else self.default_watchlist

    # -- Historical data ----------------------------------------------------

    def load_historical_data(self, ticker: str) -> pd.DataFrame | None:
        """Load daily D1 history for a ticker.

        Priority:
        1. Cache (in-memory for current session)
        2. vnstock adapter's get_daily_history()
        """
        if ticker in self.history_cache:
            return self.history_cache[ticker]

        try:
            df = self.adapter.get_daily_history(ticker, lookback_days=self.tr_lookback)
            if df is not None and not df.empty:
                self.history_cache[ticker] = df
                return df
        except Exception as exc:
            print(f"Failed to load daily history for {ticker}: {exc}")

        return None

    # -- Price extraction ---------------------------------------------------

    def _extract_current_price(self, snapshot: dict[str, Any]) -> float | None:
        if snapshot is None:
            return None
        for key in ("matchPrice", "lastPrice", "currentPrice", "price", "close"):
            value = snapshot.get(key)
            if value is not None:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    continue
        return None

    # -- Alert formatting (PRD section 6) -----------------------------------

    def _build_alert_message(
        self,
        ticker: str,
        status: str,
        signal: dict[str, Any],
    ) -> str:
        """Build Telegram alert message matching PRD format."""
        signal_type = signal["type"]
        timeframe = signal["timeframe"]
        close = signal["current_price"]
        low = signal["low"]
        shadow_pct = signal.get("shadow_pct", 0.0)
        current_vol = signal.get("current_vol", 0)
        vol_ratio = signal.get("vol_ratio_pct", 0.0)
        now = datetime.datetime.now().strftime("%H:%M:%S")

        # Map signal type to Vietnamese action
        action_map = {
            "SPRING_RUT_CHAN": "Theo doi mua vao khi xac nhan Spring thanh cong",
            "UPTHRUST_BAY_GIA": "Can nhac chot loi / giam vi the",
            "THUNG_SL": "CAT LO NGAY LAP TUC theo ke hoach",
        }
        action = action_map.get(signal_type, "Theo doi them")

        # Extra info for SL breach
        sl_line = ""
        if signal_type == "THUNG_SL":
            sl_price = signal.get("sl_price", "N/A")
            sl_source = signal.get("sl_source", "auto")
            sl_line = f"\n- Muc cat lo ({sl_source}): {sl_price}"

        return (
            f"🚨 [CANH BAO SOM WYCKOFF - KHUNG {timeframe}] 🚨\n"
            f"Ma co phieu: *{ticker}* (Trang thai: {status})\n"
            f"\n"
            f"Tin hieu phat hien: *{signal_type}*\n"
            f"- Gia hien tai: {close:,.0f}\n"
            f"- Gia thap nhat trong phien: {low:,.0f} (Do dai rau nen: {shadow_pct}%)\n"
            f"- Khoi luong hien tai: {current_vol:,.0f} (Vuot {vol_ratio}% so voi trung binh)"
            f"{sl_line}\n"
            f"\n"
            f"🎯 Hanh dong khuyen nghi: {action}\n"
            f"Thoi gian ghi nhan: {now}"
        )

    # -- Main cycle ---------------------------------------------------------

    def run_cycle(self) -> None:
        """Execute one monitoring cycle (called every minute)."""
        self.state.reset_if_new_day()
        watchlist = self.load_watchlist()
        current_time = datetime.datetime.now().time()
        today_str = datetime.date.today().strftime("%Y-%m-%d")

        try:
            # Get current prices for all tickers
            tickers = [item["ticker"] for item in watchlist]
            snapshots = self.adapter.get_snapshot(tickers)

            for item in watchlist:
                ticker = item["ticker"]
                status = item["status"]
                sl_manual = item["sl_manual"]
                snapshot = snapshots.get(ticker)

                current_price = self._extract_current_price(snapshot)
                if current_price is None:
                    print(f"No current price for {ticker}")
                    continue

                # Load daily D1 history for Trading Range + Volume calc
                daily_hist = self.load_historical_data(ticker)
                if daily_hist is None or daily_hist.empty:
                    print(f"No daily D1 data for {ticker}; skipping Wyckoff check")
                    continue

                # Calculate Trading Range (cache per ticker per session)
                if ticker not in self.tr_cache:
                    try:
                        self.tr_cache[ticker] = calculate_trading_range(daily_hist, n=self.tr_lookback)
                    except Exception as exc:
                        print(f"Failed to calculate TR for {ticker}: {exc}")
                        continue
                tr = self.tr_cache[ticker]

                # Get minute candles for virtual candle aggregation
                try:
                    minute_df = self.adapter.get_minute_candles(ticker, date=today_str)
                except Exception as exc:
                    print(f"Failed to get minute candles for {ticker}: {exc}")
                    continue

                if minute_df is None or minute_df.empty:
                    print(f"No minute candle data for {ticker}; skipping virtual candle")
                    continue

                # Check both H1 and H4 timeframes
                for tf in ("H1", "H4"):
                    candle = calculate_virtual_candle(minute_df, timeframe=tf, current_time=current_time)
                    if candle is None:
                        continue

                    signal = None

                    if status == "WATCH":
                        signal = is_wyckoff_buy_setup(
                            virtual_candle=candle,
                            tr_low=tr["tr_low"],
                            tr_low_range=tr["tr_low_range"],
                            daily_history=daily_hist,
                        )
                    elif status == "HOLD":
                        signal = is_wyckoff_sell_setup(
                            virtual_candle=candle,
                            tr_high=tr["tr_high"],
                            tr_high_range=tr["tr_high_range"],
                            daily_history=daily_hist,
                            sl_manual=sl_manual,
                            tr_low=tr["tr_low"],
                        )

                    if signal is not None:
                        anti_spam_key = f"{ticker}:{tf}:{candle['slot_id']}"
                        if not self.state.has_alerted(anti_spam_key):
                            message = self._build_alert_message(ticker, status, signal)
                            self._send_alert(message)
                            self.state.mark_alerted(anti_spam_key)

            self.state.consecutive_failures = 0
            self.state.admin_alert_sent = False

        except Exception as exc:
            self.state.consecutive_failures += 1
            print(f"Cycle failed ({self.state.consecutive_failures}): {exc}")
            traceback.print_exc()
            if self.state.consecutive_failures >= 5 and not self.state.admin_alert_sent:
                self._send_admin_alert(exc)
                self.state.admin_alert_sent = True

    # -- Telegram helpers ---------------------------------------------------

    def _send_alert(self, message: str) -> None:
        if not self.telegram_chat_id:
            print("Telegram chat id not configured; alert skipped")
            return
        print("Sending alert:", message)
        send_telegram(self.telegram_chat_id, message)

    def _send_admin_alert(self, exc: Exception) -> None:
        if not self.admin_chat_id:
            print("Admin chat id not configured; admin alert skipped")
            return
        text = (
            "🚨 [HE THONG GAP SU CO NGHIEM TRONG] 🚨\n"
            f"Bot da bi mat ket noi API lien tuc {self.state.consecutive_failures} lan.\n"
            f"- Thoi gian: {datetime.datetime.now().strftime('%H:%M:%S')}\n"
            f"- Chi tiet loi cuoi cung: {exc}\n"
            "👉 Vui long kiem tra lai ket noi mang cua Server hoac token API ngay lap tuc!"
        )
        print(text)
        send_telegram(self.admin_chat_id, text)


def create_monitor() -> MarketMonitor:
    return MarketMonitor()
