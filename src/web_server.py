import os
import json
import urllib.parse
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any
import pandas as pd

from src.backtest import WyckoffBacktester
from src.wyckoff import calculate_trading_range
from src.simulator import WyckoffTradeSimulator

PORT = 8000
DATA_CACHE_DIR = "data_cache"


class NumpyEncoder(json.JSONEncoder):
    """JSON encoder that handles numpy and pandas types."""
    def default(self, obj):
        import numpy as np
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, pd.Timestamp):
            return obj.isoformat()
        return super().default(obj)


class WebDashboardHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        import datetime as _dt
        timestamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {args[0] if args else ''}")

    def _validate_ticker(self, ticker: str) -> str | None:
        """Validate and sanitize ticker symbol to prevent path traversal."""
        ticker = ticker.upper().strip()
        if not re.match(r'^[A-Z0-9]{1,10}$', ticker):
            return None
        return ticker

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        # -------------------------------------------------------------------
        # API Endpoints
        # -------------------------------------------------------------------

        # Get list of cached tickers
        if path == "/api/tickers":
            if not os.path.exists(DATA_CACHE_DIR):
                self._send_json([])
                return
            tickers = [
                d for d in os.listdir(DATA_CACHE_DIR)
                if os.path.isdir(os.path.join(DATA_CACHE_DIR, d))
            ]
            self._send_json(sorted(tickers))
            return

        # Get daily data for a ticker
        elif path.startswith("/api/ticker/") and path.endswith("/daily"):
            parts = path.split("/")
            ticker = self._validate_ticker(parts[3])
            if ticker is None:
                self._send_error(400, "Invalid ticker symbol")
                return
            csv_path = os.path.join(DATA_CACHE_DIR, ticker, "daily.csv")
            if not os.path.exists(csv_path):
                self._send_error(404, f"Daily data for {ticker} not found")
                return

            try:
                df = pd.read_csv(csv_path)
                # Sort and format date
                df = df.sort_values("time").reset_index(drop=True)
                # Convert time to string format yyyy-mm-dd
                df["time"] = pd.to_datetime(df["time"]).dt.strftime("%Y-%m-%d")
                records = df.to_dict("records")
                self._send_json(records)
            except Exception as e:
                self._send_error(500, str(e))
            return

        # Get list of available 1-minute dates for a ticker
        elif path.startswith("/api/ticker/") and path.endswith("/minutes"):
            parts = path.split("/")
            ticker = self._validate_ticker(parts[3])
            if ticker is None:
                self._send_error(400, "Invalid ticker symbol")
                return
            ticker_dir = os.path.join(DATA_CACHE_DIR, ticker)
            if not os.path.exists(ticker_dir):
                self._send_json([])
                return

            dates = []
            for f in os.listdir(ticker_dir):
                if f.startswith("minute_") and f.endswith(".csv"):
                    # Extract date from minute_YYYY-MM-DD.csv
                    date_str = f.replace("minute_", "").replace(".csv", "")
                    dates.append(date_str)
            self._send_json(sorted(dates))
            return

        # Get 1-minute data for a specific ticker and date
        elif path.startswith("/api/ticker/") and "/minute/" in path:
            # Format: /api/ticker/{ticker}/minute/{date}
            parts = path.split("/")
            ticker = self._validate_ticker(parts[3])
            if ticker is None:
                self._send_error(400, "Invalid ticker symbol")
                return
            date = parts[5]
            csv_path = os.path.join(DATA_CACHE_DIR, ticker, f"minute_{date}.csv")
            if not os.path.exists(csv_path):
                self._send_error(404, f"1m data for {ticker} on {date} not found")
                return

            try:
                df = pd.read_csv(csv_path)
                df = df.sort_values("time").reset_index(drop=True)
                # Convert datetime to timestamp string (HH:MM)
                df["time_label"] = pd.to_datetime(df["time"]).dt.strftime("%H:%M")
                # Format to timestamp for charts
                df["time"] = pd.to_datetime(df["time"]).astype(int) // 10**9
                records = df.to_dict("records")
                self._send_json(records)
            except Exception as e:
                self._send_error(500, str(e))
            return

        # Run backtest dynamically to get markers
        elif path.startswith("/api/ticker/") and path.endswith("/backtest"):
            parts = path.split("/")
            ticker = self._validate_ticker(parts[3])
            if ticker is None:
                self._send_error(400, "Invalid ticker symbol")
                return
            
            # Read parameters from query
            query_params = urllib.parse.parse_qs(parsed_url.query)
            status = query_params.get("status", ["WATCH"])[0]
            
            # Auto-detect date range from local daily cache if start_date/end_date not provided
            _default_start = None
            _default_end = None
            csv_path = os.path.join(DATA_CACHE_DIR, ticker, "daily.csv")
            if os.path.exists(csv_path):
                try:
                    df_daily = pd.read_csv(csv_path)
                    if not df_daily.empty and "time" in df_daily.columns:
                        df_daily = df_daily.sort_values("time").reset_index(drop=True)
                        # Start from the 60th trading day to ensure a baseline TR lookback is available
                        idx = min(60, len(df_daily) - 1)
                        _default_start = pd.to_datetime(df_daily.iloc[idx]["time"]).strftime("%Y-%m-%d")
                        _default_end = pd.to_datetime(df_daily.iloc[-1]["time"]).strftime("%Y-%m-%d")
                except Exception:
                    pass
            
            if not _default_start:
                import datetime as _dt
                _today = _dt.date.today()
                _default_start = (_today - _dt.timedelta(days=60)).strftime("%Y-%m-%d")
                _default_end = _today.strftime("%Y-%m-%d")
                
            start_date = query_params.get("start_date", [_default_start])[0]
            end_date = query_params.get("end_date", [_default_end])[0]

            try:
                tester = WyckoffBacktester()
                # Run backtest leveraging cache
                signals = tester.run_backtest(
                    ticker=ticker,
                    start_date=start_date,
                    end_date=end_date,
                    status=status,
                    use_cache=True,
                )
                self._send_json(signals)
            except Exception as e:
                self._send_error(500, str(e))
            return

        # Run trade simulation to test strategy performance
        elif path.startswith("/api/ticker/") and path.endswith("/simulate"):
            parts = path.split("/")
            ticker = self._validate_ticker(parts[3])
            if ticker is None:
                self._send_error(400, "Invalid ticker symbol")
                return
            
            # Read parameters from query
            query_params = urllib.parse.parse_qs(parsed_url.query)
            
            # Auto-detect date range from local daily cache if start_date/end_date not provided
            _default_start = None
            _default_end = None
            csv_path = os.path.join(DATA_CACHE_DIR, ticker, "daily.csv")
            if os.path.exists(csv_path):
                try:
                    df_daily = pd.read_csv(csv_path)
                    if not df_daily.empty and "time" in df_daily.columns:
                        df_daily = df_daily.sort_values("time").reset_index(drop=True)
                        # Start from the 60th trading day to ensure a baseline TR lookback is available
                        idx = min(60, len(df_daily) - 1)
                        _default_start = pd.to_datetime(df_daily.iloc[idx]["time"]).strftime("%Y-%m-%d")
                        _default_end = pd.to_datetime(df_daily.iloc[-1]["time"]).strftime("%Y-%m-%d")
                except Exception:
                    pass
            
            if not _default_start:
                import datetime as _dt
                _today = _dt.date.today()
                _default_start = (_today - _dt.timedelta(days=60)).strftime("%Y-%m-%d")
                _default_end = _today.strftime("%Y-%m-%d")
                
            start_date = query_params.get("start_date", [_default_start])[0]
            end_date = query_params.get("end_date", [_default_end])[0]

            try:
                simulator = WyckoffTradeSimulator()
                result = simulator.run_simulation(
                    ticker=ticker,
                    start_date=start_date,
                    end_date=end_date,
                    risk_pct=0.02, # 2% risk of NAV
                    rr_ratio=3.0,  # 3.0 R:R target
                )
                if "error" in result:
                    self._send_error(400, result["error"])
                else:
                    self._send_json(result)
            except Exception as e:
                self._send_error(500, str(e))
            return

        # Get Trading Range info
        elif path.startswith("/api/ticker/") and path.endswith("/tr"):
            parts = path.split("/")
            ticker = self._validate_ticker(parts[3])
            if ticker is None:
                self._send_error(400, "Invalid ticker symbol")
                return
            csv_path = os.path.join(DATA_CACHE_DIR, ticker, "daily.csv")
            if not os.path.exists(csv_path):
                self._send_error(404, f"Daily data for {ticker} not found")
                return
            try:
                df = pd.read_csv(csv_path)
                tr = calculate_trading_range(df, n=60)
                self._send_json(tr)
            except Exception as e:
                self._send_error(500, str(e))
            return

        # -------------------------------------------------------------------
        # Static HTML Dashboard serving
        # -------------------------------------------------------------------
        elif path == "/" or path == "/index.html":
            self._send_html_file(os.path.join("src", "web", "index.html"))
            return

        self._send_error(404, "Page not found")

    # -- Helper utilities ---------------------------------------------------

    def _send_json(self, data: Any):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, cls=NumpyEncoder).encode("utf-8"))

    def _send_error(self, code: int, message: str):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": message}).encode("utf-8"))

    def _send_html_file(self, filepath: str):
        if not os.path.exists(filepath):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"HTML dashboard file not found. Please create it first.")
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        with open(filepath, "rb") as f:
            self.wfile.write(f.read())


def run_web_server():
    server = HTTPServer(("0.0.0.0", PORT), WebDashboardHandler)
    print(f"\n==================================================")
    print(f"[Dashboard] Wyckoff/VSA Interactive Web Dashboard is running!")
    print(f"Access here: http://localhost:{PORT}")
    print(f"==================================================\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Web server stopped.")


if __name__ == "__main__":
    run_web_server()
