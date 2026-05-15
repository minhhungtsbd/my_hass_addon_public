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
cp config.example.json data/config.json
uvicorn app:app --host 0.0.0.0 --port 8090
```

Mở:

```text
http://<server-ip>:8090
```

## Cấu Hình

Trong tab **Settings**:

| Field | Mô tả |
| --- | --- |
| `RTSP URL` | RTSP từ go2rtc, ví dụ `rtsp://10.10.0.2:8554/bep_sub` |
| `AI Base URL` | Base URL OpenAI-compatible, ví dụ `https://9router.minhhungtsbd.me/v1` |
| `Vision Model` | Model vision, ví dụ `gh/oswe-vscode-prime` |
| `AI API Key` | API key, lưu local trong `data/config.json` |
| `YOLO Model` | Model YOLO, ví dụ `yolov8s.pt` |
| `Telegram Bot Token` | Bot token |
| `Telegram Chat ID` | Chat nhận cảnh báo |
| `YOLO Confidence` | Ngưỡng phát hiện person |
| `Verify Interval` | Khoảng cách tối thiểu giữa hai lần gọi AI khi có person |
| `Alert Cooldown` | Khoảng cách tối thiểu giữa hai cảnh báo Telegram |
| `Frame Skip` | Bỏ bớt frame để giảm CPU |
| `Loop Sleep` | Thời gian nghỉ mỗi vòng lặp |

Không commit file `data/config.json` vì có token/API key.

## UI

Các tab chính:

- **Dashboard**: Start/Stop monitor, capture snapshot, xem snapshot mới nhất.
- **Settings**: cấu hình RTSP, AI, YOLO, Telegram và timeout/cooldown.
- **Events**: log các trạng thái `started`, `verified`, `telegram_sent`, `ai_error`, `rtsp_reconnect`.
- **Tools**: test AI bằng snapshot mới nhất, upload ảnh test AI, test Telegram.

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

