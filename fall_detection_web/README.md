# Fall Detection Web

Web UI nhẹ để chạy script fall detection:

```text
RTSP từ go2rtc
-> YOLO person detection
-> AI vision verification
-> Telegram alert
```

Ứng dụng này tách riêng khỏi addon `simple_ai_vision`. Nó dùng OpenCV/YOLO vì mục tiêu là chạy fall detection trực tiếp trên VPS/DC.

## Lỗi Đã Fix

Script cũ dùng:

```python
result = response.json()
```

Một số OpenAI-compatible gateway có thể trả:

- JSON chuẩn.
- SSE dạng `data: {...}`.
- Nhiều JSON object nối nhau.

Khi gặp nhiều JSON object nối nhau, `response.json()` báo:

```text
Extra data: line 2 column 1
```

Backend mới xử lý cả ba dạng response:

- `response.json()` cho JSON chuẩn.
- Parser SSE cho `data: ...`.
- `json.JSONDecoder().raw_decode()` lặp nhiều lần cho JSON nối nhau.

## Cài Đặt

```bash
cd fall_detection_web
python3 -m venv venv
. venv/bin/activate
pip install -r requirements.txt
mkdir -p data
cp config.example.json data/config.json
cp .env.example .env
uvicorn app:app --host 0.0.0.0 --port 8090
```

Mở:

```text
http://<server-ip>:8090
```

## Cấu Hình

Ứng dụng dùng kết hợp hai nguồn cấu hình:

```text
.env hoặc environment variables
-> override
data/config.json
-> cấu hình Web UI
```

Nên đặt secret trong `.env` hoặc environment:

```dotenv
RTSP_URL=rtsp://10.10.0.2:8554/bep_sub
AI_API_KEY=sk-...
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=1602998514
```

Các biến `.env` được hỗ trợ:

| Env | Config field |
| --- | --- |
| `RTSP_URL` | `rtsp_url` |
| `AI_BASE_URL` | `ai_base_url` |
| `AI_API_KEY` | `ai_api_key` |
| `VISION_MODEL` | `vision_model` |
| `YOLO_MODEL` | `yolo_model` |
| `TELEGRAM_BOT_TOKEN` | `telegram_bot_token` |
| `TELEGRAM_CHAT_ID` | `telegram_chat_id` |
| `CONFIDENCE` | `confidence` |
| `VERIFY_INTERVAL` | `verify_interval` |
| `ALERT_COOLDOWN` | `alert_cooldown` |
| `FRAME_SKIP` | `frame_skip` |
| `LOOP_SLEEP` | `loop_sleep` |

Nếu một secret đã có trong `.env`, khi bấm **Save Settings** UI sẽ không ghi lại secret đó vào `data/config.json`.

Trong tab **Settings**:

| Field | Mô tả |
| --- | --- |
| `RTSP URL` | RTSP từ go2rtc, ví dụ `rtsp://10.10.0.2:8554/bep_sub` |
| `AI Base URL` | Base URL OpenAI-compatible, ví dụ `https://9router.minhhungtsbd.me/v1` |
| `Vision Model` | Model vision, ví dụ `gh/oswe-vscode-prime` |
| `AI API Key` | API key, nên lấy từ `.env` |
| `YOLO Model` | Model YOLO, ví dụ `yolov8s.pt` |
| `Telegram Bot Token` | Bot token, nên lấy từ `.env` |
| `Telegram Chat ID` | Chat nhận cảnh báo, có thể lấy từ `.env` |
| `YOLO Confidence` | Ngưỡng phát hiện person |
| `Verify Interval` | Khoảng cách tối thiểu giữa hai lần gọi AI khi có person |
| `Alert Cooldown` | Khoảng cách tối thiểu giữa hai cảnh báo Telegram |
| `Frame Skip` | Bỏ bớt frame để giảm CPU |
| `Loop Sleep` | Thời gian nghỉ mỗi vòng lặp |

Không commit file `.env` hoặc `data/config.json` vì có thể chứa token/API key.

## UI

Các tab chính:

- **Dashboard**: Start/Stop monitor, capture snapshot, xem snapshot mới nhất.
- **Cameras**: thêm nhiều camera RTSP, bật/tắt từng camera, xem snapshot/video và test AI từng camera.
- **Live**: xem nhiều camera cùng lúc bằng MJPEG proxy từ RTSP.
- **Settings**: cấu hình RTSP, AI, YOLO, Telegram và timeout/cooldown.
- **Events**: log các trạng thái `started`, `verified`, `telegram_sent`, `ai_error`, `rtsp_reconnect`.
- **Tools**: test AI bằng snapshot mới nhất, upload ảnh test AI, test Telegram.

## Nhiều Camera

Danh sách camera được lưu trong `data/config.json`:

```json
{
  "cameras": [
    {
      "enabled": true,
      "name": "bep",
      "rtsp_url": "rtsp://10.10.0.2:8554/bep_sub"
    }
  ]
}
```

Trường `rtsp_url` ở Settings vẫn được giữ làm fallback cho cấu hình cũ. Nếu chưa có `cameras`, app sẽ tự tạo một camera mặc định từ `rtsp_url`.

Các endpoint camera:

```http
GET /api/camera/snapshot?index=0
GET /api/camera/video?index=0
POST /api/test-ai-camera?index=0
```

`/api/camera/video` trả MJPEG stream để browser xem trực tiếp được, thay vì mở RTSP raw.

## Chạy Nền Bằng systemd

Ví dụ service:

```ini
[Unit]
Description=Fall Detection Web
After=network-online.target

[Service]
WorkingDirectory=/opt/fall_detection_web
ExecStart=/opt/fall_detection_web/venv/bin/uvicorn app:app --host 0.0.0.0 --port 8090
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## Kiến Trúc Gợi Ý

```text
HOME
Camera
-> go2rtc
-> WireGuard

DC/VPS
RTSP from go2rtc
-> YOLO person detection
-> AI fall verification
-> Telegram
```
