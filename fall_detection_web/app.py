import base64
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CONFIG_PATH = DATA_DIR / "config.json"
ENV_PATH = ROOT / ".env"
EVENTS_PATH = DATA_DIR / "events.jsonl"
SNAPSHOT_PATH = DATA_DIR / "latest.jpg"
VERIFY_PATH = DATA_DIR / "verify.jpg"

DEFAULT_CONFIG: dict[str, Any] = {
    "rtsp_url": "",
    "cameras": [],
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "ai_base_url": "https://9router.minhhungtsbd.me/v1",
    "ai_api_key": "",
    "vision_model": "gh/oswe-vscode-prime",
    "verify_prompt": """Đây là ảnh camera giám sát người già trong nhà.

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
""",
    "yolo_model": "yolov8s.pt",
    "confidence": 0.5,
    "verify_interval": 20,
    "alert_cooldown": 300,
    "frame_skip": 2,
    "loop_sleep": 0.3,
}

ENV_CONFIG_KEYS = {
    "RTSP_URL": "rtsp_url",
    "TELEGRAM_BOT_TOKEN": "telegram_bot_token",
    "TELEGRAM_CHAT_ID": "telegram_chat_id",
    "AI_BASE_URL": "ai_base_url",
    "AI_API_KEY": "ai_api_key",
    "VISION_MODEL": "vision_model",
    "YOLO_MODEL": "yolo_model",
    "CONFIDENCE": "confidence",
    "VERIFY_INTERVAL": "verify_interval",
    "ALERT_COOLDOWN": "alert_cooldown",
    "FRAME_SKIP": "frame_skip",
    "LOOP_SLEEP": "loop_sleep",
}

SECRET_CONFIG_KEYS = {
    "rtsp_url",
    "telegram_bot_token",
    "telegram_chat_id",
    "ai_api_key",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("fall_detection_web")

app = FastAPI(title="Fall Detection Web")

state_lock = threading.Lock()
stop_event = threading.Event()
worker_thread: threading.Thread | None = None
status: dict[str, Any] = {
    "running": False,
    "started_at": "",
    "last_camera": "",
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
    .camera-head,
    .camera-row {
      display: grid;
      grid-template-columns: 60px minmax(120px, .8fr) minmax(260px, 1.4fr) max-content;
      gap: 8px;
      align-items: center;
    }
    .camera-head {
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      margin: 14px 0 6px;
    }
    .camera-row {
      margin-bottom: 8px;
    }
    .camera-row > * { min-width: 0; }
    .camera-row input[type="checkbox"] {
      width: auto;
    }
    .camera-actions {
      display: flex;
      gap: 6px;
      justify-content: flex-end;
    }
    .live-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 12px;
    }
    .live-card {
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      background: var(--panel-2);
    }
    .live-card h3 {
      font-size: 14px;
      padding: 10px;
      border-bottom: 1px solid var(--line);
    }
    .live-card img {
      width: 100%;
      aspect-ratio: 16 / 9;
      object-fit: contain;
      background: #03070b;
      display: block;
    }
    dialog {
      width: min(960px, calc(100vw - 28px));
      max-height: calc(100vh - 28px);
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      color: var(--text);
      padding: 0;
    }
    dialog::backdrop {
      background: rgba(0, 0, 0, .72);
    }
    .viewer-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      padding: 12px;
      border-bottom: 1px solid var(--line);
    }
    .viewer-head h2 {
      margin: 0;
      font-size: 16px;
    }
    .viewer-actions {
      display: flex;
      gap: 8px;
    }
    .viewer-body {
      padding: 12px;
      background: #03070b;
    }
    .viewer-body img {
      width: 100%;
      max-height: calc(100vh - 160px);
      object-fit: contain;
      display: block;
    }
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
      .camera-head { display: none; }
      .camera-row {
        grid-template-columns: 1fr;
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: 10px;
      }
      .camera-actions {
        flex-direction: column;
      }
      .viewer-head,
      .viewer-actions {
        flex-direction: column;
        align-items: stretch;
      }
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
      <button class="tab-btn" data-tab="camerasPanel" type="button">Cameras</button>
      <button class="tab-btn" data-tab="livePanel" type="button">Live</button>
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

    <section id="camerasPanel" class="tab-panel hidden">
      <div class="panel">
        <h2>Cameras</h2>
        <div class="camera-head">
          <div>Enabled</div>
          <div>Name</div>
          <div>RTSP URL</div>
          <div>Actions</div>
        </div>
        <div id="cameraList"></div>
        <div class="actions" style="margin-top:14px">
          <button id="addCameraBtn" type="button">Add Camera</button>
          <button id="saveCamerasBtn" class="primary" type="button">Save Cameras</button>
          <span id="cameraStatus"></span>
        </div>
      </div>
    </section>

    <section id="livePanel" class="tab-panel hidden">
      <div class="panel">
        <h2>Live Cameras</h2>
        <div class="actions">
          <button id="refreshLiveBtn" type="button">Refresh Live</button>
          <span id="liveStatus"></span>
        </div>
        <div id="liveGrid" class="live-grid" style="margin-top:14px"></div>
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
            <label for="vision_model">AI Model</label>
            <input id="vision_model" autocomplete="off" placeholder="gh/oswe-vscode-prime">
          </div>
          <div class="full">
            <label for="verify_prompt">AI Verify Prompt</label>
            <textarea id="verify_prompt" placeholder="Prompt xác minh té ngã gửi tới AI"></textarea>
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
            <tr><th>Time</th><th>Status</th><th>Camera</th><th>Confidence</th><th>AI</th><th>AI Raw / Message</th></tr>
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

    <dialog id="viewerDialog">
      <div class="viewer-head">
        <h2 id="viewerTitle">Viewer</h2>
        <div class="viewer-actions">
          <button id="refreshViewerBtn" type="button">Refresh</button>
          <button id="openViewerBtn" type="button">Open Tab</button>
          <button id="closeViewerBtn" type="button">Close</button>
        </div>
      </div>
      <div id="viewerBody" class="viewer-body"></div>
    </dialog>
  </main>

  <script>
    let cameras = [];
    let currentViewerUrl = "";
    let currentViewerMode = "";
    const numericIds = ["confidence", "verify_interval", "alert_cooldown", "frame_skip", "loop_sleep"];
    const configIds = [
      "rtsp_url", "ai_base_url", "ai_api_key", "vision_model", "verify_prompt", "yolo_model",
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
      data.cameras = cameras;
      return data;
    }
    function renderConfig(config) {
      for (const id of configIds) {
        if (config[id] !== undefined) document.getElementById(id).value = config[id];
      }
      cameras = Array.isArray(config.cameras) ? config.cameras : [];
      renderCameras();
      renderLive();
    }
    function renderStatus(data) {
      const s = data.status || {};
      const dot = document.getElementById("runDot");
      dot.className = "dot" + (s.running ? " running" : "") + (s.last_error ? " error" : "");
      setText("runText", s.running ? "Running" : "Stopped");
      setText("frames", s.frames || 0);
      setText("personConf", s.last_person_confidence ? Number(s.last_person_confidence).toFixed(2) : "0");
      setText("aiResult", s.last_ai_result ? `${s.last_ai_result} ${s.last_camera ? "(" + s.last_camera + ")" : ""}` : "-");
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
          event.camera || "",
          event.confidence ? Number(event.confidence).toFixed(2) : "",
          event.ai_result || "",
          event.ai_raw || event.message || event.error || ""
        ]) {
          const cell = document.createElement("td");
          cell.textContent = value;
          row.append(cell);
        }
        body.append(row);
      }
      setStatus("eventsStatus", `Loaded ${events.length} events`, "ok");
    }
    function showViewer(title, url, mode) {
      currentViewerUrl = url;
      currentViewerMode = mode;
      document.getElementById("viewerTitle").textContent = title;
      const body = document.getElementById("viewerBody");
      body.innerHTML = "";
      const img = document.createElement("img");
      img.alt = title;
      img.src = mode === "snapshot" ? `${url}${url.includes("?") ? "&" : "?"}ts=${Date.now()}` : url;
      body.append(img);
      document.getElementById("refreshViewerBtn").style.display = mode === "snapshot" ? "" : "none";
      document.getElementById("viewerDialog").showModal();
    }
    function closeViewer() {
      const body = document.getElementById("viewerBody");
      body.innerHTML = "";
      document.getElementById("viewerDialog").close();
      currentViewerUrl = "";
      currentViewerMode = "";
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
    function normalizeCamera(camera = {}) {
      return {
        enabled: camera.enabled !== false,
        name: camera.name || "",
        rtsp_url: camera.rtsp_url || ""
      };
    }
    function renderCameras() {
      const list = document.getElementById("cameraList");
      list.innerHTML = "";
      cameras = cameras.map(normalizeCamera);
      cameras.forEach((camera, index) => {
        const row = document.createElement("div");
        row.className = "camera-row";

        const enabled = document.createElement("input");
        enabled.type = "checkbox";
        enabled.checked = camera.enabled;
        enabled.addEventListener("change", () => cameras[index].enabled = enabled.checked);

        const name = document.createElement("input");
        name.placeholder = "bep";
        name.value = camera.name;
        name.addEventListener("input", () => cameras[index].name = name.value);

        const rtsp = document.createElement("input");
        rtsp.placeholder = "rtsp://10.10.0.2:8554/bep_sub";
        rtsp.value = camera.rtsp_url;
        rtsp.addEventListener("input", () => cameras[index].rtsp_url = rtsp.value);

        const actions = document.createElement("div");
        actions.className = "camera-actions";
        const snapshot = document.createElement("button");
        snapshot.type = "button";
        snapshot.textContent = "Snapshot";
        snapshot.addEventListener("click", () => showViewer(
          `Snapshot: ${camera.name || "Camera " + (index + 1)}`,
          `/api/camera/snapshot?index=${index}`,
          "snapshot"
        ));
        const video = document.createElement("button");
        video.type = "button";
        video.textContent = "Video";
        video.addEventListener("click", () => showViewer(
          `Video: ${camera.name || "Camera " + (index + 1)}`,
          `/api/camera/video?index=${index}`,
          "video"
        ));
        const test = document.createElement("button");
        test.type = "button";
        test.textContent = "Test AI";
        test.addEventListener("click", async () => {
          try {
            const data = await api(`/api/test-ai-camera?index=${index}`, {method: "POST", timeout: 150000});
            document.getElementById("toolResult").textContent = JSON.stringify(data, null, 2);
            setStatus("cameraStatus", "AI test complete", "ok");
          } catch (err) {
            setStatus("cameraStatus", err.message, "err");
          }
        });
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "danger";
        remove.textContent = "Remove";
        remove.addEventListener("click", () => {
          cameras.splice(index, 1);
          renderCameras();
          renderLive();
        });
        actions.append(snapshot, video, test, remove);
        row.append(enabled, name, rtsp, actions);
        list.append(row);
      });
    }
    function renderLive() {
      const grid = document.getElementById("liveGrid");
      grid.innerHTML = "";
      const visible = cameras
        .map((camera, index) => ({camera: normalizeCamera(camera), index}))
        .filter(item => item.camera.enabled && item.camera.rtsp_url.trim());
      for (const item of visible) {
        const camera = item.camera;
        const index = item.index;
        const card = document.createElement("div");
        card.className = "live-card";
        const title = document.createElement("h3");
        title.textContent = camera.name || camera.rtsp_url;
        const img = document.createElement("img");
        img.alt = title.textContent;
        img.src = `/api/camera/video?index=${index}&ts=${Date.now()}`;
        card.append(title, img);
        grid.append(card);
      }
      setStatus("liveStatus", visible.length ? `Showing ${visible.length} camera(s)` : "No enabled cameras", visible.length ? "ok" : "warn");
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
    document.getElementById("addCameraBtn").addEventListener("click", () => {
      cameras.push({enabled: true, name: "", rtsp_url: document.getElementById("rtsp_url").value.trim()});
      renderCameras();
      renderLive();
    });
    document.getElementById("saveCamerasBtn").addEventListener("click", async () => {
      try {
        const data = await api("/api/config", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(collectConfig())
        });
        renderConfig(data.config);
        setStatus("cameraStatus", "Saved", "ok");
      } catch (err) {
        setStatus("cameraStatus", err.message, "err");
      }
    });
    document.getElementById("refreshLiveBtn").addEventListener("click", renderLive);
    document.getElementById("refreshEventsBtn").addEventListener("click", loadEvents);
    document.getElementById("refreshViewerBtn").addEventListener("click", () => {
      if (currentViewerUrl && currentViewerMode === "snapshot") {
        showViewer(document.getElementById("viewerTitle").textContent, currentViewerUrl, currentViewerMode);
      }
    });
    document.getElementById("openViewerBtn").addEventListener("click", () => {
      if (currentViewerUrl) window.open(currentViewerUrl, "_blank");
    });
    document.getElementById("closeViewerBtn").addEventListener("click", closeViewer);
    document.getElementById("viewerDialog").addEventListener("close", () => {
      document.getElementById("viewerBody").innerHTML = "";
    });
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


def parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def coerce_config_value(key: str, value: str) -> Any:
    if key in {"verify_interval", "alert_cooldown", "frame_skip"}:
        return positive_int(value, key)
    if key == "confidence":
        return clamp_float(value, 0.01, 1.0, key)
    if key == "loop_sleep":
        return max(0.0, float(value))
    return value


def env_config_values() -> tuple[dict[str, Any], dict[str, str]]:
    raw_env = parse_env_file(ENV_PATH)
    raw_env.update(os.environ)
    values: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for env_key, config_key in ENV_CONFIG_KEYS.items():
        raw_value = raw_env.get(env_key, "")
        if raw_value == "":
            continue
        try:
            values[config_key] = coerce_config_value(config_key, raw_value)
            sources[config_key] = env_key
        except ValueError as exc:
            logger.warning("Ignoring invalid %s value from environment: %s", env_key, exc)
    return values, sources


def read_stored_config() -> dict[str, Any]:
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


def read_config() -> dict[str, Any]:
    config = read_stored_config()
    env_values, _ = env_config_values()
    config.update(env_values)
    config["cameras"] = normalize_cameras(config)
    return config


def normalize_cameras(config: dict[str, Any]) -> list[dict[str, Any]]:
    raw_cameras = config.get("cameras", [])
    cameras: list[dict[str, Any]] = []
    if isinstance(raw_cameras, list):
        for index, camera in enumerate(raw_cameras):
            if not isinstance(camera, dict):
                continue
            rtsp_url = str(camera.get("rtsp_url", "")).strip()
            name = str(camera.get("name", "")).strip() or f"Camera {index + 1}"
            cameras.append({
                "enabled": camera.get("enabled") is not False,
                "name": name,
                "rtsp_url": rtsp_url,
            })
    fallback_rtsp = str(config.get("rtsp_url", "")).strip()
    if not cameras and fallback_rtsp:
        cameras.append({"enabled": True, "name": "Default", "rtsp_url": fallback_rtsp})
    return cameras


def write_config(config: dict[str, Any]) -> dict[str, Any]:
    ensure_data_dir()
    clean = DEFAULT_CONFIG.copy()
    for key in clean:
        clean[key] = config.get(key, clean[key])
    clean["cameras"] = normalize_cameras(clean)
    clean["confidence"] = clamp_float(clean["confidence"], 0.01, 1.0, "confidence")
    clean["verify_interval"] = positive_int(clean["verify_interval"], "verify_interval")
    clean["alert_cooldown"] = positive_int(clean["alert_cooldown"], "alert_cooldown")
    clean["frame_skip"] = positive_int(clean["frame_skip"], "frame_skip")
    clean["loop_sleep"] = max(0.0, float(clean["loop_sleep"]))
    env_values, _ = env_config_values()
    for key in SECRET_CONFIG_KEYS:
        if key in env_values and str(clean.get(key, "")) == str(env_values[key]):
            clean[key] = ""
    CONFIG_PATH.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    return read_config()


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


def camera_snapshot_path(index: int) -> Path:
    return DATA_DIR / f"camera_{index}.jpg"


def get_camera(config: dict[str, Any], index: int) -> dict[str, Any]:
    cameras = normalize_cameras(config)
    if index < 0 or index >= len(cameras):
        raise ValueError("Invalid camera index")
    camera = cameras[index]
    if not str(camera.get("rtsp_url", "")).strip():
        raise ValueError("Camera RTSP URL is empty")
    return camera


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
    require_config(config, ["ai_api_key", "ai_base_url", "vision_model", "verify_prompt"])
    payload = {
        "model": config["vision_model"],
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": str(config["verify_prompt"])},
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


def capture_rtsp_snapshot(rtsp_url: str, output_path: Path) -> Path:
    import cv2

    cap = cv2.VideoCapture(rtsp_url)
    try:
        ok, frame = cap.read()
        if not ok:
            raise RuntimeError("Could not read frame from RTSP source")
        ensure_data_dir()
        cv2.imwrite(str(output_path), frame)
    finally:
        cap.release()
    return output_path


def capture_snapshot(config: dict[str, Any], output_path: Path = SNAPSHOT_PATH) -> Path:
    require_config(config, ["rtsp_url"])
    return capture_rtsp_snapshot(str(config["rtsp_url"]), output_path)


def capture_camera_snapshot(config: dict[str, Any], index: int) -> Path:
    camera = get_camera(config, index)
    return capture_rtsp_snapshot(str(camera["rtsp_url"]), camera_snapshot_path(index))


def mjpeg_frames(rtsp_url: str):
    import cv2

    cap = cv2.VideoCapture(rtsp_url)
    try:
      while True:
          ok, frame = cap.read()
          if not ok:
              time.sleep(0.5)
              continue
          ok, encoded = cv2.imencode(".jpg", frame)
          if not ok:
              continue
          yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + encoded.tobytes() + b"\r\n"
          time.sleep(0.08)
    finally:
        cap.release()


def monitor_loop(config: dict[str, Any]) -> None:
    import cv2
    from ultralytics import YOLO

    cameras = [camera for camera in normalize_cameras(config) if camera.get("enabled") and camera.get("rtsp_url")]
    if not cameras:
        raise ValueError("No enabled cameras")
    require_config(config, ["yolo_model"])
    logger.info("[MONITOR] loading YOLO model=%s", config["yolo_model"])
    model = YOLO(config["yolo_model"])
    caps = [cv2.VideoCapture(camera["rtsp_url"]) for camera in cameras]
    frame_counts = [0 for _ in cameras]
    last_verify = [0.0 for _ in cameras]
    last_alert = [0.0 for _ in cameras]
    total_frames = 0
    set_state(running=True, started_at=now_iso(), last_error="")
    add_event("started", message=f"Monitor started for {len(cameras)} camera(s)")

    try:
        while not stop_event.is_set():
            for index, camera in enumerate(cameras):
                camera_name = str(camera["name"])
                ok, frame = caps[index].read()
                if not ok:
                    logger.warning("[RTSP] reconnect stream camera=%s", camera_name)
                    set_state(last_error=f"RTSP read failed for {camera_name}, reconnecting", last_camera=camera_name)
                    add_event("rtsp_reconnect", camera=camera_name, message="RTSP read failed")
                    caps[index].release()
                    caps[index] = cv2.VideoCapture(camera["rtsp_url"])
                    continue

                frame_counts[index] += 1
                total_frames += 1
                set_state(frames=total_frames, last_camera=camera_name)
                if frame_counts[index] % int(config["frame_skip"]) != 0:
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
                    set_state(last_person_confidence=best_confidence, last_error="", last_camera=camera_name)
                    logger.info("[PERSON] camera=%s confidence=%.2f", camera_name, best_confidence)
                    now = time.time()
                    if now - last_verify[index] > float(config["verify_interval"]):
                        ensure_data_dir()
                        verify_path = camera_snapshot_path(index)
                        cv2.imwrite(str(verify_path), frame)
                        cv2.imwrite(str(SNAPSHOT_PATH), frame)
                        try:
                            ai_result, raw = verify_scene(verify_path, config)
                            last_verify[index] = now
                            set_state(last_ai_result=ai_result, last_verify_at=now_iso(), last_error="")
                            add_event("verified", camera=camera_name, confidence=best_confidence, ai_result=ai_result, ai_raw=raw, message=raw)
                        except Exception as exc:
                            last_verify[index] = now
                            set_state(last_error=str(exc), last_verify_at=now_iso())
                            add_event("ai_error", camera=camera_name, confidence=best_confidence, error=str(exc))
                            ai_result = "SAFE"

                        if ai_result == "EMERGENCY":
                            if now - last_alert[index] > float(config["alert_cooldown"]):
                                try:
                                    send_telegram(
                                        verify_path,
                                        f"⚠️ AI phát hiện người có thể bị té ngã hoặc gặp nguy hiểm!\nCamera: {camera_name}",
                                        config,
                                    )
                                    last_alert[index] = now
                                    set_state(last_alert_at=now_iso())
                                    add_event("telegram_sent", camera=camera_name, confidence=best_confidence, ai_result=ai_result)
                                except Exception as exc:
                                    set_state(last_error=str(exc))
                                    add_event("telegram_error", camera=camera_name, confidence=best_confidence, error=str(exc))
                            else:
                                add_event("cooldown", camera=camera_name, confidence=best_confidence, ai_result=ai_result)

            time.sleep(float(config["loop_sleep"]))
    except Exception as exc:
        logger.exception("[MONITOR] failed")
        set_state(last_error=str(exc))
        add_event("monitor_error", error=str(exc))
    finally:
        for cap in caps:
            cap.release()
        set_state(running=False)
        add_event("stopped", message="Monitor stopped")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(INDEX_HTML)


@app.get("/api/config")
def api_config() -> JSONResponse:
    _, sources = env_config_values()
    return JSONResponse({"success": True, "config": read_config(), "env_sources": sources})


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
        if not [camera for camera in normalize_cameras(config) if camera.get("enabled") and camera.get("rtsp_url")]:
            raise ValueError("No enabled cameras")
        require_config(config, ["yolo_model"])
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
        config = read_config()
        cameras = normalize_cameras(config)
        path = capture_camera_snapshot(config, 0) if cameras else capture_snapshot(config)
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


@app.get("/api/camera/snapshot")
def api_camera_snapshot(index: int = 0) -> Response:
    try:
        path = capture_camera_snapshot(read_config(), index)
    except Exception as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)
    return Response(path.read_bytes(), media_type="image/jpeg")


@app.get("/api/camera/video")
def api_camera_video(index: int = 0) -> StreamingResponse:
    try:
        camera = get_camera(read_config(), index)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StreamingResponse(
        mjpeg_frames(str(camera["rtsp_url"])),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/api/events")
def api_events() -> JSONResponse:
    return JSONResponse({"success": True, "events": read_events()})


@app.post("/api/test-ai")
def api_test_ai() -> JSONResponse:
    if not SNAPSHOT_PATH.exists():
        return JSONResponse({"success": False, "error": "No snapshot. Capture first."}, status_code=400)
    try:
        result, raw = verify_scene(SNAPSHOT_PATH, read_config())
        add_event("test_ai", ai_result=result, ai_raw=raw, message=raw)
        return JSONResponse({"success": True, "result": result, "raw": raw})
    except Exception as exc:
        add_event("test_ai_error", error=str(exc))
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)


@app.post("/api/test-ai-camera")
def api_test_ai_camera(index: int = 0) -> JSONResponse:
    try:
        config = read_config()
        path = capture_camera_snapshot(config, index)
        result, raw = verify_scene(path, config)
        camera = get_camera(config, index)
        add_event("test_ai_camera", camera=camera["name"], ai_result=result, ai_raw=raw, message=raw)
        return JSONResponse({"success": True, "camera": camera["name"], "result": result, "raw": raw})
    except Exception as exc:
        add_event("test_ai_camera_error", error=str(exc))
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
        add_event("test_ai_upload", ai_result=result, ai_raw=raw, message=raw)
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
