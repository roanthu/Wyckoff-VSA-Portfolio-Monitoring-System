# Product Requirement Document (PRD)

## Project Name: Automated Wyckoff/VSA Portfolio Monitoring System (Serverless Architecture)

### 1. Bối cảnh & Mục tiêu (Context & Objective)

Hệ thống này được thiết kế để tự động giám sát danh mục cổ phiếu Việt Nam theo thời gian thực từng phút trong phiên giao dịch, dựa trên phương pháp **Wyckoff và VSA (Volume Spread Analysis)**.
Mục tiêu chính là phát hiện sớm các hành vi của dòng tiền lớn như **Spring (Rũ bỏ)** hoặc **Upthrust (Bẫy tăng giá)** trên khung thời gian **H1 và H4**, rồi gửi cảnh báo tức thì qua Telegram mà không cần đợi đóng nến.

### 2. Hạ tầng & Công nghệ mục tiêu (Target Infrastructure)

* **Ngôn ngữ:** Python 3.10+
* **Môi trường triển khai:** AWS Lambda hoặc Cloud VPS chạy định kỳ mỗi phút (cron).
* **Nguồn dữ liệu:** OpenAPI TCBS để lấy dữ liệu giá và khối lượng, ưu tiên nến 1-phút.
* **Đầu vào danh mục:** Google Sheets public CSV.
* **Thông báo:** Telegram Bot API.
* **Lưu trạng thái anti-spam:** In-memory dictionary trong thời gian chạy (RAM).
* **Triển khai:** Hỗ trợ cả Cloud VPS và Lambda-ready.

### 3. Cấu trúc Dữ liệu Đầu vào (Data Input Format)

Hệ thống đọc danh mục giám sát từ file CSV public từ Google Sheets.

Yêu cầu cột:

* `Ticker`: Mã cổ phiếu (Ví dụ: TCB, HPG, SSI).
* `Entry`: Giá vốn của người dùng.
* `SL_Manual`: Giá cắt lỗ thủ công. Nếu trống, hệ thống tính theo quy tắc tự động.
* `Status`: `WATCH` hoặc `HOLD`.

Ví dụ mẫu:

```csv
Ticker,Entry,SL_Manual,Status
TCB,48500,,WATCH
HPG,29200,28100,HOLD
SSI,36400,,HOLD
DIG,25000,23500,WATCH
VHM,42000,40500,HOLD
```

### 4. Thuật toán Xử lý Core Logic (Technical Specifications)

#### 4.1. Cơ chế gộp nến H1/H4 Giả lập Giữa phiên (Mid-bar Virtual Candle Generation)

Hệ thống chạy mỗi phút nên phải tự tổng hợp nến H1/H4 từ dữ liệu nến 1-phút:

* `Open`: giá mở cây lớn tại phút đầu khung.
* `High`: giá cao nhất trong khung từ đầu tới hiện tại.
* `Low`: giá thấp nhất trong khung từ đầu tới hiện tại.
* `Close`: giá khớp lệnh hiện tại.
* `Volume`: tổng volume tích lũy từ đầu khung tới hiện tại.

Thời gian cây lớn thực tế tại thị trường Việt Nam:

* H1: các cây có độ dài không đều do nghỉ trưa và ATC.
  * 09:15–10:15 = 60 phút
  * 10:15–11:30 = 75 phút
  * 13:00–14:00 = 60 phút
  * 14:00–14:45 = 45 phút
* H4: gộp thành 2 cây mỗi ngày, không phải 240 phút.
  * H4 sáng: 09:15–13:00 = 150 phút
  * H4 chiều: 13:00–14:45 = 105 phút

#### 4.2. Xác định Trading Range (Vùng tích lũy)

Trading range được xác định tự động từ dữ liệu lịch sử với thuật toán Swing High/Low kết hợp Volume:

* **Biên dưới (TR_Low):** mức Low thấp nhất trong N phiên trước, ưu tiên cây có Volume > 1.5 × MA20 Vol.
* **Biên trên (TR_High):** mức High của cú hồi AR đầu tiên sau điểm đáy.
* Mức biên dùng buffer ±0.5% để xử lý nhiễu giá.

Hàm cần có: `calculate_trading_range(ticker_data)` trả về `TR_High`, `TR_Low`.

#### 4.3. Logic Nhận diện Tín hiệu Wyckoff

##### A. Tín hiệu MUA: Spring (trạng thái `WATCH`)

Kích hoạt khi giá hiện tại tiếp cận biên dưới của Trading Range hoặc đáy thấp nhất.

1. **Râu nến dưới dài:**
   * Lower Shadow = min(Open, Close) - Low
   * Điều kiện OR:
     * Lower Shadow >= 1.5% × Low
     * Hoặc Lower Shadow >= 50% chiều dài cây nến (High - Low)
   * Ưu tiên kiểm tra: điều kiện 1 trước, nếu thỏa thì kích hoạt; nếu không thì kiểm tra điều kiện 2.
2. **Close** phải rút lên gần hỗ trợ hoặc nằm ở nửa trên của cây nến.
3. **Volume đột biến:**
   * Tính trung bình Vol 20 phiên trước bằng Trimmed Mean: loại bỏ phiên có volume lớn nhất rồi lấy mean của 19 giá trị còn lại.
   * Điều kiện:

```text
Volume tích lũy >= (MeanVol20 * t / Tổng_thời_gian) * 1.3
```

với `t` là số phút đã trôi qua trong cây H1/H4 hiện tại và `Tổng_thời_gian` là độ dài thực tế của cây đó.

##### B. Tín hiệu BÁN / Rủi ro (trạng thái `HOLD`)

1. **Thủng SL:**
   * Nếu Close <= SL_Manual, hoặc Close <= (Low của cây Spring thấp nhất trong N phiên) × 0.995.
2. **Upthrust (UTAD):**
   * Giá vượt đỉnh cũ nhưng cây H1/H4 giả lập có râu trên dài >= 1.5% và thân nhỏ, kèm volume lớn, rồi không tiếp tục tăng.

### 5. Luồng Vận hành Hệ thống (Workflow Execution)

Mỗi phút:

1. Đọc CSV Google Sheets public.
2. Lọc `WATCH` / `HOLD`.
3. Với mỗi mã, gọi OpenAPI TCBS lấy dữ liệu realtime và lịch sử.
4. Tính nến giả lập H1/H4 bằng dữ liệu 1-phút.
5. Tính Trading Range khi cần và kiểm tra logic Wyckoff.
6. Kiểm tra anti-spam: mỗi mã chỉ báo 1 lần/1 cây H1 hoặc H4.
7. Gửi Telegram nếu thỏa.

### 6. Yêu cầu định dạng thông báo Telegram (Output Telegram Format)

Tin nhắn cần rõ ràng và kỹ thuật:

```text
🚨 [CẢNH BÁO SỚM WYCKOFF - KHUNG KHUNG_GIO] 🚨
Mã cổ phiếu: **{Ticker}** (Trạng thái: {Status})

Tín hiệu phát hiện: **{SPRING_RUT_CHAN / UPTHRUST_BAY_GIA / THUNG_SL}**
- Giá hiện tại: {Close}
- Giá thấp nhất trong phiên: {Low} (Độ dài râu nến: {Shadow_Percentage}%)
- Khối lượng hiện tại: {Current_Vol} (Vượt {Vol_Ratio}% so với trung bình)

🎯 Hành động khuyến nghị: {Hành động tương ứng với chiến lược}
Thời gian ghi nhận: {Giờ_Phút_Giây}
```

### 7. Yêu cầu về Code & Xử lý ngoại lệ (Code Quality & Exception Handling)

* **Clean Code:** Chia rõ chức năng (`read_database`, `get_market_data`, `calculate_virtual_candle`, `calculate_trading_range`, `check_wyckoff_logic`, `send_telegram`).
* **Error Handling:** `try/except` quanh toàn bộ lượt gọi API `vnstock` và Telegram.
* **Retry/backoff:** Retry tối đa 3 lần cho mỗi call API với 2/4/8 giây.
* **Admin alert:** Nếu toàn bộ luồng quét fail 5 lần liên tiếp, gửi Telegram cảnh báo admin.
* **Bảo mật:** Đọc token qua `os.environ.get()`.

### 8. Mẫu dữ liệu đầu vào

```csv
Ticker,Entry,SL_Manual,Status
TCB,48500,,WATCH
HPG,29200,28100,HOLD
SSI,36400,,HOLD
DIG,25000,23500,WATCH
VHM,42000,40500,HOLD
```

---

**Yêu cầu dành cho Claude:** *"Hãy viết một file script Python hoàn chỉnh, tối ưu, sẵn sàng deploy dựa trên các yêu cầu chi tiết trong bản PRD trên."*
