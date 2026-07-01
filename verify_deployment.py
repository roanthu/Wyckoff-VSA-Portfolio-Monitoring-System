import os
import sys
import datetime
from src.market_api_adapter import create_market_data_provider
from src.monitor import create_monitor

def verify():
    print("="*50)
    print("[START] BAT DAU KIEM TRA MOI TRUONG DEPLOYMENT VPS")
    print("="*50)

    # 1. Check environment variables
    print("\n[1/3] Kiem tra Environment Variables...")
    api_key = os.environ.get("DNSE_API_KEY")
    secret_key = os.environ.get("DNSE_SECRET_KEY")
    if not api_key or not secret_key:
        print("[FAIL] Thieu DNSE_API_KEY hoac DNSE_SECRET_KEY trong file .env!")
        sys.exit(1)
    else:
        print(f"[OK] DNSE_API_KEY da thiet lap (Bat dau voi: {api_key[:5]}...)")

    # 2. Check DNSE Connection & Time Sync
    print("\n[2/3] Kiem tra ket noi DNSE API & Time Sync...")
    try:
        provider = create_market_data_provider("dnse")
        print("Dang lay Snapshot gia cho FPT...")
        snap = provider.get_snapshot(["FPT"])
        if "FPT" in snap and snap["FPT"]["currentPrice"] is not None:
            print(f"[OK] Lay gia thanh cong! Gia hien tai FPT: {snap['FPT']['currentPrice']}")
        else:
            print("[WARN] Lay duoc du lieu nhung khong co gia (Co the ngoai gio giao dich).")
        
        if hasattr(provider, '_time_delta'):
            print(f"[OK] Time Sync hoat dong tot! Do lech thoi gian VPS vs DNSE: {provider._time_delta} giay.")
    except Exception as e:
        print(f"[FAIL] Loi ket noi DNSE API: {e}")
        sys.exit(1)

    # 3. Check Monitor Cycle
    print("\n[3/3] Chay thu mot vong Monitor (Dry-run)...")
    try:
        monitor = create_monitor()
        monitor.default_watchlist = [{"ticker": "FPT", "entry": None, "sl_manual": None, "status": "WATCH"}]
        monitor.watchlist_url = None
        
        monitor.run_cycle()
        print("[OK] Vong lap Monitor chay thanh cong khong gap loi Exception nao.")
    except Exception as e:
        print(f"[FAIL] Vong lap Monitor gap loi: {e}")
        sys.exit(1)

    print("\n" + "="*50)
    print("[SUCCESS] TAT CA CAC BAI KIEM TRA DEU VUOT QUA!")
    print("VPS cua ban da san sang de chay Bot lau dai.")
    print("="*50)

if __name__ == "__main__":
    from draw_chart import load_env_file
    load_env_file()
    verify()
