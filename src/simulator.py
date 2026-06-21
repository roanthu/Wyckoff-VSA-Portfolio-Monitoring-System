from __future__ import annotations
import os
import pandas as pd
import numpy as np
from typing import Any

from .backtest import WyckoffBacktester

class WyckoffTradeSimulator:
    """Simulates trading based on detected Wyckoff Spring signals."""

    # Vietnamese market transaction costs
    EXCHANGE_FEE_RATE = 0.0003  # 0.03% exchange regulation fee per side
    COMMISSION_RATE = 0.0       # 0% brokerage fee (commission)
    SELLING_TAX = 0.001         # 0.1% selling tax
    SLIPPAGE_RATE = 0.001       # 0.1% estimated slippage per side

    def __init__(self) -> None:
        self.backtester = WyckoffBacktester()

    def run_simulation(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        initial_nav: float = 100_000_000.0,
        risk_pct: float = 0.02,  # Risk at most 2% of NAV per trade
        rr_ratio: float = 3.0,   # Default to 3.0 Risk-to-Reward ratio
        timeframe_mode: str = "ALL",
        tr_lookback: int = 60,
    ) -> dict[str, Any]:
        """Runs a trade simulation for a ticker over a date range.

        Args:
            ticker: Stock symbol (e.g. "HPG")
            start_date: Start date of simulation (YYYY-MM-DD)
            end_date: End date of simulation (YYYY-MM-DD)
            initial_nav: Starting cash/portfolio value in VND
            risk_pct: Percentage of NAV to risk per trade (e.g. 0.02 = 2%)
            rr_ratio: Reward-to-Risk ratio for Take Profit targets
            timeframe_mode: "ALL" or "D1"
            tr_lookback: Lookback days for baseline Trading Range calculation

        Returns:
            Dict containing trade logs and summary metrics.
        """
        # 1. Run backtest to get Spring (Buy) signals
        # Spring signals occur under WATCH status
        try:
            signals = self.backtester.run_backtest(
                ticker=ticker,
                start_date=start_date,
                end_date=end_date,
                status="WATCH",
                use_cache=True,
                timeframe_mode=timeframe_mode,
                tr_lookback=tr_lookback,
            )
        except Exception as exc:
            return {"error": f"Failed to run backtest: {str(exc)}"}

        spring_signals = [
            s for s in signals if s.get("type") == "SPRING_RUT_CHAN"
        ]
        
        # Sort signals by date and slot time
        time_slots = {
            "H1_1": 1, "H1_2": 2, "H1_3": 3, "H1_4": 4,
            "H4_AM": 1.5, "H4_PM": 4.5, "D1": 5
        }
        spring_signals.sort(
            key=lambda x: (x["date"], time_slots.get(x.get("slot_id", "D1"), 5))
        )

        # 2. Load daily price history for tracking exits
        daily_path = os.path.join("data_cache", ticker, "daily.csv")
        if not os.path.exists(daily_path):
            return {"error": f"Daily price cache for {ticker} not found."}
        
        df_daily = pd.read_csv(daily_path)
        df_daily["time"] = pd.to_datetime(df_daily["time"])
        df_daily = df_daily.sort_values("time").reset_index(drop=True)

        current_nav = initial_nav
        trades = []
        active_trade = None
        nav_history = [{"date": start_date, "nav": initial_nav}]

        # Consecutive loss tracking & Cooldown for Fix C
        consecutive_losses = 0
        cooldown_until_idx = -1

        # Keep track of daily NAV for drawdown calculations
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        trading_dates = df_daily[
            (df_daily["time"] >= start_dt) & (df_daily["time"] <= end_dt)
        ]["time"].unique()
        
        trading_dates = sorted(trading_dates)

        # 3. Simulation loop day-by-day
        for day_idx, current_day in enumerate(trading_dates):
            current_day_str = pd.to_datetime(current_day).strftime("%Y-%m-%d")
            
            # A. Check if current active trade exits on this day
            if active_trade is not None:
                day_bar = df_daily[df_daily["time"] == current_day]
                if not day_bar.empty:
                    low_val = float(day_bar.iloc[0]["low"])
                    high_val = float(day_bar.iloc[0]["high"])
                    
                    sl = active_trade["sl"]
                    tp = active_trade["tp"]
                    shares = active_trade["shares"]
                    entry_price = active_trade["entry_price"]

                    exited = False
                    exit_price = None
                    result = None

                    # Check if hit SL and TP on the same day (conservative: assume SL hit)
                    if low_val <= sl and high_val >= tp:
                        exited = True
                        exit_price = sl
                        result = "LOSS"
                    elif low_val <= sl:
                        exited = True
                        exit_price = sl
                        result = "LOSS"
                    elif high_val >= tp:
                        exited = True
                        exit_price = tp
                        result = "WIN"
                    
                    if exited:
                        # Transaction costs: exchange fee + commission + tax + slippage
                        buy_cost = shares * entry_price * (self.EXCHANGE_FEE_RATE + self.COMMISSION_RATE + self.SLIPPAGE_RATE)
                        sell_cost = shares * exit_price * (self.EXCHANGE_FEE_RATE + self.COMMISSION_RATE + self.SLIPPAGE_RATE + self.SELLING_TAX)
                        total_fees = buy_cost + sell_cost
                        pnl_vnd = shares * (exit_price - entry_price) - total_fees
                        pnl_pct = pnl_vnd / (shares * entry_price) * 100
                        current_nav += pnl_vnd
                        
                        active_trade.update({
                            "exit_date": current_day_str,
                            "exit_price": round(exit_price, 2),
                            "result": result,
                            "pnl_vnd": round(pnl_vnd, 0),
                            "pnl_pct": round(pnl_pct, 2),
                            "fees_vnd": round(total_fees, 0),
                            "ending_nav": round(current_nav, 0)
                        })
                        trades.append(active_trade)
                        active_trade = None

                        # Fix C: Track consecutive losses
                        if result == "LOSS":
                            consecutive_losses += 1
                            if consecutive_losses >= 2:
                                cooldown_until_idx = day_idx + 30
                                consecutive_losses = 0  # Reset counter after triggering cooldown
                        elif result == "WIN":
                            consecutive_losses = 0

            # B. Check for new entry signals on this day (only if no active trade and not in cooldown)
            if active_trade is None:
                if day_idx <= cooldown_until_idx:
                    # Fix C: Skip signal if in cooldown period (after 2 consecutive losses)
                    pass
                else:
                    day_signals = [s for s in spring_signals if s["date"] == current_day_str]
                    if day_signals:
                        sig = day_signals[0]
                        entry_price = float(sig["current_price"])

                        # SL is 0.5% below the low of the Spring candle
                        sl_price = float(sig["low"]) * 0.995
                        risk_per_share = entry_price - sl_price

                        if risk_per_share > 0:
                            # Target TP is based on fixed R:R ratio (Fix A)
                            tp_price = entry_price + (rr_ratio * risk_per_share)

                        # Position sizing based on Option B (2% of current NAV risk)
                        risk_cash = current_nav * risk_pct
                        shares = int(risk_cash / risk_per_share)
                        
                        # HOSE lot size rounding
                        shares = (shares // 100) * 100
                        
                        # Check capital constraint
                        max_allowed_shares = int(current_nav / entry_price)
                        max_allowed_shares = (max_allowed_shares // 100) * 100
                        
                        if shares > max_allowed_shares:
                            shares = max_allowed_shares

                        if shares >= 100:
                            entry_cost = shares * entry_price
                            active_trade = {
                                "ticker": ticker,
                                "entry_date": current_day_str,
                                "entry_price": entry_price,
                                "sl": round(sl_price, 2),
                                "tp": round(tp_price, 2),
                                "shares": shares,
                                "cost": round(entry_cost, 0),
                                "risk_per_share": round(risk_per_share, 2),
                                "exit_date": "Holding",
                                "exit_price": 0.0,
                                "result": "HOLD",
                                "pnl_vnd": 0.0,
                                "pnl_pct": 0.0,
                                "starting_nav": round(current_nav, 0),
                                "ending_nav": round(current_nav, 0)
                            }

            # C. Record NAV history for the day (mark-to-market)
            mtm_nav = current_nav
            if active_trade is not None:
                day_bar = df_daily[df_daily["time"] == current_day]
                if not day_bar.empty:
                    mtm_price = float(day_bar.iloc[0]["close"])
                    unrealized = active_trade["shares"] * (mtm_price - active_trade["entry_price"])
                    mtm_nav = current_nav + unrealized
            nav_history.append({
                "date": current_day_str,
                "nav": round(mtm_nav, 0)
            })

        # 4. If backtest ends and we are still holding an active trade, force exit at last close
        if active_trade is not None:
            if not df_daily.empty:
                # Filter to only data within the simulation period to avoid look-ahead
                df_in_range = df_daily[df_daily["time"] <= end_dt]
                last_row = df_in_range.iloc[-1] if not df_in_range.empty else df_daily.iloc[-1]
                exit_price = float(last_row["close"])
                exit_date_str = pd.to_datetime(last_row["time"]).strftime("%Y-%m-%d")
            else:
                exit_price = active_trade["entry_price"]
                exit_date_str = end_date
                
            entry_price = active_trade["entry_price"]
            shares = active_trade["shares"]
            
            buy_cost = shares * entry_price * (self.EXCHANGE_FEE_RATE + self.COMMISSION_RATE + self.SLIPPAGE_RATE)
            sell_cost = shares * exit_price * (self.EXCHANGE_FEE_RATE + self.COMMISSION_RATE + self.SLIPPAGE_RATE + self.SELLING_TAX)
            total_fees = buy_cost + sell_cost
            pnl_vnd = shares * (exit_price - entry_price) - total_fees
            pnl_pct = pnl_vnd / (shares * entry_price) * 100
            current_nav += pnl_vnd
            
            active_trade.update({
                "exit_date": exit_date_str,
                "exit_price": round(exit_price, 2),
                "result": "HOLD",
                "pnl_vnd": round(pnl_vnd, 0),
                "pnl_pct": round(pnl_pct, 2),
                "fees_vnd": round(total_fees, 0),
                "ending_nav": round(current_nav, 0)
            })
            trades.append(active_trade)
            active_trade = None

        # 5. Calculate summary metrics
        total_trades = len(trades)
        wins = sum(1 for t in trades if t["result"] == "WIN")
        losses = sum(1 for t in trades if t["result"] == "LOSS")
        holds = sum(1 for t in trades if t["result"] == "HOLD")

        win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0.0
        
        # Net Return
        net_return_vnd = current_nav - initial_nav
        net_return_pct = (net_return_vnd / initial_nav) * 100
        
        # Average Win vs Average Loss
        win_trades = [t["pnl_pct"] for t in trades if t["result"] == "WIN"]
        loss_trades = [t["pnl_pct"] for t in trades if t["result"] == "LOSS"]
        
        avg_win_pct = float(np.mean(win_trades)) if win_trades else 0.0
        avg_loss_pct = float(np.mean(loss_trades)) if loss_trades else 0.0
        
        # Profit Factor
        gross_profit = sum(t["pnl_vnd"] for t in trades if t["pnl_vnd"] > 0)
        gross_loss = abs(sum(t["pnl_vnd"] for t in trades if t["pnl_vnd"] < 0))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 1.0)

        # Max Drawdown
        navs = [h["nav"] for h in nav_history]
        peaks = np.maximum.accumulate(navs)
        drawdowns = (peaks - navs) / peaks * 100
        max_drawdown = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

        summary = {
            "ticker": ticker,
            "start_date": start_date,
            "end_date": end_date,
            "initial_nav": initial_nav,
            "ending_nav": round(current_nav, 0),
            "net_return_vnd": round(net_return_vnd, 0),
            "net_return_pct": round(net_return_pct, 2),
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "holds": holds,
            "win_rate": round(win_rate, 2),
            "avg_win_pct": round(avg_win_pct, 2),
            "avg_loss_pct": round(avg_loss_pct, 2),
            "profit_factor": round(profit_factor, 2),
            "max_drawdown_pct": round(max_drawdown, 2),
            "trades": trades,
            "nav_history": nav_history
        }

        return summary
