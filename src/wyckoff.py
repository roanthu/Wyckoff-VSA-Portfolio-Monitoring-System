from __future__ import annotations
import datetime
import math
from typing import Any
from zoneinfo import ZoneInfo
import pandas as pd

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


# ---------------------------------------------------------------------------
# VN Market Session Definitions (Phase 3)
# ---------------------------------------------------------------------------

# H1 candle slots — real VN market hours (not uniform 60-min)
H1_SLOTS = [
    {"id": "H1_1", "start": "09:15", "end": "10:15", "duration": 60},
    {"id": "H1_2", "start": "10:15", "end": "11:30", "duration": 75},
    {"id": "H1_3", "start": "13:00", "end": "14:00", "duration": 60},
    {"id": "H1_4", "start": "14:00", "end": "14:45", "duration": 45},
]

# H4 candle slots — 2 candles per day, not 240 minutes
H4_SLOTS = [
    {"id": "H4_AM", "start": "09:15", "end": "13:00", "duration": 150},
    {"id": "H4_PM", "start": "13:00", "end": "14:45", "duration": 105},
]


def _parse_time(t: str) -> datetime.time:
    """Parse HH:MM string to datetime.time."""
    parts = t.split(":")
    return datetime.time(int(parts[0]), int(parts[1]))


def _get_current_slot(timeframe: str, current_time: datetime.time) -> dict | None:
    """Find which H1/H4 slot the current_time falls into.

    If current_time is exactly the end of a slot, it falls into that slot (candle close).
    Otherwise, it falls into the slot where start <= current_time < end.
    """
    slots = H1_SLOTS if timeframe == "H1" else H4_SLOTS
    # Prioritize slot ends (candle close)
    for slot in slots:
        if current_time == _parse_time(slot["end"]):
            return slot

    for slot in slots:
        start = _parse_time(slot["start"])
        end = _parse_time(slot["end"])
        if start <= current_time < end:
            return slot
    return None


def _time_to_minutes(t: datetime.time) -> int:
    """Convert time to minutes since midnight."""
    return t.hour * 60 + t.minute


# ---------------------------------------------------------------------------
# Data normalization
# ---------------------------------------------------------------------------

def _normalize_ticker_data(ticker_data: Any) -> pd.DataFrame:
    if isinstance(ticker_data, pd.DataFrame):
        df = ticker_data.copy()
    else:
        df = pd.DataFrame(ticker_data)
    lower_cols = {c.lower(): c for c in df.columns}
    rename_map = {}
    for required in ["date", "time", "open", "high", "low", "close", "volume"]:
        for col_lower, col_orig in lower_cols.items():
            if col_lower == required:
                rename_map[col_orig] = required
                break
    df = df.rename(columns=rename_map)
    # Unify date/time column
    if "time" not in df.columns and "date" in df.columns:
        df = df.rename(columns={"date": "time"})
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], errors="coerce")
        df = df.sort_values("time")
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Phase 3: Virtual Candle Engine
# ---------------------------------------------------------------------------

def calculate_virtual_candle(
    minute_candles: pd.DataFrame,
    timeframe: str = "H1",
    current_time: datetime.time | None = None,
) -> dict | None:
    """Aggregate minute-level candles into a virtual H1 or H4 candle.

    This function filters minute candles to only include those within the
    current H1/H4 slot based on real VN market hours, then aggregates them.

    Args:
        minute_candles: DataFrame with columns time, open, high, low, close, volume.
        timeframe: "H1" or "H4".
        current_time: Current time. Defaults to now (VN timezone).

    Returns:
        Dict with open, high, low, close, volume, slot metadata, and timing info.
        Returns None if outside trading hours or no data in current slot.
    """
    if timeframe not in {"H1", "H4"}:
        raise ValueError("timeframe must be H1 or H4")

    df = _normalize_ticker_data(minute_candles)
    if df.empty:
        return None

    if current_time is None:
        current_time = datetime.datetime.now(tz=VN_TZ).time()

    # Find current slot
    slot = _get_current_slot(timeframe, current_time)
    if slot is None:
        return None

    slot_start = _parse_time(slot["start"])
    slot_end = _parse_time(slot["end"])

    # Filter candles within this slot
    if "time" in df.columns and pd.api.types.is_datetime64_any_dtype(df["time"]):
        candle_times = df["time"].dt.time
        mask = (candle_times >= slot_start) & (candle_times < slot_end)
        slot_candles = df[mask]
    else:
        # No parseable time column — cannot filter by slot, return None
        return None

    if slot_candles.empty:
        return None

    # Aggregate OHLCV
    virtual_open = float(slot_candles.iloc[0]["open"])
    virtual_high = float(slot_candles["high"].max())
    virtual_low = float(slot_candles["low"].min())
    virtual_close = float(slot_candles.iloc[-1]["close"])
    virtual_volume = int(slot_candles["volume"].sum())

    # Calculate elapsed time
    current_minutes = _time_to_minutes(current_time)
    slot_start_minutes = _time_to_minutes(slot_start)
    elapsed_minutes = min(slot["duration"], max(1, current_minutes - slot_start_minutes))

    return {
        "timeframe": timeframe,
        "slot_id": slot["id"],
        "slot_start": slot["start"],
        "slot_end": slot["end"],
        "slot_duration_minutes": slot["duration"],
        "elapsed_minutes": elapsed_minutes,
        "count": len(slot_candles),
        "open": virtual_open,
        "high": virtual_high,
        "low": virtual_low,
        "close": virtual_close,
        "volume": virtual_volume,
    }


# ---------------------------------------------------------------------------
# Phase 4 helpers: Volume & Shadow calculations
# ---------------------------------------------------------------------------

def _calculate_trimmed_mean_volume(daily_history: pd.DataFrame, periods: int = 20) -> float:
    """Calculate Trimmed Mean of volume over last N periods.

    Removes the single highest volume session, then takes the mean of the rest.
    This avoids outlier spikes distorting the average.
    """
    df = _normalize_ticker_data(daily_history)
    if "volume" not in df.columns or df.empty:
        return 0.0

    vols = df["volume"].tail(periods)
    if len(vols) < 2:
        return float(vols.mean()) if len(vols) > 0 else 0.0

    # Remove the highest volume (trim top 5% ≈ 1 session out of 20)
    sorted_vols = vols.sort_values()
    trimmed = sorted_vols.iloc[:-1]  # Remove highest
    return float(trimmed.mean())


def _check_volume_spike(
    current_vol: float,
    trimmed_mean_vol: float,
    elapsed_minutes: int,
    slot_duration_minutes: int,
    multiplier: float = 1.3,
) -> tuple[bool, float]:
    """Check if volume is spiking relative to time-adjusted average.

    Formula from PRD:
        Volume_tích_lũy >= (MeanVol20 * t / Tổng_thời_gian) * 1.3

    Returns:
        (is_spike, vol_ratio) — vol_ratio is the percentage above average.
    """
    if trimmed_mean_vol <= 0 or slot_duration_minutes <= 0:
        return False, 0.0

    expected_vol = trimmed_mean_vol * elapsed_minutes / slot_duration_minutes
    if expected_vol <= 0:
        return False, 0.0

    vol_ratio = current_vol / expected_vol
    is_spike = vol_ratio >= multiplier
    return is_spike, round((vol_ratio - 1) * 100, 1)  # ratio as percentage above average


# ---------------------------------------------------------------------------
# Phase 3 (kept): Trading Range
# ---------------------------------------------------------------------------

def calculate_trading_range(ticker_data: Any, n: int = 60, volume_multiplier: float = 1.5, rally_window: int = 20, buffer_pct: float = 0.005) -> dict:
    """Calculate Wyckoff trading range support/resistance from daily price-volume history.

    Args:
        ticker_data: DataFrame or list of dicts containing open/high/low/close/volume.
        n: lookback length in sessions for the TR baseline.
        volume_multiplier: SC volume threshold relative to 20-session average volume.
        rally_window: number of sessions after the SC to search for AR high.
        buffer_pct: optional zone padding for support/resistance.

    Returns:
        dict with `tr_low`, `tr_high`, `tr_low_range`, `tr_high_range`, `sc_index`, `ar_index`.
    """
    df = _normalize_ticker_data(ticker_data)
    if df.empty or "low" not in df.columns or "high" not in df.columns or "volume" not in df.columns:
        raise ValueError("ticker_data must contain low, high, and volume columns")

    tail = df.iloc[-n:].copy() if len(df) >= n else df.copy()
    tail["vol_ma20"] = tail["volume"].rolling(20, min_periods=1).mean()
    tail["sc_candidate"] = tail["volume"] > (volume_multiplier * tail["vol_ma20"])

    sc_candidates = tail[tail["sc_candidate"]].copy()
    if not sc_candidates.empty:
        sc_row = sc_candidates.loc[sc_candidates["low"].idxmin()]
        sc_index = int(sc_row.name)
    else:
        sc_index = int(tail["low"].idxmin())
        sc_row = tail.loc[sc_index]

    tr_low = float(sc_row["low"])
    ar_start = sc_index + 1
    ar_end = min(ar_start + rally_window, len(tail))
    ar_slice = tail.iloc[ar_start:ar_end]
    if not ar_slice.empty:
        ar_row = ar_slice.loc[ar_slice["high"].idxmax()]
        ar_index = int(ar_row.name)
    else:
        ar_index = int(tail["high"].idxmax())
        ar_row = tail.loc[ar_index]

    tr_high = float(ar_row["high"])
    if tr_high <= tr_low:
        tr_high = float(tail["high"].max())

    return {
        "tr_low": tr_low,
        "tr_high": tr_high,
        "tr_low_range": (round(tr_low * (1 - buffer_pct), 2), round(tr_low * (1 + buffer_pct), 2)),
        "tr_high_range": (round(tr_high * (1 - buffer_pct), 2), round(tr_high * (1 + buffer_pct), 2)),
        "sc_index": sc_index,
        "ar_index": ar_index,
        "sc_volume": float(sc_row["volume"] if "volume" in sc_row else math.nan),
        "ar_volume": float(ar_row["volume"] if "volume" in ar_row else math.nan),
        "n": len(tail),
        "lookback_n": n,
    }


# ---------------------------------------------------------------------------
# Phase 4: Wyckoff Signal Detection
# ---------------------------------------------------------------------------

def is_wyckoff_buy_setup(
    virtual_candle: dict,
    tr_low: float,
    tr_low_range: tuple[float, float],
    daily_history: pd.DataFrame,
    tr_high: float = 0.0,
) -> dict | None:
    """Detect Spring (buy) signal for WATCH stocks.

    Checks 3 conditions from PRD section 4.3.A:
    1. Long lower shadow (OR: >= 1.5% × Low, or >= 50% of candle range)
    2. Close is in upper half of candle
    3. Volume spike (Trimmed Mean formula with time ratio)

    Args:
        virtual_candle: Dict from calculate_virtual_candle().
        tr_low: Trading range support level.
        tr_low_range: (lower_bound, upper_bound) of TR support zone.
        daily_history: Daily OHLCV DataFrame for volume calculation.

    Returns:
        Signal dict if all conditions met, None otherwise.
    """
    if virtual_candle is None:
        return None

    o = virtual_candle["open"]
    h = virtual_candle["high"]
    low = virtual_candle["low"]
    c = virtual_candle["close"]
    vol = virtual_candle["volume"]
    candle_range = h - low

    # Price must penetrate below TR_Low support zone for a true Spring
    # The low must touch or break below the TR_Low zone lower bound
    if low > tr_low_range[1]:
        return None
    # Close must recover back above TR_Low (price rejection = Spring confirmation)
    if c < tr_low_range[0]:
        return None

    # --- Condition 1: Long lower shadow (OR logic, check absolute first) ---
    lower_shadow = min(o, c) - low
    shadow_pct = (lower_shadow / low * 100) if low > 0 else 0.0

    cond1_absolute = lower_shadow >= 0.015 * low  # >= 1.5% of Low
    cond1_relative = (lower_shadow >= 0.5 * candle_range) if candle_range > 0 else False

    if not (cond1_absolute or cond1_relative):
        return None

    # --- Condition 2: Close retraces to upper half of candle ---
    if candle_range > 0:
        midpoint = (h + low) / 2
        if c < midpoint:
            return None
    # If candle_range == 0 (doji), skip this check

    # --- Condition 3: Volume spike (Trimmed Mean with time ratio) ---
    trimmed_mean = _calculate_trimmed_mean_volume(daily_history, periods=20)
    elapsed = virtual_candle.get("elapsed_minutes", 1)
    slot_duration = virtual_candle.get("slot_duration_minutes", 60)
    # Scale daily average volume to slot by using total daily trading minutes as base (240 for D1/H1, 255 for H4)
    tf = virtual_candle.get("timeframe", "H1")
    total_day_minutes = 255.0 if tf == "H4" else 240.0
    is_spike, vol_ratio_pct = _check_volume_spike(vol, trimmed_mean, elapsed, total_day_minutes, multiplier=1.3)

    if not is_spike:
        return None

    # All 3 conditions met → Spring signal
    return {
        "type": "SPRING_RUT_CHAN",
        "timeframe": virtual_candle["timeframe"],
        "slot_id": virtual_candle["slot_id"],
        "current_price": c,
        "low": low,
        "high": h,
        "open": o,
        "shadow_pct": round(shadow_pct, 2),
        "shadow_condition": "absolute" if cond1_absolute else "relative",
        "current_vol": vol,
        "vol_ratio_pct": vol_ratio_pct,
        "trimmed_mean_vol": round(trimmed_mean, 0),
        "tr_low": tr_low,
        "tr_high": tr_high,
        "elapsed_minutes": elapsed,
        "slot_duration_minutes": slot_duration,
    }


def is_wyckoff_sell_setup(
    virtual_candle: dict | None,
    tr_high: float,
    tr_high_range: tuple[float, float],
    daily_history: pd.DataFrame,
    sl_manual: float | None = None,
    tr_low: float | None = None,
) -> dict | None:
    """Detect Upthrust (sell) or SL breach signal for HOLD stocks.

    Checks from PRD section 4.3.B:
    B1. SL breach: Close <= SL_Manual, or Close <= TR_Low × 0.995
    B2. Upthrust: Price above TR_High + long upper shadow + small body + high vol

    Args:
        virtual_candle: Dict from calculate_virtual_candle(). Can be None for SL-only check.
        tr_high: Trading range resistance level.
        tr_high_range: (lower_bound, upper_bound) of TR resistance zone.
        daily_history: Daily OHLCV DataFrame for volume calculation.
        sl_manual: Manual stop-loss price (from CSV). None means use auto SL.
        tr_low: Trading range support (used for auto SL = tr_low × 0.995).

    Returns:
        Signal dict if conditions met, None otherwise.
    """
    if virtual_candle is None:
        return None

    o = virtual_candle["open"]
    h = virtual_candle["high"]
    low = virtual_candle["low"]
    c = virtual_candle["close"]
    vol = virtual_candle["volume"]
    candle_range = h - low

    # --- Check B1: SL breach ---
    sl_price = None
    if sl_manual is not None:
        sl_price = sl_manual
    elif tr_low is not None:
        sl_price = tr_low * 0.995  # Auto SL = lowest low (Spring) - 0.5%

    if sl_price is not None and c <= sl_price:
        return {
            "type": "THUNG_SL",
            "timeframe": virtual_candle["timeframe"],
            "slot_id": virtual_candle["slot_id"],
            "current_price": c,
            "sl_price": round(sl_price, 2),
            "sl_source": "manual" if sl_manual is not None else "auto",
            "low": low,
            "high": h,
            "open": o,
            "shadow_pct": 0.0,
            "current_vol": vol,
            "vol_ratio_pct": 0.0,
            "tr_high": tr_high,
            "elapsed_minutes": virtual_candle.get("elapsed_minutes", 0),
            "slot_duration_minutes": virtual_candle.get("slot_duration_minutes", 0),
        }

    # --- Check B2: Upthrust (UTAD) ---
    # Price must be at or above TR high zone
    if h < tr_high_range[0]:
        return None

    upper_shadow = h - max(o, c)
    upper_shadow_pct = (upper_shadow / h * 100) if h > 0 else 0.0

    # Upper shadow >= 1.5% of High
    if upper_shadow < 0.015 * h:
        return None

    # Small body (body < 30% of candle range)
    body = abs(c - o)
    if candle_range > 0 and body >= 0.3 * candle_range:
        return None

    # Volume spike
    trimmed_mean = _calculate_trimmed_mean_volume(daily_history, periods=20)
    elapsed = virtual_candle.get("elapsed_minutes", 1)
    slot_duration = virtual_candle.get("slot_duration_minutes", 60)
    # Scale daily average volume to slot by using total daily trading minutes as base (240 for D1/H1, 255 for H4)
    tf = virtual_candle.get("timeframe", "H1")
    total_day_minutes = 255.0 if tf == "H4" else 240.0
    is_spike, vol_ratio_pct = _check_volume_spike(vol, trimmed_mean, elapsed, total_day_minutes, multiplier=1.3)

    if not is_spike:
        return None

    # Close must fall back below TR_High for a true Upthrust
    if c >= tr_high:
        return None

    return {
        "type": "UPTHRUST_BAY_GIA",
        "timeframe": virtual_candle["timeframe"],
        "slot_id": virtual_candle["slot_id"],
        "current_price": c,
        "low": low,
        "high": h,
        "open": o,
        "shadow_pct": round(upper_shadow_pct, 2),
        "current_vol": vol,
        "vol_ratio_pct": vol_ratio_pct,
        "trimmed_mean_vol": round(trimmed_mean, 0),
        "tr_high": tr_high,
        "elapsed_minutes": elapsed,
        "slot_duration_minutes": slot_duration,
    }
