# Simple AI Vision

Simple AI Vision là Home Assistant Add-on tối giản để phân tích snapshot JPEG từ go2rtc bằng AI Vision API và gửi thông báo Telegram khi kết quả phân tích khớp keyword.

## Tính Năng

- Nhận trigger qua `POST /analyze`.
- Lấy snapshot từ go2rtc: `/api/frame.jpeg?src={camera}`.
- Gửi ảnh dạng `data:image/jpeg;base64,...` tới OpenAI-compatible `chat/completions`.
- Match keyword case-insensitive, hỗ trợ regex.
- Gửi Telegram bằng Bot API `sendPhoto`.
- Web UI đơn giản để chỉnh cấu hình và test nhiều camera.
- Có nút test AI API riêng trước khi test camera.
- Có nút lưu riêng trong phần Cameras.
- Cấu hình lưu từ Web UI được giữ trong `/data/simple_ai_vision_config.json` để tránh bị Supervisor ghi đè khi restart hoặc update.
- Không database, không MQTT, không video streaming, không frontend SPA.

## Cài Đặt

1. Mở Home Assistant.
2. Vào **Settings** -> **Add-ons** -> **Add-on Store**.
3. Bấm menu **...** -> **Repositories**.
4. Thêm repository:

```text
https://github.com/minhhungtsbd/my_hass_addon_public
```

5. Cài add-on **Simple AI Vision**.
6. Mở tab **Configuration** và điền options.
7. Bấm **Start**.
8. Bấm **Open Web UI** để chỉnh cấu hình, thêm camera và test nhanh.

## Cấu Hình

```yaml
go2rtc_url: "http://homeassistant.local:1984"
ai_api_key: "sk-..."
ai_base_url: "https://api.openai.com/v1"
ai_model: "gpt-4o-mini"
telegram_bot_token: "123456:ABC..."
telegram_chat_id: "123456789"
prompt: "Bạn đang phân tích ảnh camera an ninh.\nChỉ mô tả các sự kiện quan trọng liên quan đến an ninh.\nNếu không có gì quan trọng hãy trả lời NORMAL."
keyword_match:
  - person
  - human
  - stranger
  - fire
  - smoke
  - người
  - cháy
cameras:
  - garage
  - front_gate
ai_timeout: 30
snapshot_timeout: 10
telegram_timeout: 10
```

## Lấy IP Và Hostname Local Cho go2rtc

go2rtc API thường chạy ở port `1984`. Log go2rtc sẽ có dòng:

```text
[api] listen addr=:1984
```

Cách lấy IP hoặc hostname trong Home Assistant:

1. Vào **Settings** -> **System** -> **Network**.
2. Xem **The name your instance will have on your network** để lấy hostname.
3. Nếu hostname là `HomeAssistant-Hung`, thử dùng:

```text
http://homeassistant-hung.local:1984
```

4. Xem **Home Assistant URL** -> **Local network** để lấy IP nội bộ, ví dụ:

```text
http://192.168.1.101:8123
```

5. Đổi port `8123` thành `1984`:

```text
http://192.168.1.101:1984
```

Trong Web UI, trường `go2rtc_url` chỉ nhập base URL:

```text
http://192.168.1.101:1984
```

Không nhập nguyên URL snapshot:

```text
http://192.168.1.101:1984/api/frame.jpeg?src=bep
```

Camera chỉ nhập tên stream:

```text
bep
```

Addon sẽ tự ghép thành:

```text
http://192.168.1.101:1984/api/frame.jpeg?src=bep
```

## Options

| Option | Mô tả |
| --- | --- |
| `go2rtc_url` | URL go2rtc, ví dụ `http://homeassistant.local:1984` |
| `ai_api_key` | API key của provider OpenAI-compatible |
| `ai_base_url` | Base URL API, ví dụ `https://api.openai.com/v1` |
| `ai_model` | Model vision cần dùng |
| `telegram_bot_token` | Telegram bot token |
| `telegram_chat_id` | Telegram chat ID nhận cảnh báo |
| `prompt` | Prompt gửi cho AI |
| `keyword_match` | Danh sách keyword hoặc regex để quyết định gửi Telegram |
| `cameras` | Danh sách camera go2rtc để thao tác nhanh trong Web UI |
| `ai_timeout` | Timeout khi gọi AI API, đơn vị giây |
| `snapshot_timeout` | Timeout khi lấy snapshot, đơn vị giây |
| `telegram_timeout` | Timeout khi gửi Telegram, đơn vị giây |

## API

Web UI:

```http
GET /
```

Config API dùng bởi Web UI:

```http
GET /api/config
POST /api/config
POST /api/test-ai
```

Endpoint:

```http
POST /analyze
Content-Type: application/json
```

Request:

```json
{
  "camera": "garage"
}
```

Response khi khớp keyword:

```json
{
  "success": true,
  "matched": true,
  "analysis": "Có một người đang đứng trước cổng."
}
```

Response khi không khớp:

```json
{
  "success": true,
  "matched": false,
  "analysis": "NORMAL"
}
```

## Home Assistant Automation

Thêm `rest_command`:

```yaml
rest_command:
  simple_ai_vision_analyze:
    url: "http://127.0.0.1:8000/analyze"
    method: post
    content_type: "application/json"
    payload: '{"camera":"garage"}'
```

Gọi từ automation:

```yaml
action:
  - service: rest_command.simple_ai_vision_analyze
```

Nếu Home Assistant không gọi được `127.0.0.1`, dùng IP hoặc hostname của máy chạy add-on:

```yaml
url: "http://<home-assistant-ip>:8000/analyze"
```

## Provider AI

Add-on dùng chuẩn OpenAI-compatible `chat/completions`.

Ảnh được gửi trong message content:

```text
data:image/jpeg;base64,...
```

Các provider thường dùng:

- OpenAI
- OpenRouter
- 9Router
- Gemini qua OpenAI-compatible gateway

## Telegram

Add-on gửi ảnh bằng Telegram Bot API `sendPhoto`.

Caption gồm:

```text
Camera: <camera>

<AI analysis result>
```

## Kiểm Tra Nhanh

```bash
curl -X POST http://<home-assistant-ip>:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"camera":"garage"}'
```
