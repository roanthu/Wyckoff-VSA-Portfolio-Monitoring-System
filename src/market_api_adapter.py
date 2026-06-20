from __future__ import annotations
import datetime
import os
import time
import functools
from typing import Callable, Dict, Iterable, Any, Protocol

import pandas as pd
import requests


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------

def _retry_with_backoff(max_retries: int = 3, base_delay: float = 2.0):
    """Decorator that retries a function with exponential backoff (2/4/8s)."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = base_delay
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    if attempt == max_retries:
                        raise
                    print(f"{func.__name__} failed ({attempt}/{max_retries}): {exc}. Retrying in {delay}s...")
                    time.sleep(delay)
                    delay *= 2
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Protocol (interface)
# ---------------------------------------------------------------------------

class MarketDataProvider(Protocol):
    """Interface for all market data adapters."""

    def get_snapshot(self, tickers: Iterable[str]) -> Dict[str, Any]:
        """Get current price snapshot for one or more tickers."""
        ...

    def get_trade_history(self, ticker: str, page: int = 1, size: int = 200) -> list[Any]:
        """Get intraday tick-by-tick trade history."""
        ...

    def get_minute_candles(self, ticker: str, date: str | None = None, interval: str = "1m") -> pd.DataFrame:
        """Get OHLCV candles at minute-level resolution for a given date.

        Returns DataFrame with columns: time, open, high, low, close, volume.
        """
        ...

    def get_daily_history(self, ticker: str, lookback_days: int = 90) -> pd.DataFrame:
        """Get daily OHLCV history for trading range calculation.

        Returns DataFrame with columns: time (or date), open, high, low, close, volume.
        """
        ...

    def stream_quotes(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        ...


# ---------------------------------------------------------------------------
# TCBS Adapter (original, kept for backward compatibility)
# ---------------------------------------------------------------------------

class MarketAPIAdapter(MarketDataProvider):
    """Default TCBS adapter: REST methods implemented, WS left as a simple stub.

    Environment:
    - TCBS_API_BASE_URL: base URL for TCBS OpenAPI (e.g. https://openapi.tcbs.com.vn)
    - TCBS_API_KEY: API key / bearer token
    """

    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = base_url or os.environ.get("TCBS_API_BASE_URL", "https://openapi.tcbs.com.vn")
        self.api_key = api_key or os.environ.get("TCBS_API_KEY")
        self.session = requests.Session()
        if self.api_key:
            self.session.headers.update({"Authorization": f"Bearer {self.api_key}"})

    def _request_with_retry(self, method: str, path: str, **kwargs) -> requests.Response:
        url = self.base_url.rstrip("/") + path
        delay = 2.0
        for attempt in range(1, 4):
            try:
                resp = self.session.request(method, url, timeout=10, **kwargs)
                resp.raise_for_status()
                return resp
            except requests.RequestException as exc:
                print(f"Request failed ({attempt}/3) {method} {url}: {exc}")
                if attempt == 3:
                    raise
                time.sleep(delay)
                delay *= 2

    def get_snapshot(self, tickers: Iterable[str]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        symbol_list = ",".join(tickers)
        path = f"/tartarus/v1/tickerCommons?symbols={symbol_list}"
        try:
            resp = self._request_with_retry("GET", path)
            data = resp.json()
            if isinstance(data, list):
                for item in data:
                    sym = item.get("symbol") or item.get("code")
                    if sym:
                        result[sym] = item
            elif isinstance(data, dict):
                if "data" in data and isinstance(data["data"], list):
                    for item in data["data"]:
                        sym = item.get("symbol") or item.get("code")
                        if sym:
                            result[sym] = item
                else:
                    for k, v in data.items():
                        result[k] = v
        except Exception as exc:
            print(f"Failed to get snapshot: {exc}")
            for t in tickers:
                result[t] = None
        return result

    def get_trade_history(self, ticker: str, page: int = 1, size: int = 200) -> list[Any]:
        path = f"/nyx/v1/intraday/{ticker}/his/paging?pageIndex={page}&pageSize={size}"
        try:
            resp = self._request_with_retry("GET", path)
            data = resp.json()
            if isinstance(data, dict) and "data" in data:
                return data["data"]
            if isinstance(data, list):
                return data
            return []
        except Exception as exc:
            print(f"Failed to get trade history for {ticker}: {exc}")
            return []

    def get_minute_candles(self, ticker: str, date: str | None = None, interval: str = "1m") -> pd.DataFrame:
        """TCBS minute candle stub — not fully implemented yet."""
        print(f"TCBS get_minute_candles not implemented; returning empty DataFrame for {ticker}")
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])

    def get_daily_history(self, ticker: str, lookback_days: int = 90) -> pd.DataFrame:
        """TCBS daily history stub — not fully implemented yet."""
        print(f"TCBS get_daily_history not implemented; returning empty DataFrame for {ticker}")
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])

    def stream_quotes(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        print("WebSocket streaming not implemented; using polling fallback.")
        try:
            while True:
                raise NotImplementedError("Use get_snapshot in scheduled loop instead of stream_quotes")
        except KeyboardInterrupt:
            print("stream_quotes interrupted by user")


# ---------------------------------------------------------------------------
# Vnstock Adapter
# ---------------------------------------------------------------------------

class VnstockMarketAPIAdapter(MarketDataProvider):
    """Adapter for vnstock Quote-based market data.

    This adapter normalizes vnstock results to the same snapshot/trade history interface,
    plus provides minute-candle and daily-history methods required by the Wyckoff engine.
    """

    def __init__(self, source: str = "VCI", intraday_page_size: int = 100):
        self.source = source
        self.intraday_page_size = intraday_page_size

    def _make_quote(self, ticker: str):
        from vnstock import Quote
        return Quote(symbol=ticker, source=self.source)

    # -- Snapshot (current price) ------------------------------------------

    @_retry_with_backoff(max_retries=3, base_delay=2.0)
    def _fetch_intraday(self, ticker: str, page_size: int) -> pd.DataFrame:
        quote = self._make_quote(ticker)
        return quote.provider.intraday(page_size=page_size)

    def get_snapshot(self, tickers: Iterable[str]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for ticker in tickers:
            try:
                df = self._fetch_intraday(ticker, page_size=self.intraday_page_size)
                if hasattr(df, "iloc") and len(df):
                    latest = df.iloc[0]
                    price = float(latest["price"])
                    volume = int(latest["volume"]) if "volume" in latest.index else None
                else:
                    price = None
                    volume = None
                result[ticker] = {
                    "symbol": ticker,
                    "matchPrice": price,
                    "lastPrice": price,
                    "currentPrice": price,
                    "price": price,
                    "volume": volume,
                }
            except Exception as exc:
                print(f"vnstock get_snapshot failed for {ticker}: {exc}")
                result[ticker] = {
                    "symbol": ticker,
                    "matchPrice": None,
                    "lastPrice": None,
                    "currentPrice": None,
                    "price": None,
                    "volume": None,
                }
        return result

    # -- Trade history (tick-by-tick) ---------------------------------------

    @_retry_with_backoff(max_retries=3, base_delay=2.0)
    def get_trade_history(self, ticker: str, page: int = 1, size: int = 200) -> list[Any]:
        quote = self._make_quote(ticker)
        df = quote.provider.intraday(page_size=size)
        if hasattr(df, "to_dict"):
            return df.to_dict("records")
        return list(df)

    # -- Minute candles (OHLCV 1m / 5m) ------------------------------------

    @_retry_with_backoff(max_retries=3, base_delay=2.0)
    def get_minute_candles(self, ticker: str, date: str | None = None, interval: str = "1m") -> pd.DataFrame:
        """Get minute-level OHLCV candles for a given date.

        Args:
            ticker: Stock symbol (e.g. "TCB").
            date: Date string in YYYY-MM-DD format. Defaults to today.
            interval: Candle interval — "1m", "5m", "15m", "30m". Defaults to "1m".

        Returns:
            DataFrame with columns: time, open, high, low, close, volume.
        """
        if date is None:
            date = datetime.date.today().strftime("%Y-%m-%d")

        quote = self._make_quote(ticker)
        df = quote.history(start=date, end=date, interval=interval)

        # Normalize column names to lowercase
        if df is not None and not df.empty:
            df.columns = [c.lower() for c in df.columns]
            # Ensure 'time' column exists
            if "time" not in df.columns and "date" in df.columns:
                df = df.rename(columns={"date": "time"})
            # Filter to only the requested date (API may return multiple days)
            if "time" in df.columns:
                df["time"] = pd.to_datetime(df["time"], errors="coerce")
                df = df[df["time"].dt.strftime("%Y-%m-%d") == date]
                df = df.reset_index(drop=True)
        return df

    # -- Daily history (OHLCV D1) ------------------------------------------

    @_retry_with_backoff(max_retries=3, base_delay=2.0)
    def get_daily_history(self, ticker: str, lookback_days: int = 90) -> pd.DataFrame:
        """Get daily OHLCV history using vnstock.

        Args:
            ticker: Stock symbol (e.g. "TCB").
            lookback_days: Number of days to look back. Defaults to 90.

        Returns:
            DataFrame with columns: time, open, high, low, close, volume.
        """
        quote = self._make_quote(ticker)

        # Use length parameter for lookback
        length_str = f"{lookback_days}b" if lookback_days <= 365 else f"{lookback_days // 365}Y"
        df = quote.history(length=length_str, interval="1D")

        # Normalize column names
        if df is not None and not df.empty:
            df.columns = [c.lower() for c in df.columns]
            if "date" in df.columns and "time" not in df.columns:
                df = df.rename(columns={"date": "time"})
        return df

    # -- Stream (not supported) --------------------------------------------

    def stream_quotes(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        print("vnstock stream_quotes not implemented; use polling via get_snapshot instead.")
        raise NotImplementedError("Use get_snapshot in scheduled loop instead of stream_quotes")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_market_data_provider(provider: str | None = None, **kwargs: Any) -> MarketDataProvider:
    """Create a market data provider by name.

    Supported providers:
    - tcbs: default TCBS OpenAPI adapter
    - vnstock: vnstock-based adapter (recommended, free, no API key required)

    The provider can also be selected by environment variable MARKET_DATA_PROVIDER.
    Defaults to 'vnstock' if not specified.
    """
    provider_name = (provider or os.environ.get("MARKET_DATA_PROVIDER", "vnstock")).strip().lower()
    if provider_name == "vnstock":
        source = kwargs.pop("source", os.environ.get("VNSTOCK_SOURCE", "VCI"))
        return VnstockMarketAPIAdapter(source=source, **kwargs)
    if provider_name == "tcbs" or provider_name == "default":
        return MarketAPIAdapter(**kwargs)
    raise ValueError(f"Unsupported market data provider: {provider_name}")
