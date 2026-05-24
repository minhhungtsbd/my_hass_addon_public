# Hệ Thống Giám Sát Camera AI & Cảnh Báo Té Ngã (Fall Detection Web)

Hệ thống giám sát camera thông minh, tự động phát hiện người bằng YOLO và xác thực hành vi (té ngã, sự cố đột xuất) thông qua Trí Tuệ Nhân Tạo (AI Vision), sau đó gửi cảnh báo tức thời kèm theo hình ảnh bằng chứng qua Telegram.

Dự án được xây dựng dưới dạng ứng dụng Web độc lập (Self-hosted Web App), phù hợp triển khai trên VPS, Máy chủ nội bộ (LAN), Mini PC hoặc máy tính giám sát chuyên dụng.

```text
Camera / RTSP / go2rtc 
  -> Nhận diện người cục bộ (YOLO)
  -> Xác thực hình ảnh qua AI Vision (OpenAI API/Gemini/OpenRouter)
  -> Tạo dòng thời gian sự kiện (Incident Timeline)
  -> Gửi cảnh báo tức thì qua Telegram (sendPhoto)
  -> Ghi hình & Lưu trữ bằng chứng video (Teldrive / VPS)
```

---

## Các Tính Năng Cốt Lõi

- **Bảng điều khiển chuyên nghiệp (SOC Dashboard)**: Theo dõi trạng thái hoạt động của hệ thống, tải tài nguyên CPU/RAM/Disk trực quan, biểu đồ xu hướng sự cố 7 ngày gần nhất, và danh sách sự cố mới nhất.
- **Quản lý đa camera**: Thêm, sửa, xóa, kích hoạt/vô hiệu hóa, chụp nhanh snapshot, test AI trực tiếp.
- **Giám sát trực tiếp (Live View)**: Xem live stream độ trễ thấp thông qua go2rtc (Tự động thương lượng WebRTC/MSE), live URL tùy chỉnh hoặc Proxy MJPEG dự phòng.
- **Xác thực AI Vision**: Gửi hình ảnh snapshot đến các API tương thích OpenAI (OpenAI, Gemini, OpenRouter, 9Router...) để phân loại chính xác sự cố (`SAFE` hoặc `EMERGENCY`).
- **Cảnh báo Telegram**: Gửi ảnh chụp sự cố kèm theo nội dung mô tả chi tiết ngay khi AI xác nhận có tình huống khẩn cấp (`EMERGENCY`).
- **Dòng thời gian sự kiện (Events)**: Lưu trữ lịch sử sự cố kèm ảnh thu nhỏ (thumbnail), thời gian (Múi giờ Việt Nam UTC+7), trạng thái và mô tả từ AI.
- **Xem lại video ghi hình (Recordings)**: Cho phép xem lại các đoạn video sự cố được quay trực tiếp trên giao diện hoặc lưu trữ trên Teldrive (Hỗ trợ trình phát Web player popup và copy link tải nhanh).
- **Trình quản lý Prompt**: Thiết lập các mẫu Prompt AI riêng biệt để chỉ định cho từng khu vực camera (ví dụ: camera trong nhà cần prompt khác camera ngoài sân).
- **Bảo mật**: Cơ chế đăng nhập an toàn sử dụng mã hóa mật khẩu bcrypt và phiên làm việc qua JWT Cookie.

---

## Hướng Dẫn Cài Đặt Nhanh

### 1. Trên Linux / Ubuntu VPS

Mở Terminal và chạy các lệnh sau:

```bash
# 1. Clone mã nguồn về máy
git clone <url-kho-chua-cua-ban>
cd fall_detection_web

# 2. Tạo môi trường ảo Python
python3 -m venv venv
source venv/bin/activate

# 3. Cài đặt các thư viện phụ thuộc
pip install -r requirements.txt

# 4. Chạy ứng dụng web
uvicorn app:app --host 0.0.0.0 --port 8090
```

### 2. Trên Windows (PowerShell)

Mở PowerShell tại thư mục dự án và chạy:

```powershell
# 1. Tạo môi trường ảo Python
python -m venv venv

# 2. Kích hoạt môi trường ảo
.\venv\Scripts\Activate.ps1

# 3. Cài đặt thư viện phụ thuộc
pip install -r requirements.txt

# 4. Chạy ứng dụng web
uvicorn app:app --host 0.0.0.0 --port 8090
```

Sau khi chạy thành công, truy cập giao diện qua trình duyệt:
* Địa chỉ: `http://<IP-SERVER>:8090` hoặc `http://localhost:8090`
* Tài khoản mặc định: **`admin`**
* Mật khẩu mặc định: **`admin`**
* *Lưu ý: Bạn nên đổi mật khẩu tài khoản ngay sau lần đầu đăng nhập thành công tại mục Settings.*

---

## Hướng Dẫn Cấu Hình Hệ Thống (Settings)

Sau khi đăng nhập, hãy truy cập menu **Settings** (hoặc biểu tượng bánh răng) trên thanh điều hướng bên trái để thiết lập các thông số hệ thống:

### 1. Cấu hình AI Vision (AI Provider)
* **AI Base URL**: Địa chỉ API của nhà cung cấp (ví dụ: `https://api.openai.com/v1` hoặc cổng dịch vụ của OpenRouter `https://openrouter.ai/api/v1`, Gemini OpenAI-gateway).
* **AI API Key**: Khóa API bảo mật của tài khoản AI của bạn.
* **Vision Model**: Tên model hỗ trợ đọc hiểu hình ảnh (ví dụ: `gpt-4o`, `google/gemini-2.5-flash`...).

### 2. Cấu hình Cảnh Báo Telegram
* **Telegram Bot Token**: Token của Telegram Bot do bạn tạo ra từ `@BotFather`.
* **Telegram Chat ID**: ID của người nhận hoặc ID của Nhóm/Kênh Telegram nhận cảnh báo.

### 3. Cấu hình go2rtc (Quản lý luồng Stream & Snapshot)
* **go2rtc URL**: Link API của go2rtc (ví dụ: `http://127.0.0.1:1984` hoặc URL public của bạn `https://go2rtc.example.me`).

### 4. Cấu hình Lưu Trữ Lịch Sử (Teldrive - Tùy chọn)
Nếu bạn muốn lưu trữ video sự cố lên Telegram không giới hạn dung lượng qua Teldrive:
* **Teldrive Enabled**: Tích chọn để kích hoạt.
* **Teldrive Base URL**: Đường dẫn đến server Teldrive của bạn (ví dụ: `https://teldrive.yourdomain.com`).
* **Teldrive Token**: Token JWT/Bearer để xác thực tài khoản Teldrive.
* **Teldrive Root Path**: Đường dẫn thư mục gốc để lưu trữ (ví dụ: `/Fall Detection`).

---

## Hướng Hẫn Thiết Lập Camera (Cameras)

Truy cập menu **Cameras** > **Add Camera** hoặc chỉnh sửa camera hiện tại bằng nút **Edit** trong trang chi tiết camera. Hãy điền các thông số theo hướng dẫn sau để camera hoạt động tối ưu nhất:

| Tên Trường Cấu Hình | Cách Thiết Lập & Giá Trị Hợp Lý |
| :--- | :--- |
| **Tên camera / source go2rtc** | Nhập chính xác tên stream được khai báo trong cấu hình `go2rtc.yaml` (ví dụ: `h9ccam2_sub`). Không chứa khoảng trắng hoặc ký tự đặc biệt. |
| **Prompt** | Chọn mẫu Prompt AI phù hợp cho camera này (đã được tạo ở tab Prompts). |
| **go2rtc frame URL hoặc source** | Nhập tên stream ngắn (ví dụ: `h9ccam2_sub`) nếu bạn đã điền go2rtc URL chung ở phần Settings. Hệ thống sẽ tự động chuyển đổi thành đường dẫn lấy ảnh tĩnh `https://<go2rtc-url>/api/frame.jpeg?src=h9ccam2_sub`. |
| **go2rtc live URL** | Nên để trống. Hệ thống sẽ tự động tạo link live stream dạng `https://<go2rtc-url>/stream.html?src=h9ccam2_sub`. Trình phát này sẽ tự động chạy **WebRTC** (Hỗ trợ mượt mà H.265/HEVC, không giật lag) và tự fallback về MSE/HLS khi cần. |
| **RTSP URL Camera (fallback)** | **⚠️ QUAN TRỌNG:** Phải điền **RTSP trực tiếp từ địa chỉ IP của camera** (ví dụ: `rtsp://admin:PASS@192.168.2.152:554/Streaming/Channels/201`), **KHÔNG điền link RTSP của go2rtc**. Đây là đường dẫn dự phòng để hệ thống tự kết nối trực tiếp đến camera chụp ảnh khi go2rtc bị lỗi. |
| **Chế độ live (Live Mode)** | Chọn **Tự động: go2rtc iframe** để chạy mượt mà nhất. Nếu camera HEVC/H.265 của bạn vẫn bị đen màn hình trên các trình duyệt cũ, có thể chuyển sang chế độ **Snapshot refresh**. |
| **Lưu trữ & Ghi hình** | Tích chọn các mục **Lưu ảnh/video trên VPS** hoặc **Ghi và upload video** (qua Teldrive) theo nhu cầu. |
| **Thời lượng quay video** | Thời gian ghi hình khi phát hiện sự cố (thường đặt từ **10 giây đến 30 giây** là hợp lý). |
| **Thời gian chờ quay tiếp theo** | Cooldown (giây) để tránh ghi hình liên tục lặp lại cho cùng một sự cố (nên đặt **300 giây - 5 phút**). |

---

## Hướng Dẫn Sử Dụng Chi Tiết

1. **Kích hoạt Giám Sát**: Tại trang chủ (Dashboard) hoặc trang chi tiết camera, nhấn nút **Start** ở góc phải trên cùng để bắt đầu chạy vòng lặp giám sát nhận diện người bằng YOLO.
2. **Theo dõi Trạng thái**: Bảng điều khiển sẽ hiển thị biểu đồ và tài nguyên hệ thống theo thời gian thực.
3. **Phát Hiện Người & Xác Thực**:
   * Khi YOLO phát hiện có người xuất hiện trong khung hình, nó sẽ trigger chụp snapshot từ go2rtc.
   * Snapshot được gửi tới AI Vision để phân tích hành vi.
   * Nếu AI xác nhận là `EMERGENCY` (ví dụ: Té ngã, bất tỉnh, đột nhập đột xuất...):
     * Gửi cảnh báo hình ảnh và lời thoại mô tả sự việc đến Telegram của bạn ngay lập tức.
     * Tự động kích hoạt chế độ ghi hình video ngắn (nếu cấu hình bật).
     * Đẩy sự kiện vào dòng thời gian **Events** trên web.
   * Nếu AI xác nhận là `SAFE` (ví dụ: Người đi bộ bình thường, dọn dẹp...): Sự kiện được ghi lại trên danh sách events là Safe và không gửi cảnh báo Telegram để tránh spam.
4. **Xem Lại Bằng Chứng**:
   * **Events**: Truy cập tab **Events** để xem dòng thời gian sự cố, lọc theo camera, lọc theo trạng thái AI, click vào ảnh thu nhỏ để xem ảnh gốc kích thước lớn.
   * **Recordings**: Truy cập tab **Recordings** để xem lại video sự cố. Bạn có thể chọn hiển thị danh sách dạng Lưới (Grid) hoặc Danh sách (List), thay đổi số lượng cột (2 hoặc 3 cột), bật/tắt ảnh thu nhỏ và chế độ **Play Cover** (cho phép play video trong một popup mượt mà hoặc nhúng trực tiếp video vào trang). Bạn cũng có thể copy nhanh link video bằng nút **Copy Link** để tải về máy.

---

## Cấu Hình Chạy Ngầm Hệ Thống (Systemd Service trên Linux)

Để ứng dụng tự động khởi động cùng VPS và luôn chạy ngầm trong hệ thống, hãy cấu hình dịch vụ Systemd:

1. Tạo file dịch vụ:
   ```bash
   sudo nano /etc/systemd/system/fall-detection.service
   ```
2. Dán nội dung sau vào file (thay đổi `/opt/fall-detection` thành thư mục chứa code thực tế của bạn):
   ```ini
   [Unit]
   Description=Fall Detection Web Service
   After=network-online.target

   [Service]
   User=root
   WorkingDirectory=/opt/fall-detection
   ExecStart=/opt/fall-detection/venv/bin/uvicorn app:app --host 0.0.0.0 --port 8090 --no-access-log
   Restart=always
   RestartSec=5

   [Install]
   WantedBy=multi-user.target
   ```
3. Lưu file lại (`Ctrl+O`, `Enter`, `Ctrl+X`), sau đó chạy các lệnh sau để kích hoạt dịch vụ:
   ```bash
   # Tải lại cấu hình dịch vụ
   sudo systemctl daemon-reload

   # Kích hoạt khởi động cùng hệ thống và chạy dịch vụ ngay lập tức
   sudo systemctl enable --now fall-detection

   # Kiểm tra trạng thái dịch vụ đang chạy
   sudo systemctl status fall-detection

   # Xem log hoạt động theo thời gian thực
   journalctl -u fall-detection -f
   ```

---

## Một Số Lưu Ý Quan Trọng khi Sử Dụng

1. **Bảo mật**: Luôn đổi mật khẩu mặc định `admin/admin` ngay sau khi cài đặt thành công. Nếu bạn public ứng dụng ra internet ngoài mạng LAN, hãy cài đặt SSL (HTTPS) thông qua một Reverse Proxy (Nginx, Caddy, hoặc Cloudflare Tunnel) để bảo mật mã hóa JWT Cookie.
2. **CPU VPS**: 
   * Hãy tận dụng tối đa go2rtc để stream và lấy snapshot. 
   * Tính năng ghi hình video đã được tối ưu hóa để ghi hình nguyên bản (copy codec) nhằm giải phóng CPU VPS khỏi tác vụ transcode nặng nề.
3. **Độ ổn định của Camera**: Chất lượng kết nối hình ảnh và độ trễ phụ thuộc lớn vào chất lượng mạng nội bộ của camera và cấu hình go2rtc của bạn. Nên ưu tiên kết nối mạng dây (LAN) cho camera thay vì kết nối Wifi không ổn định.
