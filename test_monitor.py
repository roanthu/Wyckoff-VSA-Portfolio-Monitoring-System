import os
from src.monitor import create_monitor

def test_monitor():
    print("Testing monitor flow...")
    monitor = create_monitor()
    # Force watchlist to just 1 ticker for testing
    monitor.default_watchlist = [{"ticker": "FPT", "entry": None, "sl_manual": None, "status": "WATCH"}]
    monitor.watchlist_url = None
    monitor.run_cycle()
    print("Monitor flow completed successfully!")

if __name__ == "__main__":
    from draw_chart import load_env_file
    load_env_file()
    test_monitor()
