import base64
import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CONFIG_PATH = DATA_DIR / "config.json"
EVENTS_PATH = DATA_DIR / "events.jsonl"
SNAPSHOT_PATH = DATA_DIR / "latest.jpg"
VERIFY_PATH = DATA_DIR / "verify.jpg"

DEFAULT_CONFIG: dict[str, Any] = {
    "rtsp_url": "",
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "ai_base_url": "https://9router.minhhungtsbd.me/v1",
    "ai_api_key": "",
    "vision_model": "gh/oswe-vscode-prime",
    "yolo_model": "yolov8s.pt",
    "confidence": 0.5,
    "verify_interval": 20,
    "alert_cooldown": 300,
    "frame_skip": 2,
    "loop_sleep": 0.3,
}

PROMPT = """Đây là ảnh camera giám sát người già trong nhà.

Hãy xác định:
- Người có bị té ngã không
- Người có đang gặp nguy hiểm không
- Người có đang nằm dưới đất bất thường không
- Người có đang cần trợ giúp không
- Người có đang cố đứng dậy nhưng thất bại không

Nếu nguy hiểm trả lời:
EMERGENCY

Nếu bình thường trả lời:
SAFE

Chỉ trả lời đúng 1 từ:
SAFE
hoặc
EMERGENCY
"""

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("fall_detection_web")

app = FastAPI(title="Fall Detection Web")

state_lock = threading.Lock()
stop_event = threading.Event()
worker_thread: threading.Thread | None = None
status: dict[str, Any] = {
    "running": False,
    "started_at": "",
    "last_error": "",
    "last_person_confidence": 0,
    "last_ai_result": "",
    "last_verify_at": "",
    "last_alert_at": "",
    "frames": 0,
}


INDEX_HTML = r"""
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Fall Detection Control</title>
  <style>
    :root {
      --bg: #081018;
      --panel: #132130;
      --panel-2: #0d1722;
      --text: #f4f8ff;
      --muted: #9bb1c8;
      --line: #284158;
      --accent: #12a9f5;
      --danger: #ff453a;
      --ok: #20c26a;
      --warn: #ffb020;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Arial, Helvetica, sans-serif;
      font-size: 14px;
    }
    main {
      max-width: 1180px;
      margin: 0 auto;
      padding: 22px;
    }
    header {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: flex-start;
      margin-bottom: 18px;
    }
    h1, h2, h3 { margin: 0; }
    h1 { font-size: 26px; }
    h2 { font-size: 18px; margin-bottom: 14px; }
    p { color: var(--muted); margin: 6px 0 0; }
    .tabs {
      display: flex;
      gap: 18px;
      border-bottom: 1px solid var(--line);
      margin-bottom: 14px;
      overflow-x: auto;
    }
    .tab-btn {
      border: 0;
      border-bottom: 2px solid transparent;
      border-radius: 0;
      background: transparent;
      color: var(--muted);
      padding: 12px 0;
    }
    .tab-btn.active {
      color: var(--text);
      border-color: var(--accent);
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
      margin-bottom: 14px;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }
    .full { grid-column: 1 / -1; }
    label {
      display: block;
      color: var(--muted);
      font-weight: 700;
      font-size: 12px;
      margin-bottom: 6px;
    }
    input, textarea {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--panel-2);
      color: var(--text);
      padding: 11px;
      font: inherit;
    }
    textarea { min-height: 120px; resize: vertical; }
    button {
      border: 1px solid var(--accent);
      background: transparent;
      color: var(--accent);
      border-radius: 6px;
      padding: 10px 14px;
      font-weight: 700;
      cursor: pointer;
    }
    button.primary {
      background: var(--accent);
      color: #00111d;
    }
    button.danger {
      border-color: var(--danger);
      color: var(--danger);
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }
    .status-pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 8px 12px;
      color: var(--muted);
      background: var(--panel-2);
      font-weight: 700;
    }
    .dot {
      width: 10px;
      height: 10px;
      border-radius: 999px;
      background: var(--muted);
    }
    .dot.running { background: var(--ok); }
    .dot.error { background: var(--danger); }
    .cards {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 14px;
    }
    .card {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: var(--panel-2);
    }
    .card b { display: block; font-size: 18px; margin-top: 4px; }
    img.preview {
      width: 100%;
      max-height: 560px;
      object-fit: contain;
      background: #03070b;
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
    }
    th, td {
      text-align: left;
      border-bottom: 1px solid var(--line);
      padding: 9px 8px;
      vertical-align: top;
    }
    th { color: var(--muted); font-size: 12px; }
    pre {
      white-space: pre-wrap;
      overflow: auto;
      background: var(--panel-2);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      min-height: 48px;
    }
    .ok { color: var(--ok); }
    .err { color: var(--danger); }
    .warn { color: var(--warn); }
    .hidden { display: none; }
    @media (max-width: 760px) {
      main { padding: 14px; }
      header { flex-direction: column; }
      .grid, .cards { grid-template-columns: 1fr; }
      button { width: 100%; }
      .actions { align-items: stretch; flex-direction: column; }
      th:nth-child(5), td:nth-child(5) { display: none; }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Fall Detection Control</h1>
        <p>YOLO person detect -> AI fall verification -> Telegram alert</p>
      </div>
      <div class="status-pill"><span id="runDot" class="dot"></span><span id="runText">Stopped</span></div>
    </header>

    <nav class="tabs">
      <button class="tab-btn active" data-tab="dashboardPanel" type="button">Dashboard</button>
      <button class="tab-btn" data-tab="settingsPanel" type="button">Settings</button>
      <button class="tab-btn" data-tab="eventsPanel" type="button">Events</button>
      <button class="tab-btn" data-tab="toolsPanel" type="button">Tools</button>
    </nav>

    <section id="dashboardPanel" class="tab-panel">
      <div class="cards">
        <div class="card"><span>Frames</span><b id="frames">0</b></div>
        <div class="card"><span>Person conf</span><b id="personConf">0</b></div>
        <div class="card"><span>AI result</span><b id="aiResult">-</b></div>
        <div class="card"><span>Last verify</span><b id="lastVerify">-</b></div>
      </div>
      <div class="panel">
        <h2>Monitor</h2>
        <div class="actions">
          <button id="startBtn" class="primary" type="button">Start</button>
          <button id="stopBtn" class="danger" type="button">Stop</button>
          <button id="captureBtn" type="button">Capture Snapshot</button>
          <button id="refreshStatusBtn" type="button">Refresh</button>
          <span id="actionStatus"></span>
        </div>
      </div>
      <div class="panel">
        <h2>Latest Snapshot</h2>
        <img id="snapshotImg" class="preview" alt="Latest snapshot">
      </div>
    </section>

    <section id="settingsPanel" class="tab-panel hidden">
      <div class="panel">
        <h2>Settings</h2>
        <div class="grid">
          <div class="full">
            <label for="rtsp_url">RTSP URL</label>
            <input id="rtsp_url" autocomplete="off" placeholder="rtsp://10.10.0.2:8554/bep_sub">
          </div>
          <div>
            <label for="ai_base_url">AI Base URL</label>
            <input id="ai_base_url" autocomplete="off" placeholder="https://9router.minhhungtsbd.me/v1">
          </div>
          <div>
            <label for="vision_model">Vision Model</label>
            <input id="vision_model" autocomplete="off" placeholder="gh/oswe-vscode-prime">
          </div>
          <div>
            <label for="ai_api_key">AI API Key</label>
            <input id="ai_api_key" type="password" autocomplete="new-password">
          </div>
          <div>
            <label for="yolo_model">YOLO Model</label>
            <input id="yolo_model" autocomplete="off" placeholder="yolov8s.pt">
          </div>
          <div>
            <label for="telegram_bot_token">Telegram Bot Token</label>
            <input id="telegram_bot_token" type="password" autocomplete="new-password">
          </div>
          <div>
            <label for="telegram_chat_id">Telegram Chat ID</label>
            <input id="telegram_chat_id" autocomplete="off">
          </div>
          <div>
            <label for="confidence">YOLO Confidence</label>
            <input id="confidence" type="number" min="0.01" max="1" step="0.01">
          </div>
          <div>
            <label for="verify_interval">Verify Interval (seconds)</label>
            <input id="verify_interval" type="number" min="1">
          </div>
          <div>
            <label for="alert_cooldown">Alert Cooldown (seconds)</label>
            <input id="alert_cooldown" type="number" min="1">
          </div>
          <div>
            <label for="frame_skip">Frame Skip</label>
            <input id="frame_skip" type="number" min="1">
          </div>
          <div>
            <label for="loop_sleep">Loop Sleep (seconds)</label>
            <input id="loop_sleep" type="number" min="0" step="0.1">
          </div>
        </div>
        <div class="actions" style="margin-top:14px">
          <button id="saveConfigBtn" class="primary" type="button">Save Settings</button>
          <button id="reloadConfigBtn" type="button">Reload</button>
          <span id="configStatus"></span>
        </div>
      </div>
    </section>

    <section id="eventsPanel" class="tab-panel hidden">
      <div class="panel">
        <h2>Events</h2>
        <div class="actions">
          <button id="refreshEventsBtn" type="button">Refresh Events</button>
          <span id="eventsStatus"></span>
        </div>
        <table>
          <thead>
            <tr><th>Time</th><th>Status</th><th>Confidence</th><th>AI</th><th>Message</th></tr>
          </thead>
          <tbody id="eventsBody"></tbody>
        </table>
      </div>
    </section>

    <section id="toolsPanel" class="tab-panel hidden">
      <div class="panel">
        <h2>Tools</h2>
        <div class="actions">
          <button id="testAiBtn" type="button">Test AI With Latest Snapshot</button>
          <button id="testTelegramBtn" type="button">Test Telegram</button>
          <span id="toolStatus"></span>
        </div>
        <div style="margin-top:14px">
          <label for="uploadImage">Upload image and test AI</label>
          <input id="uploadImage" type="file" accept="image/*">
        </div>
      </div>
      <div class="panel">
        <h2>Last Tool Result</h2>
        <pre id="toolResult">{}</pre>
      </div>
    </section>
  </main>

  <script>
    const numericIds = ["confidence", "verify_interval", "alert_cooldown", "frame_skip", "loop_sleep"];
    const configIds = [
      "rtsp_url", "ai_base_url", "ai_api_key", "vision_model", "yolo_model",
      "telegram_bot_token", "telegram_chat_id", ...numericIds
    ];

    function setText(id, value) {
      document.getElementById(id).textContent = value || "-";
    }
    function setStatus(id, text, cls = "") {
      const el = document.getElementById(id);
      el.className = cls;
      el.textContent = text;
    }
    async function api(path, options = {}) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), options.timeout || 30000);
      try {
        const response = await fetch(path, {...options, signal: controller.signal});
        const data = await response.json();
        if (!response.ok || data.success === false) {
          throw new Error(data.error || `HTTP ${response.status}`);
        }
        return data;
      } finally {
        clearTimeout(timer);
      }
    }
    function showTab(id) {
      document.querySelectorAll(".tab-panel").forEach(panel => panel.classList.add("hidden"));
      document.getElementById(id).classList.remove("hidden");
      document.querySelectorAll(".tab-btn").forEach(btn => btn.classList.toggle("active", btn.dataset.tab === id));
    }
    function collectConfig() {
      const data = {};
      for (const id of configIds) {
        const raw = document.getElementById(id).value.trim();
        data[id] = numericIds.includes(id) ? Number(raw) : raw;
      }
      return data;
    }
    function renderConfig(config) {
      for (const id of configIds) {
        if (config[id] !== undefined) document.getElementById(id).value = config[id];
      }
    }
    function renderStatus(data) {
      const s = data.status || {};
      const dot = document.getElementById("runDot");
      dot.className = "dot" + (s.running ? " running" : "") + (s.last_error ? " error" : "");
      setText("runText", s.running ? "Running" : "Stopped");
      setText("frames", s.frames || 0);
      setText("personConf", s.last_person_confidence ? Number(s.last_person_confidence).toFixed(2) : "0");
      setText("aiResult", s.last_ai_result || "-");
      setText("lastVerify", s.last_verify_at || "-");
      if (s.last_error) setStatus("actionStatus", s.last_error, "err");
      const img = document.getElementById("snapshotImg");
      img.src = "/api/snapshot?ts=" + Date.now();
    }
    function renderEvents(events) {
      const body = document.getElementById("eventsBody");
      body.innerHTML = "";
      for (const event of events) {
        const row = document.createElement("tr");
        for (const value of [
          event.time || "",
          event.status || "",
          event.confidence ? Number(event.confidence).toFixed(2) : "",
          event.ai_result || "",
          event.message || event.error || ""
        ]) {
          const cell = document.createElement("td");
          cell.textContent = value;
          row.append(cell);
        }
        body.append(row);
      }
      setStatus("eventsStatus", `Loaded ${events.length} events`, "ok");
    }
    async function loadConfig() {
      const data = await api("/api/config");
      renderConfig(data.config);
    }
    async function loadStatus() {
      const data = await api("/api/status", {timeout: 10000});
      renderStatus(data);
    }
    async function loadEvents() {
      const data = await api("/api/events", {timeout: 10000});
      renderEvents(data.events || []);
    }

    document.querySelectorAll(".tab-btn").forEach(btn => btn.addEventListener("click", () => showTab(btn.dataset.tab)));
    document.getElementById("saveConfigBtn").addEventListener("click", async () => {
      try {
        const data = await api("/api/config", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(collectConfig())
        });
        renderConfig(data.config);
        setStatus("configStatus", "Saved", "ok");
      } catch (err) {
        setStatus("configStatus", err.message, "err");
      }
    });
    document.getElementById("reloadConfigBtn").addEventListener("click", () => loadConfig().catch(err => setStatus("configStatus", err.message, "err")));
    document.getElementById("startBtn").addEventListener("click", async () => {
      try {
        await api("/api/start", {method: "POST"});
        setStatus("actionStatus", "Started", "ok");
        await loadStatus();
      } catch (err) {
        setStatus("actionStatus", err.message, "err");
      }
    });
    document.getElementById("stopBtn").addEventListener("click", async () => {
      try {
        await api("/api/stop", {method: "POST"});
        setStatus("actionStatus", "Stopped", "ok");
        await loadStatus();
      } catch (err) {
        setStatus("actionStatus", err.message, "err");
      }
    });
    document.getElementById("captureBtn").addEventListener("click", async () => {
      try {
        const data = await api("/api/capture", {method: "POST", timeout: 20000});
        setStatus("actionStatus", data.message || "Captured", "ok");
        await loadStatus();
      } catch (err) {
        setStatus("actionStatus", err.message, "err");
      }
    });
    document.getElementById("refreshStatusBtn").addEventListener("click", loadStatus);
    document.getElementById("refreshEventsBtn").addEventListener("click", loadEvents);
    document.getElementById("testAiBtn").addEventListener("click", async () => {
      try {
        const data = await api("/api/test-ai", {method: "POST", timeout: 140000});
        document.getElementById("toolResult").textContent = JSON.stringify(data, null, 2);
        setStatus("toolStatus", "AI test complete", "ok");
      } catch (err) {
        setStatus("toolStatus", err.message, "err");
      }
    });
    document.getElementById("testTelegramBtn").addEventListener("click", async () => {
      try {
        const data = await api("/api/test-telegram", {method: "POST", timeout: 70000});
        document.getElementById("toolResult").textContent = JSON.stringify(data, null, 2);
        setStatus("toolStatus", "Telegram test sent", "ok");
      } catch (err) {
        setStatus("toolStatus", err.message, "err");
      }
    });
    document.getElementById("uploadImage").addEventListener("change", async event => {
      const file = event.target.files[0];
      if (!file) return;
      const form = new FormData();
      form.append("file", file);
      try {
        const data = await api("/api/test-ai-upload", {method: "POST", body: form, timeout: 140000});
        document.getElementById("toolResult").textContent = JSON.stringify(data, null, 2);
        setStatus("toolStatus", "Upload AI test complete", "ok");
      } catch (err) {
        setStatus("toolStatus", err.message, "err");
      }
    });

    loadConfig().catch(err => setStatus("configStatus", err.message, "err"));
    loadStatus().catch(() => {});
    loadEvents().catch(() => {});
    setInterval(loadStatus, 5000);
    setInterval(loadEvents, 15000);
  </script>
</body>
</html>
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def read_config() -> dict[str, Any]:
    ensure_data_dir()
    if not CONFIG_PATH.exists():
        return DEFAULT_CONFIG.copy()
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DEFAULT_CONFIG.copy()
    config = DEFAULT_CONFIG.copy()
    if isinstance(data, dict):
        config.update(data)
    return config


def write_config(config: dict[str, Any]) -> dict[str, Any]:
    ensure_data_dir()
    clean = DEFAULT_CONFIG.copy()
    for key in clean:
        clean[key] = config.get(key, clean[key])
    clean["confidence"] = clamp_float(clean["confidence"], 0.01, 1.0, "confidence")
    clean["verify_interval"] = positive_int(clean["verify_interval"], "verify_interval")
    clean["alert_cooldown"] = positive_int(clean["alert_cooldown"], "alert_cooldown")
    clean["frame_skip"] = positive_int(clean["frame_skip"], "frame_skip")
    clean["loop_sleep"] = max(0.0, float(clean["loop_sleep"]))
    CONFIG_PATH.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    return clean


def positive_int(value: Any, name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if parsed < 1:
        raise ValueError(f"{name} must be a positive integer")
    return parsed


def clamp_float(value: Any, min_value: float, max_value: float, name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc
    if parsed < min_value or parsed > max_value:
        raise ValueError(f"{name} must be between {min_value} and {max_value}")
    return parsed


def require_config(config: dict[str, Any], keys: list[str]) -> None:
    missing = [key for key in keys if not str(config.get(key, "")).strip()]
    if missing:
        raise ValueError(f"Missing required config: {', '.join(missing)}")


def set_state(**updates: Any) -> None:
    with state_lock:
        status.update(updates)


def read_state() -> dict[str, Any]:
    with state_lock:
        return status.copy()


def add_event(status_name: str, **fields: Any) -> None:
    ensure_data_dir()
    event = {"time": now_iso(), "status": status_name, **fields}
    with EVENTS_PATH.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, ensure_ascii=False) + "\n")


def read_events(limit: int = 100) -> list[dict[str, Any]]:
    if not EVENTS_PATH.exists():
        return []
    lines = EVENTS_PATH.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
    events: list[dict[str, Any]] = []
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return list(reversed(events))


def image_to_data_url(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:image/jpeg;base64,{encoded}"


def chat_url(config: dict[str, Any]) -> str:
    base_url = str(config["ai_base_url"]).rstrip("/")
    if base_url.endswith("/chat/completions"):
        return base_url
    return f"{base_url}/chat/completions"


def parse_ai_content(data: dict[str, Any]) -> str:
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("invalid AI API response") from exc
    if isinstance(content, list):
        parts = [part.get("text", "") for part in content if isinstance(part, dict)]
        content = "\n".join(part for part in parts if part)
    return str(content).strip()


def parse_ai_sse(text: str) -> str:
    parts: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        collect_choice_text(data, parts)
    result = "".join(parts).strip()
    if not result:
        raise ValueError("AI API returned SSE response without text content")
    return result


def collect_choice_text(data: dict[str, Any], parts: list[str]) -> None:
    for choice in data.get("choices", []):
        if not isinstance(choice, dict):
            continue
        message = choice.get("message")
        if isinstance(message, dict) and message.get("content"):
            parts.append(str(message["content"]))
            continue
        delta = choice.get("delta")
        if isinstance(delta, dict) and delta.get("content"):
            parts.append(str(delta["content"]))
            continue
        text = choice.get("text")
        if text:
            parts.append(str(text))


def parse_concatenated_json(text: str) -> str:
    decoder = json.JSONDecoder()
    index = 0
    parts: list[str] = []
    while index < len(text):
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            break
        data, end = decoder.raw_decode(text, index)
        if isinstance(data, dict):
            collect_choice_text(data, parts)
        index = end
    result = "".join(parts).strip()
    if not result:
        raise ValueError("AI API returned JSON without text content")
    return result


def response_ai_content(response: requests.Response) -> str:
    text = response.text
    content_type = response.headers.get("content-type", "").lower()
    if "text/event-stream" in content_type or text.lstrip().startswith("data:"):
        return parse_ai_sse(text)
    try:
        return parse_ai_content(response.json())
    except ValueError:
        return parse_concatenated_json(text)


def normalize_ai_result(content: str) -> str:
    upper = content.upper()
    if "EMERGENCY" in upper:
        return "EMERGENCY"
    if "SAFE" in upper:
        return "SAFE"
    return content.strip()[:80] or "SAFE"


def verify_scene(image_path: Path, config: dict[str, Any]) -> tuple[str, str]:
    require_config(config, ["ai_api_key", "ai_base_url", "vision_model"])
    payload = {
        "model": config["vision_model"],
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {"url": image_to_data_url(image_path)}},
                ],
            }
        ],
        "max_tokens": 20,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {config['ai_api_key']}",
        "Content-Type": "application/json",
    }
    logger.info("[AI] verifying scene")
    response = requests.post(chat_url(config), headers=headers, json=payload, timeout=120)
    response.raise_for_status()
    content = response_ai_content(response)
    result = normalize_ai_result(content)
    logger.info("[AI] result=%s raw=%r", result, content[:200])
    return result, content


def send_telegram(photo_path: Path, message: str, config: dict[str, Any]) -> None:
    require_config(config, ["telegram_bot_token", "telegram_chat_id"])
    url = f"https://api.telegram.org/bot{config['telegram_bot_token']}/sendPhoto"
    with photo_path.open("rb") as photo:
        response = requests.post(
            url,
            data={"chat_id": config["telegram_chat_id"], "caption": message},
            files={"photo": photo},
            timeout=60,
        )
    response.raise_for_status()


def capture_snapshot(config: dict[str, Any], output_path: Path = SNAPSHOT_PATH) -> Path:
    require_config(config, ["rtsp_url"])
    import cv2

    cap = cv2.VideoCapture(config["rtsp_url"])
    try:
        ok, frame = cap.read()
        if not ok:
            raise RuntimeError("Could not read frame from RTSP source")
        ensure_data_dir()
        cv2.imwrite(str(output_path), frame)
    finally:
        cap.release()
    return output_path


def monitor_loop(config: dict[str, Any]) -> None:
    import cv2
    from ultralytics import YOLO

    require_config(config, ["rtsp_url", "yolo_model"])
    logger.info("[MONITOR] loading YOLO model=%s", config["yolo_model"])
    model = YOLO(config["yolo_model"])
    cap = cv2.VideoCapture(config["rtsp_url"])
    frame_count = 0
    last_verify = 0.0
    last_alert = 0.0
    set_state(running=True, started_at=now_iso(), last_error="")
    add_event("started", message="Monitor started")

    try:
        while not stop_event.is_set():
            ok, frame = cap.read()
            if not ok:
                logger.warning("[RTSP] reconnect stream")
                set_state(last_error="RTSP read failed, reconnecting")
                add_event("rtsp_reconnect", message="RTSP read failed")
                time.sleep(2)
                cap.release()
                cap = cv2.VideoCapture(config["rtsp_url"])
                continue

            frame_count += 1
            set_state(frames=frame_count)
            if frame_count % int(config["frame_skip"]) != 0:
                continue

            results = model(frame, verbose=False, conf=float(config["confidence"]))
            person_detected = False
            best_confidence = 0.0
            for result in results:
                for box in result.boxes:
                    if int(box.cls[0]) == 0:
                        person_detected = True
                        best_confidence = max(best_confidence, float(box.conf[0]))

            if person_detected:
                set_state(last_person_confidence=best_confidence, last_error="")
                logger.info("[PERSON] detected confidence=%.2f", best_confidence)
                now = time.time()
                if now - last_verify > float(config["verify_interval"]):
                    ensure_data_dir()
                    cv2.imwrite(str(VERIFY_PATH), frame)
                    cv2.imwrite(str(SNAPSHOT_PATH), frame)
                    try:
                        ai_result, raw = verify_scene(VERIFY_PATH, config)
                        last_verify = now
                        set_state(last_ai_result=ai_result, last_verify_at=now_iso(), last_error="")
                        add_event("verified", confidence=best_confidence, ai_result=ai_result, message=raw)
                    except Exception as exc:
                        last_verify = now
                        set_state(last_error=str(exc), last_verify_at=now_iso())
                        add_event("ai_error", confidence=best_confidence, error=str(exc))
                        ai_result = "SAFE"

                    if ai_result == "EMERGENCY":
                        if now - last_alert > float(config["alert_cooldown"]):
                            try:
                                send_telegram(
                                    VERIFY_PATH,
                                    "⚠️ AI phát hiện người có thể bị té ngã hoặc gặp nguy hiểm!",
                                    config,
                                )
                                last_alert = now
                                set_state(last_alert_at=now_iso())
                                add_event("telegram_sent", confidence=best_confidence, ai_result=ai_result)
                            except Exception as exc:
                                set_state(last_error=str(exc))
                                add_event("telegram_error", confidence=best_confidence, error=str(exc))
                        else:
                            add_event("cooldown", confidence=best_confidence, ai_result=ai_result)
            else:
                set_state(last_person_confidence=0)

            time.sleep(float(config["loop_sleep"]))
    except Exception as exc:
        logger.exception("[MONITOR] failed")
        set_state(last_error=str(exc))
        add_event("monitor_error", error=str(exc))
    finally:
        cap.release()
        set_state(running=False)
        add_event("stopped", message="Monitor stopped")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(INDEX_HTML)


@app.get("/api/config")
def api_config() -> JSONResponse:
    return JSONResponse({"success": True, "config": read_config()})


@app.post("/api/config")
async def api_save_config(request: Request) -> JSONResponse:
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError("Invalid config payload")
        config = write_config(body)
        return JSONResponse({"success": True, "config": config})
    except (json.JSONDecodeError, ValueError) as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=400)


@app.get("/api/status")
def api_status() -> JSONResponse:
    return JSONResponse({"success": True, "status": read_state()})


@app.post("/api/start")
def api_start() -> JSONResponse:
    global worker_thread
    if worker_thread and worker_thread.is_alive():
        return JSONResponse({"success": True, "message": "already running", "status": read_state()})
    try:
        config = read_config()
        require_config(config, ["rtsp_url", "yolo_model"])
    except ValueError as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=400)
    stop_event.clear()
    worker_thread = threading.Thread(target=monitor_loop, args=(config,), daemon=True)
    worker_thread.start()
    return JSONResponse({"success": True, "message": "started"})


@app.post("/api/stop")
def api_stop() -> JSONResponse:
    stop_event.set()
    return JSONResponse({"success": True, "message": "stopping"})


@app.post("/api/capture")
def api_capture() -> JSONResponse:
    try:
        path = capture_snapshot(read_config())
        add_event("snapshot", message=f"Captured {path.name}")
        return JSONResponse({"success": True, "message": "snapshot captured"})
    except Exception as exc:
        add_event("snapshot_error", error=str(exc))
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)


@app.get("/api/snapshot")
def api_snapshot() -> Response:
    if not SNAPSHOT_PATH.exists():
        return Response(status_code=204)
    return Response(SNAPSHOT_PATH.read_bytes(), media_type="image/jpeg")


@app.get("/api/events")
def api_events() -> JSONResponse:
    return JSONResponse({"success": True, "events": read_events()})


@app.post("/api/test-ai")
def api_test_ai() -> JSONResponse:
    if not SNAPSHOT_PATH.exists():
        return JSONResponse({"success": False, "error": "No snapshot. Capture first."}, status_code=400)
    try:
        result, raw = verify_scene(SNAPSHOT_PATH, read_config())
        add_event("test_ai", ai_result=result, message=raw)
        return JSONResponse({"success": True, "result": result, "raw": raw})
    except Exception as exc:
        add_event("test_ai_error", error=str(exc))
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)


@app.post("/api/test-ai-upload")
async def api_test_ai_upload(file: UploadFile = File(...)) -> JSONResponse:
    ensure_data_dir()
    path = DATA_DIR / "upload_test.jpg"
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty upload")
    path.write_bytes(content)
    try:
        result, raw = verify_scene(path, read_config())
        add_event("test_ai_upload", ai_result=result, message=raw)
        return JSONResponse({"success": True, "result": result, "raw": raw})
    except Exception as exc:
        add_event("test_ai_upload_error", error=str(exc))
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)


@app.post("/api/test-telegram")
def api_test_telegram() -> JSONResponse:
    try:
        if not SNAPSHOT_PATH.exists():
            capture_snapshot(read_config())
        send_telegram(SNAPSHOT_PATH, "Fall Detection test alert", read_config())
        add_event("test_telegram", message="Telegram test sent")
        return JSONResponse({"success": True, "message": "Telegram test sent"})
    except Exception as exc:
        add_event("test_telegram_error", error=str(exc))
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)
