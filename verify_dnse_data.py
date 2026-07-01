import os
import datetime
from src.market_api_adapter import create_market_data_provider

def load_env_file():
    if os.path.exists(".env"):
        with open(".env", "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip()

def verify():
    load_env_file()
    print("Khởi tạo kết nối đến DNSE API...")
    # Khởi tạo adapter kết nối DNSE (tự động lấy key từ .env)
    provider = create_market_data_provider("dnse")
    
    # Chọn một mã cổ phiếu quốc dân để test, ví dụ FPT hoặc HPG
    ticker = "FPT"
    print(f"\n==============================================")
    print(f"  KIỂM TRA DỮ LIỆU TỪ DNSE CHO MÃ: {ticker}  ")
    print(f"==============================================\n")
    
    # 1. Kiểm tra Snapshot (Giá khớp lệnh gần nhất)
    print("[1] Đang kéo giá khớp lệnh gần nhất (Snapshot)...")
    try:
        snapshot = provider.get_snapshot([ticker])
        data = snapshot.get(ticker, {})
        
        if data.get("currentPrice"):
            print(f" ✅ Lấy thành công!")
            print(f"    - Giá khớp gần nhất: {data.get('price')} VND")
            print(f"    - Khối lượng khớp  : {data.get('volume')} cổ phiếu")
        else:
            print(f" ❌ Dữ liệu trống hoặc ngoài giờ giao dịch: {snapshot}")
    except Exception as e:
        print(f" ❌ Lỗi khi lấy Snapshot: {e}")
    
    # 2. Kiểm tra dữ liệu nến OHLC (Nến 1 ngày)
    print("\n[2] Đang kéo nến D1 (Ngày) để so sánh giá Đóng/Mở cửa...")
    try:
        now = datetime.datetime.now()
        start = now - datetime.timedelta(days=7) # Lấy 1 tuần gần nhất
        df = provider.get_historical_data(ticker, "1D", start, now)
        
        if not df.empty:
            last_candle = df.iloc[-1]
            print(f" ✅ Lấy thành công nến ngày {last_candle['time']}!")
            print(f"    - Mở cửa (Open)   : {last_candle['open']}")
            print(f"    - Cao nhất (High) : {last_candle['high']}")
            print(f"    - Thấp nhất (Low) : {last_candle['low']}")
            print(f"    - Đóng cửa (Close): {last_candle['close']}")
            print(f"    - Khối lượng (Vol): {last_candle['volume']}")
        else:
            print(" ❌ Không có dữ liệu nến.")
    except Exception as e:
        print(f" ❌ Lỗi khi lấy nến: {e}")
        
    print("\n==============================================")
    print("👉 BƯỚC TIẾP THEO: ")
    print(f"Hãy mở App DNSE (EntradeX) hoặc bảng điện FireAnt lên.")
    print(f"Mở biểu đồ mã {ticker} và so sánh các con số Giá/Volume")
    print(f"vừa in ra ở trên xem có khớp 100% không nhé!")
    print("==============================================\n")

if __name__ == "__main__":
    verify()
