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

from ui import INDEX_HTML


UI_OPTIONS_PATH = "/data/simple_ai_vision_config.json"
EVENT_LOG_PATH = "/data/simple_ai_vision_events.jsonl"
DEFAULT_PROMPT = (
    "B\u1ea1n \u0111ang ph\u00e2n t\u00edch \u1ea3nh camera an ninh.\n"
    "Ch\u1ec9 m\u00f4 t\u1ea3 c\u00e1c s\u1ef1 ki\u1ec7n quan tr\u1ecdng li\u00ean quan \u0111\u1ebfn an ninh.\n"
    "N\u1ebfu kh\u00f4ng c\u00f3 g\u00ec quan tr\u1ecdng h\u00e3y tr\u1ea3 l\u1eddi NORMAL."
)
DEFAULT_KEYWORDS = ["person", "human", "stranger", "fire", "smoke", "ng\u01b0\u1eddi", "ch\u00e1y"]
CAMERA_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")


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
        "frigate_url": "",
        "go2rtc_host_url": "",
        "frigate_host_url": "",
        "ai_api_key": "",
        "ai_base_url": "https://api.openai.com/v1",
        "ai_model": "gpt-4o-mini",
        "telegram_bot_token": "",
        "telegram_chat_id": "",
        "prompt": DEFAULT_PROMPT,
        "prompt_profiles": [],
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

    if not isinstance(options.get("prompt_profiles"), list):
        options["prompt_profiles"] = []
    options["prompt_profiles"] = normalize_prompt_profiles(options.get("prompt_profiles", []))

    for key in ("ai_timeout", "snapshot_timeout", "telegram_timeout"):
        try:
            options[key] = int(options.get(key, 1))
        except (TypeError, ValueError):
            options[key] = 1



def normalize_camera_list(cameras: list[Any]) -> list[dict[str, str]]:
    normalized = []
    for camera in cameras:
        if isinstance(camera, str):
            item = {"enabled": True, "name": "", "src": camera.strip(), "prompt_profile": ""}
        elif isinstance(camera, dict):
            item = {
                "enabled": camera.get("enabled") is not False,
                "name": str(camera.get("name", "")).strip(),
                "src": str(camera.get("src", "")).strip(),
                "prompt_profile": str(camera.get("prompt_profile", "")).strip(),
            }
        else:
            continue

        if item["name"] or item["src"]:
            normalized.append(item)

    return normalized


def normalize_prompt_profiles(profiles: list[Any]) -> list[dict[str, str]]:
    normalized = []
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        item = {
            "title": str(profile.get("title", "")).strip(),
            "prompt": str(profile.get("prompt", "")).strip(),
        }
        if item["title"] or item["prompt"]:
            normalized.append(item)
    return normalized


def validate_saved_options(options: dict[str, Any]) -> None:
    if not isinstance(options.get("keyword_match"), list):
        raise ValueError("keyword_match must be a list")

    if not isinstance(options.get("cameras"), list):
        raise ValueError("cameras must be a list")

    if not isinstance(options.get("prompt_profiles"), list):
        raise ValueError("prompt_profiles must be a list")

    prompt_titles = set()
    for profile in options["prompt_profiles"]:
        if not isinstance(profile, dict):
            raise ValueError("prompt profile entries must be objects")
        title = str(profile.get("title", "")).strip()
        prompt = str(profile.get("prompt", "")).strip()
        if prompt and not title:
            raise ValueError("prompt profile title is required")
        if title and not prompt:
            raise ValueError("prompt profile prompt is required")
        if title in prompt_titles:
            raise ValueError(f"duplicate prompt profile: {title}")
        if title:
            prompt_titles.add(title)

    for camera in options["cameras"]:
        if not isinstance(camera, dict):
            raise ValueError("camera entries must be objects")
        if camera.get("src"):
            validate_camera(camera["src"])
        elif camera.get("name"):
            raise ValueError("go2rtc src is required for each camera")
        if camera.get("prompt_profile") and camera["prompt_profile"] not in prompt_titles:
            raise ValueError(f"unknown prompt profile: {camera['prompt_profile']}")

    for key in ("ai_timeout", "snapshot_timeout", "telegram_timeout"):
        try:
            options[key] = int(options[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be an integer") from exc
        if options[key] < 1:
            raise ValueError(f"{key} must be greater than 0")

def find_saved_camera(
    options: dict[str, Any],
    camera: str | None,
) -> dict[str, str] | None:
    for item in options.get("cameras", []):
        if not isinstance(item, dict):
            continue
        if camera and item.get("src") == camera:
            return item
    return None


def prompt_for_camera(camera: dict[str, str] | None, options: dict[str, Any]) -> str:
    profile_title = str((camera or {}).get("prompt_profile", "")).strip()
    if profile_title:
        for profile in options.get("prompt_profiles", []):
            if not isinstance(profile, dict):
                continue
            if str(profile.get("title", "")).strip() == profile_title:
                prompt = str(profile.get("prompt", "")).strip()
                if prompt:
                    return prompt
    return str(options.get("prompt", DEFAULT_PROMPT)).strip() or DEFAULT_PROMPT


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


def resolve_go2rtc_url(options: dict[str, Any]) -> str:
    base_url = str(options.get("go2rtc_url", "")).strip().rstrip("/")
    if base_url:
        return base_url

    timeout = max(1, min(int(options.get("snapshot_timeout", 10)), 5))
    for candidate in frigate_go2rtc_candidates(options):
        try:
            request_go2rtc_streams(candidate, timeout)
            logger.info("Using Frigate go2rtc URL=%s", candidate)
            return candidate
        except (ValueError, requests.RequestException) as exc:
            logger.info("Frigate go2rtc snapshot candidate failed url=%s error=%s", candidate, exc)

    raise ValueError("go2rtc_url is required")


def resolve_frigate_api_url(options: dict[str, Any]) -> str:
    timeout = max(1, min(int(options.get("snapshot_timeout", 10)), 5))
    for candidate in frigate_api_candidates(options):
        try:
            request_frigate_config_streams(candidate, timeout)
            logger.info("Using Frigate API URL=%s", candidate)
            return candidate
        except (ValueError, requests.RequestException) as exc:
            logger.info("Frigate API snapshot candidate failed url=%s error=%s", candidate, exc)

    raise ValueError("frigate_url is required when go2rtc is unavailable")


def write_snapshot_file(camera: str, content: bytes) -> str:
    tmp = tempfile.NamedTemporaryFile(
        mode="wb",
        suffix=".jpg",
        prefix=f"simple_ai_vision_{camera}_",
        dir="/tmp",
        delete=False,
    )
    with tmp:
        tmp.write(content)

    return tmp.name


def validate_image_response(response: requests.Response, error: str) -> None:
    content_type = response.headers.get("content-type", "")
    if "image" not in content_type and not response.content.startswith(b"\xff\xd8"):
        raise ValueError(error)


def fetch_snapshot(camera: str, options: dict[str, Any]) -> str:
    logger.info("Fetching snapshot for camera=%s", camera)
    base_url = resolve_go2rtc_url(options)
    url = f"{base_url}/api/frame.jpeg"

    response = requests.get(
        url,
        params={"src": camera},
        timeout=options["snapshot_timeout"],
    )
    response.raise_for_status()
    validate_image_response(response, "snapshot response is not a JPEG image")

    return write_snapshot_file(camera, response.content)


def fetch_frigate_snapshot(camera: str, options: dict[str, Any]) -> str:
    logger.info("Fetching Frigate latest frame for camera=%s", camera)
    base_url = resolve_frigate_api_url(options)
    response = requests.get(
        f"{base_url}/api/{camera}/latest.jpg",
        timeout=options["snapshot_timeout"],
    )
    response.raise_for_status()
    validate_image_response(response, "Frigate latest frame response is not an image")

    return write_snapshot_file(camera, response.content)


def fetch_snapshot_with_fallback(camera: str, options: dict[str, Any]) -> str:
    try:
        return fetch_snapshot(camera, options)
    except (ValueError, requests.RequestException) as exc:
        if not frigate_api_candidates(options):
            raise
        logger.info("go2rtc snapshot failed, trying Frigate latest frame camera=%s error=%s", camera, exc)
        return fetch_frigate_snapshot(camera, options)


def fetch_camera_snapshot(camera: str, options: dict[str, Any]) -> tuple[str, str]:
    camera_name = validate_camera(camera)
    return fetch_snapshot_with_fallback(camera_name, options), camera_name


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


def parse_go2rtc_streams_payload(data: Any) -> list[dict[str, str]]:
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


def request_go2rtc_streams(base_url: str, timeout: int) -> list[dict[str, str]]:
    response = requests.get(
        f"{base_url.rstrip('/')}/api/streams",
        timeout=timeout,
    )
    response.raise_for_status()

    try:
        data = response.json()
    except ValueError as exc:
        raise ValueError("go2rtc returned non-JSON response") from exc

    return parse_go2rtc_streams_payload(data)


def parse_frigate_config_streams(data: Any) -> list[dict[str, str]]:
    if not isinstance(data, dict):
        raise ValueError("Frigate returned invalid config payload")

    streams: dict[str, str] = {}
    go2rtc = data.get("go2rtc", {})
    if isinstance(go2rtc, dict) and isinstance(go2rtc.get("streams"), dict):
        for src in go2rtc["streams"]:
            name = str(src).strip()
            if name:
                streams[name] = name

    cameras = data.get("cameras", {})
    if isinstance(cameras, dict):
        for camera_name, camera_config in cameras.items():
            name = str(camera_name).strip()
            if not name:
                continue
            streams.setdefault(name, name)

    return [{"src": src, "name": name} for src, name in sorted(streams.items())]


def request_frigate_config_streams(base_url: str, timeout: int) -> list[dict[str, str]]:
    response = requests.get(
        f"{base_url.rstrip('/')}/api/config",
        timeout=timeout,
    )
    response.raise_for_status()

    try:
        data = response.json()
    except ValueError as exc:
        raise ValueError("Frigate returned non-JSON response") from exc

    return parse_frigate_config_streams(data)


def request_frigate_go2rtc_streams(base_url: str, timeout: int) -> list[dict[str, str]]:
    response = requests.get(
        f"{base_url.rstrip('/')}/api/go2rtc/streams",
        timeout=timeout,
    )
    response.raise_for_status()

    try:
        data = response.json()
    except ValueError as exc:
        raise ValueError("Frigate go2rtc API returned non-JSON response") from exc

    return parse_go2rtc_streams_payload(data)


def supervisor_frigate_hosts(timeout: int) -> list[str]:
    token = os.environ.get("SUPERVISOR_TOKEN", "")
    if not token:
        return []

    try:
        response = requests.get(
            "http://supervisor/addons",
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
    except (ValueError, requests.RequestException) as exc:
        logger.warning("Could not discover Frigate add-on from Supervisor: %s", exc)
        return []

    addons = []
    if isinstance(payload, dict):
        raw_addons = payload.get("data", {}).get("addons") if isinstance(payload.get("data"), dict) else payload.get("addons")
        if isinstance(raw_addons, list):
            addons = raw_addons

    hosts: list[str] = []
    for addon in addons:
        if not isinstance(addon, dict):
            continue
        slug = str(addon.get("slug") or addon.get("name") or "").strip()
        if "frigate" not in slug.lower():
            continue
        hostname = str(addon.get("hostname") or "").strip()
        for host in (hostname, slug.replace("_", "-"), slug):
            if host and host not in hosts:
                hosts.append(host)

    return hosts


def unique_urls(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for url in urls:
        clean = url.strip().rstrip("/")
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def frigate_go2rtc_candidates(options: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    configured = str(options.get("frigate_url", "")).strip().rstrip("/")
    if configured:
        match = re.match(r"^(https?://[^/:]+)(?::\d+)?", configured)
        if match:
            urls.append(f"{match.group(1)}:1984")

    for host in supervisor_frigate_hosts(3):
        urls.append(f"http://{host}:1984")

    urls.extend(
        [
            "http://ccab4aaf-frigate:1984",
            "http://ccab4aaf_frigate:1984",
            "http://frigate:1984",
        ]
    )
    return unique_urls(urls)


def frigate_api_candidates(options: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    configured = str(options.get("frigate_url", "")).strip().rstrip("/")
    if configured:
        urls.append(configured)

    for host in supervisor_frigate_hosts(3):
        urls.append(f"http://{host}:5000")

    urls.extend(
        [
            "http://ccab4aaf-frigate:5000",
            "http://ccab4aaf_frigate:5000",
            "http://frigate:5000",
        ]
    )
    return unique_urls(urls)


def get_go2rtc_streams(options: dict[str, Any]) -> dict[str, Any]:
    timeout = int(options.get("snapshot_timeout", 10))
    base_url = str(options.get("go2rtc_url", "")).strip().rstrip("/")
    last_error = "go2rtc_url is required"
    if base_url:
        try:
            return {
                "streams": request_go2rtc_streams(base_url, timeout),
                "go2rtc_url": base_url,
                "source": "go2rtc",
            }
        except (ValueError, requests.RequestException) as exc:
            last_error = str(exc)
            logger.info("Configured go2rtc failed url=%s error=%s", base_url, exc)

    for candidate in frigate_go2rtc_candidates(options):
        try:
            streams = request_go2rtc_streams(candidate, timeout)
            return {
                "streams": streams,
                "go2rtc_url": candidate,
                "source": "Frigate go2rtc",
            }
        except (ValueError, requests.RequestException) as exc:
            last_error = str(exc)
            logger.info("Frigate go2rtc candidate failed url=%s error=%s", candidate, exc)

    for candidate in frigate_api_candidates(options):
        try:
            streams = request_frigate_go2rtc_streams(candidate, timeout)
            return {
                "streams": streams,
                "frigate_url": candidate,
                "source": "Frigate go2rtc proxy",
            }
        except (ValueError, requests.RequestException) as exc:
            last_error = str(exc)
            logger.info("Frigate go2rtc proxy candidate failed url=%s error=%s", candidate, exc)

    for candidate in frigate_api_candidates(options):
        try:
            streams = request_frigate_config_streams(candidate, timeout)
            return {
                "streams": streams,
                "frigate_url": candidate,
                "source": "Frigate config",
            }
        except (ValueError, requests.RequestException) as exc:
            last_error = str(exc)
            logger.info("Frigate API candidate failed url=%s error=%s", candidate, exc)

    raise ValueError(f"could not load go2rtc or Frigate streams: {last_error}")


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
        if str(event.get("status", "")) == "disabled":
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


@app.get("/api/go2rtc/streams")
def go2rtc_streams(go2rtc_url: str = "", frigate_url: str = "") -> JSONResponse:
    try:
        options = read_options()
        if go2rtc_url.strip():
            options["go2rtc_url"] = go2rtc_url.strip()
        if frigate_url.strip():
            options["frigate_url"] = frigate_url.strip()
        payload = get_go2rtc_streams(options)
        payload["success"] = True
        return JSONResponse(payload)
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
def camera_frame(camera: str = "") -> Response:
    snapshot_path = None
    try:
        options = read_options()
        snapshot_path, _ = fetch_camera_snapshot(camera.strip(), options)
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
        event_camera = camera_value or "unknown"
        logger.info("Analyze request camera=%s", camera_value)
        saved_camera = find_saved_camera(
            options,
            camera_value or None,
        )
        if options.get("cameras") and not saved_camera:
            logger.info("Skipping unknown camera=%s", camera_value)
            return JSONResponse(
                {
                    "success": True,
                    "skipped": True,
                    "reason": "camera not configured",
                    "camera": camera_value,
                }
            )
        if saved_camera and saved_camera.get("enabled") is False:
            camera_name = saved_camera.get("src") or "camera"
            logger.info("Skipping disabled camera=%s", camera_name)
            return JSONResponse(
                {
                    "success": True,
                    "skipped": True,
                    "reason": "camera disabled",
                    "camera": camera_name,
                }
            )

        snapshot_path, camera = fetch_camera_snapshot(camera_value, options)
        event_camera = camera
        data_url = image_to_data_url(snapshot_path)
        options["prompt"] = prompt_for_camera(saved_camera, options)
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
