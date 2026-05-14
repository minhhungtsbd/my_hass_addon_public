import base64
import json
import logging
import os
import re
import tempfile
from typing import Any

import requests
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse


OPTIONS_PATH = "/data/options.json"
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
      grid-template-columns: 1fr auto auto;
      gap: 8px;
      margin-bottom: 8px;
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
      .grid, .camera-row { grid-template-columns: 1fr; }
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

    <section class="panel">
      <h2>Core Settings</h2>
      <div class="grid">
        <div>
          <label for="go2rtc_url">go2rtc URL</label>
          <input id="go2rtc_url" autocomplete="off" placeholder="http://192.168.1.101:1984 hoặc http://homeassistant-hung.local:1984">
          <div class="hint">Chỉ nhập base URL, không nhập <code>/api/frame.jpeg?src=...</code>.</div>
        </div>
        <div>
          <label for="ai_base_url">AI Base URL</label>
          <input id="ai_base_url" autocomplete="off" placeholder="https://api.openai.com/v1">
        </div>
        <div>
          <label for="ai_model">AI Model</label>
          <input id="ai_model" autocomplete="off" placeholder="gpt-4o-mini">
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

    <section class="panel">
      <h2>Cameras</h2>
      <div class="hint">Nhập đúng tên stream trong go2rtc, ví dụ <code>bep</code>. Addon sẽ gọi <code>{go2rtc_url}/api/frame.jpeg?src=bep</code>.</div>
      <div id="cameraList"></div>
      <div class="actions">
        <button class="secondary" id="addCameraBtn" type="button">Add Camera</button>
      </div>
    </section>

    <section class="panel">
      <h2>Last Test Result</h2>
      <pre id="result">{}</pre>
    </section>
  </main>

  <script>
    const fields = [
      "go2rtc_url", "ai_api_key", "ai_base_url", "ai_model",
      "telegram_bot_token", "telegram_chat_id", "prompt",
      "ai_timeout", "snapshot_timeout", "telegram_timeout"
    ];
    let cameras = [];

    function apiPath(path) {
      const base = window.location.pathname.endsWith("/")
        ? window.location.pathname
        : window.location.pathname + "/";
      return base + path.replace(/^\/+/, "");
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
          data = await response.json();
        } catch (err) {
          data = {success: false, error: "invalid JSON response"};
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
      payload.cameras = cameras.map(v => v.trim()).filter(Boolean);
      return payload;
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
        const row = document.createElement("div");
        row.className = "camera-row";
        const input = document.createElement("input");
        input.value = camera;
        input.placeholder = "bep";
        input.addEventListener("input", () => cameras[index] = input.value);

        const test = document.createElement("button");
        test.className = "secondary";
        test.type = "button";
        test.textContent = "Test";
        test.addEventListener("click", () => testCamera(input.value));

        const remove = document.createElement("button");
        remove.className = "danger";
        remove.type = "button";
        remove.textContent = "Remove";
        remove.addEventListener("click", () => {
          cameras.splice(index, 1);
          renderCameras();
        });

        row.append(input, test, remove);
        list.append(row);
      });
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
      const name = (camera || "").trim();
      if (!name) {
        document.getElementById("result").textContent = "Camera name is required.";
        return;
      }
      document.getElementById("result").textContent = "Running camera test...";
      try {
        const {data} = await requestJson("analyze", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({camera: name})
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
    document.getElementById("saveBtn").addEventListener("click", saveConfig);
    document.getElementById("testAiBtn").addEventListener("click", testAiApi);
    document.getElementById("addCameraBtn").addEventListener("click", () => {
      cameras.push("");
      renderCameras();
    });
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

    if os.path.exists(OPTIONS_PATH):
        with open(OPTIONS_PATH, "r", encoding="utf-8") as file:
            data = json.load(file)
        options.update(data)

    normalize_options(options)
    return options


def load_options() -> dict[str, Any]:
    options = read_options()
    validate_options(options)
    return options


def save_options(options: dict[str, Any]) -> dict[str, Any]:
    current = read_options()
    current.update(options)
    normalize_options(current)
    validate_options(current)

    os.makedirs(os.path.dirname(OPTIONS_PATH), exist_ok=True)
    tmp_path = f"{OPTIONS_PATH}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as file:
        json.dump(current, file, ensure_ascii=False, indent=2)
    os.replace(tmp_path, OPTIONS_PATH)
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
    options["cameras"] = [
        str(item).strip()
        for item in options.get("cameras", [])
        if str(item).strip()
    ]

    for key in ("ai_timeout", "snapshot_timeout", "telegram_timeout"):
        try:
            options[key] = int(options.get(key, 1))
        except (TypeError, ValueError):
            options[key] = 1


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

    if not isinstance(options.get("keyword_match"), list):
        raise ValueError("keyword_match must be a list")

    if not isinstance(options.get("cameras"), list):
        raise ValueError("cameras must be a list")

    for camera in options["cameras"]:
        validate_camera(camera)

    for key in ("ai_timeout", "snapshot_timeout", "telegram_timeout"):
        try:
            options[key] = int(options[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be an integer") from exc
        if options[key] < 1:
            raise ValueError(f"{key} must be greater than 0")


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
    }
    headers = {
        "Authorization": f"Bearer {options['ai_api_key']}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=options["ai_timeout"],
    )
    response.raise_for_status()
    data = response.json()
    return parse_ai_content(data)


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
    }
    headers = {
        "Authorization": f"Bearer {options['ai_api_key']}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=options["ai_timeout"],
    )
    response.raise_for_status()
    return parse_ai_content(response.json())


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
            options.update(body)
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
        return error_response("AI API timeout", 504)
    except requests.RequestException as exc:
        logger.error("AI API test network error: %s", exc)
        return error_response("AI API network error", 502)
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
        return error_response("network timeout", 504)
    except requests.RequestException as exc:
        logger.error("Network error: %s", exc)
        return error_response("network error", 502)
    except Exception as exc:
        logger.exception("Unexpected error")
        return error_response("internal error", 500)
    finally:
        cleanup_file(snapshot_path)
