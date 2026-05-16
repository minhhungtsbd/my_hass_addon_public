# Simple AI Vision

Simple AI Vision là Home Assistant Add-on nhẹ để phân tích ảnh snapshot camera bằng AI Vision API, match keyword và gửi cảnh báo Telegram.

Luồng chính:

```text
Frigate person event qua MQTT
-> POST /analyze
-> lấy snapshot từ go2rtc hoặc Frigate latest frame
-> OpenAI-compatible Vision API
-> keyword matching
-> Telegram sendPhoto
-> ghi sự kiện
```

Addon không tự polling camera mặc định. Home Assistant Automation là nơi quyết định khi nào cần gọi `/analyze`.

## Tính Năng

- Nhận trigger qua `POST /analyze`.
- Hỗ trợ snapshot từ go2rtc `/api/frame.jpeg?src={camera}`.
- Fallback snapshot từ Frigate API `/api/<camera>/latest.jpg`.
- Gửi ảnh dạng `data:image/jpeg;base64,...` tới OpenAI-compatible `chat/completions`.
- Hỗ trợ OpenAI, OpenRouter, 9Router, Gemini qua OpenAI-compatible gateway.
- Match keyword hoặc regex, không phân biệt hoa thường.
- Gửi Telegram bằng Bot API `sendPhoto`.
- Nút test AI API và test Telegram riêng.
- Tab Cameras để quản lý camera, bật/tắt monitor từng camera.
- Load stream trực tiếp từ go2rtc.
- Tab Live để xem live bằng snapshot refresh qua backend.
- Tab Sự kiện để xem kết quả analyze: `sent`, `no_match`, `telegram_error`, lỗi network/config.
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
| `go2rtc src` | Tên stream go2rtc, ví dụ `bep` |

Nút trong tab Cameras:

- `Load go2rtc`: load stream từ `go2rtc_url/api/streams`.
- `Add Stream`: thêm stream go2rtc đã chọn.
- `Snapshot`: xem ảnh snapshot.
- `Live`: xem snapshot refresh qua backend.
- `Test`: gọi `/analyze` thủ công.
- `Save Cameras`: lưu camera.

Camera cấu hình bằng `go2rtc src`. Với Frigate fallback, `go2rtc src` chính là tên camera/stream trong Frigate, ví dụ `bep`.

## Home Assistant Automation

Addon không tự chạy nền. Muốn tự động thì Home Assistant Automation cần gọi `/analyze`.

Ví dụ `rest_command`:

```yaml
rest_command:
  simple_ai_vision_analyze:
    url: "http://127.0.0.1:8000/analyze"
    method: post
    content_type: "application/json"
    payload: "{{ payload }}"
```

Ví dụ automation dùng chung cho mọi camera Frigate:

```yaml
automation:
  - alias: "Simple AI Vision - Frigate person"
    trigger:
      - platform: mqtt
        topic: frigate/events
    condition:
      - condition: template
        value_template: >
          {{ trigger.payload_json["after"]["label"] == "person"
             and trigger.payload_json["type"] in ["new", "update"] }}
    action:
      - service: rest_command.simple_ai_vision_analyze
        data:
          payload: >
            {"camera":"{{ trigger.payload_json['after']['camera'] }}"}
    mode: single
```

Nếu đã cấu hình danh sách camera trong tab Cameras, `/analyze` chỉ xử lý camera có trong danh sách đó. Camera chưa thêm vào Simple AI Vision sẽ được bỏ qua.

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
GET /api/go2rtc/streams
GET /api/events
```

Analyze:

```http
POST /analyze
Content-Type: application/json

{
  "camera": "bep"
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

Tab Live dùng snapshot refresh qua Simple AI Vision backend. Cách này hoạt động với Frigate add-on hostname nội bộ như `ccab4aaf-frigate`.

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
| `telegram_error` | Match keyword nhưng Telegram lỗi |
| `config_error` | Thiếu hoặc sai cấu hình |
| `timeout` | Timeout mạng |
| `upstream_error` | API upstream trả HTTP error |
| `network_error` | Lỗi network |
| `internal_error` | Lỗi không mong muốn |

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

## Frigate Add-on Streams

Simple AI Vision can discover camera names from the Frigate add-on when loading go2rtc streams. It tries the configured `go2rtc_url` first, then Frigate built-in go2rtc on port `1984`, then Frigate API on port `5000`.

Use the optional `frigate_url` setting when auto-discovery cannot find the Frigate add-on, for example:

```text
http://ccab4aaf-frigate:5000
```

Snapshot analysis prefers go2rtc:

```text
{go2rtc_url}/api/frame.jpeg?src=<camera>
```

If Frigate's go2rtc API port `1984` is not reachable, Simple AI Vision falls back to the Frigate API latest frame endpoint:

```text
{frigate_url}/api/<camera>/latest.jpg
```

For the Home Assistant Frigate add-on, use:

```text
frigate_url = http://ccab4aaf-frigate:5000
```

The Frigate `8555` port is WebRTC and is not used for snapshot analysis.

The **Live** button and **Live** tab use a lightweight refreshed snapshot view through Simple AI Vision, which works with the Frigate API fallback and internal add-on hostnames.

To trigger analysis from Frigate person detection, enable MQTT in Frigate and use a Home Assistant automation on `frigate/events`:

```yaml
trigger:
  - platform: mqtt
    topic: frigate/events
condition:
  - condition: template
    value_template: >
      {{ trigger.payload_json["after"]["label"] == "person"
         and trigger.payload_json["type"] in ["new", "update"] }}
action:
  - service: rest_command.simple_ai_vision_analyze
    data:
      payload: >
        {"camera":"{{ trigger.payload_json['after']['camera'] }}"}
```
