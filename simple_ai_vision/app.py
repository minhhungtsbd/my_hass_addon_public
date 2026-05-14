import base64
import json
import logging
import os
import re
import tempfile
from typing import Any

import requests
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response


UI_OPTIONS_PATH = "/data/simple_ai_vision_config.json"
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
    .camera-row {
      display: grid;
      grid-template-columns: minmax(120px, 1fr) minmax(160px, 1.3fr) minmax(120px, 1fr) auto auto auto auto;
      gap: 8px;
      margin-bottom: 8px;
    }
    .entity-picker {
      display: grid;
      grid-template-columns: minmax(180px, 1fr) auto auto;
      gap: 8px;
      margin: 12px 0 14px;
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
      </div>
      <div class="actions">
        <button id="saveBtn" type="button">Save Configuration</button>
        <button class="secondary" id="testAiBtn" type="button">Test AI API</button>
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
      <div id="cameraList"></div>
      <div class="actions">
        <button class="secondary" id="addCameraBtn" type="button">Add Camera</button>
        <button class="secondary" id="saveCamerasBtn" type="button">Save Cameras</button>
      </div>
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
      "ai_timeout", "snapshot_timeout", "telegram_timeout"
    ];
    let cameras = [];
    let currentViewerUrl = "";
    let currentSnapshotCamera = "";

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
    }

    function buildGo2rtcUrl(camera, path, params = {}) {
      const base = document.getElementById("go2rtc_url").value.trim().replace(/\/+$/, "");
      const query = new URLSearchParams({src: camera, ...params});
      return `${base}${path}?${query.toString()}`;
    }

    function snapshotUrl(camera) {
      return apiPath(`api/camera/frame?camera=${encodeURIComponent(camera)}&_=${Date.now()}`);
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
      payload.keyword_match = linesToList(document.getElementById("keyword_match").value);
      payload.cameras = cameras.map(normalizeCamera).filter(camera => (
        camera.name || camera.entity_id || camera.src
      ));
      return payload;
    }

    function normalizeCamera(camera) {
      if (typeof camera === "string") {
        return {name: "", entity_id: "", src: camera.trim()};
      }
      return {
        name: String(camera?.name || "").trim(),
        entity_id: String(camera?.entity_id || "").trim(),
        src: String(camera?.src || "").trim()
      };
    }

    function cameraLabel(camera) {
      const item = normalizeCamera(camera);
      return item.name || item.entity_id || item.src || "Camera";
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

        const nameInput = document.createElement("input");
        nameInput.value = item.name;
        nameInput.placeholder = "Display name";
        nameInput.addEventListener("input", () => cameras[index].name = nameInput.value);

        const entityInput = document.createElement("input");
        entityInput.value = item.entity_id;
        entityInput.placeholder = "HA entity";
        entityInput.addEventListener("input", () => cameras[index].entity_id = entityInput.value);

        const srcInput = document.createElement("input");
        srcInput.value = item.src;
        srcInput.placeholder = "go2rtc src, e.g. bep";
        srcInput.addEventListener("input", () => cameras[index].src = srcInput.value);

        const test = document.createElement("button");
        test.className = "secondary";
        test.type = "button";
        test.textContent = "Test";
        test.addEventListener("click", () => testCamera(srcInput.value, cameraLabel(cameras[index])));

        const snapshot = document.createElement("button");
        snapshot.className = "secondary";
        snapshot.type = "button";
        snapshot.textContent = "Snapshot";
        snapshot.addEventListener("click", () => viewSnapshot(srcInput.value, cameraLabel(cameras[index])));

        const video = document.createElement("button");
        video.className = "secondary";
        video.type = "button";
        video.textContent = "Video";
        video.addEventListener("click", () => viewVideo(srcInput.value, cameraLabel(cameras[index])));

        const remove = document.createElement("button");
        remove.className = "danger";
        remove.type = "button";
        remove.textContent = "Remove";
        remove.addEventListener("click", () => {
          cameras.splice(index, 1);
          renderCameras();
        });

        row.append(nameInput, entityInput, srcInput, snapshot, video, test, remove);
        list.append(row);
      });
    }

    function cameraSrcOrError(camera) {
      const src = (camera || "").trim();
      if (!src) {
        document.getElementById("result").textContent = "go2rtc src is required.";
        return "";
      }
      return src;
    }

    function showViewer(title, content, openUrl) {
      currentViewerUrl = openUrl || "";
      document.getElementById("viewerTitle").textContent = title;
      const body = document.getElementById("viewerBody");
      body.innerHTML = "";
      body.append(content);
      document.getElementById("openViewerBtn").style.display = currentViewerUrl ? "" : "none";
      document.getElementById("refreshViewerBtn").style.display = currentSnapshotCamera ? "" : "none";
      document.getElementById("viewerDialog").showModal();
    }

    function viewSnapshot(camera, label = "") {
      const src = cameraSrcOrError(camera);
      if (!src) return;
      currentSnapshotCamera = src;
      const img = document.createElement("img");
      img.id = "snapshotImage";
      img.alt = `Snapshot ${label || src}`;
      img.src = snapshotUrl(src);
      showViewer(`Snapshot: ${label || src}`, img, img.src);
    }

    function viewVideo(camera, label = "") {
      const src = cameraSrcOrError(camera);
      if (!src) return;
      currentSnapshotCamera = "";
      const url = buildGo2rtcUrl(src, "/stream.html", {mode: "mse"});
      const frame = document.createElement("iframe");
      frame.src = url;
      frame.title = `Video ${label || src}`;
      frame.allow = "autoplay; fullscreen; picture-in-picture";
      showViewer(`Video: ${label || src}`, frame, url);
    }

    function refreshSnapshot() {
      if (!currentSnapshotCamera) return;
      const img = document.getElementById("snapshotImage");
      if (!img) return;
      img.src = snapshotUrl(currentSnapshotCamera);
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

    function addSelectedEntity() {
      const select = document.getElementById("haEntitySelect");
      const value = select.value.trim();
      if (!value) {
        setStatus("entityStatus", "Select an entity first, or use Add Camera for manual input.", "err");
        return;
      }
      const selected = select.selectedOptions[0];
      cameras.push({
        name: selected?.dataset.name || "",
        entity_id: value,
        src: ""
      });
      renderCameras();
      setStatus("entityStatus", `Added ${value}. Fill go2rtc src before testing.`, "ok");
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
        document.getElementById("keyword_match").value = (config.keyword_match || []).join("\n");
        cameras = config.cameras || [];
        renderCameras();
        setStatus("configStatus", "Loaded", "ok");
      } catch (err) {
        setStatus("configStatus", err.name === "AbortError" ? "Load timeout" : err.message, "err");
      }
    }

    async function saveConfig() {
      let payload;
      try {
        validateTimeoutInputs();
        payload = buildConfigPayload();
      } catch (err) {
        setStatus("configStatus", err.message, "err");
        return null;
      }

      try {
        setStatus("configStatus", "Saving...", "");
        const {response, data} = await requestJson("api/config", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(payload)
        }, 20000);
        if (!response.ok || !data.success) {
          setStatus("configStatus", data.error || "Save failed", "err");
          return null;
        }
        cameras = data.config.cameras || [];
        renderCameras();
        setStatus("configStatus", "Saved", "ok");
        return data.config;
      } catch (err) {
        setStatus("configStatus", err.name === "AbortError" ? "Save timeout" : err.message, "err");
        return null;
      }
    }

    async function testCamera(camera) {
      const src = cameraSrcOrError(camera);
      if (!src) return;
      document.getElementById("result").textContent = "Running camera test...";
      try {
        const {data} = await requestJson("analyze", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({camera: src})
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

    document.getElementById("reloadBtn").addEventListener("click", loadConfig);
    document.querySelectorAll(".tab-btn").forEach(button => {
      button.addEventListener("click", () => setActiveTab(button.dataset.tab));
    });
    document.getElementById("saveBtn").addEventListener("click", saveConfig);
    document.getElementById("testAiBtn").addEventListener("click", testAiApi);
    document.getElementById("saveCamerasBtn").addEventListener("click", saveConfig);
    document.getElementById("loadEntitiesBtn").addEventListener("click", loadHaEntities);
    document.getElementById("addEntityBtn").addEventListener("click", addSelectedEntity);
    document.getElementById("addCameraBtn").addEventListener("click", () => {
      cameras.push({name: "", entity_id: "", src: ""});
      renderCameras();
    });
    document.getElementById("closeViewerBtn").addEventListener("click", () => {
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
    for secret_key in ("ai_api_key", "telegram_bot_token"):
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


def normalize_camera_list(cameras: list[Any]) -> list[dict[str, str]]:
    normalized = []
    for camera in cameras:
        if isinstance(camera, str):
            item = {"name": "", "entity_id": "", "src": camera.strip()}
        elif isinstance(camera, dict):
            item = {
                "name": str(camera.get("name", "")).strip(),
                "entity_id": str(camera.get("entity_id", "")).strip(),
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
        elif camera.get("name") or camera.get("entity_id"):
            raise ValueError("go2rtc src is required for each camera")

    for key in ("ai_timeout", "snapshot_timeout", "telegram_timeout"):
        try:
            options[key] = int(options[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be an integer") from exc
        if options[key] < 1:
            raise ValueError(f"{key} must be greater than 0")


def validate_options(options: dict[str, Any]) -> None:
    required = [
        "go2rtc_url",
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


def validate_camera(camera: Any) -> str:
    if not isinstance(camera, str) or not camera.strip():
        raise ValueError("camera is required")

    camera = camera.strip()
    if not CAMERA_RE.fullmatch(camera):
        raise ValueError("invalid camera name")

    return camera


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
    logger.info("Checking keyword match")
    for keyword in keywords:
        pattern = str(keyword).strip()
        if not pattern:
            continue
        try:
            if re.search(pattern, analysis, flags=re.IGNORECASE):
                return True
        except re.error:
            if pattern.lower() in analysis.lower():
                return True
    return False


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


def cleanup_file(path: str | None) -> None:
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            logger.warning("Could not remove temp file: %s", path)


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


@app.get("/api/camera/frame")
def camera_frame(camera: str) -> Response:
    snapshot_path = None
    try:
        options = read_options()
        if not str(options.get("go2rtc_url", "")).strip():
            return error_response("go2rtc_url is required", 400)

        camera_name = validate_camera(camera)
        snapshot_path = fetch_snapshot(camera_name, options)
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


@app.post("/analyze")
async def analyze(request: Request) -> JSONResponse:
    snapshot_path = None
    try:
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return error_response("invalid JSON", 400)

        if not isinstance(body, dict):
            return error_response("invalid JSON body", 400)

        options = load_options()
        camera = validate_camera(body.get("camera"))

        snapshot_path = fetch_snapshot(camera, options)
        data_url = image_to_data_url(snapshot_path)
        analysis = call_ai(data_url, options)
        matched = keyword_matched(analysis, options["keyword_match"])

        if matched:
            send_telegram(camera, analysis, snapshot_path, options)
            logger.info("Telegram sent for camera=%s", camera)
        else:
            logger.info("No keyword match for camera=%s", camera)

        return JSONResponse(
            {
                "success": True,
                "matched": matched,
                "analysis": analysis,
            }
        )

    except ValueError as exc:
        logger.error("%s", exc)
        return error_response(str(exc), 400)
    except requests.Timeout:
        logger.error("Network timeout")
        return JSONResponse({"success": False, "error": "network timeout"})
    except requests.HTTPError as exc:
        logger.error("Upstream HTTP error: %s", exc)
        return upstream_error_response(exc)
    except requests.RequestException as exc:
        logger.error("Network error: %s", exc)
        return JSONResponse({"success": False, "error": "network error", "details": str(exc)})
    except Exception as exc:
        logger.exception("Unexpected error")
        return error_response("internal error", 500)
    finally:
        cleanup_file(snapshot_path)
