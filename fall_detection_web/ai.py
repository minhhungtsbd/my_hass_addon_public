"""AI verification (vision model) and Telegram alerting."""

from __future__ import annotations

import base64
import json
import logging
import time
from pathlib import Path
from typing import Any

import requests

from config import require_config

logger = logging.getLogger("fall_detection_web")

# Shared session for connection reuse
_session = requests.Session()
_session.headers.update({"User-Agent": "fall-detection-web/2.0"})


def image_to_data_url(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:image/jpeg;base64,{encoded}"


def chat_url(config: dict[str, Any]) -> str:
    base_url = str(config["ai_base_url"]).rstrip("/")
    if base_url.endswith("/chat/completions"):
        return base_url
    return f"{base_url}/chat/completions"


# ──────────────────────────────────────────────
# AI response parsers
# ──────────────────────────────────────────────

def parse_ai_content(data: dict[str, Any]) -> str:
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("invalid AI API response") from exc
    if isinstance(content, list):
        parts = [part.get("text", "") for part in content if isinstance(part, dict)]
        content = "\n".join(part for part in parts if part)
    return str(content).strip()


def _collect_choice_text(data: dict[str, Any], parts: list[str]) -> None:
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
        _collect_choice_text(data, parts)
    result = "".join(parts).strip()
    if not result:
        raise ValueError("AI API returned SSE response without text content")
    return result


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
            _collect_choice_text(data, parts)
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


# ──────────────────────────────────────────────
# Verdict parsing
# ──────────────────────────────────────────────

def strip_thinking_content(text: str) -> str:
    import re
    if not text:
        return ""
    # Strip <think>...</think> blocks
    cleaned = re.sub(r"(?i)<think>.*?</think>", "", text, flags=re.DOTALL)
    # Strip truncated open <think> blocks
    cleaned = re.sub(r"(?i)<think>.*$", "", cleaned, flags=re.DOTALL)
    # Strip lines starting with "Thought for " or "Thinking "
    lines = []
    for line in cleaned.splitlines():
        l_upper = line.strip().upper()
        if l_upper.startswith("THOUGHT FOR") or l_upper.startswith("THINKING"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def normalize_ai_result(content: str) -> str:
    cleaned = strip_thinking_content(content)
    upper = cleaned.upper()
    if "EMERGENCY" in upper:
        return "EMERGENCY"
    if "SAFE" in upper:
        return "SAFE"
    return "SAFE"


def short_text(value: str, limit: int = 20) -> str:
    value = " ".join(str(value).split())
    return value[:limit]


def parse_ai_verdict(content: str) -> tuple[str, str, str]:
    cleaned = strip_thinking_content(content)
    lines = [line.strip() for line in str(cleaned).splitlines() if line.strip()]
    result = ""
    description = ""

    if lines:
        first = lines[0].upper()
        if first == "EMERGENCY" or first.startswith("EMERGENCY"):
            result = "EMERGENCY"
        elif first == "SAFE" or first.startswith("SAFE"):
            result = "SAFE"

    if not result:
        result = normalize_ai_result(cleaned)

    for line in lines[1:]:
        cleaned_line = line
        for prefix in ("DESC:", "DESCRIPTION:", "MÔ TẢ:", "MO TA:", "-", "2."):
            if cleaned_line.upper().startswith(prefix):
                cleaned_line = cleaned_line[len(prefix):].strip()
        if cleaned_line.upper() not in {"SAFE", "EMERGENCY"}:
            description = cleaned_line
            break

    if not description:
        for line in lines:
            if line.upper() not in {"SAFE", "EMERGENCY"}:
                description = line
                break

    if not description:
        description = result

    return result, short_text(description), str(content).strip()


# ──────────────────────────────────────────────
# Main calls
# ──────────────────────────────────────────────

def _call_vision_api(model_name: str, prompt_text: str, image_path: Path, config: dict[str, Any]) -> tuple[str, str, str]:
    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_text},
                    {"type": "image_url", "image_url": {"url": image_to_data_url(image_path)}},
                ],
            }
        ],
        "max_tokens": 1000,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {config['ai_api_key']}",
        "Content-Type": "application/json",
    }
    
    t0 = time.monotonic()
    response = _session.post(chat_url(config), headers=headers, json=payload, timeout=120)
    latency = time.monotonic() - t0
    
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as exc:
        err_msg = response.text.strip()
        if err_msg.startswith("<") or "html" in response.headers.get("content-type", "").lower():
            err_msg = f"HTML Response ({response.status_code} {response.reason})"
        logger.error("[AI] HTTP Error %s (Model: %s): %s", response.status_code, model_name, err_msg)
        raise RuntimeError(f"{response.status_code} Error: {short_text(err_msg, 100)}") from exc
    
    content = response_ai_content(response)
    result, description, raw = parse_ai_verdict(content)
    logger.info("[AI] latency=%.2fs result=%s description=%r", latency, result, description)
    return result, description, raw

def verify_scene(image_path: Path, config: dict[str, Any], camera: dict[str, Any] | None = None) -> tuple[str, str, str]:
    require_config(config, ["ai_api_key", "ai_base_url", "vision_model"])
    
    prompt_text = str(config.get("verify_prompt", ""))
    if camera and camera.get("prompt_id"):
        for p in config.get("prompts", []):
            if p.get("id") == camera.get("prompt_id"):
                prompt_text = str(p.get("content", prompt_text))
                break

    prompt_text = prompt_text.strip() or "Please analyze this image."
    primary_model = str(config["vision_model"]).strip()
    fallback_model = str(config.get("fallback_vision_model", "")).strip()

    logger.info("[AI] verifying scene image=%s", image_path.name)
    
    try:
        return _call_vision_api(primary_model, prompt_text, image_path, config)
    except RuntimeError as exc:
        if fallback_model and fallback_model != primary_model:
            logger.warning("[AI] Primary model %s failed, retrying with fallback %s. Error: %s", primary_model, fallback_model, exc)
            return _call_vision_api(fallback_model, prompt_text, image_path, config)
        raise


def send_telegram(photo_path: Path, message: str, config: dict[str, Any]) -> None:
    require_config(config, ["telegram_bot_token", "telegram_chat_id"])
    url = f"https://api.telegram.org/bot{config['telegram_bot_token']}/sendPhoto"
    with photo_path.open("rb") as photo:
        response = _session.post(
            url,
            data={"chat_id": config["telegram_chat_id"], "caption": message},
            files={"photo": photo},
            timeout=60,
        )
    response.raise_for_status()
