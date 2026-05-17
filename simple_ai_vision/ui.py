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
    input, textarea, select {
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
    .camera-head,
    .camera-row {
      --camera-grid: 42px minmax(120px, .9fr) minmax(130px, .9fr) minmax(160px, 1fr) max-content;
      display: grid;
      grid-template-columns: var(--camera-grid);
      gap: 6px;
      align-items: center;
    }
    .camera-head {
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      margin-bottom: 6px;
    }
    .camera-row {
      margin-bottom: 8px;
    }
    .profile-list {
      display: grid;
      margin-top: 14px;
    }
    .profile-head,
    .profile-item {
      align-items: start;
      border-bottom: 1px solid var(--line);
      display: grid;
      gap: 12px;
      grid-template-columns: minmax(120px, .45fr) minmax(220px, 1fr) max-content;
      padding: 10px 0;
    }
    .profile-head {
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      padding-top: 0;
    }
    .profile-item-title {
      font-weight: 750;
      overflow-wrap: anywhere;
    }
    .profile-preview {
      color: var(--muted);
      margin: 0;
      max-height: 72px;
      overflow: hidden;
      white-space: pre-wrap;
    }
    .camera-head > div,
    .camera-row > div,
    .camera-row > label {
      min-width: 0;
    }
    .camera-row button {
      padding: 9px 10px;
      white-space: nowrap;
    }
    .action-menu {
      position: relative;
      justify-self: end;
    }
    .action-menu summary {
      cursor: pointer;
      list-style: none;
      border: 1px solid var(--accent);
      color: var(--accent);
      background: transparent;
      border-radius: 6px;
      padding: 10px 14px;
      font-weight: 700;
      line-height: 1;
      user-select: none;
    }
    .action-menu summary::-webkit-details-marker {
      display: none;
    }
    .action-menu summary::after {
      content: " ▾";
      font-size: 11px;
    }
    .action-menu[open] summary::after {
      content: " ▴";
    }
    .action-menu-items {
      position: absolute;
      right: 0;
      top: calc(100% + 6px);
      z-index: 10;
      min-width: 150px;
      padding: 6px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: 0 12px 24px rgba(0, 0, 0, .3);
      display: grid;
      gap: 6px;
    }
    .action-menu-items button {
      width: 100%;
      text-align: left;
    }
    .monitor-toggle {
      display: flex;
      align-items: center;
      justify-content: center;
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
    .viewer-body img {
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
    .status.warn { color: var(--muted); }
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
        gap: 10px;
      }
      .camera-head,
      .camera-row {
        --camera-grid: 1fr;
      }
      .camera-row button { padding: 10px 14px; }
      .action-menu,
      .action-menu summary {
        width: 100%;
      }
      .action-menu-items {
        position: static;
        margin-top: 8px;
      }
      .camera-head { display: none; }
      .profile-head { display: none; }
      .profile-item { grid-template-columns: 1fr; }
      .mobile-label { display: block; }
      .viewer {
        width: calc(100vw - 12px);
        max-height: calc(100vh - 12px);
      }
      .viewer-head {
        align-items: stretch;
        flex-direction: column;
      }
      .viewer-body img {
        height: min(56vh, 420px);
      }
      .live-grid { grid-template-columns: 1fr; }
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
      <button class="tab-btn" data-tab="promptsPanel" type="button">Prompt Profiles</button>
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
          <label for="frigate_url">Frigate URL</label>
          <input id="frigate_url" autocomplete="off" placeholder="Optional, e.g. http://ccab4aaf-frigate:5000">
          <div class="hint">Used to load cameras from the Frigate add-on when no standalone go2rtc URL is configured.</div>
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
          <label for="prompt">Default Prompt</label>
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
        <button class="secondary" id="testTelegramBtn" type="button">Test Telegram</button>
        <span id="configStatus" class="status"></span>
      </div>
    </section>

    <section class="panel tab-panel active" id="camerasPanel">
      <h2>Cameras</h2>
      <div class="hint">Nhập đúng tên stream trong go2rtc, ví dụ <code>bep</code>. Addon sẽ gọi <code>{go2rtc_url}/api/frame.jpeg?src=bep</code>.</div>
      <div class="entity-picker">
        <select id="go2rtcStreamSelect">
          <option value="">Load go2rtc streams...</option>
        </select>
        <button class="secondary" id="loadStreamsBtn" type="button">Load go2rtc</button>
        <button class="secondary" id="addStreamBtn" type="button">Add Stream</button>
      </div>
      <div id="streamStatus" class="status"></div>
      <div class="camera-head">
        <div>Monitor</div>
        <div>Name</div>
        <div>go2rtc src</div>
        <div>Prompt</div>
        <div>Actions</div>
      </div>
      <div id="cameraList"></div>
      <div class="actions">
        <button class="secondary" id="addCameraBtn" type="button">Add Camera</button>
        <button class="secondary" id="saveCamerasBtn" type="button">Save Cameras</button>
        <span id="cameraStatus" class="status"></span>
      </div>
    </section>

    <section class="panel tab-panel" id="promptsPanel">
      <h2>Prompt Profiles</h2>
      <div class="hint">Tao prompt theo nhom moi truong, vi du Cong, Bep, Thu cung. Moi camera co the chon mot prompt profile rieng.</div>
      <div id="promptProfileList"></div>
      <div class="actions">
        <button class="secondary" id="addPromptProfileBtn" type="button">Add Prompt</button>
        <button class="secondary" id="savePromptProfilesBtn" type="button">Save Prompts</button>
        <span id="promptStatus" class="status"></span>
      </div>
    </section>

    <section class="panel tab-panel" id="livePanel">
      <h2>Live</h2>
      <div class="grid">
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

    <dialog class="viewer" id="promptProfileDialog">
      <div class="viewer-box">
        <div class="viewer-head">
          <div class="viewer-title" id="promptDialogTitle">Prompt Profile</div>
          <div class="actions">
            <button class="secondary" id="cancelPromptProfileBtn" type="button">Cancel</button>
            <button id="savePromptProfileBtn" type="button">Save</button>
          </div>
        </div>
        <div class="grid">
          <div class="full">
            <label for="promptProfileTitle">Title</label>
            <input id="promptProfileTitle" autocomplete="off" placeholder="Gate, Kitchen, Pets">
          </div>
          <div class="full">
            <label for="promptProfilePrompt">Prompt</label>
            <textarea id="promptProfilePrompt" placeholder="Prompt for this camera group"></textarea>
          </div>
        </div>
        <div id="promptDialogStatus" class="status"></div>
      </div>
    </dialog>
  </main>

  <script>
    const fields = [
      "go2rtc_url", "frigate_url", "ai_api_key", "ai_base_url", "ai_model",
      "telegram_bot_token", "telegram_chat_id", "prompt",
      "ai_timeout", "snapshot_timeout", "telegram_timeout"
    ];
    let cameras = [];
    let promptProfiles = [];
    let editingPromptIndex = -1;
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

    function snapshotUrl(camera) {
      return apiPath(`api/camera/frame?camera=${encodeURIComponent(camera)}&_=${Date.now()}`);
    }

    function cameraFrameUrl(camera) {
      const item = normalizeCamera(camera);
      return snapshotUrl(item.src);
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
        camera.name || camera.src
      ));
      payload.prompt_profiles = promptProfiles.map(normalizePromptProfile).filter(profile => (
        profile.title || profile.prompt
      ));
      return payload;
    }

    function normalizePromptProfile(profile) {
      return {
        title: String(profile?.title || "").trim(),
        prompt: String(profile?.prompt || "").trim()
      };
    }

    function normalizeCamera(camera) {
      if (typeof camera === "string") {
        return {enabled: true, name: "", src: camera.trim(), prompt_profile: ""};
      }
      return {
        enabled: camera?.enabled !== false,
        name: String(camera?.name || "").trim(),
        src: String(camera?.src || "").trim(),
        prompt_profile: String(camera?.prompt_profile || "").trim()
      };
    }

    function cameraLabel(camera) {
      const item = normalizeCamera(camera);
      return item.name || item.src || "Camera";
    }

    function liveCameraItems() {
      const limitValue = document.getElementById("liveLimit")?.value.trim() || "";
      let items = cameras.map(normalizeCamera).filter(camera => camera.src);

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
        monitorWrap.append(monitorInput);

        const nameWrap = document.createElement("div");
        const nameLabel = document.createElement("div");
        nameLabel.className = "mobile-label";
        nameLabel.textContent = "Name";
        const nameInput = document.createElement("input");
        nameInput.value = item.name;
        nameInput.placeholder = "Display name";
        nameInput.addEventListener("input", () => cameras[index].name = nameInput.value);
        nameWrap.append(nameLabel, nameInput);

        const srcWrap = document.createElement("div");
        const srcLabel = document.createElement("div");
        srcLabel.className = "mobile-label";
        srcLabel.textContent = "go2rtc src";
        const srcInput = document.createElement("input");
        srcInput.value = item.src;
        srcInput.placeholder = "go2rtc src, e.g. bep";
        srcInput.addEventListener("input", () => cameras[index].src = srcInput.value);
        srcWrap.append(srcLabel, srcInput);

        const promptWrap = document.createElement("div");
        const promptLabel = document.createElement("div");
        promptLabel.className = "mobile-label";
        promptLabel.textContent = "Prompt";
        const promptSelect = document.createElement("select");
        const defaultOption = document.createElement("option");
        defaultOption.value = "";
        defaultOption.textContent = "Default Prompt";
        promptSelect.append(defaultOption);
        promptProfiles.map(normalizePromptProfile).filter(profile => profile.title).forEach(profile => {
          const option = document.createElement("option");
          option.value = profile.title;
          option.textContent = profile.title;
          promptSelect.append(option);
        });
        promptSelect.value = item.prompt_profile;
        promptSelect.addEventListener("change", () => cameras[index].prompt_profile = promptSelect.value);
        promptWrap.append(promptLabel, promptSelect);

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
        video.textContent = "Live";
        video.addEventListener("click", () => viewVideo(cameras[index], cameraLabel(cameras[index])));

        const remove = document.createElement("button");
        remove.className = "danger";
        remove.type = "button";
        remove.textContent = "Remove";
        remove.addEventListener("click", () => {
          cameras.splice(index, 1);
          renderCameras();
        });

        const actions = document.createElement("details");
        actions.className = "action-menu";
        const actionsSummary = document.createElement("summary");
        actionsSummary.textContent = "Actions";
        const actionsList = document.createElement("div");
        actionsList.className = "action-menu-items";
        actionsList.append(snapshot, video, test, remove);
        actions.append(actionsSummary, actionsList);

        row.append(monitorWrap, nameWrap, srcWrap, promptWrap, actions);
        list.append(row);
      });
      renderLiveCameras();
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
      if (item.src) return item;
      document.getElementById("result").textContent = "go2rtc src is required.";
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
      currentSnapshotCamera = item.src;
      const img = document.createElement("img");
      img.id = "snapshotImage";
      img.dataset.src = item.src;
      img.alt = `Snapshot ${label || item.src}`;
      img.src = cameraFrameUrl(item);
      showViewer(`Snapshot: ${label || item.src}`, img, img.src);
    }

    function viewVideo(camera, label = "") {
      const item = snapshotSourceOrError(camera);
      if (!item) return;
      currentSnapshotCamera = "";
      const img = document.createElement("img");
      img.id = "snapshotImage";
      img.dataset.src = item.src;
      img.alt = `Live snapshot ${label || item.src}`;
      img.src = cameraFrameUrl(item);
      currentSnapshotCamera = item.src;
      showViewer(`Live snapshot: ${label || item.src}`, img, img.src);
      viewerRefreshTimer = setInterval(refreshSnapshot, 1500);
    }

    function refreshSnapshot() {
      const img = document.getElementById("snapshotImage");
      if (!img) return;
      const src = img.dataset.src || "";
      img.src = snapshotUrl(src);
      currentViewerUrl = img.src;
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
        const params = new URLSearchParams();
        const currentGo2rtc = document.getElementById("go2rtc_url").value.trim();
        const currentFrigate = document.getElementById("frigate_url").value.trim();
        if (currentGo2rtc) params.set("go2rtc_url", currentGo2rtc);
        if (currentFrigate) params.set("frigate_url", currentFrigate);
        const path = `api/go2rtc/streams${params.toString() ? "?" + params.toString() : ""}`;
        const {response, data} = await requestJson(path, {}, 15000);
        if (!response.ok || !data.success) {
          setStatus("streamStatus", data.error || "Could not load go2rtc streams", "err");
          return;
        }
        renderGo2rtcStreams(data.streams || []);
        if (data.go2rtc_url) {
          document.getElementById("go2rtc_url").value = data.go2rtc_url;
        }
        if (data.frigate_url) {
          document.getElementById("frigate_url").value = data.frigate_url;
        }
        const source = data.source ? ` from ${data.source}` : "";
        setStatus("streamStatus", `Loaded ${(data.streams || []).length} stream(s)${source}`, "ok");
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
      cameras.push({enabled: true, name: src, src, prompt_profile: ""});
      renderCameras();
      setStatus("streamStatus", `Added go2rtc stream ${src}`, "ok");
    }

    function renderPromptProfiles() {
      const list = document.getElementById("promptProfileList");
      if (!list) return;
      list.innerHTML = "";
      promptProfiles = promptProfiles.map(normalizePromptProfile);
      list.className = "profile-list";
      if (!promptProfiles.length) {
        const empty = document.createElement("div");
        empty.className = "hint";
        empty.textContent = "No prompt profiles yet.";
        list.append(empty);
        return;
      }

      const header = document.createElement("div");
      header.className = "profile-head";
      header.innerHTML = "<div>Title</div><div>Prompt</div><div>Actions</div>";
      list.append(header);

      promptProfiles.forEach((profile, index) => {
        const row = document.createElement("div");
        row.className = "profile-item";

        const title = document.createElement("div");
        title.className = "profile-item-title";
        title.textContent = profile.title || "Untitled";

        const preview = document.createElement("pre");
        preview.className = "profile-preview";
        preview.textContent = profile.prompt || "No prompt text.";

        const actions = document.createElement("div");
        actions.className = "actions";
        const edit = document.createElement("button");
        edit.className = "secondary";
        edit.type = "button";
        edit.textContent = "Edit";
        edit.addEventListener("click", () => openPromptProfileDialog(index));
        const remove = document.createElement("button");
        remove.className = "danger";
        remove.type = "button";
        remove.textContent = "Remove";
        remove.addEventListener("click", () => {
          const removedTitle = promptProfiles[index].title;
          promptProfiles.splice(index, 1);
          cameras = cameras.map(camera => {
            const item = normalizeCamera(camera);
            if (item.prompt_profile === removedTitle) item.prompt_profile = "";
            return item;
          });
          renderPromptProfiles();
          renderCameras();
        });
        actions.append(edit, remove);

        row.append(title, preview, actions);
        list.append(row);
      });
    }

    function openPromptProfileDialog(index = -1) {
      editingPromptIndex = index;
      const profile = index >= 0 ? normalizePromptProfile(promptProfiles[index]) : {title: "", prompt: ""};
      document.getElementById("promptDialogTitle").textContent = index >= 0 ? "Edit Prompt Profile" : "Add Prompt Profile";
      document.getElementById("promptProfileTitle").value = profile.title;
      document.getElementById("promptProfilePrompt").value = profile.prompt;
      setStatus("promptDialogStatus", "", "");
      document.getElementById("promptProfileDialog").showModal();
    }

    function savePromptProfileFromDialog() {
      const title = document.getElementById("promptProfileTitle").value.trim();
      const prompt = document.getElementById("promptProfilePrompt").value.trim();
      if (!title || !prompt) {
        setStatus("promptDialogStatus", "Title and prompt are required.", "err");
        return;
      }
      const duplicate = promptProfiles
        .map(normalizePromptProfile)
        .some((profile, index) => index !== editingPromptIndex && profile.title === title);
      if (duplicate) {
        setStatus("promptDialogStatus", "Prompt title already exists.", "err");
        return;
      }

      const previousTitle = editingPromptIndex >= 0 ? normalizePromptProfile(promptProfiles[editingPromptIndex]).title : "";
      const nextProfile = {title, prompt};
      if (editingPromptIndex >= 0) {
        promptProfiles[editingPromptIndex] = nextProfile;
        if (previousTitle && previousTitle !== title) {
          cameras = cameras.map(camera => {
            const item = normalizeCamera(camera);
            if (item.prompt_profile === previousTitle) item.prompt_profile = title;
            return item;
          });
        }
      } else {
        promptProfiles.push(nextProfile);
      }

      document.getElementById("promptProfileDialog").close();
      renderPromptProfiles();
      renderCameras();
      setStatus("promptStatus", "Unsaved changes", "warn");
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
        const srcLabel = document.createElement("span");
        srcLabel.textContent = camera.src;
        title.append(name, srcLabel);

        const media = document.createElement("img");
        media.dataset.src = camera.src;
        media.src = snapshotUrl(camera.src);
        media.alt = `Live snapshot ${cameraLabel(camera)}`;
        media.title = `Live ${cameraLabel(camera)}`;

        item.append(title, media);
        grid.append(item);
      });

      liveRefreshTimer = setInterval(() => {
        document.querySelectorAll("#liveGrid img").forEach(img => {
          const src = img.dataset.src || "";
          img.src = snapshotUrl(src);
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
        document.getElementById("keyword_match").value = (config.keyword_match || []).join("\n");
        cameras = config.cameras || [];
        promptProfiles = config.prompt_profiles || [];
        renderPromptProfiles();
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
        promptProfiles = data.config.prompt_profiles || [];
        renderPromptProfiles();
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
        const {data} = await requestJson("analyze", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({camera: item.src})
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
    document.getElementById("savePromptProfilesBtn").addEventListener("click", () => saveConfig("promptStatus"));
    document.getElementById("addPromptProfileBtn").addEventListener("click", () => openPromptProfileDialog());
    document.getElementById("savePromptProfileBtn").addEventListener("click", savePromptProfileFromDialog);
    document.getElementById("cancelPromptProfileBtn").addEventListener("click", () => {
      document.getElementById("promptProfileDialog").close();
    });
    document.getElementById("loadStreamsBtn").addEventListener("click", loadGo2rtcStreams);
    document.getElementById("addStreamBtn").addEventListener("click", addSelectedStream);
    document.getElementById("refreshLiveBtn").addEventListener("click", renderLiveCameras);
    document.getElementById("liveLimit").addEventListener("input", renderLiveCameras);
    document.getElementById("refreshEventsBtn").addEventListener("click", loadEvents);
    document.getElementById("addCameraBtn").addEventListener("click", () => {
      cameras.push({enabled: true, name: "", src: "", prompt_profile: ""});
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
