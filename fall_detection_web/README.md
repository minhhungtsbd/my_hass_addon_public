# Fall Detection Web

Web UI nhẹ để chạy script fall detection:

```text
Frigate/OpenVINO person detection
-> webhook /analyze hoặc /verify
-> snapshot mới nhất từ go2rtc JPEG
-> AI vision verification
-> Telegram alert
```

Ứng dụng này tách riêng khỏi addon `simple_ai_vision`. Mode mặc định là Frigate/OpenVINO trigger: Frigate chạy object detection, còn Python app chỉ nhận webhook, lấy snapshot, gọi AI và gửi Telegram.

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

### Python app

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

### Chạy độc lập trên cùng VPS

Trên cùng một VPS sẽ có 3 service riêng:

```text
go2rtc
-> cung cấp stream/snapshot camera

Frigate
-> đọc stream từ go2rtc
-> dùng OpenVINO detect person
-> gọi webhook Python app

Fall Detection Web
-> nhận webhook /analyze hoặc /verify
-> lấy snapshot mới từ go2rtc
-> gửi ảnh lên AI cloud xác minh té ngã/nguy hiểm
-> gửi Telegram nếu AI trả EMERGENCY
```

Python app không tự chạy Frigate. Nếu chọn `Detection Mode = Frigate/OpenVINO trigger`, bạn cần cài và chạy Frigate như một service/container riêng trên VPS đó.

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
| `DETECTION_MODE` | `detection_mode` |
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
| `RTSP URL` | Fallback RTSP nếu không dùng được snapshot từ go2rtc, ví dụ `rtsp://10.10.0.2:8554/bep_sub` |
| `go2rtc URL` | Base URL go2rtc để lấy snapshot và xem live trực tiếp, ví dụ `http://10.10.0.2:1984` |
| `AI Base URL` | Base URL OpenAI-compatible, ví dụ `https://9router.minhhungtsbd.me/v1` |
| `Vision Model` | Model vision, ví dụ `gh/oswe-vscode-prime` |
| `AI API Key` | API key, nên lấy từ `.env` |
| `AI Verify Prompt` | Prompt xác minh té ngã gửi tới AI. Có thể chỉnh trực tiếp trong UI |
| `Detection Mode` | `Frigate/OpenVINO trigger` là mode nhẹ mặc định; `YOLO prefilter` chỉ dùng nếu tự cài OpenCV/Ultralytics; `AI interval only` gọi AI theo chu kỳ |
| `YOLO Model` | Chỉ dùng cho mode YOLO, khuyến nghị `yolov8n.pt` để giảm RAM/CPU |
| `YOLO Image Size` | Kích thước inference YOLO, ví dụ `416`; giảm xuống `320` sẽ nhẹ hơn nhưng kém chính xác hơn |
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

- **Dashboard**: Start/Stop monitor, xem tổng quan camera, go2rtc public URL, AI model và recent events.
- **Cameras**: thêm nhiều camera, bật/tắt từng camera, cấu hình `go2rtc_src`, xem snapshot/video và test AI từng camera.
- **Live**: xem nhiều camera cùng lúc bằng MJPEG proxy từ RTSP.
- **Settings**: cấu hình go2rtc, AI, Frigate/YOLO mode, Telegram và timeout/cooldown.
- **Events**: log các trạng thái `started`, `verified`, `telegram_sent`, `ai_error`, `rtsp_reconnect`.
- **Tools**: test AI bằng snapshot mới nhất, upload ảnh test AI, test Telegram.

Các tab có hash URL riêng, ví dụ `#cameras`, `#live`, `#events`. Khi reload trang, UI sẽ giữ lại tab đang mở.

Mỗi event `verified`, `test_ai`, `test_ai_camera`, `test_ai_upload` lưu thêm trường `ai_raw`, là nội dung text AI trả về sau khi parse response từ 9Router/OpenAI-compatible gateway.

Events hiển thị thời gian theo UTC+7 trên UI. Event vẫn lưu `time` UTC và thêm `time_local` UTC+7 trong file JSONL.

Các event có snapshot sẽ lưu ảnh trong:

```text
data/event_images
```

Ảnh event được giữ tối đa 24 giờ, hiển thị thumbnail trong tab Events và có thể click để phóng to trong modal.

Prompt mặc định yêu cầu AI trả đúng 2 dòng:

```text
SAFE hoặc EMERGENCY
Mô tả dưới 20 ký tự
```

Backend sẽ lưu dòng 1 vào cột `AI`, dòng 2 vào cột `AI Raw / Message`, đồng thời giữ response đầy đủ trong trường event `ai_response` để debug.

## Nhiều Camera

Danh sách camera được lưu trong `data/config.json`:

```json
{
  "cameras": [
    {
      "enabled": true,
      "name": "bep",
      "rtsp_url": "rtsp://10.10.0.2:8554/bep_sub",
      "go2rtc_src": "bep",
      "live_url": ""
    }
  ]
}
```

Trong Frigate mode, mỗi camera nên có `go2rtc_src` và `go2rtc_url` để app lấy JPEG trực tiếp từ `{go2rtc_url}/api/frame.jpeg?src={go2rtc_src}`. Trường `rtsp_url` vẫn được giữ làm fallback cho cấu hình cũ. Nếu chưa có `cameras`, app sẽ tự tạo một camera mặc định từ `rtsp_url`.

Live view ưu tiên nguồn trực tiếp từ go2rtc:

1. Nếu camera có `live_url`, UI embed trực tiếp URL đó.
2. Nếu camera có `go2rtc_src` và Settings có `go2rtc_url`, UI tự tạo:

```text
{go2rtc_url}/stream.html?src={go2rtc_src}&mode=mse
```

3. Nếu thiếu cả hai, UI mới fallback sang Python MJPEG proxy `/api/camera/video`.

Khuyến nghị dùng `go2rtc_src` hoặc `live_url` để live mượt hơn và tránh delay do Python/OpenCV proxy.

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
Frigate/OpenVINO person detection
-> webhook /analyze hoặc /verify
-> go2rtc snapshot
-> AI fall verification
-> Telegram
```

## Realtime Notes

Frigate mode không chạy vòng lặp phân tích ảnh trong app. App chỉ nằm chờ webhook, lấy snapshot mới nhất rồi gọi AI. Các capture thread chỉ dùng cho mode YOLO/AI interval cũ.

## Resource Tuning

Repo vẫn giữ `opencv-python` và `ultralytics` trong `requirements.txt` để có thể quay lại mode YOLO hoặc dùng MJPEG proxy khi cần. Tuy nhiên nếu chọn `Detection Mode = Frigate/OpenVINO trigger`, Python app không load YOLO model trong luồng chính. RAM/CPU phát hiện người lúc đó nằm ở Frigate/OpenVINO.

Các cách giảm RAM/CPU:

- Dùng `Detection Mode = Frigate/OpenVINO trigger`.
- Cấu hình `go2rtc_url` và `go2rtc_src` để snapshot qua HTTP JPEG, tránh mở RTSP bằng OpenCV.
- Không bấm `Start` ở mode YOLO nếu muốn Frigate chịu trách nhiệm detect person.

Các log như:

```text
[h264] error while decoding
[rtsp] RTP: bad cseq
```

đến từ FFmpeg/OpenCV khi RTSP mất gói hoặc lệch thứ tự packet. App sẽ reconnect/tiếp tục đọc frame mới. Nếu lỗi xuất hiện dày đặc, nên ưu tiên RTSP TCP hoặc stream phụ ổn định hơn từ go2rtc.

## Frigate/OpenVINO Trigger Mode

Chọn `Detection Mode = Frigate/OpenVINO trigger` nếu Frigate đã detect `person`.
Mode này không load YOLO/PyTorch và không chạy object detection trong app.

Frigate hoặc Home Assistant gọi một trong các webhook:

```http
POST /api/frigate-trigger
POST /verify
POST /analyze
Content-Type: application/json
```

Payload tối thiểu:

```json
{
  "camera": "bep",
  "label": "person",
  "score": 0.82
}
```

Payload Frigate event có `after.camera`, `after.label`, `after.top_score` cũng được hỗ trợ.
Tên camera sẽ được map với `name` hoặc `go2rtc_src` trong danh sách Cameras. Khi nhận trigger hợp lệ, app ưu tiên chụp snapshot từ go2rtc JPEG; nếu thiếu `go2rtc_url` hoặc `go2rtc_src` thì fallback sang RTSP. Sau đó app gọi AI verify và gửi Telegram nếu AI trả về `EMERGENCY`.

Khi save Settings hoặc Cameras trong UI lúc monitor đang chạy, app sẽ tự restart monitor worker với cấu hình mới. Không cần restart uvicorn.

Với Frigate mode, endpoint webhook vẫn hoạt động dù YOLO được cài sẵn, vì app chỉ chạy verify khi Frigate gửi event `person`.
