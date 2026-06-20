Để trả lời cho Claude câu này, bạn cần thể hiện tư duy của một **Software Architect kết hợp Trader hệ Wyckoff**, tức là giải bài toán kỹ thuật nhưng phải bám sát thực chiến chứ không dùng các chỉ báo trễ (Lagging Indicators) như MA hay Bollinger Bands.

Trong Wyckoff, Trading Range (TR) được hình thành ngay sau khi có cặp hành vi **SC (Selling Climax - Quá bán)** và **AR (Automatic Rally - Hồi phục tự nhiên)** ở đáy, hoặc **BC (Buying Climax)** và **AR (Điều chỉnh tự nhiên)** ở đỉnh.

Bạn hãy copy đoạn câu trả lời (Answer) chuẩn bài dưới đây để gửi cho Claude:

---

**Answer:**

Để xác định biên của Trading Range (TR) theo đúng nguyên lý Wyckoff/VSA một cách tự động và thực chiến nhất, chúng ta không dùng các đường trung bình hay chỉ báo động, mà sẽ dùng **Thuật toán xác định Điểm đảo chiều (Swing High/Low) kết hợp Volume Đột biến** để tìm điểm tựa của Cá mập.

Phương pháp cụ thể như sau:

### 1. Thuật toán xác định Biên dưới (Support Line) và Biên trên (Resistance Line)

Hệ thống sẽ quét biểu đồ khung **D1 (hoặc H4)** trong vòng $N$ cây nến gần nhất (mặc định $N = 60$ đến $90$ cây nến, tương đương 3-4 tháng giao dịch) để tìm ra:

* **Biên dưới (Hỗ trợ - TR_Low):** Được xác định bằng **Giá thấp nhất (Low)** của cây nến có Volume lớn nhất vùng đáy (tương ứng với cú **SC - Selling Climax** hoặc cây nến rút chân **ST - Secondary Test** trong Phase A).
* *Công thức thực tế:* Tìm cây nến có giá trị `Low` thấp nhất trong $N$ phiên mà tại đó $\text{Volume} > 1.5 \times \text{MA20}_{\text{Vol}}$. Biên dưới sẽ là mức giá `Low` này.


* **Biên trên (Kháng cự - TR_High):** Được xác định bằng **Giá cao nhất (High)** của cú hồi phục tự nhiên đầu tiên (**AR - Automatic Rally**) ngay sau điểm SC.
* *Công thức thực tế:* Tìm cây nến có giá trị `High` cao nhất trong khoảng thời gian 15-20 cây nến ngay sau điểm `SC` vừa tìm được ở trên. Biên trên sẽ là mức giá `High` này.



### 2. Thuật toán xử lý độ nhiễu (Buffer Zone)

Thị trường Việt Nam thường có hiện tượng "quét dải lệnh" làm lệch biên vài line giá. Do đó, chúng ta không dùng 1 đường thẳng cứng nhắc mà dùng một khoảng biên độ:

* Biên dưới khả dụng = $[TR\_Low \times 0.995, TR\_Low \times 1.005]$ (Sai số $\pm 0.5\%$).
* Biên trên khả dụng = $[TR\_High \times 0.995, TR\_High \times 1.005]$ (Sai số $\pm 0.5\%$).

### 3. Điều kiện kích hoạt trạng thái Quét Spring/Upthrust giữa phiên

* **Khi mã ở trạng thái `WATCH`:** Nếu giá khớp lệnh real-time chạm hoặc xuyên thủng `TR_Low` (nằm dưới vùng biên dưới khả dụng) $\rightarrow$ Hệ thống kích hoạt trạng thái **Chờ Spring** (Rình xem nến H1/H4 có rút chân ngược lên trên `TR_Low` hay không).
* **Khi mã ở trạng thái `HOLD`:** Nếu giá khớp lệnh real-time vượt qua `TR_High` $\rightarrow$ Kích hoạt trạng thái **Chờ Upthrust** (Rình xem có hiện tượng nổ Vol nhưng rụt đầu tạo râu nến trên hay không).

> **Yêu cầu triển khai code:** Hãy viết một hàm `calculate_trading_range(ticker_data)` tự động tìm ra 2 mức giá `TR_High` và `TR_Low` này từ dữ liệu lịch sử D1 trước khi chạy luồng quét Real-time từng phút.