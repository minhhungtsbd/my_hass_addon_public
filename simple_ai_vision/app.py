import base64
from datetime import datetime, timezone
import json
import logging
import os
import re
import tempfile
from typing import Any

import requests
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

try:
    import paho.mqtt.publish as mqtt_publish
except ImportError:
    mqtt_publish = None


UI_OPTIONS_PATH = "/data/simple_ai_vision_config.json"
EVENT_LOG_PATH = "/data/simple_ai_vision_events.jsonl"
DEFAULT_PROMPT = (
    "B\u1ea1n \u0111ang ph\u00e2n t\u00edch \u1ea3nh camera an ninh.\n"
    "Ch\u1ec9 m\u00f4 t\u1ea3 c\u00e1c s\u1ef1 ki\u1ec7n quan tr\u1ecdng li\u00ean quan \u0111\u1ebfn an ninh.\n"
    "N\u1ebfu kh\u00f4ng c\u00f3 g\u00ec quan tr\u1ecdng h\u00e3y tr\u1ea3 l\u1eddi NORMAL."
)
DEFAULT_KEYWORDS = ["person", "human", "stranger", "fire", "smoke", "ng\u01b0\u1eddi", "ch\u00e1y"]
CAMERA_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")

INDEX_HTML = r"""
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Simple AI Vision</title>
  <style>
    :root {
      color-scheme: light dark;
      --bg: #f6f8fb;
      --panel: #ffffff;
      --text: #152033;
      --muted: #637083;
      --line: #d9e1ea;
      --primary: #0b8ecf;
      --danger: #b42318;
      --ok: #087443;
    }
    @media (prefers-color-scheme: dark) {
      :root {
        --bg: #101820;
        --panel: #172330;
        --text: #eff6ff;
        --muted: #a7b4c3;
        --line: #2b3c4e;
      }
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    main {
      max-width: 980px;
      margin: 0 auto;
      padding: 24px;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 18px;
    }
    h1 { margin: 0; font-size: 24px; }
    h2 { margin: 0 0 14px; font-size: 17px; }
    .sub { color: var(--muted); margin-top: 4px; }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
      margin-bottom: 16px;
    }
    .tabs {
      display: flex;
      gap: 8px;
      margin-bottom: 16px;
      border-bottom: 1px solid var(--line);
    }
    .tab-btn {
      border: 0;
      border-bottom: 3px solid transparent;
      border-radius: 0;
      background: transparent;
      color: var(--muted);
      padding: 10px 12px;
    }
    .tab-btn.active {
      border-bottom-color: var(--primary);
      color: var(--text);
    }
    .tab-panel { display: none; }
    .tab-panel.active { display: block; }
    .grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }
    label {
      display: block;
      color: var(--muted);
      font-size: 12px;
      font-weight: 650;
      margin-bottom: 6px;
    }
    .hint {
      color: var(--muted);
      font-size: 12px;
      margin-top: 6px;
    }
    code {
      background: rgba(0, 0, 0, .12);
      border-radius: 4px;
      padding: 1px 4px;
    }
    input, textarea {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
      background: transparent;
      color: var(--text);
      font: inherit;
    }
    textarea { min-height: 96px; resize: vertical; }
    .full { grid-column: 1 / -1; }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
      margin-top: 14px;
    }
    button {
      border: 1px solid var(--primary);
      border-radius: 6px;
      background: var(--primary);
      color: #fff;
      padding: 10px 14px;
      font-weight: 700;
      cursor: pointer;
    }
    button.secondary {
      background: transparent;
      color: var(--primary);
    }
    button.danger {
      border-color: var(--danger);
      color: var(--danger);
      background: transparent;
    }
    .camera-head {
      display: grid;
      grid-template-columns: minmax(90px, .7fr) minmax(120px, 1fr) minmax(160px, 1.3fr) minmax(140px, 1.2fr) minmax(120px, 1fr) auto auto auto auto;
      gap: 8px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      margin-bottom: 6px;
    }
    .camera-row {
      display: grid;
      grid-template-columns: minmax(90px, .7fr) minmax(120px, 1fr) minmax(160px, 1.3fr) minmax(140px, 1.2fr) minmax(120px, 1fr) auto auto auto auto;
      gap: 8px;
      margin-bottom: 8px;
    }
    .monitor-toggle {
      display: flex;
      align-items: center;
      gap: 8px;
      min-height: 40px;
      color: var(--text);
      font-weight: 650;
    }
    .monitor-toggle input {
      width: auto;
      min-width: 18px;
      height: 18px;
    }
    .entity-picker {
      display: grid;
      grid-template-columns: minmax(180px, 1fr) auto auto;
      gap: 8px;
      margin: 12px 0 14px;
    }
    .live-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 14px;
    }
    .live-item {
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      background: rgba(0, 0, 0, .04);
    }
    .live-title {
      display: flex;
      justify-content: space-between;
      gap: 8px;
      padding: 10px;
      font-weight: 750;
    }
    .live-title span {
      color: var(--muted);
      font-weight: 600;
      overflow-wrap: anywhere;
    }
    .live-item iframe,
    .live-item img {
      display: block;
      width: 100%;
      height: 260px;
      border: 0;
      object-fit: contain;
      background: #05080c;
    }
    .events-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    .events-table th,
    .events-table td {
      border-bottom: 1px solid var(--line);
      padding: 9px 8px;
      text-align: left;
      vertical-align: top;
    }
    .events-table td {
      overflow-wrap: anywhere;
    }
    select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
      background: var(--panel);
      color: var(--text);
      font: inherit;
    }
    .viewer {
      border: 0;
      padding: 0;
      background: transparent;
      width: min(920px, calc(100vw - 28px));
    }
    .viewer::backdrop { background: rgba(0, 0, 0, .62); }
    .viewer-box {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }
    .viewer-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 12px;
    }
    .viewer-title {
      font-weight: 750;
      overflow-wrap: anywhere;
    }
    .viewer-body {
      min-height: 260px;
      background: #05080c;
      border-radius: 6px;
      overflow: hidden;
    }
    .viewer-body img,
    .viewer-body iframe {
      display: block;
      width: 100%;
      height: min(68vh, 560px);
      border: 0;
      object-fit: contain;
      background: #05080c;
    }
    .mobile-label {
      display: none;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      margin-bottom: 4px;
    }
    .status {
      min-height: 22px;
      color: var(--muted);
    }
    .status.ok { color: var(--ok); }
    .status.err { color: var(--danger); }
    pre {
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 12px;
      background: rgba(0, 0, 0, .05);
      white-space: pre-wrap;
    }
    @media (max-width: 720px) {
      main { padding: 16px; }
      header { align-items: flex-start; flex-direction: column; }
      .grid, .camera-row, .entity-picker { grid-template-columns: 1fr; }
      .tabs { overflow-x: auto; }
      button { width: 100%; }
      .actions { align-items: stretch; flex-direction: column; }
      .camera-row {
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: 10px;
      }
      .camera-head { display: none; }
      .mobile-label { display: block; }
      .viewer {
        width: calc(100vw - 12px);
        max-height: calc(100vh - 12px);
      }
      .viewer-head {
        align-items: stretch;
        flex-direction: column;
      }
      .viewer-body img,
      .viewer-body iframe {
        height: min(56vh, 420px);
      }
      .live-grid { grid-template-columns: 1fr; }
      .live-item iframe,
      .live-item img { height: 220px; }
      .events-table,
      .events-table thead,
      .events-table tbody,
      .events-table tr,
      .events-table th,
      .events-table td {
        display: block;
        width: 100%;
      }
      .events-table thead { display: none; }
      .events-table tr {
        border-bottom: 1px solid var(--line);
        padding: 8px 0;
      }
      .events-table td {
        border-bottom: 0;
        padding: 5px 0;
      }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Simple AI Vision</h1>
        <div class="sub">Configure AI snapshot alerts and test cameras.</div>
      </div>
      <button class="secondary" id="reloadBtn" type="button">Reload</button>
    </header>

    <nav class="tabs" aria-label="Main views">
      <button class="tab-btn active" data-tab="camerasPanel" type="button">Cameras</button>
      <button class="tab-btn" data-tab="livePanel" type="button">Live</button>
      <button class="tab-btn" data-tab="eventsPanel" type="button">Sự kiện</button>
      <button class="tab-btn" data-tab="settingsPanel" type="button">Core Settings</button>
    </nav>

    <section class="panel tab-panel" id="settingsPanel">
      <h2>Core Settings</h2>
      <div class="grid">
        <div>
          <label for="go2rtc_url">go2rtc URL</label>
          <input id="go2rtc_url" autocomplete="off" placeholder="http://192.168.1.101:1984 hoặc http://homeassistant-hung.local:1984">
          <div class="hint">Chỉ nhập base URL, không nhập <code>/api/frame.jpeg?src=...</code>.</div>
        </div>
        <div>
          <label for="ai_base_url">AI Base URL</label>
          <input id="ai_base_url" autocomplete="off" placeholder="https://api.openai.com/v1 hoặc http://9router.local:20128/v1">
        </div>
        <div>
          <label for="ai_model">AI Model</label>
          <input id="ai_model" autocomplete="off" placeholder="gpt-4o-mini hoặc cc/claude-opus-4-7">
        </div>
        <div>
          <label for="telegram_chat_id">Telegram Chat ID</label>
          <input id="telegram_chat_id" autocomplete="off" placeholder="123456789 hoặc -1001234567890">
        </div>
        <div>
          <label for="ai_api_key">AI API Key</label>
          <input id="ai_api_key" type="password" autocomplete="new-password" placeholder="sk-...">
        </div>
        <div>
          <label for="telegram_bot_token">Telegram Bot Token</label>
          <input id="telegram_bot_token" type="password" autocomplete="new-password" placeholder="123456789:ABCDEF...">
        </div>
        <div class="full">
          <label for="prompt">Prompt</label>
          <textarea id="prompt" placeholder="Bạn đang phân tích ảnh camera an ninh.
Chỉ mô tả các sự kiện quan trọng liên quan đến an ninh.
Nếu không có gì quan trọng hãy trả lời NORMAL."></textarea>
        </div>
        <div class="full">
          <label for="keyword_match">Keyword Match, one per line</label>
          <textarea id="keyword_match" placeholder="person
human
stranger
fire
smoke
người
cháy"></textarea>
          <div class="hint">Mỗi dòng là một keyword hoặc regex. Match không phân biệt chữ hoa/thường.</div>
        </div>
        <div>
          <label for="ai_timeout">AI Timeout</label>
          <input id="ai_timeout" type="number" min="1" placeholder="30">
        </div>
        <div>
          <label for="snapshot_timeout">Snapshot Timeout</label>
          <input id="snapshot_timeout" type="number" min="1" placeholder="10">
        </div>
        <div>
          <label for="telegram_timeout">Telegram Timeout</label>
          <input id="telegram_timeout" type="number" min="1" placeholder="10">
        </div>
        <div>
          <label for="mqtt_enabled">MQTT Publish</label>
          <label class="monitor-toggle">
            <input id="mqtt_enabled" type="checkbox">
            <span>Enable MQTT events</span>
          </label>
        </div>
        <div>
          <label for="mqtt_host">MQTT Host</label>
          <input id="mqtt_host" autocomplete="off" placeholder="core-mosquitto hoặc 192.168.1.10">
        </div>
        <div>
          <label for="mqtt_port">MQTT Port</label>
          <input id="mqtt_port" type="number" min="1" placeholder="1883">
        </div>
        <div>
          <label for="mqtt_topic">MQTT Topic</label>
          <input id="mqtt_topic" autocomplete="off" placeholder="simple_ai_vision/events">
        </div>
        <div>
          <label for="mqtt_username">MQTT Username</label>
          <input id="mqtt_username" autocomplete="off">
        </div>
        <div>
          <label for="mqtt_password">MQTT Password</label>
          <input id="mqtt_password" type="password" autocomplete="new-password">
        </div>
      </div>
      <div class="actions">
        <button id="saveBtn" type="button">Save Configuration</button>
        <button class="secondary" id="testAiBtn" type="button">Test AI API</button>
        <button class="secondary" id="testTelegramBtn" type="button">Test Telegram</button>
        <span id="configStatus" class="status"></span>
      </div>
    </section>

    <section class="panel tab-panel active" id="camerasPanel">
      <h2>Cameras</h2>
      <div class="hint">Nhập đúng tên stream trong go2rtc, ví dụ <code>bep</code>. Addon sẽ gọi <code>{go2rtc_url}/api/frame.jpeg?src=bep</code>.</div>
      <div class="entity-picker">
        <select id="haEntitySelect">
          <option value="">Load Home Assistant camera entities...</option>
        </select>
        <button class="secondary" id="loadEntitiesBtn" type="button">Load Entities</button>
        <button class="secondary" id="addEntityBtn" type="button">Add Selected</button>
      </div>
      <div id="entityStatus" class="status"></div>
      <div class="entity-picker">
        <select id="go2rtcStreamSelect">
          <option value="">Load go2rtc streams...</option>
        </select>
        <button class="secondary" id="loadStreamsBtn" type="button">Load go2rtc</button>
        <button class="secondary" id="addStreamBtn" type="button">Add Stream</button>
      </div>
      <div id="streamStatus" class="status"></div>
      <div class="actions">
        <button class="secondary" id="loadTriggersBtn" type="button">Load Motion/Sensors</button>
        <span id="triggerStatus" class="status"></span>
      </div>
      <datalist id="triggerEntityList"></datalist>
      <div class="camera-head">
        <div>Monitor</div>
        <div>Name</div>
        <div>HA entity</div>
        <div>Trigger</div>
        <div>go2rtc src</div>
        <div></div>
        <div></div>
        <div></div>
        <div></div>
      </div>
      <div id="cameraList"></div>
      <div class="actions">
        <button class="secondary" id="addCameraBtn" type="button">Add Camera</button>
        <button class="secondary" id="saveCamerasBtn" type="button">Save Cameras</button>
        <span id="cameraStatus" class="status"></span>
      </div>
      <h2>Automation YAML</h2>
      <pre id="automationYaml">Select motion/sensor triggers to generate Home Assistant automation YAML.</pre>
    </section>

    <section class="panel tab-panel" id="livePanel">
      <h2>Live</h2>
      <div class="grid">
        <div>
          <label for="liveSourceFilter">Live Source</label>
          <select id="liveSourceFilter">
            <option value="all">Both sources</option>
            <option value="entity">Entities only</option>
            <option value="go2rtc">go2rtc only</option>
          </select>
        </div>
        <div>
          <label for="liveLimit">Camera Limit</label>
          <input id="liveLimit" type="number" min="1" placeholder="All">
        </div>
      </div>
      <div class="actions">
        <button class="secondary" id="refreshLiveBtn" type="button">Refresh Live</button>
      </div>
      <div id="liveGrid" class="live-grid"></div>
    </section>

    <section class="panel tab-panel" id="eventsPanel">
      <h2>Sự kiện</h2>
      <div class="actions">
        <button class="secondary" id="refreshEventsBtn" type="button">Refresh Events</button>
        <span id="eventsStatus" class="status"></span>
      </div>
      <div id="eventsList"></div>
    </section>

    <section class="panel">
      <h2>Last Test Result</h2>
      <pre id="result">{}</pre>
    </section>

    <dialog class="viewer" id="viewerDialog">
      <div class="viewer-box">
        <div class="viewer-head">
          <div class="viewer-title" id="viewerTitle">Camera</div>
          <div class="actions">
            <button class="secondary" id="refreshViewerBtn" type="button">Refresh</button>
            <button class="secondary" id="openViewerBtn" type="button">Open Tab</button>
            <button class="secondary" id="closeViewerBtn" type="button">Close</button>
          </div>
        </div>
        <div class="viewer-body" id="viewerBody"></div>
      </div>
    </dialog>
  </main>

  <script>
    const fields = [
      "go2rtc_url", "ai_api_key", "ai_base_url", "ai_model",
      "telegram_bot_token", "telegram_chat_id", "prompt",
      "ai_timeout", "snapshot_timeout", "telegram_timeout",
      "mqtt_host", "mqtt_port", "mqtt_topic", "mqtt_username",
      "mqtt_password"
    ];
    let cameras = [];
    let currentViewerUrl = "";
    let currentSnapshotCamera = "";
    let liveRefreshTimer = null;
    let viewerRefreshTimer = null;

    function apiPath(path) {
      const base = window.location.pathname.endsWith("/")
        ? window.location.pathname
        : window.location.pathname + "/";
      return base + path.replace(/^\/+/, "");
    }

    function setActiveTab(panelId) {
      document.querySelectorAll(".tab-panel").forEach(panel => {
        panel.classList.toggle("active", panel.id === panelId);
      });
      document.querySelectorAll(".tab-btn").forEach(button => {
        button.classList.toggle("active", button.dataset.tab === panelId);
      });
      if (panelId === "livePanel") renderLiveCameras();
      if (panelId === "eventsPanel") loadEvents();
    }

    function buildGo2rtcUrl(camera, path, params = {}) {
      const base = document.getElementById("go2rtc_url").value.trim().replace(/\/+$/, "");
      const query = new URLSearchParams({src: camera, ...params});
      return `${base}${path}?${query.toString()}`;
    }

    function snapshotUrl(camera) {
      return apiPath(`api/camera/frame?camera=${encodeURIComponent(camera)}&_=${Date.now()}`);
    }

    function entitySnapshotUrl(entityId) {
      return apiPath(`api/camera/frame?entity_id=${encodeURIComponent(entityId)}&_=${Date.now()}`);
    }

    function cameraFrameUrl(camera) {
      const item = normalizeCamera(camera);
      return item.src ? snapshotUrl(item.src) : entitySnapshotUrl(item.entity_id);
    }

    async function requestJson(path, options = {}, timeoutMs = 45000) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), timeoutMs);
      try {
        const response = await fetch(apiPath(path), {
          ...options,
          signal: controller.signal
        });
        let data = {};
        try {
          data = await response.clone().json();
        } catch (err) {
          const text = await response.text().catch(() => "");
          data = {
            success: false,
            error: "invalid JSON response",
            status: response.status,
            response: text.slice(0, 500)
          };
        }
        return {response, data};
      } finally {
        clearTimeout(timer);
      }
    }

    function linesToList(value) {
      return value.split("\n").map(v => v.trim()).filter(Boolean);
    }

    function setStatus(id, text, type) {
      const el = document.getElementById(id);
      el.textContent = text || "";
      el.className = "status" + (type ? " " + type : "");
    }

    function buildConfigPayload() {
      const payload = {};
      fields.forEach(id => payload[id] = document.getElementById(id).value);
      payload.mqtt_enabled = document.getElementById("mqtt_enabled").checked;
      payload.keyword_match = linesToList(document.getElementById("keyword_match").value);
      payload.cameras = cameras.map(normalizeCamera).filter(camera => (
        camera.name || camera.entity_id || camera.src
      ));
      return payload;
    }

    function normalizeCamera(camera) {
      if (typeof camera === "string") {
        return {enabled: true, name: "", entity_id: "", trigger_entity_id: "", src: camera.trim()};
      }
      return {
        enabled: camera?.enabled !== false,
        name: String(camera?.name || "").trim(),
        entity_id: String(camera?.entity_id || "").trim(),
        trigger_entity_id: String(camera?.trigger_entity_id || "").trim(),
        src: String(camera?.src || "").trim()
      };
    }

    function cameraLabel(camera) {
      const item = normalizeCamera(camera);
      return item.name || item.entity_id || item.src || "Camera";
    }

    function camerasWithSrc() {
      return cameras.map(normalizeCamera).filter(camera => camera.src);
    }

    function camerasWithPreview() {
      return cameras.map(normalizeCamera).filter(camera => camera.src || camera.entity_id);
    }

    function liveCameraItems() {
      const source = document.getElementById("liveSourceFilter")?.value || "all";
      const limitValue = document.getElementById("liveLimit")?.value.trim() || "";
      let items = camerasWithPreview();

      if (source === "entity") {
        items = items.filter(camera => camera.entity_id)
          .map(camera => ({...camera, live_source: "entity"}));
      } else if (source === "go2rtc") {
        items = items.filter(camera => camera.src)
          .map(camera => ({...camera, live_source: "go2rtc"}));
      } else {
        items = items.map(camera => ({
          ...camera,
          live_source: camera.src ? "go2rtc" : "entity"
        }));
      }

      if (/^[1-9][0-9]*$/.test(limitValue)) {
        items = items.slice(0, Number(limitValue));
      }
      return items;
    }

    function validateTimeoutInputs() {
      const labels = {
        ai_timeout: "AI Timeout",
        snapshot_timeout: "Snapshot Timeout",
        telegram_timeout: "Telegram Timeout"
      };
      for (const id of Object.keys(labels)) {
        const value = document.getElementById(id).value.trim();
        if (!/^[1-9][0-9]*$/.test(value)) {
          throw new Error(`${labels[id]} must be a positive integer.`);
        }
      }
    }

    function renderCameras() {
      const list = document.getElementById("cameraList");
      list.innerHTML = "";
      cameras.forEach((camera, index) => {
        cameras[index] = normalizeCamera(camera);
        const item = cameras[index];
        const row = document.createElement("div");
        row.className = "camera-row";

        const monitorWrap = document.createElement("label");
        monitorWrap.className = "monitor-toggle";
        const monitorInput = document.createElement("input");
        monitorInput.type = "checkbox";
        monitorInput.checked = item.enabled;
        monitorInput.addEventListener("change", () => cameras[index].enabled = monitorInput.checked);
        const monitorText = document.createElement("span");
        monitorText.textContent = "Monitor";
        monitorWrap.append(monitorInput, monitorText);

        const nameWrap = document.createElement("div");
        const nameLabel = document.createElement("div");
        nameLabel.className = "mobile-label";
        nameLabel.textContent = "Name";
        const nameInput = document.createElement("input");
        nameInput.value = item.name;
        nameInput.placeholder = "Display name";
        nameInput.addEventListener("input", () => cameras[index].name = nameInput.value);
        nameWrap.append(nameLabel, nameInput);

        const entityWrap = document.createElement("div");
        const entityLabel = document.createElement("div");
        entityLabel.className = "mobile-label";
        entityLabel.textContent = "HA entity";
        const entityInput = document.createElement("input");
        entityInput.value = item.entity_id;
        entityInput.placeholder = "HA entity";
        entityInput.addEventListener("input", () => cameras[index].entity_id = entityInput.value);
        entityWrap.append(entityLabel, entityInput);

        const triggerWrap = document.createElement("div");
        const triggerLabel = document.createElement("div");
        triggerLabel.className = "mobile-label";
        triggerLabel.textContent = "Trigger";
        const triggerInput = document.createElement("input");
        triggerInput.value = item.trigger_entity_id;
        triggerInput.placeholder = "Motion/sensor trigger";
        triggerInput.setAttribute("list", "triggerEntityList");
        triggerInput.addEventListener("input", () => cameras[index].trigger_entity_id = triggerInput.value);
        triggerWrap.append(triggerLabel, triggerInput);

        const srcWrap = document.createElement("div");
        const srcLabel = document.createElement("div");
        srcLabel.className = "mobile-label";
        srcLabel.textContent = "go2rtc src";
        const srcInput = document.createElement("input");
        srcInput.value = item.src;
        srcInput.placeholder = "go2rtc src, e.g. bep";
        srcInput.addEventListener("input", () => cameras[index].src = srcInput.value);
        srcWrap.append(srcLabel, srcInput);

        const test = document.createElement("button");
        test.className = "secondary";
        test.type = "button";
        test.textContent = "Test";
        test.addEventListener("click", () => testCamera(cameras[index]));

        const snapshot = document.createElement("button");
        snapshot.className = "secondary";
        snapshot.type = "button";
        snapshot.textContent = "Snapshot";
        snapshot.addEventListener("click", () => viewSnapshot(cameras[index], cameraLabel(cameras[index])));

        const video = document.createElement("button");
        video.className = "secondary";
        video.type = "button";
        video.textContent = "Video";
        video.addEventListener("click", () => viewVideo(cameras[index], cameraLabel(cameras[index])));

        const remove = document.createElement("button");
        remove.className = "danger";
        remove.type = "button";
        remove.textContent = "Remove";
        remove.addEventListener("click", () => {
          cameras.splice(index, 1);
          renderCameras();
        });

        row.append(monitorWrap, nameWrap, entityWrap, triggerWrap, srcWrap, snapshot, video, test, remove);
        list.append(row);
      });
      renderLiveCameras();
      renderAutomationYaml();
    }

    function analyzePayload(camera) {
      const item = normalizeCamera(camera);
      if (item.src) return `{"camera":"${item.src}"}`;
      if (item.entity_id) return `{"entity_id":"${item.entity_id}"}`;
      return "{}";
    }

    function renderAutomationYaml() {
      const output = document.getElementById("automationYaml");
      if (!output) return;
      const items = cameras.map(normalizeCamera).filter(camera => (
        camera.enabled && camera.trigger_entity_id && (camera.src || camera.entity_id)
      ));
      if (!items.length) {
        output.textContent = "Select motion/sensor triggers to generate Home Assistant automation YAML.";
        return;
      }
      const blocks = items.map((camera, index) => {
        const alias = `Simple AI Vision - ${cameraLabel(camera)}`;
        return [
          `- alias: "${alias}"`,
          "trigger:",
          "    - platform: state",
          `      entity_id: ${camera.trigger_entity_id}`,
          `      to: "on"`,
          "action:",
          "    - service: rest_command.simple_ai_vision_analyze",
          "      data:",
          `        payload: '${analyzePayload(camera)}'`,
          "mode: single"
        ].join("\n");
      });
      output.textContent = [
        "rest_command:",
        "  simple_ai_vision_analyze:",
        '    url: "http://127.0.0.1:8000/analyze"',
        "    method: post",
        '    content_type: "application/json"',
        '    payload: "{{ payload }}"',
        "",
        "automation:",
        blocks.map(block => block.split("\n").map(line => `  ${line}`).join("\n")).join("\n\n")
      ].join("\n");
    }

    function cameraSrcOrError(camera) {
      const src = (camera || "").trim();
      if (!src) {
        document.getElementById("result").textContent = "go2rtc src is required.";
        return "";
      }
      return src;
    }

    function snapshotSourceOrError(camera) {
      const item = normalizeCamera(camera);
      if (item.src || item.entity_id) return item;
      document.getElementById("result").textContent = "go2rtc src or HA entity is required.";
      return null;
    }

    function showViewer(title, content, openUrl) {
      currentViewerUrl = openUrl || "";
      stopViewerRefresh();
      document.getElementById("viewerTitle").textContent = title;
      const body = document.getElementById("viewerBody");
      body.innerHTML = "";
      body.append(content);
      document.getElementById("openViewerBtn").style.display = currentViewerUrl ? "" : "none";
      document.getElementById("refreshViewerBtn").style.display = currentSnapshotCamera ? "" : "none";
      document.getElementById("viewerDialog").showModal();
    }

    function stopViewerRefresh() {
      if (viewerRefreshTimer) {
        clearInterval(viewerRefreshTimer);
        viewerRefreshTimer = null;
      }
    }

    function viewSnapshot(camera, label = "") {
      const item = snapshotSourceOrError(camera);
      if (!item) return;
      currentSnapshotCamera = item.src || item.entity_id;
      const img = document.createElement("img");
      img.id = "snapshotImage";
      img.dataset.src = item.src;
      img.dataset.entityId = item.entity_id;
      img.alt = `Snapshot ${label || item.src || item.entity_id}`;
      img.src = cameraFrameUrl(item);
      showViewer(`Snapshot: ${label || item.src || item.entity_id}`, img, img.src);
    }

    function viewVideo(camera, label = "") {
      const item = snapshotSourceOrError(camera);
      if (!item) return;
      currentSnapshotCamera = "";
      if (item.src) {
        const url = buildGo2rtcUrl(item.src, "/stream.html", {mode: "mse"});
        const frame = document.createElement("iframe");
        frame.src = url;
        frame.title = `Video ${label || item.src}`;
        frame.allow = "autoplay; fullscreen; picture-in-picture";
        showViewer(`Video: ${label || item.src}`, frame, url);
        return;
      }

      const img = document.createElement("img");
      img.id = "snapshotImage";
      img.dataset.src = "";
      img.dataset.entityId = item.entity_id;
      img.alt = `Live snapshot ${label || item.entity_id}`;
      img.src = entitySnapshotUrl(item.entity_id);
      currentSnapshotCamera = item.entity_id;
      showViewer(`Live snapshot: ${label || item.entity_id}`, img, img.src);
      viewerRefreshTimer = setInterval(refreshSnapshot, 3000);
    }

    function refreshSnapshot() {
      const img = document.getElementById("snapshotImage");
      if (!img) return;
      const src = img.dataset.src || "";
      const entityId = img.dataset.entityId || "";
      img.src = src ? snapshotUrl(src) : entitySnapshotUrl(entityId);
      currentViewerUrl = img.src;
    }

    function renderHaEntities(entities) {
      const select = document.getElementById("haEntitySelect");
      select.innerHTML = "";
      const empty = document.createElement("option");
      empty.value = "";
      empty.textContent = entities.length ? "Select Home Assistant entity" : "No camera entities found";
      select.append(empty);

      entities.forEach(entity => {
        const option = document.createElement("option");
        option.value = entity.entity_id;
        option.dataset.name = entity.name || "";
        option.textContent = entity.name
          ? `${entity.name} (${entity.entity_id})`
          : entity.entity_id;
        select.append(option);
      });
    }

    async function loadHaEntities() {
      setStatus("entityStatus", "Loading Home Assistant entities...", "");
      try {
        const {response, data} = await requestJson("api/hass/cameras", {}, 15000);
        if (!response.ok || !data.success) {
          setStatus("entityStatus", data.error || "Could not load Home Assistant entities", "err");
          return;
        }
        renderHaEntities(data.entities || []);
        setStatus("entityStatus", `Loaded ${(data.entities || []).length} camera entities`, "ok");
      } catch (err) {
        setStatus("entityStatus", err.name === "AbortError" ? "Entity load timeout" : err.message, "err");
      }
    }

    function renderTriggerEntities(entities) {
      const list = document.getElementById("triggerEntityList");
      list.innerHTML = "";
      entities.forEach(entity => {
        const option = document.createElement("option");
        option.value = entity.entity_id;
        option.label = entity.name ? `${entity.name} (${entity.entity_id})` : entity.entity_id;
        list.append(option);
      });
    }

    async function loadTriggerEntities() {
      setStatus("triggerStatus", "Loading motion/sensor triggers...", "");
      try {
        const {response, data} = await requestJson("api/hass/triggers", {}, 15000);
        if (!response.ok || !data.success) {
          setStatus("triggerStatus", data.error || "Could not load trigger entities", "err");
          return;
        }
        renderTriggerEntities(data.entities || []);
        setStatus("triggerStatus", `Loaded ${(data.entities || []).length} trigger entities`, "ok");
      } catch (err) {
        setStatus("triggerStatus", err.name === "AbortError" ? "Trigger load timeout" : err.message, "err");
      }
    }

    function addSelectedEntity() {
      const select = document.getElementById("haEntitySelect");
      const value = select.value.trim();
      if (!value) {
        setStatus("entityStatus", "Select an entity first, or use Add Camera for manual input.", "err");
        return;
      }
      const selected = select.selectedOptions[0];
      cameras.push({
        enabled: true,
        name: selected?.dataset.name || "",
        entity_id: value,
        trigger_entity_id: "",
        src: ""
      });
      renderCameras();
      setStatus("entityStatus", `Added ${value}. Fill go2rtc src before testing.`, "ok");
    }

    function renderGo2rtcStreams(streams) {
      const select = document.getElementById("go2rtcStreamSelect");
      select.innerHTML = "";
      const empty = document.createElement("option");
      empty.value = "";
      empty.textContent = streams.length ? "Select go2rtc stream" : "No go2rtc streams found";
      select.append(empty);

      streams.forEach(stream => {
        const option = document.createElement("option");
        option.value = stream.src;
        option.textContent = stream.name && stream.name !== stream.src
          ? `${stream.name} (${stream.src})`
          : stream.src;
        select.append(option);
      });
    }

    async function loadGo2rtcStreams() {
      setStatus("streamStatus", "Loading go2rtc streams...", "");
      try {
        const {response, data} = await requestJson("api/go2rtc/streams", {}, 15000);
        if (!response.ok || !data.success) {
          setStatus("streamStatus", data.error || "Could not load go2rtc streams", "err");
          return;
        }
        renderGo2rtcStreams(data.streams || []);
        setStatus("streamStatus", `Loaded ${(data.streams || []).length} go2rtc streams`, "ok");
      } catch (err) {
        setStatus("streamStatus", err.name === "AbortError" ? "go2rtc stream load timeout" : err.message, "err");
      }
    }

    function addSelectedStream() {
      const select = document.getElementById("go2rtcStreamSelect");
      const src = select.value.trim();
      if (!src) {
        setStatus("streamStatus", "Select a go2rtc stream first, or use Add Camera for manual input.", "err");
        return;
      }
      cameras.push({enabled: true, name: src, entity_id: "", trigger_entity_id: "", src});
      renderCameras();
      setStatus("streamStatus", `Added go2rtc stream ${src}`, "ok");
    }

    function renderLiveCameras() {
      const grid = document.getElementById("liveGrid");
      if (!grid) return;
      if (liveRefreshTimer) {
        clearInterval(liveRefreshTimer);
        liveRefreshTimer = null;
      }
      grid.innerHTML = "";
      const items = liveCameraItems();
      if (!items.length) {
        grid.textContent = "No camera matches the selected live filter.";
        return;
      }

      items.forEach(camera => {
        const item = document.createElement("div");
        item.className = "live-item";

        const title = document.createElement("div");
        title.className = "live-title";
        const name = document.createElement("div");
        name.textContent = cameraLabel(camera);
        const src = document.createElement("span");
        src.textContent = camera.live_source === "go2rtc" ? camera.src : camera.entity_id;
        title.append(name, src);

        let media;
        if (camera.live_source === "go2rtc") {
          media = document.createElement("iframe");
          media.src = buildGo2rtcUrl(camera.src, "/stream.html", {mode: "mse"});
          media.allow = "autoplay; fullscreen; picture-in-picture";
        } else {
          media = document.createElement("img");
          media.dataset.entityId = camera.entity_id;
          media.src = entitySnapshotUrl(camera.entity_id);
          media.alt = `Live snapshot ${cameraLabel(camera)}`;
        }
        media.title = `Live ${cameraLabel(camera)}`;

        item.append(title, media);
        grid.append(item);
      });

      liveRefreshTimer = setInterval(() => {
        document.querySelectorAll("#liveGrid img[data-entity-id]").forEach(img => {
          img.src = entitySnapshotUrl(img.dataset.entityId);
        });
      }, 5000);
    }

    function renderEvents(events) {
      const list = document.getElementById("eventsList");
      list.innerHTML = "";
      if (!events.length) {
        list.textContent = "No sent alert events yet.";
        return;
      }

      const table = document.createElement("table");
      table.className = "events-table";
      table.innerHTML = "<thead><tr><th>Time</th><th>Status</th><th>Camera</th><th>Keyword</th><th>Analysis</th></tr></thead>";
      const body = document.createElement("tbody");
      events.forEach(event => {
        const row = document.createElement("tr");
        const time = document.createElement("td");
        time.textContent = event.time || "";
        const status = document.createElement("td");
        status.textContent = event.status || "";
        const camera = document.createElement("td");
        camera.textContent = event.camera || "";
        const keyword = document.createElement("td");
        keyword.textContent = event.keyword || "";
        const analysis = document.createElement("td");
        analysis.textContent = event.error || event.analysis || "";
        row.append(time, status, camera, keyword, analysis);
        body.append(row);
      });
      table.append(body);
      list.append(table);
    }

    async function loadEvents() {
      setStatus("eventsStatus", "Loading events...", "");
      try {
        const {response, data} = await requestJson("api/events", {}, 15000);
        if (!response.ok || !data.success) {
          setStatus("eventsStatus", data.error || "Could not load events", "err");
          return;
        }
        renderEvents(data.events || []);
        setStatus("eventsStatus", `Loaded ${(data.events || []).length} events`, "ok");
      } catch (err) {
        setStatus("eventsStatus", err.name === "AbortError" ? "Event load timeout" : err.message, "err");
      }
    }

    async function loadConfig() {
      try {
        setStatus("configStatus", "Loading...", "");
        const {response, data} = await requestJson("api/config", {}, 15000);
        if (!response.ok || !data.success) {
          setStatus("configStatus", data.error || "Could not load config", "err");
          return;
        }
        const config = data.config;
        fields.forEach(id => document.getElementById(id).value = config[id] ?? "");
        document.getElementById("mqtt_enabled").checked = !!config.mqtt_enabled;
        document.getElementById("keyword_match").value = (config.keyword_match || []).join("\n");
        cameras = config.cameras || [];
        renderCameras();
        setStatus("configStatus", "Loaded", "ok");
      } catch (err) {
        setStatus("configStatus", err.name === "AbortError" ? "Load timeout" : err.message, "err");
      }
    }

    async function saveConfig(statusId = "configStatus") {
      let payload;
      try {
        validateTimeoutInputs();
        payload = buildConfigPayload();
      } catch (err) {
        setStatus(statusId, err.message, "err");
        return null;
      }

      try {
        setStatus(statusId, "Saving...", "");
        const {response, data} = await requestJson("api/config", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(payload)
        }, 20000);
        if (!response.ok || !data.success) {
          setStatus(statusId, data.error || "Save failed", "err");
          return null;
        }
        cameras = data.config.cameras || [];
        renderCameras();
        setStatus(statusId, "Saved", "ok");
        return data.config;
      } catch (err) {
        setStatus(statusId, err.name === "AbortError" ? "Save timeout" : err.message, "err");
        return null;
      }
    }

    async function testCamera(camera) {
      const item = snapshotSourceOrError(camera);
      if (!item) return;
      document.getElementById("result").textContent = "Running camera test...";
      try {
        const body = item.src
          ? {camera: item.src, entity_id: item.entity_id}
          : {entity_id: item.entity_id};
        const {data} = await requestJson("analyze", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(body)
        }, 90000);
        document.getElementById("result").textContent = JSON.stringify(data, null, 2);
      } catch (err) {
        document.getElementById("result").textContent =
          err.name === "AbortError" ? "Camera test timeout." : `Camera test error: ${err.message}`;
      }
    }

    async function testAiApi() {
      try {
        validateTimeoutInputs();
      } catch (err) {
        setStatus("configStatus", err.message, "err");
        document.getElementById("result").textContent = err.message;
        return;
      }
      document.getElementById("result").textContent = "Running AI API test...";
      setStatus("configStatus", "Testing AI API...", "");
      try {
        const {response, data} = await requestJson("api/test-ai", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(buildConfigPayload())
        }, 60000);
        document.getElementById("result").textContent = JSON.stringify(data, null, 2);
        setStatus("configStatus", response.ok && data.success ? "AI API OK" : "AI API failed", response.ok && data.success ? "ok" : "err");
      } catch (err) {
        const message = err.name === "AbortError" ? "AI API test timeout." : `AI API test error: ${err.message}`;
        document.getElementById("result").textContent = message;
        setStatus("configStatus", message, "err");
      }
    }

    async function testTelegram() {
      try {
        validateTimeoutInputs();
      } catch (err) {
        setStatus("configStatus", err.message, "err");
        document.getElementById("result").textContent = err.message;
        return;
      }
      document.getElementById("result").textContent = "Sending Telegram test...";
      setStatus("configStatus", "Testing Telegram...", "");
      try {
        const {response, data} = await requestJson("api/test-telegram", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(buildConfigPayload())
        }, 30000);
        document.getElementById("result").textContent = JSON.stringify(data, null, 2);
        setStatus("configStatus", response.ok && data.success ? "Telegram OK" : "Telegram failed", response.ok && data.success ? "ok" : "err");
      } catch (err) {
        const message = err.name === "AbortError" ? "Telegram test timeout." : `Telegram test error: ${err.message}`;
        document.getElementById("result").textContent = message;
        setStatus("configStatus", message, "err");
      }
    }

    document.getElementById("reloadBtn").addEventListener("click", loadConfig);
    document.querySelectorAll(".tab-btn").forEach(button => {
      button.addEventListener("click", () => setActiveTab(button.dataset.tab));
    });
    document.getElementById("saveBtn").addEventListener("click", () => saveConfig());
    document.getElementById("testAiBtn").addEventListener("click", testAiApi);
    document.getElementById("testTelegramBtn").addEventListener("click", testTelegram);
    document.getElementById("saveCamerasBtn").addEventListener("click", () => saveConfig("cameraStatus"));
    document.getElementById("loadEntitiesBtn").addEventListener("click", loadHaEntities);
    document.getElementById("addEntityBtn").addEventListener("click", addSelectedEntity);
    document.getElementById("loadTriggersBtn").addEventListener("click", loadTriggerEntities);
    document.getElementById("loadStreamsBtn").addEventListener("click", loadGo2rtcStreams);
    document.getElementById("addStreamBtn").addEventListener("click", addSelectedStream);
    document.getElementById("refreshLiveBtn").addEventListener("click", renderLiveCameras);
    document.getElementById("liveSourceFilter").addEventListener("change", renderLiveCameras);
    document.getElementById("liveLimit").addEventListener("input", renderLiveCameras);
    document.getElementById("refreshEventsBtn").addEventListener("click", loadEvents);
    document.getElementById("addCameraBtn").addEventListener("click", () => {
      cameras.push({enabled: true, name: "", entity_id: "", trigger_entity_id: "", src: ""});
      renderCameras();
    });
    document.getElementById("closeViewerBtn").addEventListener("click", () => {
      stopViewerRefresh();
      document.getElementById("viewerDialog").close();
      document.getElementById("viewerBody").innerHTML = "";
      currentSnapshotCamera = "";
    });
    document.getElementById("openViewerBtn").addEventListener("click", () => {
      if (currentViewerUrl) window.open(currentViewerUrl, "_blank", "noopener");
    });
    document.getElementById("refreshViewerBtn").addEventListener("click", refreshSnapshot);
    loadConfig();
  </script>
</body>
</html>
"""


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("simple-ai-vision")

app = FastAPI(title="Simple AI Vision", docs_url=None, redoc_url=None)


def error_response(message: str, status_code: int = 400, **extra: Any) -> JSONResponse:
    payload = {"success": False, "error": message}
    payload.update(extra)
    return JSONResponse(payload, status_code=status_code)


def provider_error_response(exc: requests.HTTPError) -> JSONResponse:
    response = exc.response
    provider_status = response.status_code if response is not None else None
    provider_body = ""
    if response is not None:
        provider_body = response.text[:1000]

    if provider_status == 404:
        message = "AI API endpoint not found. Check ai_base_url and provider path."
    elif provider_status == 401:
        message = "AI API unauthorized. Check ai_api_key."
    elif provider_status == 403:
        message = "AI API forbidden. Check key permission or provider access."
    elif provider_status == 429:
        message = "AI API rate limited or quota exceeded."
    else:
        message = "AI API provider error"

    return JSONResponse(
        {
            "success": False,
            "error": message,
            "provider_status": provider_status,
            "provider_response": provider_body,
        }
    )


def upstream_error_response(exc: requests.HTTPError) -> JSONResponse:
    response = exc.response
    upstream_status = response.status_code if response is not None else None
    upstream_body = response.text[:1000] if response is not None else ""
    return JSONResponse(
        {
            "success": False,
            "error": "upstream HTTP error",
            "upstream_status": upstream_status,
            "upstream_response": upstream_body,
        }
    )


def default_options() -> dict[str, Any]:
    return {
        "go2rtc_url": "",
        "ai_api_key": "",
        "ai_base_url": "https://api.openai.com/v1",
        "ai_model": "gpt-4o-mini",
        "telegram_bot_token": "",
        "telegram_chat_id": "",
        "prompt": DEFAULT_PROMPT,
        "keyword_match": DEFAULT_KEYWORDS,
        "cameras": [],
        "ai_timeout": 30,
        "snapshot_timeout": 10,
        "telegram_timeout": 10,
        "mqtt_enabled": False,
        "mqtt_host": "",
        "mqtt_port": 1883,
        "mqtt_username": "",
        "mqtt_password": "",
        "mqtt_topic": "simple_ai_vision/events",
    }


def read_options() -> dict[str, Any]:
    options = default_options()

    if os.path.exists(UI_OPTIONS_PATH):
        with open(UI_OPTIONS_PATH, "r", encoding="utf-8") as file:
            data = json.load(file)
        if isinstance(data, dict):
            options.update(data)

    normalize_options(options)
    return options


def load_options() -> dict[str, Any]:
    options = read_options()
    validate_options(options)
    return options


def merge_user_options(current: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(current)
    cleaned = dict(incoming)
    for secret_key in ("ai_api_key", "telegram_bot_token", "mqtt_password"):
        if secret_key in cleaned and not str(cleaned.get(secret_key, "")).strip():
            cleaned.pop(secret_key)
    merged.update(cleaned)
    return merged


def save_options(options: dict[str, Any]) -> dict[str, Any]:
    current = read_options()
    current = merge_user_options(current, options)
    normalize_options(current)
    validate_saved_options(current)

    os.makedirs(os.path.dirname(UI_OPTIONS_PATH), exist_ok=True)
    tmp_path = f"{UI_OPTIONS_PATH}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as file:
        json.dump(current, file, ensure_ascii=False, indent=2)
    os.replace(tmp_path, UI_OPTIONS_PATH)
    return current


def normalize_options(options: dict[str, Any]) -> None:
    if not isinstance(options.get("keyword_match"), list):
        options["keyword_match"] = []
    options["keyword_match"] = [
        str(item).strip()
        for item in options.get("keyword_match", [])
        if str(item).strip()
    ]

    if not isinstance(options.get("cameras"), list):
        options["cameras"] = []
    options["cameras"] = normalize_camera_list(options.get("cameras", []))

    for key in ("ai_timeout", "snapshot_timeout", "telegram_timeout"):
        try:
            options[key] = int(options.get(key, 1))
        except (TypeError, ValueError):
            options[key] = 1

    options["mqtt_enabled"] = bool(options.get("mqtt_enabled"))
    try:
        options["mqtt_port"] = int(options.get("mqtt_port", 1883))
    except (TypeError, ValueError):
        options["mqtt_port"] = 1883


def normalize_camera_list(cameras: list[Any]) -> list[dict[str, str]]:
    normalized = []
    for camera in cameras:
        if isinstance(camera, str):
            item = {"enabled": True, "name": "", "entity_id": "", "src": camera.strip()}
        elif isinstance(camera, dict):
            item = {
                "enabled": camera.get("enabled") is not False,
                "name": str(camera.get("name", "")).strip(),
                "entity_id": str(camera.get("entity_id", "")).strip(),
                "trigger_entity_id": str(camera.get("trigger_entity_id", "")).strip(),
                "src": str(camera.get("src", "")).strip(),
            }
        else:
            continue

        if item["name"] or item["entity_id"] or item["src"]:
            normalized.append(item)

    return normalized


def validate_saved_options(options: dict[str, Any]) -> None:
    if not isinstance(options.get("keyword_match"), list):
        raise ValueError("keyword_match must be a list")

    if not isinstance(options.get("cameras"), list):
        raise ValueError("cameras must be a list")

    for camera in options["cameras"]:
        if not isinstance(camera, dict):
            raise ValueError("camera entries must be objects")
        if camera.get("src"):
            validate_camera(camera["src"])
        elif camera.get("entity_id"):
            validate_entity_id(camera["entity_id"])
        elif camera.get("name"):
            raise ValueError("go2rtc src or HA entity is required for each camera")

    for key in ("ai_timeout", "snapshot_timeout", "telegram_timeout"):
        try:
            options[key] = int(options[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be an integer") from exc
        if options[key] < 1:
            raise ValueError(f"{key} must be greater than 0")

    if options.get("mqtt_enabled"):
        if not str(options.get("mqtt_host", "")).strip():
            raise ValueError("mqtt_host is required when MQTT is enabled")
        if not str(options.get("mqtt_topic", "")).strip():
            raise ValueError("mqtt_topic is required when MQTT is enabled")
        if int(options.get("mqtt_port", 1883)) < 1:
            raise ValueError("mqtt_port must be greater than 0")


def find_saved_camera(
    options: dict[str, Any],
    camera: str | None,
    entity_id: str | None,
) -> dict[str, str] | None:
    for item in options.get("cameras", []):
        if not isinstance(item, dict):
            continue
        if camera and item.get("src") == camera:
            return item
        if entity_id and item.get("entity_id") == entity_id:
            return item
    return None


def validate_options(options: dict[str, Any]) -> None:
    required = [
        "ai_api_key",
        "ai_base_url",
        "ai_model",
        "telegram_bot_token",
        "telegram_chat_id",
    ]
    missing = [key for key in required if not str(options.get(key, "")).strip()]
    if missing:
        raise ValueError(f"Missing required option(s): {', '.join(missing)}")

    validate_saved_options(options)


def validate_ai_options(options: dict[str, Any]) -> None:
    required = ["ai_api_key", "ai_base_url", "ai_model"]
    missing = [key for key in required if not str(options.get(key, "")).strip()]
    if missing:
        raise ValueError(f"Missing required AI option(s): {', '.join(missing)}")

    try:
        options["ai_timeout"] = int(options.get("ai_timeout", 30))
    except (TypeError, ValueError) as exc:
        raise ValueError("ai_timeout must be an integer") from exc

    if options["ai_timeout"] < 1:
        raise ValueError("ai_timeout must be greater than 0")


def validate_telegram_options(options: dict[str, Any]) -> None:
    required = ["telegram_bot_token", "telegram_chat_id"]
    missing = [key for key in required if not str(options.get(key, "")).strip()]
    if missing:
        raise ValueError(f"Missing required Telegram option(s): {', '.join(missing)}")

    try:
        options["telegram_timeout"] = int(options.get("telegram_timeout", 10))
    except (TypeError, ValueError) as exc:
        raise ValueError("telegram_timeout must be an integer") from exc

    if options["telegram_timeout"] < 1:
        raise ValueError("telegram_timeout must be greater than 0")


def validate_camera(camera: Any) -> str:
    if not isinstance(camera, str) or not camera.strip():
        raise ValueError("camera is required")

    camera = camera.strip()
    if not CAMERA_RE.fullmatch(camera):
        raise ValueError("invalid camera name")

    return camera


def validate_entity_id(entity_id: Any) -> str:
    if not isinstance(entity_id, str) or not entity_id.strip():
        raise ValueError("entity_id is required")

    entity_id = entity_id.strip()
    if not re.fullmatch(r"^(camera|image)\.[A-Za-z0-9_]+$", entity_id):
        raise ValueError("invalid Home Assistant camera entity")

    return entity_id


def fetch_snapshot(camera: str, options: dict[str, Any]) -> str:
    logger.info("Fetching snapshot for camera=%s", camera)
    base_url = options["go2rtc_url"].rstrip("/")
    url = f"{base_url}/api/frame.jpeg"

    response = requests.get(
        url,
        params={"src": camera},
        timeout=options["snapshot_timeout"],
    )
    response.raise_for_status()

    content_type = response.headers.get("content-type", "")
    if "image" not in content_type and not response.content.startswith(b"\xff\xd8"):
        raise ValueError("snapshot response is not a JPEG image")

    tmp = tempfile.NamedTemporaryFile(
        mode="wb",
        suffix=".jpg",
        prefix=f"simple_ai_vision_{camera}_",
        dir="/tmp",
        delete=False,
    )
    with tmp:
        tmp.write(response.content)

    return tmp.name


def fetch_hass_snapshot(entity_id: str, options: dict[str, Any]) -> str:
    entity_id = validate_entity_id(entity_id)
    token = os.environ.get("SUPERVISOR_TOKEN", "")
    if not token:
        raise ValueError("Home Assistant API is not available")

    logger.info("Fetching Home Assistant snapshot for entity=%s", entity_id)
    response = requests.get(
        f"http://supervisor/core/api/camera_proxy/{entity_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=options["snapshot_timeout"],
    )
    response.raise_for_status()

    content_type = response.headers.get("content-type", "")
    if "image" not in content_type and not response.content.startswith(b"\xff\xd8"):
        raise ValueError("Home Assistant camera response is not an image")

    tmp = tempfile.NamedTemporaryFile(
        mode="wb",
        suffix=".jpg",
        prefix=f"simple_ai_vision_{entity_id.replace('.', '_')}_",
        dir="/tmp",
        delete=False,
    )
    with tmp:
        tmp.write(response.content)

    return tmp.name


def fetch_snapshot_for_source(
    camera: str | None,
    entity_id: str | None,
    options: dict[str, Any],
) -> tuple[str, str]:
    if camera:
        camera_name = validate_camera(camera)
        return fetch_snapshot(camera_name, options), camera_name

    if entity_id:
        entity = validate_entity_id(entity_id)
        return fetch_hass_snapshot(entity, options), entity

    raise ValueError("camera or entity_id is required")


def image_to_data_url(path: str) -> str:
    with open(path, "rb") as file:
        encoded = base64.b64encode(file.read()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def parse_ai_content(data: dict[str, Any]) -> str:
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("invalid AI API response") from exc

    if isinstance(content, list):
        text_parts = [part.get("text", "") for part in content if isinstance(part, dict)]
        content = "\n".join(part for part in text_parts if part)

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

        for choice in data.get("choices", []):
            if not isinstance(choice, dict):
                continue
            delta = choice.get("delta")
            if isinstance(delta, dict) and delta.get("content"):
                parts.append(str(delta["content"]))
                continue
            message = choice.get("message")
            if isinstance(message, dict) and message.get("content"):
                parts.append(str(message["content"]))

    result = "".join(parts).strip()
    if not result:
        raise ValueError("AI API returned SSE response without text content")
    return result


def response_json(response: requests.Response, service: str) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError as exc:
        body = response.text[:1000]
        raise ValueError(
            f"{service} returned non-JSON response "
            f"(status={response.status_code}, body={body!r})"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(f"{service} returned invalid JSON payload")

    return data


def response_ai_content(response: requests.Response) -> str:
    content_type = response.headers.get("content-type", "").lower()
    text = response.text
    if "text/event-stream" in content_type or text.lstrip().startswith("data:"):
        return parse_ai_sse(text)
    return parse_ai_content(response_json(response, "AI API"))


def call_ai(data_url: str, options: dict[str, Any]) -> str:
    logger.info("Sending AI vision request")
    url = f"{options['ai_base_url'].rstrip('/')}/chat/completions"
    payload = {
        "model": options["ai_model"],
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": options["prompt"]},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "temperature": 0.2,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {options['ai_api_key']}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=options["ai_timeout"],
    )
    response.raise_for_status()
    return response_ai_content(response)


def call_ai_text(options: dict[str, Any]) -> str:
    logger.info("Sending AI API test request")
    url = f"{options['ai_base_url'].rstrip('/')}/chat/completions"
    payload = {
        "model": options["ai_model"],
        "messages": [
            {
                "role": "user",
                "content": "Reply with OK only.",
            }
        ],
        "temperature": 0,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {options['ai_api_key']}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=options["ai_timeout"],
    )
    response.raise_for_status()
    return response_ai_content(response)


def keyword_matched(analysis: str, keywords: list[Any]) -> bool:
    return bool(matched_keyword(analysis, keywords))


def matched_keyword(analysis: str, keywords: list[Any]) -> str:
    logger.info("Checking keyword match")
    for keyword in keywords:
        pattern = str(keyword).strip()
        if not pattern:
            continue
        try:
            if re.search(pattern, analysis, flags=re.IGNORECASE):
                return pattern
        except re.error:
            if pattern.lower() in analysis.lower():
                return pattern
    return ""


def send_telegram(camera: str, analysis: str, photo_path: str, options: dict[str, Any]) -> None:
    logger.info("Sending Telegram photo")
    url = f"https://api.telegram.org/bot{options['telegram_bot_token']}/sendPhoto"
    caption = f"Camera: {camera}\n\n{analysis}"

    with open(photo_path, "rb") as photo:
        response = requests.post(
            url,
            data={
                "chat_id": options["telegram_chat_id"],
                "caption": caption[:1024],
            },
            files={"photo": photo},
            timeout=options["telegram_timeout"],
        )
    response.raise_for_status()


def send_telegram_text(message: str, options: dict[str, Any]) -> None:
    logger.info("Sending Telegram text test")
    url = f"https://api.telegram.org/bot{options['telegram_bot_token']}/sendMessage"
    response = requests.post(
        url,
        data={
            "chat_id": options["telegram_chat_id"],
            "text": message,
        },
        timeout=options["telegram_timeout"],
    )
    response.raise_for_status()


def cleanup_file(path: str | None) -> None:
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            logger.warning("Could not remove temp file: %s", path)


def get_go2rtc_streams(options: dict[str, Any]) -> list[dict[str, str]]:
    base_url = str(options.get("go2rtc_url", "")).strip().rstrip("/")
    if not base_url:
        raise ValueError("go2rtc_url is required")

    response = requests.get(
        f"{base_url}/api/streams",
        timeout=options.get("snapshot_timeout", 10),
    )
    response.raise_for_status()

    try:
        data = response.json()
    except ValueError as exc:
        raise ValueError("go2rtc returned non-JSON response") from exc

    streams: list[dict[str, str]] = []
    if isinstance(data, dict):
        for key, value in data.items():
            src = str(key).strip()
            if not src:
                continue
            name = src
            if isinstance(value, dict):
                name = str(value.get("name") or src).strip()
            streams.append({"src": src, "name": name})
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, str):
                src = item.strip()
                name = src
            elif isinstance(item, dict):
                src = str(item.get("src") or item.get("name") or "").strip()
                name = str(item.get("name") or src).strip()
            else:
                continue
            if src:
                streams.append({"src": src, "name": name})
    else:
        raise ValueError("go2rtc returned invalid streams payload")

    return sorted(streams, key=lambda stream: stream["src"])


def record_event(
    camera: str,
    analysis: str,
    status: str,
    keyword: str = "",
    error: str = "",
) -> None:
    event = {
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": status,
        "camera": camera,
        "keyword": keyword,
        "analysis": analysis,
        "error": error,
    }
    os.makedirs(os.path.dirname(EVENT_LOG_PATH), exist_ok=True)
    with open(EVENT_LOG_PATH, "a", encoding="utf-8") as file:
        file.write(json.dumps(event, ensure_ascii=False) + "\n")
    publish_mqtt_event(event)


def publish_mqtt_event(event: dict[str, str]) -> None:
    try:
        options = read_options()
    except Exception as exc:
        logger.warning("Could not read config for MQTT publish: %s", exc)
        return

    if not options.get("mqtt_enabled"):
        return

    if mqtt_publish is None:
        logger.error("MQTT publish requested but paho-mqtt is not installed")
        return

    host = str(options.get("mqtt_host", "")).strip()
    topic = str(options.get("mqtt_topic", "")).strip()
    if not host or not topic:
        logger.error("MQTT publish skipped because mqtt_host or mqtt_topic is empty")
        return

    auth = None
    username = str(options.get("mqtt_username", "")).strip()
    password = str(options.get("mqtt_password", ""))
    if username:
        auth = {"username": username, "password": password}

    try:
        mqtt_publish.single(
            topic,
            payload=json.dumps(event, ensure_ascii=False),
            hostname=host,
            port=int(options.get("mqtt_port", 1883)),
            auth=auth,
            qos=0,
            retain=False,
        )
        logger.info("MQTT event published topic=%s status=%s", topic, event.get("status"))
    except Exception as exc:
        logger.error("MQTT publish failed: %s", exc)


def read_events(limit: int = 100) -> list[dict[str, str]]:
    if not os.path.exists(EVENT_LOG_PATH):
        return []

    with open(EVENT_LOG_PATH, "r", encoding="utf-8") as file:
        lines = file.readlines()[-limit:]

    events = []
    for line in reversed(lines):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        events.append(
            {
                "time": str(event.get("time", "")),
                "status": str(event.get("status", "sent")),
                "camera": str(event.get("camera", "")),
                "keyword": str(event.get("keyword", "")),
                "analysis": str(event.get("analysis", "")),
                "error": str(event.get("error", "")),
            }
        )
    return events


def get_hass_camera_entities() -> list[dict[str, str]]:
    token = os.environ.get("SUPERVISOR_TOKEN", "")
    if not token:
        raise ValueError("Home Assistant API is not available")

    response = requests.get(
        "http://supervisor/core/api/states",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    response.raise_for_status()

    try:
        states = response.json()
    except ValueError as exc:
        raise ValueError("Home Assistant returned non-JSON response") from exc

    if not isinstance(states, list):
        raise ValueError("Home Assistant returned invalid states payload")

    entities: list[dict[str, str]] = []
    for item in states:
        if not isinstance(item, dict):
            continue

        entity_id = str(item.get("entity_id", "")).strip()
        domain = entity_id.split(".", 1)[0]
        if domain not in ("camera", "image"):
            continue

        attributes = item.get("attributes", {})
        name = ""
        if isinstance(attributes, dict):
            name = str(attributes.get("friendly_name", "")).strip()

        entities.append({"entity_id": entity_id, "name": name})

    return sorted(entities, key=lambda entity: entity["entity_id"])


def get_hass_trigger_entities() -> list[dict[str, str]]:
    token = os.environ.get("SUPERVISOR_TOKEN", "")
    if not token:
        raise ValueError("Home Assistant API is not available")

    response = requests.get(
        "http://supervisor/core/api/states",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    response.raise_for_status()

    try:
        states = response.json()
    except ValueError as exc:
        raise ValueError("Home Assistant returned non-JSON response") from exc

    if not isinstance(states, list):
        raise ValueError("Home Assistant returned invalid states payload")

    entities: list[dict[str, str]] = []
    for item in states:
        if not isinstance(item, dict):
            continue

        entity_id = str(item.get("entity_id", "")).strip()
        domain = entity_id.split(".", 1)[0]
        if domain not in ("binary_sensor", "sensor"):
            continue

        attributes = item.get("attributes", {})
        name = ""
        device_class = ""
        if isinstance(attributes, dict):
            name = str(attributes.get("friendly_name", "")).strip()
            device_class = str(attributes.get("device_class", "")).strip()

        entities.append(
            {
                "entity_id": entity_id,
                "name": name,
                "device_class": device_class,
            }
        )

    return sorted(entities, key=lambda entity: entity["entity_id"])


@app.get("/health")
def health() -> dict[str, bool]:
    return {"success": True}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return INDEX_HTML


@app.get("/api/config")
def get_config() -> JSONResponse:
    try:
        return JSONResponse({"success": True, "config": read_options()})
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Could not read config: %s", exc)
        return error_response("could not read config", 500)


@app.get("/api/hass/cameras")
def hass_cameras() -> JSONResponse:
    try:
        return JSONResponse({"success": True, "entities": get_hass_camera_entities()})
    except ValueError as exc:
        logger.error("%s", exc)
        return error_response(str(exc), 400)
    except requests.Timeout:
        logger.error("Home Assistant entity load timeout")
        return JSONResponse({"success": False, "error": "Home Assistant API timeout"})
    except requests.HTTPError as exc:
        logger.error("Home Assistant API HTTP error: %s", exc)
        return upstream_error_response(exc)
    except requests.RequestException as exc:
        logger.error("Home Assistant API network error: %s", exc)
        return JSONResponse({"success": False, "error": "Home Assistant API network error", "details": str(exc)})


@app.get("/api/hass/triggers")
def hass_triggers() -> JSONResponse:
    try:
        return JSONResponse({"success": True, "entities": get_hass_trigger_entities()})
    except ValueError as exc:
        logger.error("%s", exc)
        return error_response(str(exc), 400)
    except requests.Timeout:
        logger.error("Home Assistant trigger load timeout")
        return JSONResponse({"success": False, "error": "Home Assistant API timeout"})
    except requests.HTTPError as exc:
        logger.error("Home Assistant trigger API HTTP error: %s", exc)
        return upstream_error_response(exc)
    except requests.RequestException as exc:
        logger.error("Home Assistant trigger API network error: %s", exc)
        return JSONResponse({"success": False, "error": "Home Assistant API network error", "details": str(exc)})


@app.get("/api/go2rtc/streams")
def go2rtc_streams() -> JSONResponse:
    try:
        options = read_options()
        return JSONResponse({"success": True, "streams": get_go2rtc_streams(options)})
    except ValueError as exc:
        logger.error("%s", exc)
        return error_response(str(exc), 400)
    except requests.Timeout:
        logger.error("go2rtc stream load timeout")
        return JSONResponse({"success": False, "error": "go2rtc API timeout"})
    except requests.HTTPError as exc:
        logger.error("go2rtc API HTTP error: %s", exc)
        return upstream_error_response(exc)
    except requests.RequestException as exc:
        logger.error("go2rtc API network error: %s", exc)
        return JSONResponse({"success": False, "error": "go2rtc API network error", "details": str(exc)})


@app.get("/api/events")
def events() -> JSONResponse:
    try:
        return JSONResponse({"success": True, "events": read_events()})
    except OSError as exc:
        logger.error("Could not read events: %s", exc)
        return error_response("could not read events", 500)


@app.get("/api/camera/frame")
def camera_frame(camera: str = "", entity_id: str = "") -> Response:
    snapshot_path = None
    try:
        options = read_options()
        snapshot_path, _ = fetch_snapshot_for_source(
            camera.strip() or None,
            entity_id.strip() or None,
            options,
        )
        with open(snapshot_path, "rb") as file:
            content = file.read()

        return Response(
            content=content,
            media_type="image/jpeg",
            headers={"Cache-Control": "no-store"},
        )
    except ValueError as exc:
        logger.error("%s", exc)
        return error_response(str(exc), 400)
    except requests.Timeout:
        logger.error("Snapshot preview timeout")
        return JSONResponse({"success": False, "error": "snapshot timeout"})
    except requests.HTTPError as exc:
        logger.error("Snapshot preview HTTP error: %s", exc)
        return upstream_error_response(exc)
    except requests.RequestException as exc:
        logger.error("Snapshot preview network error: %s", exc)
        return JSONResponse({"success": False, "error": "snapshot network error", "details": str(exc)})
    finally:
        cleanup_file(snapshot_path)


@app.post("/api/config")
async def update_config(request: Request) -> JSONResponse:
    try:
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return error_response("invalid JSON", 400)

        if not isinstance(body, dict):
            return error_response("invalid JSON body", 400)

        config = save_options(body)
        logger.info("Configuration saved")
        return JSONResponse({"success": True, "config": config})
    except ValueError as exc:
        logger.error("%s", exc)
        return error_response(str(exc), 400)
    except OSError as exc:
        logger.error("Could not save config: %s", exc)
        return error_response("could not save config", 500)


@app.post("/api/test-ai")
async def test_ai(request: Request) -> JSONResponse:
    try:
        options = read_options()
        try:
            body = await request.json()
        except json.JSONDecodeError:
            body = {}
        if isinstance(body, dict):
            options = merge_user_options(options, body)
            normalize_options(options)
        validate_ai_options(options)
        result = call_ai_text(options)
        return JSONResponse(
            {
                "success": True,
                "message": "AI API reachable",
                "result": result,
            }
        )
    except ValueError as exc:
        logger.error("%s", exc)
        return error_response(str(exc), 400)
    except requests.Timeout:
        logger.error("AI API test timeout")
        return JSONResponse({"success": False, "error": "AI API timeout"})
    except requests.HTTPError as exc:
        logger.error("AI API provider error: %s", exc)
        return provider_error_response(exc)
    except requests.RequestException as exc:
        logger.error("AI API test network error: %s", exc)
        return JSONResponse({"success": False, "error": "AI API network error", "details": str(exc)})
    except Exception:
        logger.exception("Unexpected AI API test error")
        return error_response("internal error", 500)


@app.post("/api/test-telegram")
async def test_telegram(request: Request) -> JSONResponse:
    try:
        options = read_options()
        try:
            body = await request.json()
        except json.JSONDecodeError:
            body = {}
        if isinstance(body, dict):
            options = merge_user_options(options, body)
            normalize_options(options)
        validate_telegram_options(options)
        send_telegram_text("Simple AI Vision Telegram test OK.", options)
        return JSONResponse({"success": True, "message": "Telegram message sent"})
    except ValueError as exc:
        logger.error("%s", exc)
        return error_response(str(exc), 400)
    except requests.Timeout:
        logger.error("Telegram test timeout")
        return JSONResponse({"success": False, "error": "Telegram timeout"})
    except requests.HTTPError as exc:
        logger.error("Telegram API error: %s", exc)
        return upstream_error_response(exc)
    except requests.RequestException as exc:
        logger.error("Telegram test network error: %s", exc)
        return JSONResponse({"success": False, "error": "Telegram network error", "details": str(exc)})
    except Exception:
        logger.exception("Unexpected Telegram test error")
        return error_response("internal error", 500)


@app.post("/analyze")
async def analyze(request: Request) -> JSONResponse:
    snapshot_path = None
    event_camera = ""
    try:
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return error_response("invalid JSON", 400)

        if not isinstance(body, dict):
            return error_response("invalid JSON body", 400)

        options = load_options()
        camera_value = str(body.get("camera", "")).strip()
        entity_value = str(body.get("entity_id", "")).strip()
        event_camera = camera_value or entity_value or "unknown"
        logger.info("Analyze request camera=%s entity_id=%s", camera_value, entity_value)
        saved_camera = find_saved_camera(
            options,
            camera_value or None,
            entity_value or None,
        )
        if saved_camera and saved_camera.get("enabled") is False:
            camera_name = saved_camera.get("src") or saved_camera.get("entity_id") or "camera"
            record_event(camera_name, "", "disabled")
            logger.info("Skipping disabled camera=%s", camera_name)
            return JSONResponse(
                {
                    "success": True,
                    "skipped": True,
                    "reason": "camera disabled",
                    "camera": camera_name,
                }
            )

        snapshot_path, camera = fetch_snapshot_for_source(
            camera_value or None,
            entity_value or None,
            options,
        )
        event_camera = camera
        data_url = image_to_data_url(snapshot_path)
        analysis = call_ai(data_url, options)
        keyword = matched_keyword(analysis, options["keyword_match"])
        matched = bool(keyword)

        if matched:
            try:
                send_telegram(camera, analysis, snapshot_path, options)
            except requests.RequestException as exc:
                record_event(camera, analysis, "telegram_error", keyword, str(exc))
                raise
            record_event(camera, analysis, "sent", keyword)
            logger.info("Telegram sent for camera=%s keyword=%s", camera, keyword)
        else:
            record_event(camera, analysis, "no_match")
            logger.info("No keyword match for camera=%s", camera)

        return JSONResponse(
            {
                "success": True,
                "matched": matched,
                "matched_keyword": keyword,
                "analysis": analysis,
            }
        )

    except ValueError as exc:
        logger.error("%s", exc)
        record_event(event_camera or "unknown", "", "config_error", error=str(exc))
        return error_response(str(exc), 400)
    except requests.Timeout:
        logger.error("Network timeout")
        record_event(event_camera or "unknown", "", "timeout", error="network timeout")
        return JSONResponse({"success": False, "error": "network timeout"})
    except requests.HTTPError as exc:
        logger.error("Upstream HTTP error: %s", exc)
        record_event(event_camera or "unknown", "", "upstream_error", error=str(exc))
        return upstream_error_response(exc)
    except requests.RequestException as exc:
        logger.error("Network error: %s", exc)
        record_event(event_camera or "unknown", "", "network_error", error=str(exc))
        return JSONResponse({"success": False, "error": "network error", "details": str(exc)})
    except Exception as exc:
        logger.exception("Unexpected error")
        record_event(event_camera or "unknown", "", "internal_error", error=str(exc))
        return error_response("internal error", 500)
    finally:
        cleanup_file(snapshot_path)
