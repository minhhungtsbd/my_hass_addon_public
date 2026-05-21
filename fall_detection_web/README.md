# Fall Detection Web

Fall Detection Web is a standalone camera monitoring web application for fall detection, incident verification, alerting, and event review.

The project is no longer positioned as a Home Assistant add-on. It is a self-hosted web app that can run on a VPS, local server, mini PC, or dedicated monitoring machine.

```text
Camera / RTSP / go2rtc
  -> local person detection
  -> AI vision verification
  -> incident timeline
  -> Telegram alert
  -> recordings and evidence review
```

## Product Direction

The application should feel like a professional security operations dashboard, not a minimal add-on panel.

Design goals:

- Clear camera status and incident priority at first glance.
- Fast access to live view, recent events, recordings, and test tools.
- Polished dark-mode interface suitable for 24/7 monitoring screens.
- Responsive layout for desktop, tablet, and mobile control.
- Professional UX for operators: fewer scattered controls, clearer actions, better feedback states.
- Independent deployment, configuration, and user session management.

The UI can evolve beyond the old lightweight add-on constraints when needed. Keep the product reliable, but prioritize a complete web-app experience.

## Core Features

- **Professional dashboard**: monitor state, camera health, system stats, recent incidents, and AI result summary.
- **Multi-camera management**: add, edit, enable, disable, test, and assign prompts per camera.
- **Live monitoring**: view cameras through go2rtc, custom live URLs, or fallback MJPEG proxy.
- **AI vision verification**: send snapshots to OpenAI-compatible vision APIs and classify results such as `SAFE` or `EMERGENCY`.
- **Telegram alerts**: send incident photos and captions when AI verification confirms an emergency.
- **Event history**: searchable incident log with thumbnails, timestamps, AI output, and camera metadata.
- **Recordings**: review uploaded clips by camera and date range.
- **Prompt management**: maintain reusable AI prompts for different camera contexts.
- **Settings UI**: configure AI provider, model, confidence, cooldowns, Telegram, go2rtc, Teldrive, and credentials.
- **Secure login**: HTTP-only JWT session cookie and bcrypt password hashing.
- **SQLite storage**: local database for settings, events, and users.

## UX/UI Requirements

The frontend should be treated as a real web product.

### Visual Style

- Dark operational dashboard theme.
- Dense but readable information layout.
- Strong status colors for running, stopped, warning, and emergency states.
- Consistent card, table, modal, toast, and tab styling.
- No emoji icons in UI controls; use SVG or a consistent icon set.
- Clear hover, active, disabled, loading, empty, and error states.

### Main Screens

| Screen | Purpose |
|---|---|
| Dashboard | System overview, quick actions, recent events, camera summary |
| Cameras | Camera CRUD, test snapshot, test AI, upload/record options |
| Prompts | Prompt templates for AI verification |
| Live | Multi-camera monitoring grid |
| Settings | AI, Telegram, go2rtc, Teldrive, detection, and account settings |
| Events | Incident history with thumbnails and filters |
| Recordings | Video evidence review |
| Tools | Manual AI test, Telegram test, image upload test |

### Interaction Standards

- Important actions must provide immediate feedback with toast or inline status.
- Destructive actions must require confirmation.
- Long AI or network operations must show a pending state.
- Tables must remain usable on small screens.
- Modals must be keyboard accessible.
- Focus states must be visible.
- Mobile layout must avoid horizontal page scroll except inside tables where needed.

## Tech Stack

Current backend and server-rendered frontend:

- Python
- FastAPI
- Jinja2 templates
- SQLite
- requests
- OpenCV / YOLO detection pipeline
- Telegram Bot API
- Teldrive API integration
- go2rtc integration for live view and snapshots

The app can later move to a richer frontend if needed, but the backend should remain simple to deploy and operate.

## Source Structure

```text
fall_detection_web/
├── app.py             # FastAPI routes and application lifecycle
├── auth.py            # Login, JWT cookie session, password hashing
├── config.py          # Settings loading, defaults, env override
├── db.py              # SQLite storage layer
├── monitor.py         # Camera monitoring and detection workflow
├── ai.py              # AI vision verification and Telegram sender
├── teldrive.py        # Teldrive upload and file helpers
├── requirements.txt
├── .env.example
├── templates/
│   ├── index.html     # Main web UI
│   └── login.html     # Login UI
└── data/              # Local runtime data, ignored by git
```

## Installation

```bash
git clone <repo>
cd fall_detection_web
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8090
```

Windows PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8090
```

Open:

```text
http://<server-ip>:8090
```

Default login:

```text
admin / admin
```

Change the default account after the first login.

## Configuration

Runtime settings are stored in SQLite at:

```text
data/fall_detection.db
```

Most settings can be changed from the **Settings** screen. Environment variables can override database settings for deployment secrets and container environments.

Create a local `.env` file from the template:

```bash
cp .env.example .env
```

Common variables:

| Variable | Purpose |
|---|---|
| `AI_BASE_URL` | OpenAI-compatible API endpoint |
| `AI_API_KEY` | Vision API key |
| `VISION_MODEL` | Vision model name |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Telegram chat ID |
| `GO2RTC_URL` | go2rtc base URL |
| `RTSP_URL` | Fallback RTSP URL |
| `YOLO_MODEL` | YOLO model file |
| `CONFIDENCE` | Person detection confidence threshold |
| `VERIFY_INTERVAL` | Minimum seconds between AI verification calls |
| `ALERT_COOLDOWN` | Minimum seconds between Telegram alerts |
| `TELDRIVE_ENABLED` | Enable Teldrive upload |
| `TELDRIVE_BASE_URL` | Teldrive server URL |
| `TELDRIVE_TOKEN` | Teldrive bearer token |
| `TELDRIVE_ROOT_PATH` | Root folder for uploaded evidence |

Priority:

```text
environment variables -> SQLite settings -> application defaults
```

## Camera Workflow

Each camera can define:

| Field | Description |
|---|---|
| Enabled | Include camera in monitoring |
| Name | Display name |
| RTSP URL | Source used by the local detection pipeline |
| go2rtc src | go2rtc stream name for snapshot/live/record helpers |
| Live URL | Optional direct live embed URL |
| Prompt | AI prompt assigned to this camera |
| Save event images locally | Store evidence images in `data/event_images/` |
| Upload event images | Upload evidence images to Teldrive |
| Record/upload video | Capture and upload short event clips |
| Record Seconds | Clip duration |
| Record Cooldown | Cooldown between camera recordings |

Snapshot preference:

1. go2rtc JPEG API: `{go2rtc_url}/api/frame.jpeg?src={go2rtc_src}`
2. RTSP/OpenCV fallback

Live view preference:

1. `live_url`
2. `{go2rtc_url}/stream.html?src={go2rtc_src}&mode=mse`
3. `/api/camera/video?index=N`

## AI Verification

The application uses OpenAI-compatible vision APIs. Compatible providers can include OpenAI, OpenRouter, 9Router, Gemini OpenAI-compatible gateways, or other services that accept compatible request formats.

Expected AI output should be easy to parse, preferably with clear labels such as:

```text
SAFE
EMERGENCY
```

The image input is sent as a base64 data URL.

## Telegram Alerts

Telegram alerts use the Telegram Bot API.

Preferred method:

```text
sendPhoto
```

Alerts should include:

- Camera name
- AI decision
- Timestamp
- Snapshot image
- Short explanation when available

Cooldown settings prevent repeated alerts for the same ongoing situation.

## Teldrive Evidence Storage

Teldrive can store event images and video clips for later review.

Default folder pattern:

```text
/Fall Detection/{camera}/images/
/Fall Detection/{camera}/videos/
```

The **Events** screen uses Teldrive metadata when available and falls back to local images when needed. The **Recordings** screen uses saved video metadata for filtering and playback.

## API Overview

All `/api/*` endpoints require an authenticated session.

```http
GET  /                              # Main web UI
GET  /login                         # Login page
POST /auth/login                    # Login form
POST /auth/logout                   # Logout

GET  /api/config                    # Read current config
POST /api/config                    # Save config
GET  /api/status                    # Monitor and system status
POST /api/start                     # Start monitoring
POST /api/stop                      # Stop monitoring

GET  /api/events                    # List events
DELETE /api/events                  # Clear events
GET  /api/recordings                # List recordings

GET  /api/camera/snapshot?index=N   # Capture camera snapshot
GET  /api/camera/video?index=N      # Camera video proxy

POST /api/test-ai                   # Test AI with latest snapshot
POST /api/test-ai-camera?index=N    # Test AI with selected camera
POST /api/test-telegram             # Test Telegram alert
POST /api/test-ai-upload            # Test AI with uploaded image

GET  /api/event-image/{filename}    # Local event image
GET  /api/teldrive/file/{id}/{name} # Teldrive file proxy
```

## Run as a Service

Example systemd service:

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

Enable:

```bash
systemctl enable --now fall-detection
journalctl -u fall-detection -f
```

## UI Roadmap

Near-term professional UI improvements:

- Replace emoji and text-only controls with consistent SVG icons.
- Redesign dashboard with status-first layout and incident severity hierarchy.
- Improve camera table into an operator-friendly management view.
- Add better empty states for no cameras, no events, and no recordings.
- Add loading states for AI tests, Telegram tests, snapshot capture, and recordings.
- Improve mobile navigation and table handling.
- Standardize form groups, destructive actions, modals, and toast messages.
- Add clearer visual treatment for emergency events.

Possible future frontend upgrade:

- Keep the FastAPI API as backend.
- Add a modern frontend only if the UX demands it.
- Preserve simple deployment with a single server process or a clearly documented build step.

## Notes

- `data/`, `.env`, snapshots, recordings, and local database files must not be committed.
- Change the default admin password before exposing the app.
- Put the app behind HTTPS when used outside a private LAN.
- AI provider latency and cost depend on the selected vision model.
- Camera stream stability depends on RTSP source, network quality, and go2rtc configuration.
