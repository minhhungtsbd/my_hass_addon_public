# Fall Detection Web

Web UI giám sát té ngã chạy trên VPS/server:

```text
Camera (RTSP)
  → YOLO local detect person (ultralytics, trong Python app)
  → AI vision verify (cloud API)
  → Telegram alert nếu EMERGENCY
```

## Tính Năng

- **YOLO local detection only** — dùng `ultralytics` + `opencv-python` để detect `person` từ RTSP stream. Khi phát hiện, gọi AI cloud để xác minh té ngã. Không còn detection mode khác.
- **AI Verify** — gửi ảnh lên OpenAI-compatible vision API, parse response `SAFE / EMERGENCY`.
- **Telegram Alert** — gửi ảnh kèm caption khi AI kết luận EMERGENCY, có cooldown để tránh spam.
- **Multi-camera** — cấu hình nhiều camera, bật/tắt từng camera qua UI.
- **Đăng nhập bảo mật** — HTTP-only JWT cookie, mật khẩu hash bằng bcrypt.
- **SQLite storage** — events và settings đều lưu trong `data/fall_detection.db`.
- **Live view** — xem stream qua go2rtc iframe (MSE/WebRTC) hoặc Python MJPEG proxy.
- **Auto-migrate** — tự import `events.jsonl` và `config.json` cũ vào DB khi khởi động lần đầu.

## Cấu Trúc Mã Nguồn

```text
fall_detection_web/
├── app.py           # FastAPI routes, lifespan startup/shutdown
├── auth.py          # bcrypt password + JWT HTTP-only cookie session
├── config.py        # Đọc/ghi config từ SQLite, override bằng .env
├── db.py            # SQLite layer: events, users, settings
├── monitor.py       # YOLO monitor loop + RTSP capture threads
├── ai.py            # AI verify (vision API) + Telegram sender
├── requirements.txt
├── .env.example
└── templates/
    ├── index.html   # Toàn bộ frontend (Jinja2)
    └── login.html   # Trang đăng nhập
```

## Cài Đặt

```bash
git clone <repo>
cd fall_detection_web
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8090
```

Mở trình duyệt: `http://<server-ip>:8090`

Đăng nhập mặc định: **admin / admin** (đổi ngay sau lần đầu).

## Cấu Hình

Cấu hình được lưu trong **SQLite** (`data/fall_detection.db`, bảng `settings`). Thay đổi qua tab **Settings** trong UI, nhấn **Save Settings** là lưu ngay — không cần restart.

`.env` (tùy chọn) dùng để **override** các giá trị trong DB, phù hợp cho container hoặc secrets không muốn lưu trong DB:

```dotenv
AI_API_KEY=sk-xxxxx
TELEGRAM_BOT_TOKEN=123456789:AABBCCxx
TELEGRAM_CHAT_ID=-100123456789
RTSP_URL=rtsp://10.10.0.2:8554/bep_sub
```

Sao chép từ template:

```bash
cp .env.example .env
```

### Các biến `.env` được hỗ trợ

| Biến env | Config key | Mô tả |
|---|---|---|
| `RTSP_URL` | `rtsp_url` | RTSP stream fallback |
| `GO2RTC_URL` | `go2rtc_url` | Base URL go2rtc |
| `TELEGRAM_BOT_TOKEN` | `telegram_bot_token` | Bot token |
| `TELEGRAM_CHAT_ID` | `telegram_chat_id` | Chat ID nhận alert |
| `AI_BASE_URL` | `ai_base_url` | OpenAI-compatible endpoint |
| `AI_API_KEY` | `ai_api_key` | API key |
| `VISION_MODEL` | `vision_model` | Model vision |
| `YOLO_MODEL` | `yolo_model` | File model YOLO |
| `YOLO_IMGSZ` | `yolo_imgsz` | Kích thước ảnh inference |
| `CONFIDENCE` | `confidence` | Ngưỡng detect person |
| `VERIFY_INTERVAL` | `verify_interval` | Giây tối thiểu giữa 2 lần gọi AI |
| `ALERT_COOLDOWN` | `alert_cooldown` | Giây tối thiểu giữa 2 cảnh báo Telegram |
| `FRAME_SKIP` | `frame_skip` | Bỏ N-1 frame để giảm CPU |
| `LOOP_SLEEP` | `loop_sleep` | Thời gian nghỉ mỗi vòng lặp (giây) |
| `TELDRIVE_ENABLED` | `teldrive_enabled` | Bật upload ảnh/video event lên Teldrive |
| `TELDRIVE_BASE_URL` | `teldrive_base_url` | URL Teldrive, ví dụ `https://teldrive.minhhungtsbd.me` |
| `TELDRIVE_TOKEN` | `teldrive_token` | Bearer token Teldrive |
| `TELDRIVE_ROOT_PATH` | `teldrive_root_path` | Thư mục gốc trên Teldrive |
| `TELDRIVE_CHANNEL_ID` | `teldrive_channel_id` | Channel ID Teldrive tùy chọn |
| `TELDRIVE_RECORD_SECONDS` | `teldrive_record_seconds` | Số giây ghi clip |
| `TELDRIVE_RECORD_COOLDOWN` | `teldrive_record_cooldown` | Cooldown giữa 2 lần ghi clip/camera |

> **Priority:** `.env` / os.environ > SQLite settings > default values

## Database

Tất cả dữ liệu lưu trong `data/fall_detection.db`:

| Bảng | Mô tả |
|---|---|
| `settings` | Config key-value (thay thế config.json) |
| `events` | Log sự kiện (detect, verify, alert, error…) |
| `users` | Tài khoản đăng nhập (username + bcrypt hash) |

Ảnh snapshot của events lưu tại `data/event_images/` và tự xóa sau **24 giờ**.
Events tự prune khi vượt **5000 records** (xóa batch cũ nhất).

### Auto-migration

Khi khởi động lần đầu, nếu tồn tại file cũ:

- `data/config.json` → import vào bảng `settings` → rename thành `config.json.migrated`
- `data/events.jsonl` → import vào bảng `events` → rename thành `events.jsonl.migrated`

## UI

| Tab | Chức năng |
|---|---|
| **Dashboard** | Start/Stop monitor, tổng quan trạng thái, 5 events gần nhất |
| **Cameras** | Thêm/sửa/xóa camera, test snapshot, test AI từng camera, bật/tắt upload ảnh/video theo camera |
| **Live** | Xem stream live đa camera, chọn 1/2/3 cột; double-click camera ở 2/3 cột để chuyển camera đó sang full width |
| **Settings** | Cấu hình YOLO, AI API, Telegram, cooldown, RTSP… |
| **Events** | Bảng log events với thumbnail ảnh; ưu tiên ảnh từ Teldrive nếu đã upload |
| **Recordings** | Xem lại clip đã upload theo camera và khung thời gian |
| **Tools** | Test AI với snapshot, upload ảnh test, test Telegram |

URL hash: `#dashboard`, `#cameras`, `#live`, `#settings`, `#events`, `#recordings`, `#tools`

## API Endpoints

Tất cả endpoint `/api/*` yêu cầu đăng nhập (JWT cookie). Trả `401` nếu chưa xác thực.

```http
GET  /                           # UI chính (redirect /login nếu chưa đăng nhập)
GET  /login                      # Trang đăng nhập
POST /auth/login                 # Form login
POST /auth/logout                # Logout

GET  /api/config                 # Đọc config hiện tại
POST /api/config                 # Lưu config (JSON body)
POST /api/teldrive/check         # Kiểm tra Teldrive access_token còn hợp lệ
GET  /api/status                 # Trạng thái monitor + event count
POST /api/start                  # Khởi động YOLO monitor
POST /api/stop                   # Dừng monitor

GET  /api/events                 # Lấy danh sách events
DELETE /api/events               # Xóa toàn bộ events
GET  /api/recordings             # Lấy clip Teldrive đã upload, lọc camera/date_from/date_to

GET  /api/camera/snapshot?index= # Chụp ảnh camera
GET  /api/camera/video?index=    # MJPEG stream camera

POST /api/test-ai                # Test AI với snapshot mới nhất
POST /api/test-ai-camera?index=  # Test AI với snapshot camera cụ thể
POST /api/test-telegram          # Test gửi Telegram
POST /api/test-ai-upload         # Test AI với ảnh upload (max 10MB)

GET  /api/event-image/{filename} # Ảnh event (yêu cầu đăng nhập)
GET  /api/teldrive/file/{id}/{name} # Proxy file Teldrive qua phiên đăng nhập Fall Detection
```

## Nhiều Camera

Camera được cấu hình trong tab **Cameras**. Mỗi camera gồm:

| Field | Mô tả |
|---|---|
| Enabled | Bật/tắt camera |
| Name | Tên hiển thị |
| RTSP URL | URL RTSP để YOLO capture frame |
| go2rtc src | Tên stream trong go2rtc (cho snapshot JPEG và live view) |
| Live URL | (Tùy chọn) URL stream trực tiếp thay vì tự build từ go2rtc_src |
| Upload event images | Upload ảnh event của camera này lên Teldrive |
| Record/upload video | Ghi và upload clip ngắn khi camera này phát hiện `person` |

Thứ tự ưu tiên lấy **snapshot thủ công / test AI**:

1. go2rtc JPEG API: `{go2rtc_url}/api/frame.jpeg?src={go2rtc_src}`
2. Fallback RTSP OpenCV

Monitor chạy nền vẫn dùng RTSP frame để YOLO local detect `person`. go2rtc chỉ dùng cho snapshot thủ công/test và live view khi có cấu hình.

## Teldrive Upload

Trong tab **Settings**, bật Teldrive và cấu hình base URL/token/root path chung. Tùy chọn upload ảnh event và ghi/upload video nằm trong từng camera để có thể bật riêng theo nhu cầu.

`TELDRIVE_TOKEN` là giá trị cookie `access_token` của phiên đăng nhập Teldrive. Browser không cho trang Fall Detection đọc cookie của domain Teldrive, nên không thể tự động lấy token chỉ bằng một nút bấm nếu hai app chạy khác origin. Hãy copy `access_token` từ DevTools/Cookie Editor rồi dùng nút **Check Teldrive Token** trong Settings để kiểm tra token còn live hay đã hết hạn.

Luồng upload:

1. Tạo thư mục bằng `POST /api/files/mkdir`
2. Upload file part bằng `POST /api/uploads/{upload_id}`
3. Đọc lại part bằng `GET /api/uploads/{upload_id}`
4. Tạo file metadata bằng `POST /api/files`, trong đó `path` là thư mục cha và `name` là tên file

Mặc định app dùng `https://teldrive.minhhungtsbd.me` và lưu theo cấu trúc:

```text
/Fall Detection/{camera}/images/
/Fall Detection/{camera}/videos/
```

Sau khi upload thành công, app lưu lại `file id`, `name` và `path` của Teldrive vào event. Cột ảnh trong tab **Events** sẽ dùng proxy Teldrive nếu có metadata upload, nếu chưa có thì fallback về ảnh local trong `data/event_images/`. Tab **Recordings** dùng metadata video đã lưu để xem lại/lọc theo camera và thời gian.

Clip ghi hình dùng OpenCV `VideoWriter` định dạng `.avi` để tránh phụ thuộc `ffmpeg`.

Thứ tự ưu tiên **live view**:

1. `live_url` nếu có (embed iframe)
2. `{go2rtc_url}/stream.html?src={go2rtc_src}&mode=mse` (go2rtc MSE)
3. `/api/camera/video?index=N` (Python MJPEG proxy — tốn CPU hơn)

## Chạy Nền Bằng systemd

```ini
[Unit]
Description=Fall Detection Web
After=network-online.target

[Service]
User=root
WorkingDirectory=/opt/fall-detection
ExecStart=/opt/fall-detection/venv/bin/uvicorn app:app --host 0.0.0.0 --port 8090
Restart=always
RestartSec=5
EnvironmentFile=/opt/fall-detection/.env

[Install]
WantedBy=multi-user.target
```

```bash
systemctl enable --now fall-detection
journalctl -u fall-detection -f
```

## Dependencies

```
fastapi          # Web framework
uvicorn          # ASGI server
opencv-python    # RTSP capture + MJPEG proxy
ultralytics      # YOLO person detection
requests         # AI API + Telegram (shared Session)
bcrypt           # Password hashing
python-jose      # JWT session token
jinja2           # HTML templates
python-multipart # Form + file upload parsing
```

## Lưu Ý

- `data/` đã được gitignore — DB, ảnh, `.env` không bao giờ bị commit.
- Khi save Settings từ UI, giá trị trong DB được cập nhật ngay; monitor tự restart với config mới.
- AI API chấp nhận response dạng JSON, SSE (`data: ...`) và multiple JSON objects (tương thích nhiều gateway).
- bcrypt truncate password ở 72 bytes (giới hạn của thuật toán bcrypt).
