# Home Assistant Add-ons

Repository này chứa các Home Assistant Add-on public.

## Add-ons

### Simple AI Vision

Add-on tối giản dùng để phân tích snapshot camera bằng AI Vision API và gửi cảnh báo Telegram khi nội dung phân tích khớp keyword.

Luồng xử lý:

```text
Home Assistant Automation
-> POST /analyze
-> go2rtc snapshot
-> OpenAI-compatible Vision API
-> keyword matching
-> Telegram sendPhoto
```

Add-on hiện có:

| Add-on | Mô tả |
| --- | --- |
| [Simple AI Vision](./simple_ai_vision) | Phân tích ảnh JPEG từ go2rtc bằng AI Vision API, có Web UI cấu hình cơ bản, test AI API và gửi Telegram khi khớp keyword |

## Cài Đặt Repository

1. Mở Home Assistant.
2. Vào **Settings** -> **Add-ons** -> **Add-on Store**.
3. Bấm menu **...** góc phải trên.
4. Chọn **Repositories**.
5. Thêm URL repository:

```text
https://github.com/minhhungtsbd/my_hass_addon_public
```

6. Bấm **Add**.
7. Tìm add-on **Simple AI Vision** trong Add-on Store.
8. Cài đặt, cấu hình options, rồi bấm **Start**.
9. Mở tab **Open Web UI** để chỉnh cấu hình và thêm camera.

## Yêu Cầu

- Home Assistant OS hoặc Supervised có Add-on Store.
- go2rtc đang chạy và có thể lấy snapshot qua `/api/frame.jpeg?src={camera}`.
- API key từ provider OpenAI-compatible có hỗ trợ vision.
- Telegram bot token và chat ID.

## Lấy IP Và Hostname Local

Để cấu hình `go2rtc_url`, cần lấy địa chỉ nội bộ của Home Assistant.

Cách xem trong Home Assistant:

1. Vào **Settings** -> **System** -> **Network**.
2. Xem phần **The name your instance will have on your network** để lấy hostname.
3. Nếu hostname là `HomeAssistant-Hung`, URL local thường là:

```text
http://homeassistant-hung.local:1984
```

4. Xem phần **Home Assistant URL** -> **Local network** để lấy IP nội bộ, ví dụ:

```text
http://192.168.1.101:8123
```

5. Đổi port Home Assistant `8123` sang port go2rtc `1984`:

```text
http://192.168.1.101:1984
```

URL snapshot sẽ có dạng:

```text
http://192.168.1.101:1984/api/frame.jpeg?src=bep
```

Trong Web UI chỉ điền `go2rtc_url` là base URL:

```text
http://192.168.1.101:1984
```

Camera chỉ điền tên stream:

```text
bep
```

## Gọi Từ Automation

Sau khi add-on chạy, gọi API:

```http
POST http://<home-assistant-ip>:8000/analyze
Content-Type: application/json

{
  "camera": "garage"
}
```

Ví dụ Home Assistant automation action:

```yaml
action:
  - service: rest_command.simple_ai_vision_analyze
```

Ví dụ `rest_command`:

```yaml
rest_command:
  simple_ai_vision_analyze:
    url: "http://127.0.0.1:8000/analyze"
    method: post
    content_type: "application/json"
    payload: '{"camera":"garage"}'
```
