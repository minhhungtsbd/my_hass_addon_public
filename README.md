# Home Assistant Add-ons

Repository này chứa các Home Assistant Add-on public.

## Add-ons

| Add-on | Mô tả |
| --- | --- |
| [Simple AI Vision](./simple_ai_vision) | Add-on nhẹ để phân tích snapshot camera bằng AI Vision API, match keyword và gửi cảnh báo Telegram. |

## Simple AI Vision

Luồng xử lý chính:

```text
Home Assistant motion/sensor trigger
-> POST /analyze
-> go2rtc hoặc Home Assistant Generic Camera snapshot
-> OpenAI-compatible Vision API
-> keyword matching
-> Telegram sendPhoto
-> event log và tùy chọn MQTT publish
```

Add-on này không tự polling camera mặc định. Home Assistant Automation là nơi quyết định khi nào cần gọi `/analyze`.

Tính năng chính:

- Quản lý camera trong Web UI.
- Bật/tắt Monitor cho từng camera.
- Hỗ trợ snapshot từ go2rtc `src` hoặc Home Assistant camera entity.
- Ưu tiên go2rtc nếu camera có cả `src` và `entity_id`.
- Load camera entities, go2rtc streams, motion/sensor triggers từ Home Assistant.
- Sinh YAML automation mẫu theo trigger đã chọn.
- Tab Live để xem camera từ entity, go2rtc hoặc cả hai.
- Tab Sự kiện để xem log các lần analyze.
- Tùy chọn MQTT publish event JSON.
- Test AI API, Test Telegram và Test từng camera.

Tài liệu đầy đủ: [simple_ai_vision/README.md](./simple_ai_vision/README.md)

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
8. Cài đặt rồi bấm **Start**.
9. Mở **Open Web UI** để cấu hình.

## Yêu Cầu

- Home Assistant OS hoặc Supervised có Add-on Store.
- go2rtc nếu muốn dùng snapshot/video trực tiếp từ stream.
- Camera entity trong Home Assistant nếu muốn dùng Generic Camera snapshot.
- API key từ provider OpenAI-compatible có hỗ trợ vision.
- Telegram bot token và chat ID.
- MQTT broker nếu bật tùy chọn MQTT publish.

## Gọi Từ Home Assistant Automation

Thêm `rest_command`:

```yaml
rest_command:
  simple_ai_vision_analyze:
    url: "http://127.0.0.1:8000/analyze"
    method: post
    content_type: "application/json"
    payload: "{{ payload }}"
```

Ví dụ gọi bằng go2rtc source:

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

Ví dụ gọi bằng Home Assistant camera entity:

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

Nếu `127.0.0.1:8000` không gọi được từ Home Assistant, dùng IP hoặc hostname của máy chạy add-on:

```text
http://<home-assistant-ip>:8000/analyze
```
