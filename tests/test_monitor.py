import datetime
import unittest
from unittest.mock import patch

import pandas as pd

from src.monitor import MarketMonitor


class DummyAdapter:
    def get_snapshot(self, tickers):
        return {ticker: {"matchPrice": 50} for ticker in tickers}


class TestMonitor(unittest.TestCase):
    def test_run_cycle_with_historical_data(self):
        monitor = MarketMonitor(adapter=DummyAdapter())
        monitor.telegram_chat_id = None
        monitor.admin_chat_id = None

        historical = pd.DataFrame([
            {"symbol": "AAA", "date": "2026-06-01", "open": 100, "high": 105, "low": 95, "close": 102, "volume": 1000},
            {"symbol": "AAA", "date": "2026-06-02", "open": 102, "high": 106, "low": 100, "close": 105, "volume": 1100},
            {"symbol": "AAA", "date": "2026-06-03", "open": 105, "high": 108, "low": 103, "close": 107, "volume": 1200},
            {"symbol": "AAA", "date": "2026-06-04", "open": 107, "high": 109, "low": 104, "close": 108, "volume": 1300},
            {"symbol": "AAA", "date": "2026-06-05", "open": 108, "high": 110, "low": 105, "close": 109, "volume": 1400},
        ])

        with patch.object(monitor, "load_historical_data", return_value=historical):
            monitor.run_cycle()

        self.assertEqual(monitor.state.consecutive_failures, 0)

    def test_state_daily_reset(self):
        monitor = MarketMonitor(adapter=DummyAdapter())
        state = monitor.state
        state.date = datetime.date.today() - datetime.timedelta(days=1)
        state.alerts_sent[state.date.isoformat()] = {"AAA:low"}
        state.consecutive_failures = 2
        state.admin_alert_sent = True

        state.reset_if_new_day()

        self.assertEqual(state.date, datetime.date.today())
        self.assertEqual(state.alerts_sent, {})
        self.assertEqual(state.consecutive_failures, 0)
        self.assertFalse(state.admin_alert_sent)
