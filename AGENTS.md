# AGENTS.md

## Project Overview

This project is a lightweight Home Assistant Add-on for AI camera snapshot analysis.
Always use UTF-8

Workflow:

Home Assistant Motion Trigger
→ go2rtc Snapshot
→ AI Vision API
→ Keyword Matching
→ Telegram Alert

The project is intentionally minimal.

---

## Core Principles

ALWAYS prioritize:

* simplicity
* low resource usage
* maintainability
* fast startup
* low RAM usage
* low CPU usage

Avoid unnecessary abstraction.

---

## DO NOT ADD

Never introduce:

* React
* Vue
* frontend SPA
* websocket systems
* database
* ORM
* Redis
* Celery
* Frigate integration
* object detection models
* TensorFlow
* PyTorch
* OpenCV heavy pipelines
* RTSP decoding
* ffmpeg processing
* authentication systems
* user management
* background worker queues
* complex plugin systems

This addon only analyzes JPEG snapshots.

---

## Approved Stack

Allowed libraries:

* FastAPI
* requests
* uvicorn
* paho-mqtt
* standard library modules

Avoid adding dependencies unless absolutely necessary.

MQTT is allowed only as an optional integration for publishing addon events.
Do not use MQTT as a required runtime dependency for core snapshot analysis.
Avoid persistent MQTT subscriber loops unless explicitly requested.

---

## Snapshot Source

Snapshots MUST come from go2rtc:

/api/frame.jpeg?src={camera}

Do NOT implement RTSP decoding manually.

---

## AI API Requirements

Use OpenAI-compatible APIs only.

Compatible providers include:

* OpenAI
* OpenRouter
* 9Router
* Gemini OpenAI-compatible gateways

Image input format:
base64 data URL

---

## Telegram

Use Telegram Bot API only.

Preferred method:
sendPhoto

---

## Performance Targets

Target resource usage:

* RAM under 150MB idle
* Minimal CPU usage
* No persistent background loops

The addon should remain mostly idle until triggered.

---

## API Design

Keep API minimal.

Primary endpoint:

POST /analyze

No complex REST architecture.

No auth layer.

---

## Error Handling

Always handle:

* snapshot timeout
* AI API timeout
* Telegram failure
* invalid camera name
* invalid JSON
* network errors

Return clean JSON responses.

---

## Logging

Use concise logs.

Avoid excessive debug spam.

Log important stages only:

* snapshot fetch
* AI request
* keyword match
* Telegram sent
* errors

---

## Coding Style

Prefer:

* short functions
* readable code
* explicit logic
* minimal abstraction

Avoid:

* enterprise architecture
* overengineering
* unnecessary classes

Functional style preferred.

---

## Home Assistant Compatibility

Addon must remain compatible with:

* Home Assistant OS
* Supervisor Add-ons
* amd64
* aarch64

Avoid distro-specific assumptions.

---

## GitHub Updates

After each source code update, commit the changes and push them to GitHub.
Increase the add-on version in `simple_ai_vision/config.yaml` for every update.

---

## Final Goal

A lightweight production-ready AI snapshot notifier for Home Assistant using go2rtc and AI Vision APIs.
