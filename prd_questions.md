# PRD — Câu hỏi cần trả lời và các điểm đã rõ

Hướng dẫn: với mỗi mục bên dưới, nếu là "Câu hỏi" hãy viết câu trả lời ngay bên dưới dòng `Answer:`. Nếu mục đã rõ thì tôi đã chuyển nó thành "Điểm đã rõ" — không cần trả lời.

---

## Điểm đã rõ (không cần trả lời)

- **Ngôn ngữ:** Python 3.10+
- **Môi trường triển khai mục tiêu:** AWS Lambda hoặc Cloud VPS (cron)
- **Định dạng danh mục đầu vào:** file CSV (Google Sheets/Excel Online xuất ra CSV) với cột `Ticker`, `Entry`, `SL_Manual`, `Status` (giá trị: `WATCH` hoặc `HOLD`)
- **Cách giả lập nến H1/H4 giữa phiên:** lấy nến 1-phút (hoặc 5-phút) từ thời điểm bắt đầu khung tới phút hiện tại; Open = giá phút đầu, High = max, Low = min, Close = last price, Volume = tổng tích lũy.
- **Template thông báo Telegram:** đã có mẫu trong PRD; sẽ gửi các trường: Ticker, Status, Tín hiệu, Giá hiện tại, Low, Shadow_Percentage, Current_Vol, Vol_Ratio, Hành động khuyến nghị, Thời gian.
- **Yêu cầu code & bảo mật:** tách hàm rõ ràng (`read_database`, `get_market_data`, `calculate_virtual_candle`, `check_wyckoff_logic`, `send_telegram`); `try/except` cho API calls; không hardcode tokens (đọc từ `os.environ`).

---

## Câu hỏi cần bạn trả lời (hãy điền `Answer:` dưới mỗi câu)

1) Dữ liệu real-time:
   - Câu hỏi: `vnstock` có đang được bạn dùng để lấy dữ liệu real-time 1-phút không? Nếu không, bạn có API cung cấp real-time (với key/chi tiết) hay muốn dùng dữ liệu delayed?
   - Answer:đọc fiel vnstock.md xem đã đủ chưa, review file nếu thấy tài liệu thừa, lặp thì tinh chỉnh

2) Quyền truy cập file danh mục:
   - Câu hỏi: file Google Sheets/Excel là public CSV hay private? Nếu private, bạn sẽ cung cấp OAuth/service-account JSON hay muốn sử dụng API key? (hoặc dùng link CSV public)
   - Answer: public hoàn toàn https://docs.google.com/spreadsheets/d/1soV43t1hCU-FnHO_ujDgHhr0-8Mk28qS_DHaQcoNYqU/edit?hl=vi&gid=0#gid=0

3) Phát hiện Trading Range (vùng tích lũy):
   - Câu hỏi: bạn có thuật toán/tư duy cụ thể để xác định biên trên/biên dưới của trading range không? (ví dụ: swing high/low trong N cây, hoặc dùng ATR, hoặc fixed % từ đỉnh/đáy). Nếu không, tôi sẽ đề xuất một phương pháp mặc định.
   - Answer: tôi trả lời trong C:\DATA\project\Wyckoff-VSA-Portfolio-Monitoring-System\trading-range.md

4) Thời khung nến để tổng hợp:
   - Câu hỏi: muốn dùng nến nguồn là `1-phút` hay `5-phút` khi build nến H1/H4? (1-phút chính xác hơn nhưng cần nhiều calls/memory)
   - Answer: 1 phút, để ra cấu hình

5) Công thức Volume tích lũy:
   - Câu hỏi: trong công thức PRD, `t` là số phút đã trôi qua trong cây nến lớn; `Tổng thời gian của khung nến` là bao nhiêu (H1 = 60 phút, H4 = 240 phút)? Xác nhận.
   - Answer:
   1. Đối với Khung H1 (Nến 1 giờ)Một ngày có 4 cây nến H1, nhưng thời gian chạy của chúng không đều nhau do vướng giờ nghỉ trưa và phiên ATC:Cây nến 1 (9:15 - 10:15): Chạy đúng 60 phút. $\rightarrow$ Tổng thời gian = 60.Cây nến 2 (10:15 - 11:30): Chạy 75 phút (bao gồm 15 phút lẻ cuối phiên sáng). $\rightarrow$ Tổng thời gian = 75.Cây nến 3 (13:00 - 14:00): Chạy đúng 60 phút. $\rightarrow$ Tổng thời gian = 60.Cây nến 4 (14:00 - 14:45): Chỉ chạy 45 phút (bao gồm cả 15 phút phiên ATC). $\rightarrow$ Tổng thời gian = 45.2. Đối với Khung H4 (Nến 4 giờ)Thị trường Việt Nam gộp nến H4 thành 2 cây nến mỗi ngày chứ không phải 4 tiếng (240 phút) như lý thuyết:Cây nến H4 phiên Sáng (9:15 - 13:00): Bao gồm toàn bộ phiên sáng (135 phút) + 15 phút đầu phiên chiều để khớp nến. $\rightarrow$ Tổng thời gian = 150 phút.Cây nến H4 phiên Chiều (13:00 - 14:45): Bao gồm thời gian còn lại của phiên chiều và ATC. $\rightarrow$ Tổng thời gian = 105 phút.

6) Ngưỡng râu nến (shadow):
   - Câu hỏi: PRD nêu hai tiêu chí (>=1.5% × Low) hoặc (>=50% chiều dài cây nến). Xác định rõ: dùng `OR` (thỏa 1 trong 2) hay `AND` (phải thỏa cả 2)? Nếu OR, ưu tiên thứ tự kiểm tra ra sao?
   - Answer: Sử dụng điều kiện OR (chỉ cần thỏa mãn 1 trong 2 tiêu chí là được kích hoạt). Để tối ưu hiệu năng tính toán cho Bot khi quét real-time toàn bộ thị trường, Claude nên đặt thứ tự kiểm tra như sau:Ưu tiên 1 (Check % Râu tuyệt đối): Kiểm tra điều kiện Râu dưới >= 1.5% * Low trước. Vì phép tính này chỉ cần lấy 2 biến số có sẵn để so sánh, tốc độ xử lý nhanh hơn. Nếu đúng $\rightarrow$ Bắn Alert luôn, bỏ qua bước sau.Ưu tiên 2 (Check % Thân/Râu tương đối): Nếu ưu tiên 1 không thỏa mãn (ví dụ râu mới đạt 1.1%), hệ thống mới tiếp tục tính toán tổng chiều dài cây nến (High - Low) để check xem râu nến có chiếm trên 50% tổng chiều dài không. Nếu đúng $\rightarrow$ Bắn Alert.

7) Phát hiện đột biến Volume:
   - Câu hỏi: dùng `mean` hay `median` để tính trung bình Vol 20 phiên? Có cần loại bỏ outlier (ví dụ trim top 5%) trước khi tính không? 
   - Answer: Thực hiện Trimmed Mean (Cắt ngọn 5% giá trị lớn nhất) của chuỗi 20 phiên trước khi tính trung bình cộng. Đối với chuỗi 20 phiên, việc cắt top 5% tương đương với việc loại bỏ đúng 1 phiên có Volume cao nhất ra khỏi tập dữ liệu.

8) Lưu trạng thái alert (anti-spam):
   - Câu hỏi: bạn muốn lưu trạng thái đã bắn alert ở đâu? (tùy chọn: local file JSON, Google Sheet, DynamoDB, Redis, SQLite). Nếu không chọn, tôi sẽ dùng file JSON nhỏ trong `/data/alerts.json`.
   - Answer:sử dụng một In-Memory Dictionary (Biến Dict trong RAM) để lưu trạng thái cực kỳ nhanh gọn

9) SL tự động khi `SL_Manual` rỗng:
   - Câu hỏi: nếu `SL_Manual` trống, muốn dùng công thức `Low của cây Spring cũ - 0.5%` như PRD chứ? Xác định rõ "cây nến Spring cũ" là cây đã trigger tín hiệu MUA gần nhất hay cây có Low thấp nhất trong N phiên?
   - Answer: Cây nến Spring cũ" chính là cây nến có giá Low thấp nhất trong $N$ phiên (cây nến làm điểm tựa biên dưới của Trading Range)
   . Bản chất Wyckoff: Đáy thấp nhất của TR mới là "Trận địa" cuối cùngKịch bản thực tế: Cá mập tạo ra cú rũ bỏ (Spring) thực sự, họ có thể đạp thủng biên dưới TR cũ, tạo ra một cái đáy tuyệt đối mới sâu hơn (đây chính là cây nến có giá Low thấp nhất trong $N$ phiên). Tại đáy này, lực cung bị cạn kiệt, dòng tiền lớn gom sạch hàng và kéo giá rút chân ngược lên.Tại sao không lấy cây nến vừa trigger mua gần nhất? Trong Phase C hoặc Phase D của Wyckoff, sau cú Spring đầu tiên, giá sẽ có xu hướng quay lại kiểm tra cung cầu (gọi là các phiên Secondary Test - ST hoặc Test). Các cây nến Test này thường có râu nến ngắn hơn và giá đáy của nó luôn cao hơn đáy của cây Spring đầu tiên.Nếu bạn lấy cây nến Test gần nhất này làm Stop Loss $\rightarrow$ Khoảng dừng lỗ của bạn quá ngắn. Cá mập chỉ cần rung lắc nhẹ, quét râu xuống một chút là bạn bị "văng" ra khỏi hàng (Bị dính bẫy Stop Hunter) ngay trước khi cổ phiếu vào sóng tăng chính thức.🎯 Quy tắc Stop Loss chuẩn Wyckoff: Khi bạn mua ở bất kỳ điểm Test nào phía sau, điểm tựa an toàn duy nhất để bảo vệ lệnh mua của bạn chính là Mức giá thấp nhất của cú rũ bỏ (Spring) thành công trước đó, tức là Mức đáy tuyệt đối của cả vùng tích lũy - 0.5%. Nếu giá thủng luôn cả mức này, cấu trúc Tích lũy hoàn toàn thất bại (Fail TR), cổ phiếu sẽ rơi vào Downtrend và bạn phải chạy ngay lập tức.

10) Retry / backoff khi lỗi API:
   - Câu hỏi: ngoài việc `print()` log và bỏ qua lượt quét khi lỗi, bạn có muốn retry (với backoff) X lần, hoặc gửi alert admin khi lỗi liên tục Y lần? Nếu có, cho giá trị X/Y.
   - Answer:
   1. Cơ chế Retry với Exponential Backoff (Cho từng lượt gọi API lẻ)Khi hệ thống gọi API lấy data của một mã (ví dụ vnstock) hoặc gọi API Telegram mà bị lỗi mạng:Số lần Retry tối đa ($X$): 3 lần.Cơ chế Backoff: Sử dụng công thức lũy tiến thời gian chờ để tránh làm nghẽn thêm hệ thống:Thử lại lần 1: Chờ 2 giây.Thử lại lần 2: Chờ 4 giây.Thử lại lần 3: Chờ 8 giây.Nếu sau 3 lần retry vẫn lỗi $\rightarrow$ Ghi log lỗi của mã đó và bỏ qua để chuyển sang mã tiếp theo trong danh sách, đảm bảo tiến trình tổng không bị nghẽn mạch quá lâu.2. Cơ chế Cảnh báo Admin (Khi hệ thống sập diện rộng)Điều gì xảy ra nếu lỗi không nằm ở một mã lẻ, mà là toàn bộ API của sàn bị sập, hoặc mạng của VPS/Lambda bị ngắt hoàn toàn? Lúc này bot sẽ bị lỗi liên tục qua nhiều phút quét.Số lần Lỗi liên tục ngưỡng ($Y$): 5 lần liên tiếp.Hành động: Nếu tổng luồng quét (vòng lặp phút) bị thất bại hoàn toàn 5 lần liên tiếp (tương đương hệ thống "mù thông tin" suốt 5 phút trong phiên) $\rightarrow$ Bot bắt buộc phải kích hoạt một lệnh gọi Telegram khẩn cấp về chat của Admin để "kêu cứu".
   🚨 [HỆ THỐNG GẶP SỰ CỐ NGHIÊM TRỌNG] 🚨
Bot đã bị mất kết nối API liên tục 5 lần (5 phút qua).
- Thời gian: {Giờ_Hiện_Tại}
- Chi tiết lỗi cuối cùng: {Error_Message}
👉 Vui lòng kiểm tra lại kết nối mạng của Server hoặc token API ngay lập tức!

11) Triển khai ưu tiên:
   - Câu hỏi: ưu tiên của bạn là (A) triển khai nhanh trên Cloud VPS (cron), (B) làm Lambda-ready để deploy sau, hoặc (C) cần cả hai (Dockerized)? Chọn A/B/C.
   - Answer: CẦN CẢ HAI

12) Backtesting / kiểm chứng:
   - Câu hỏi: có cần module backtest/historical-run để validate rules trên dữ liệu lịch sử trước khi bật real-time? Nếu có, muốn tôi thêm script backtest mẫu?
   - Answer: ko cần

13) Mẫu dữ liệu & mẫu thông báo:
   - Câu hỏi: vui lòng cung cấp (hoặc xác nhận) một sample CSV 3-5 dòng để tôi dùng khi test; và một ví dụ Telegram đã được điền để xác nhận format/localization.
   - Answer:
Ticker,Entry,SL_Manual,Status
TCB,48500,,WATCH
HPG,29200,28100,HOLD
SSI,36400,,HOLD
DIG,25000,23500,WATCH
VHM,42000,40500,HOLD
---

Sau khi bạn trả lời, tôi sẽ:
- cập nhật `prd.md` thành các yêu cầu rõ ràng (với các điều kiện đã được xác nhận),
- viết script Python mẫu theo lựa chọn triển khai bạn chọn.
