# TCBS OpenAPI Documentation — Sử dụng cho hệ thống giám sát Wyckoff/VSA

Tài liệu này tóm tắt những gì cần biết để dùng OpenAPI của TCBS trong dự án tự động quét thị trường Việt Nam.

## 1. Mục tiêu chính

* Dùng OpenAPI TCBS để lấy dữ liệu giá và khối lượng theo khung 1-phút.
* Tích hợp vào script Python chạy mỗi phút.
* Dùng dữ liệu này để tổng hợp nến H1/H4 giả lập và tính toán tín hiệu Spring/Upthrust.

## 2. Cài đặt

```bash
pip install -U requests pandas
```

## 3. Cách lấy dữ liệu 1-phút từ TCBS OpenAPI

### Tổng quan

TCBS OpenAPI cung cấp endpoint lấy dữ liệu thị trường theo từng phút. Thông thường bạn sẽ cần:

* `API_BASE_URL` của TCBS.
* `API_KEY` hoặc `token` do TCBS cấp.
* Tham số `symbol`, `resolution`, `from`, `to`.

### Ví dụ mẫu

```python
import os
import requests
import pandas as pd

API_BASE_URL = os.environ.get('TCBS_API_BASE_URL')
API_KEY = os.environ.get('TCBS_API_KEY')

headers = {
    'Authorization': f'Bearer {API_KEY}',
    'Accept': 'application/json',
}

params = {
    'symbol': 'SSI',
    'resolution': '1',
    'from': '2026-06-01T00:00:00',
    'to': '2026-06-20T23:59:59',
}

response = requests.get(f'{API_BASE_URL}/marketdata/ohlcv', headers=headers, params=params)
response.raise_for_status()

raw_data = response.json()

df_minute = pd.DataFrame(raw_data)
print(df_minute.head())
```

> Lưu ý: endpoint và tham số có thể thay đổi tùy cấu hình API TCBS. Hãy dùng tài liệu TCBS OpenAPI chính thức nếu có sẵn.

## 4. Lưu ý quan trọng

* Dữ liệu 1-phút thường được giới hạn theo chính sách TCBS.
* Khi lấy dữ liệu, chỉ tải dữ liệu cho các mã trong danh mục để tiết kiệm hạn mức.
* Nếu API TCBS trả về dữ liệu JSON thô, hãy chuyển sang DataFrame Pandas để dễ xử lý.

## 5. Khuyến nghị dùng trong dự án

* `get_market_data(ticker, start, end, interval='1m')` nên dùng TCBS OpenAPI.
* Dữ liệu trả về phải có đầy đủ cột: `open`, `high`, `low`, `close`, `volume`, `datetime`.
* Lưu API key trong biến môi trường, không hardcode.

## 6. Gợi ý tích hợp

* Thực hiện retry/backoff khi call API TCBS thất bại.
* Chuyển dữ liệu API sang Pandas DataFrame trước khi tổng hợp nến H1/H4.
* Nếu TCBS không hỗ trợ trực tiếp `1m`, có thể dùng dữ liệu nội bộ hoặc chuyển đổi từ nguồn phù hợp.

## 7. Nội dung đã loại bỏ

* Tài liệu về `vnstock` không còn phù hợp.
* Các phần về chỉ số tài chính không cần thiết cho workflow real-time.
