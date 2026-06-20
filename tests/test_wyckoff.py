import unittest
import datetime
import pandas as pd

from src.wyckoff import (
    calculate_trading_range,
    calculate_virtual_candle,
    is_wyckoff_buy_setup,
    is_wyckoff_sell_setup,
    _calculate_trimmed_mean_volume,
    H1_SLOTS,
    H4_SLOTS,
)


class TestTradingRange(unittest.TestCase):
    def test_calculate_trading_range_basic(self):
        data = pd.DataFrame([
            {"time": "2026-06-01", "open": 100, "high": 105, "low": 95, "close": 102, "volume": 1000},
            {"time": "2026-06-02", "open": 102, "high": 108, "low": 101, "close": 107, "volume": 1100},
            {"time": "2026-06-03", "open": 107, "high": 109, "low": 96, "close": 108, "volume": 900},
            {"time": "2026-06-04", "open": 108, "high": 110, "low": 90, "close": 98, "volume": 800},
            {"time": "2026-06-05", "open": 98, "high": 112, "low": 92, "close": 110, "volume": 1200},
        ])

        result = calculate_trading_range(data, n=5, volume_multiplier=10.0, rally_window=2)

        self.assertEqual(result["tr_low"], 90.0)
        self.assertEqual(result["tr_high"], 112.0)
        self.assertEqual(result["tr_low_range"], (89.55, 90.45))
        self.assertEqual(result["tr_high_range"], (111.44, 112.56))
        self.assertEqual(result["n"], 5)


class TestVirtualCandle(unittest.TestCase):
    def _make_minute_data(self):
        """Create sample minute candles during H1_1 slot (09:15-10:15)."""
        rows = []
        for i in range(30):
            t = datetime.datetime(2026, 6, 20, 9, 15 + i)
            rows.append({
                "time": t,
                "open": 100 + i * 0.1,
                "high": 101 + i * 0.1,
                "low": 99 + i * 0.1,
                "close": 100.5 + i * 0.1,
                "volume": 1000 + i * 10,
            })
        return pd.DataFrame(rows)

    def test_h1_virtual_candle_within_slot(self):
        df = self._make_minute_data()
        candle = calculate_virtual_candle(df, "H1", current_time=datetime.time(9, 45))

        self.assertIsNotNone(candle)
        self.assertEqual(candle["timeframe"], "H1")
        self.assertEqual(candle["slot_id"], "H1_1")
        self.assertEqual(candle["open"], 100.0)  # First candle's open
        self.assertGreater(candle["high"], candle["low"])
        self.assertGreater(candle["volume"], 0)
        self.assertEqual(candle["elapsed_minutes"], 30)
        self.assertEqual(candle["slot_duration_minutes"], 60)

    def test_h4_virtual_candle(self):
        df = self._make_minute_data()
        candle = calculate_virtual_candle(df, "H4", current_time=datetime.time(9, 45))

        self.assertIsNotNone(candle)
        self.assertEqual(candle["timeframe"], "H4")
        self.assertEqual(candle["slot_id"], "H4_AM")

    def test_returns_none_outside_trading_hours(self):
        df = self._make_minute_data()
        candle = calculate_virtual_candle(df, "H1", current_time=datetime.time(8, 0))
        self.assertIsNone(candle)

    def test_returns_none_for_empty_data(self):
        df = pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])
        candle = calculate_virtual_candle(df, "H1", current_time=datetime.time(9, 30))
        self.assertIsNone(candle)


class TestTrimmedMeanVolume(unittest.TestCase):
    def test_basic_trimmed_mean(self):
        data = pd.DataFrame({
            "volume": [100, 100, 100, 100, 100, 100, 100, 100, 100, 100,
                        100, 100, 100, 100, 100, 100, 100, 100, 100, 10000]
        })
        result = _calculate_trimmed_mean_volume(data, periods=20)
        # Should remove the 10000 outlier, mean of 19 × 100 = 100
        self.assertAlmostEqual(result, 100.0)


class TestWyckoffBuySetup(unittest.TestCase):
    def _make_daily_history(self, avg_vol=1000):
        """Create 20 days of daily data with consistent volume."""
        rows = []
        for i in range(20):
            rows.append({
                "time": f"2026-06-{i+1:02d}",
                "open": 100, "high": 105, "low": 95, "close": 102,
                "volume": avg_vol,
            })
        return pd.DataFrame(rows)

    def test_spring_signal_detected(self):
        """A candle with long lower shadow, close in upper half, and volume spike."""
        candle = {
            "timeframe": "H1",
            "slot_id": "H1_1",
            "slot_start": "09:15",
            "slot_end": "10:15",
            "slot_duration_minutes": 60,
            "elapsed_minutes": 60,
            "count": 60,
            "open": 95.0,
            "high": 96.0,
            "low": 90.0,     # Long lower shadow: 95 - 90 = 5, which is 5.5% of 90
            "close": 95.5,   # Close in upper half (midpoint = 93)
            "volume": 2000,  # 2x the daily average → spike
        }
        daily = self._make_daily_history(avg_vol=1000)
        tr_low = 91.0
        tr_low_range = (90.55, 91.45)

        signal = is_wyckoff_buy_setup(candle, tr_low, tr_low_range, daily)

        self.assertIsNotNone(signal)
        self.assertEqual(signal["type"], "SPRING_RUT_CHAN")
        self.assertGreater(signal["shadow_pct"], 1.5)

    def test_no_signal_without_volume_spike(self):
        """Same candle shape but low volume → no signal."""
        candle = {
            "timeframe": "H1", "slot_id": "H1_1",
            "slot_start": "09:15", "slot_end": "10:15",
            "slot_duration_minutes": 60, "elapsed_minutes": 60, "count": 60,
            "open": 95.0, "high": 96.0, "low": 90.0, "close": 95.5,
            "volume": 500,  # Below average → no spike
        }
        daily = self._make_daily_history(avg_vol=1000)
        signal = is_wyckoff_buy_setup(candle, 91.0, (90.55, 91.45), daily)
        self.assertIsNone(signal)

    def test_no_signal_price_above_tr(self):
        """Price well above TR low → no signal."""
        candle = {
            "timeframe": "H1", "slot_id": "H1_1",
            "slot_start": "09:15", "slot_end": "10:15",
            "slot_duration_minutes": 60, "elapsed_minutes": 60, "count": 60,
            "open": 105.0, "high": 106.0, "low": 104.0, "close": 105.5,
            "volume": 2000,
        }
        daily = self._make_daily_history(avg_vol=1000)
        signal = is_wyckoff_buy_setup(candle, 91.0, (90.55, 91.45), daily)
        self.assertIsNone(signal)


class TestWyckoffSellSetup(unittest.TestCase):
    def _make_daily_history(self, avg_vol=1000):
        rows = []
        for i in range(20):
            rows.append({
                "time": f"2026-06-{i+1:02d}",
                "open": 100, "high": 105, "low": 95, "close": 102,
                "volume": avg_vol,
            })
        return pd.DataFrame(rows)

    def test_sl_breach_manual(self):
        """Close below manual SL → THUNG_SL signal."""
        candle = {
            "timeframe": "H1", "slot_id": "H1_3",
            "slot_start": "13:00", "slot_end": "14:00",
            "slot_duration_minutes": 60, "elapsed_minutes": 30, "count": 30,
            "open": 92.0, "high": 93.0, "low": 89.0, "close": 89.5,
            "volume": 1500,
        }
        daily = self._make_daily_history()
        signal = is_wyckoff_sell_setup(
            candle, tr_high=110.0, tr_high_range=(109.45, 110.55),
            daily_history=daily, sl_manual=90.0, tr_low=91.0,
        )
        self.assertIsNotNone(signal)
        self.assertEqual(signal["type"], "THUNG_SL")

    def test_upthrust_signal(self):
        """Price above TR high + long upper shadow + small body + volume spike."""
        candle = {
            "timeframe": "H4", "slot_id": "H4_PM",
            "slot_start": "13:00", "slot_end": "14:45",
            "slot_duration_minutes": 105, "elapsed_minutes": 105, "count": 105,
            "open": 110.0,
            "high": 115.0,    # Upper shadow = 115 - 110 = 5 (4.3% of 115)
            "low": 109.5,
            "close": 110.2,   # Small body: |110.2 - 110| = 0.2 (3.6% of range 5.5)
            "volume": 2000,
        }
        daily = self._make_daily_history(avg_vol=1000)
        signal = is_wyckoff_sell_setup(
            candle, tr_high=112.0, tr_high_range=(111.44, 112.56),
            daily_history=daily, sl_manual=None, tr_low=91.0,
        )
        self.assertIsNotNone(signal)
        self.assertEqual(signal["type"], "UPTHRUST_BAY_GIA")


if __name__ == "__main__":
    unittest.main()
