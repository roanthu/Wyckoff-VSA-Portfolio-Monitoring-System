# Wyckoff VSA Portfolio Monitoring

Một scaffold Python để giám sát dữ liệu thị trường TCBS, tính biên Trading Range theo phong cách Wyckoff và gửi cảnh báo qua Telegram.

## Chức năng chính

- lấy giá hiện tại từ API snapshot của TCBS
- tính `TR_High` / `TR_Low` từ dữ liệu D1 lịch sử
- gửi cảnh báo khi giá chạm TR low hoặc vượt TR high
- gửi thông báo qua Telegram
- lưu trạng thái cảnh báo trong bộ nhớ và reset hàng ngày
- gửi cảnh báo admin qua Telegram khi 5 chu kỳ liên tiếp gặp lỗi

## Các tệp cần thiết

- `src/market_api_adapter.py` — adapter REST cho TCBS OpenAPI
- `src/wyckoff.py` — logic xác định Trading Range và nến ảo
- `src/monitor.py` — luồng giám sát chính và xử lý cảnh báo
- `src/scheduler.py` — vòng lặp chạy mỗi 60s
- `src/sample_run.py` — chạy một lần thử nghiệm
- `lambda_handler.py` — entrypoint cho AWS Lambda

## Cấu trúc project và cách chạy

### Cấu trúc thư mục chính

- `src/market_api_adapter.py`: gom các API call tới TCBS.
- `src/wyckoff.py`: tính biên Trading Range, nến H1/H4 ảo và điều kiện Wyckoff.
- `src/monitor.py`: hàm `MarketMonitor` kiểm tra giá, tính TR và ra alert.
- `src/scheduler.py`: chạy vòng lặp và gọi `MarketMonitor.run_cycle()` mỗi 60s.
- `src/sample_run.py`: chạy một chu kỳ kiểm thử duy nhất.
- `lambda_handler.py`: entrypoint Lambda, thực hiện một chu kỳ rồi dừng.
- `tests/`: chứa unit tests cho logic và monitor.

### Dòng chạy chính

1. Scheduler (trên VPS hoặc máy chủ):
   - `python -m src.scheduler`
   - mỗi 60s chạy một chu kỳ monitor
   - gọi TCBS snapshot để lấy giá hiện tại
   - nạp dữ liệu D1 và tính `TR_High` / `TR_Low`
   - so sánh giá với vùng TR để gửi cảnh báo

2. Chạy mẫu một lần:
   - `python src/sample_run.py`
   - chỉ thực hiện một chu kỳ kiểm tra

3. Lambda:
   - `lambda_handler.handler`
   - thực hiện một chu kỳ rồi kết thúc

### Luồng dữ liệu

- Giá hiện tại được lấy từ TCBS qua `market_api_adapter.get_snapshot()`.
- Dữ liệu D1 lịch sử được đọc từ `HISTORICAL_D1_CSV_URL`.
- `wyckoff.calculate_trading_range()` trả về `TR_High`, `TR_Low` và vùng biên.
- `monitor.MarketMonitor.run_cycle()` kiểm tra giá hiện tại với vùng TR và gọi `telegram_alerts.send_telegram()` khi cần.
- Trạng thái cảnh báo lưu trong bộ nhớ để tránh spam trong cùng ngày.

## Biến môi trường

Thiết lập các biến sau trước khi chạy:

- `TCBS_API_BASE_URL` (tùy chọn) — mặc định: `https://openapi.tcbs.com.vn`
- `TCBS_API_KEY` — API key để truy cập OpenAPI TCBS
- `WATCHLIST_CSV_URL` (tùy chọn) — URL CSV công khai chứa danh sách mã; nên có cột `symbol`
- `HISTORICAL_D1_CSV_URL` (tùy chọn) — URL CSV công khai chứa dữ liệu lịch sử D1 với các cột `symbol`, `date`, `open`, `high`, `low`, `close`, `volume`
- `TELEGRAM_BOT_TOKEN` — token bot Telegram để gửi cảnh báo
- `TELEGRAM_ALERT_CHAT_ID` (tùy chọn) — chat id để gửi cảnh báo giao dịch; nếu không có sẽ dùng `TELEGRAM_ADMIN_CHAT_ID`
- `TELEGRAM_ADMIN_CHAT_ID` — chat id để gửi cảnh báo admin
- `TR_LOOKBACK` (tùy chọn) — số phiên dùng để tính Trading Range, mặc định `60`

## Cài đặt

Cài đặt phụ thuộc bằng pip:

```bash
python -m pip install -r requirements.txt
```

## Chạy local

Khởi chạy monitor dạng vòng lặp, kiểm tra mỗi 60 giây:

```bash
python -m src.scheduler
```

## Chạy thử một lần

Dùng khi muốn chạy kiểm thử một chu kỳ mà không cần vòng lặp:

```bash
python src/sample_run.py
```

## Triển khai AWS Lambda

Dùng `lambda_handler.handler` làm entrypoint cho Lambda.

Hàm Lambda sẽ thực hiện một chu kỳ giám sát rồi kết thúc.

### Biến môi trường đề xuất cho Lambda

- `TCBS_API_KEY`
- `WATCHLIST_CSV_URL` hoặc `HISTORICAL_D1_CSV_URL`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ADMIN_CHAT_ID`
- `TR_LOOKBACK` (tùy chọn)

## Chạy kiểm thử

Chạy unit tests với:

```bash
python -m unittest discover tests
```

## Ghi chú

- Nếu `WATCHLIST_CSV_URL` không được cấu hình, scheduler sẽ dùng danh sách mặc định: `TCB`, `HPG`, `SSI`, `VHM`, `VCB`.
- Nếu không có `HISTORICAL_D1_CSV_URL`, cảnh báo TR sẽ bị bỏ qua.
- Nếu thiếu chat id Telegram, hệ thống vẫn in log nhưng sẽ không gửi cảnh báo.
