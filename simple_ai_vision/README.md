# Simple AI Vision

Simple AI Vision là Home Assistant Add-on nhẹ để phân tích ảnh snapshot camera bằng AI Vision API, match keyword và gửi cảnh báo Telegram.

Luồng chính:

```text
Motion/sensor trigger trong Home Assistant
-> POST /analyze
-> lấy snapshot từ go2rtc hoặc Home Assistant Generic Camera
-> OpenAI-compatible Vision API
-> keyword matching
-> Telegram sendPhoto
-> ghi sự kiện và tùy chọn publish MQTT
```

Addon không tự polling camera mặc định. Home Assistant Automation là nơi quyết định khi nào cần gọi `/analyze`.

## Tính Năng

- Nhận trigger qua `POST /analyze`.
- Hỗ trợ hai nguồn snapshot:
  - go2rtc: `/api/frame.jpeg?src={camera}`
  - Home Assistant Generic Camera: `/api/camera_proxy/{entity_id}`
- Ưu tiên go2rtc `src` nếu camera có cả `src` và `entity_id`.
- Gửi ảnh dạng `data:image/jpeg;base64,...` tới OpenAI-compatible `chat/completions`.
- Hỗ trợ OpenAI, OpenRouter, 9Router, Gemini qua OpenAI-compatible gateway.
- Match keyword hoặc regex, không phân biệt hoa thường.
- Gửi Telegram bằng Bot API `sendPhoto`.
- Nút test AI API và test Telegram riêng.
- Tab Cameras để quản lý camera, bật/tắt monitor từng camera.
- Load camera entity từ Home Assistant.
- Load stream trực tiếp từ go2rtc.
- Load motion/sensor trigger từ Home Assistant và sinh YAML automation mẫu.
- Tab Live để xem live bằng go2rtc stream hoặc snapshot entity tự refresh.
- Tab Sự kiện để xem kết quả analyze: `sent`, `no_match`, `disabled`, `telegram_error`, lỗi network/config.
- Tùy chọn MQTT publish event JSON.
- Config lưu tại `/data/simple_ai_vision_config.json`.
- Event log lưu tại `/data/simple_ai_vision_events.jsonl`.
- Không database, không object detection local, không RTSP decode, không ffmpeg processing.

## Cài Đặt

1. Mở Home Assistant.
2. Vào **Settings** -> **Add-ons** -> **Add-on Store**.
3. Bấm menu **...** -> **Repositories**.
4. Thêm repository:

```text
https://github.com/minhhungtsbd/my_hass_addon_public
```

5. Cài add-on **Simple AI Vision**.
6. Bấm **Start**.
7. Bấm **Open Web UI** để cấu hình.

## Core Settings

Các trường chính:

| Option | Mô tả |
| --- | --- |
| `go2rtc_url` | Base URL go2rtc, ví dụ `http://homeassistant.local:1984` |
| `ai_api_key` | API key provider OpenAI-compatible |
| `ai_base_url` | Base URL API, ví dụ `https://api.openai.com/v1` hoặc `https://9router.example/v1` |
| `ai_model` | Model vision cần dùng |
| `telegram_bot_token` | Telegram bot token |
| `telegram_chat_id` | Chat ID nhận cảnh báo |
| `prompt` | Prompt gửi cho AI |
| `keyword_match` | Mỗi dòng là keyword hoặc regex |
| `ai_timeout` | Thời gian chờ AI API, giây |
| `snapshot_timeout` | Thời gian chờ snapshot, giây |
| `telegram_timeout` | Thời gian chờ Telegram API, giây |

Timeout không phải lịch chạy tự động. Timeout chỉ là thời gian chờ tối đa cho từng request.

Prompt gợi ý:

```text
Bạn là hệ thống phân tích ảnh camera trong nhà.

Nếu thấy người trong ảnh, chỉ trả lời:
ALERT_PERSON: mô tả ngắn trong tối đa 20 từ.

Nếu không thấy người, chỉ trả lời:
NORMAL

Không giải thích.
Không hướng dẫn.
Không viết code.
Không nhắc đến Telegram.
```

Keyword gợi ý:

```text
ALERT_PERSON
fire
smoke
cháy
```

## Cameras

Mỗi camera có các trường:

| Field | Mô tả |
| --- | --- |
| `Monitor` | Bật/tắt theo dõi. Nếu tắt, `/analyze` sẽ trả `skipped: true` và không gọi AI |
| `Name` | Tên hiển thị |
| `HA entity` | Entity Home Assistant, ví dụ `camera.camera_bep_go2rtc` |
| `Trigger` | Motion/sensor entity dùng để sinh YAML automation |
| `go2rtc src` | Tên stream go2rtc, ví dụ `bep` |

Nút trong tab Cameras:

- `Load Entities`: load `camera` và `image` entity từ Home Assistant.
- `Add Selected`: thêm entity đã chọn.
- `Load go2rtc`: load stream từ `go2rtc_url/api/streams`.
- `Add Stream`: thêm stream go2rtc đã chọn.
- `Load Motion/Sensors`: load `binary_sensor` và `sensor` để chọn trigger.
- `Snapshot`: xem ảnh snapshot.
- `Video`: xem go2rtc stream nếu có `src`; nếu chỉ có entity thì xem snapshot tự refresh.
- `Test`: gọi `/analyze` thủ công.
- `Save Cameras`: lưu camera và trigger.

Camera chỉ có `HA entity` vẫn dùng được. Camera chỉ có `go2rtc src` cũng dùng được. Nếu có cả hai thì phân tích ưu tiên go2rtc.

## Home Assistant Automation

Addon không tự chạy nền. Muốn tự động thì Home Assistant Automation cần gọi `/analyze`.

Trong tab Cameras, sau khi chọn `Trigger`, addon sẽ sinh YAML mẫu ở phần **Automation YAML**.

Ví dụ `rest_command`:

```yaml
rest_command:
  simple_ai_vision_analyze:
    url: "http://127.0.0.1:8000/analyze"
    method: post
    content_type: "application/json"
    payload: "{{ payload }}"
```

Ví dụ automation với go2rtc source:

```yaml
automation:
  - alias: "Simple AI Vision - Bếp"
    trigger:
      - platform: state
        entity_id: binary_sensor.motion_bep
        to: "on"
    action:
      - service: rest_command.simple_ai_vision_analyze
        data:
          payload: '{"camera":"bep"}'
    mode: single
```

Ví dụ automation với Home Assistant camera entity:

```yaml
automation:
  - alias: "Simple AI Vision - Bếp Entity"
    trigger:
      - platform: state
        entity_id: binary_sensor.motion_bep
        to: "on"
    action:
      - service: rest_command.simple_ai_vision_analyze
        data:
          payload: '{"entity_id":"camera.camera_bep_go2rtc"}'
    mode: single
```

Nếu `127.0.0.1:8000` không gọi được từ Home Assistant, dùng IP/hostname của máy chạy add-on:

```text
http://<home-assistant-ip>:8000/analyze
```

## API

Web UI:

```http
GET /
```

Config và test:

```http
GET /api/config
POST /api/config
POST /api/test-ai
POST /api/test-telegram
```

Camera helpers:

```http
GET /api/camera/frame?camera=bep
GET /api/camera/frame?entity_id=camera.camera_bep_go2rtc
GET /api/hass/cameras
GET /api/hass/triggers
GET /api/go2rtc/streams
GET /api/events
```

Analyze bằng go2rtc:

```http
POST /analyze
Content-Type: application/json

{
  "camera": "bep"
}
```

Analyze bằng Home Assistant entity:

```http
POST /analyze
Content-Type: application/json

{
  "entity_id": "camera.camera_bep_go2rtc"
}
```

Response match:

```json
{
  "success": true,
  "matched": true,
  "matched_keyword": "ALERT_PERSON",
  "analysis": "ALERT_PERSON: Có người đang ngồi trước bàn."
}
```

Response không match:

```json
{
  "success": true,
  "matched": false,
  "matched_keyword": "",
  "analysis": "NORMAL"
}
```

Response camera tắt Monitor:

```json
{
  "success": true,
  "skipped": true,
  "reason": "camera disabled",
  "camera": "bep"
}
```

## Tab Live

Tab Live hỗ trợ:

- `Both sources`: ưu tiên go2rtc nếu camera có `src`, nếu không thì dùng entity snapshot.
- `Entities only`: chỉ xem nguồn Home Assistant entity.
- `go2rtc only`: chỉ xem stream go2rtc.
- `Camera Limit`: giới hạn số camera hiển thị.

go2rtc dùng `stream.html?src={src}&mode=mse`. Entity dùng snapshot proxy và tự refresh.

## Tab Sự Kiện

Tab Sự kiện đọc file:

```text
/data/simple_ai_vision_events.jsonl
```

Các trạng thái thường gặp:

| Status | Ý nghĩa |
| --- | --- |
| `sent` | Đã match keyword và gửi Telegram thành công |
| `no_match` | AI trả lời nhưng không khớp keyword |
| `disabled` | Camera bị tắt Monitor |
| `telegram_error` | Match keyword nhưng Telegram lỗi |
| `config_error` | Thiếu hoặc sai cấu hình |
| `timeout` | Timeout mạng |
| `upstream_error` | API upstream trả HTTP error |
| `network_error` | Lỗi network |
| `internal_error` | Lỗi không mong muốn |

## MQTT

MQTT là tùy chọn. Core analyze không phụ thuộc MQTT.

Khi bật `MQTT Publish`, addon publish mỗi event dạng JSON tới topic đã cấu hình.

Các trường MQTT:

| Option | Mô tả |
| --- | --- |
| `mqtt_enabled` | Bật/tắt publish MQTT |
| `mqtt_host` | MQTT broker host |
| `mqtt_port` | MQTT broker port, mặc định `1883` |
| `mqtt_topic` | Topic, mặc định `simple_ai_vision/events` |
| `mqtt_username` | Username nếu broker yêu cầu |
| `mqtt_password` | Password nếu broker yêu cầu |

Payload ví dụ:

```json
{
  "time": "2026-05-14T11:06:57+00:00",
  "status": "sent",
  "camera": "bep",
  "keyword": "ALERT_PERSON",
  "analysis": "ALERT_PERSON: Có người đang ngồi trước bàn.",
  "error": ""
}
```

## Provider AI

Addon dùng OpenAI-compatible `chat/completions`.

Ảnh được gửi trong message content:

```text
data:image/jpeg;base64,...
```

Với 9Router, trường `AI Base URL` chỉ nhập base URL có `/v1`, không nhập `/chat/completions`:

```text
https://9router.example/v1
```

Addon tự ghép:

```text
/chat/completions
```

## Telegram

Addon gửi ảnh bằng Telegram Bot API `sendPhoto`.

Caption:

```text
Camera: <camera>

<AI analysis result>
```

Nút `Test Telegram` gửi tin nhắn text để kiểm tra token/chat ID trước khi test camera.

## Kiểm Tra Nhanh

```bash
curl -X POST http://<home-assistant-ip>:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"camera":"bep"}'
```

Hoặc:

```bash
curl -X POST http://<home-assistant-ip>:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"entity_id":"camera.camera_bep_go2rtc"}'
```

## Frigate Add-on Streams

Simple AI Vision can discover camera names from the Frigate add-on when loading go2rtc streams. It tries the configured `go2rtc_url` first, then Frigate built-in go2rtc on port `1984`, then Frigate API on port `5000`.

Use the optional `frigate_url` setting when auto-discovery cannot find the Frigate add-on, for example:

```text
http://ccab4aaf-frigate:5000
```

Snapshot analysis still uses go2rtc:

```text
{go2rtc_url}/api/frame.jpeg?src=<camera>
```

If Frigate cameras load but snapshots fail, expose/enable the Frigate go2rtc API port `1984` or enter a reachable go2rtc URL manually.
