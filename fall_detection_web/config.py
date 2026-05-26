"""Configuration management — stored in SQLite, overridable via .env / os.environ.

Priority (highest → lowest):
  1. Environment variables / .env file  (secrets, container overrides)
  2. SQLite settings table              (user changes via UI)
  3. DEFAULT_CONFIG                     (built-in defaults)

config.json is no longer written. On first startup, if config.json exists it is
auto-migrated into the DB and renamed to config.json.migrated.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
ENV_PATH = ROOT / ".env"
LEGACY_CONFIG_PATH = DATA_DIR / "config.json"

logger = logging.getLogger("fall_detection_web")

DEFAULT_VERIFY_PROMPT = """Bạn là hệ thống xác minh té ngã từ ảnh camera trong nhà.

Nhiệm vụ:
- Xác định người có bị té ngã, nằm bất thường dưới đất, gặp nguy hiểm, cần trợ giúp, hoặc cố đứng dậy thất bại không.
- Nếu có nguy hiểm, dòng 1 chỉ trả lời: EMERGENCY
- Nếu bình thường, dòng 1 chỉ trả lời: SAFE
- Dòng 2 mô tả rất ngắn tình huống trong ảnh, tối đa 20 ký tự.

Chỉ trả lời đúng 2 dòng, không giải thích thêm:
SAFE hoặc EMERGENCY
Mô tả dưới 20 ký tự
"""

# Keys that are stored as plain strings in DB (including secrets — DB is local)
# All values stored as TEXT; numeric types are coerced on read.
DEFAULT_CONFIG: dict[str, Any] = {
    "rtsp_url": "",
    "go2rtc_url": "",
    "prompts": [],          # stored as JSON string
    "cameras": [],          # stored as JSON string
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "ai_base_url": "https://9router.minhhungtsbd.me/v1",
    "ai_api_key": "",
    "vision_model": "gh/oswe-vscode-prime",
    "fallback_vision_model": "",
    "verify_prompt": DEFAULT_VERIFY_PROMPT,
    "detection_mode": "yolo",
    "yolo_model": "yolov8n.pt",
    "yolo_imgsz": 416,
    "confidence": 0.5,
    "verify_interval": 20,
    "alert_cooldown": 300,
    "frame_skip": 2,
    "loop_sleep": 0.3,
    "teldrive_enabled": False,
    "teldrive_base_url": "https://teldrive.minhhungtsbd.me",
    "teldrive_token": "",
    "teldrive_root_path": "/Fall Detection",
    "teldrive_channel_id": "",
    "teldrive_upload_images": True,
    "teldrive_record_enabled": False,
    "teldrive_record_seconds": 10,
    "teldrive_record_cooldown": 300,
    "jwt_secret": "",
    "redis_enabled": False,
    "redis_host": "127.0.0.1",
    "redis_port": 6379,
    "redis_db": 0,
    "redis_password": "",
}

# Keys that env vars can override (env key → config key)
ENV_CONFIG_KEYS: dict[str, str] = {
    "RTSP_URL": "rtsp_url",
    "GO2RTC_URL": "go2rtc_url",
    "TELEGRAM_BOT_TOKEN": "telegram_bot_token",
    "TELEGRAM_CHAT_ID": "telegram_chat_id",
    "AI_BASE_URL": "ai_base_url",
    "AI_API_KEY": "ai_api_key",
    "VISION_MODEL": "vision_model",
    "YOLO_MODEL": "yolo_model",
    "YOLO_IMGSZ": "yolo_imgsz",
    "CONFIDENCE": "confidence",
    "VERIFY_INTERVAL": "verify_interval",
    "ALERT_COOLDOWN": "alert_cooldown",
    "FRAME_SKIP": "frame_skip",
    "LOOP_SLEEP": "loop_sleep",
    "TELDRIVE_ENABLED": "teldrive_enabled",
    "TELDRIVE_BASE_URL": "teldrive_base_url",
    "TELDRIVE_TOKEN": "teldrive_token",
    "TELDRIVE_ROOT_PATH": "teldrive_root_path",
    "TELDRIVE_CHANNEL_ID": "teldrive_channel_id",
    "TELDRIVE_UPLOAD_IMAGES": "teldrive_upload_images",
    "TELDRIVE_RECORD_ENABLED": "teldrive_record_enabled",
    "TELDRIVE_RECORD_SECONDS": "teldrive_record_seconds",
    "TELDRIVE_RECORD_COOLDOWN": "teldrive_record_cooldown",
    "JWT_SECRET": "jwt_secret",
    "REDIS_ENABLED": "redis_enabled",
    "REDIS_HOST": "redis_host",
    "REDIS_PORT": "redis_port",
    "REDIS_DB": "redis_db",
    "REDIS_PASSWORD": "redis_password",
}

# Numeric keys that need type coercion when read from DB (stored as TEXT)
_INT_KEYS = {"yolo_imgsz", "verify_interval", "alert_cooldown", "frame_skip", "teldrive_record_seconds", "teldrive_record_cooldown", "redis_port", "redis_db"}
_FLOAT_KEYS = {"confidence", "loop_sleep"}
_BOOL_KEYS = {"teldrive_enabled", "teldrive_upload_images", "teldrive_record_enabled", "redis_enabled"}


def normalize_go2rtc_source(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.query:
        src = parse_qs(parsed.query).get("src", [""])[0]
        if src:
            return src.strip()
    return text.rstrip("/").split("/")[-1] if parsed.scheme and parsed.path else text


def is_url(value: Any) -> bool:
    parsed = urlparse(str(value or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def positive_int(value: Any, name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if parsed < 1:
        raise ValueError(f"{name} must be >= 1")
    return parsed


def clamp_float(value: Any, min_val: float, max_val: float, name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc
    if parsed < min_val or parsed > max_val:
        raise ValueError(f"{name} must be between {min_val} and {max_val}")
    return parsed


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key:
            values[key] = val
    return values


def _env_overrides() -> dict[str, Any]:
    """Return config values set by environment / .env (highest priority)."""
    raw = _parse_env_file(ENV_PATH)
    raw.update(os.environ)
    out: dict[str, Any] = {}
    for env_key, cfg_key in ENV_CONFIG_KEYS.items():
        val = raw.get(env_key, "")
        if not val:
            continue
        try:
            out[cfg_key] = _coerce(cfg_key, val)
        except ValueError as exc:
            logger.warning("Ignoring invalid env %s: %s", env_key, exc)
    return out


def _coerce(key: str, value: Any) -> Any:
    """Cast value to the correct Python type for a given config key."""
    if key in _BOOL_KEYS:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}
    if key in _INT_KEYS:
        return positive_int(value, key)
    if key == "confidence":
        return clamp_float(value, 0.01, 1.0, key)
    if key == "loop_sleep":
        return max(0.0, float(value))
    if key in ("cameras", "prompts"):
        if isinstance(value, list):
            return value
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
    return value


def _bool_default_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"0", "false", "no", "off"}:
        return False
    if text in {"1", "true", "yes", "on"}:
        return True
    return True


def _bool_default_false(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "on"}


def _serialize(key: str, value: Any) -> str:
    """Serialize a config value to string for DB storage."""
    if key in ["cameras", "prompts"]:
        return json.dumps(value, ensure_ascii=False)
    return str(value)


# ──────────────────────────────────────────────
# Migration from config.json
# ──────────────────────────────────────────────

def migrate_config_json() -> None:
    """One-time migration: import legacy config.json into DB settings table."""
    migrated_path = LEGACY_CONFIG_PATH.with_suffix(".json.migrated")
    if migrated_path.exists() or not LEGACY_CONFIG_PATH.exists():
        return
    try:
        data = json.loads(LEGACY_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("[CONFIG] Could not read config.json for migration: %s", exc)
        return
    if not isinstance(data, dict):
        return

    import db as _db
    to_save: dict[str, str] = {}
    for key, default_val in DEFAULT_CONFIG.items():
        if key not in data:
            continue
        val = data[key]
        # Skip old yolo fields if missing
        if val == default_val and key not in data:
            continue
        to_save[key] = _serialize(key, val)

    if to_save:
        _db.set_settings_bulk(to_save)
        logger.info("[CONFIG] Migrated %d keys from config.json to DB", len(to_save))

    LEGACY_CONFIG_PATH.rename(migrated_path)
    logger.info("[CONFIG] config.json renamed to config.json.migrated — no longer used")


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────

def normalize_cameras(config: dict[str, Any]) -> list[dict[str, Any]]:
    raw = config.get("cameras", [])
    if not isinstance(raw, list):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = []
    cameras: list[dict[str, Any]] = []
    for i, cam in enumerate(raw):
        if not isinstance(cam, dict):
            continue
        cameras.append({
            "enabled": _bool_default_true(cam.get("enabled")),
            "name": str(cam.get("name", "")).strip() or f"Camera {i + 1}",
            "rtsp_url": str(cam.get("rtsp_url", "")).strip(),
            "go2rtc_src": str(cam.get("go2rtc_src", "")).strip(),
            "live_url": str(cam.get("live_url", "")).strip(),
            "live_mode": str(cam.get("live_mode", "auto")).strip() if str(cam.get("live_mode", "auto")).strip() in {"auto", "iframe", "snapshot"} else "auto",
            "prompt_id": str(cam.get("prompt_id", "")).strip(),
            "local_save_images": _bool_default_true(cam.get("local_save_images")),
            "local_save_videos": _bool_default_true(cam.get("local_save_videos")),
            "teldrive_upload_images": _bool_default_true(cam.get("teldrive_upload_images")),
            "teldrive_record_enabled": _bool_default_false(cam.get("teldrive_record_enabled")),
            "record_seconds": positive_int(cam.get("record_seconds", config.get("teldrive_record_seconds", 10)), "record_seconds"),
            "record_cooldown": positive_int(cam.get("record_cooldown", config.get("teldrive_record_cooldown", 300)), "record_cooldown"),
        })
    # Fallback: top-level rtsp_url → single default camera
    fallback = str(config.get("rtsp_url", "")).strip()
    if not cameras and fallback:
        cameras.append({"enabled": True, "name": "Default", "rtsp_url": fallback, "go2rtc_src": "", "live_url": "", "live_mode": "auto", "prompt_id": "", "local_save_images": True, "local_save_videos": True, "teldrive_upload_images": True, "teldrive_record_enabled": False, "record_seconds": int(config.get("teldrive_record_seconds", 10)), "record_cooldown": int(config.get("teldrive_record_cooldown", 300))})
    return cameras


def normalize_prompts(config: dict[str, Any]) -> list[dict[str, Any]]:
    raw = config.get("prompts", [])
    if not isinstance(raw, list):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = []
    prompts: list[dict[str, Any]] = []
    for p in raw:
        if not isinstance(p, dict):
            continue
        # Ensure it has an id, title, and content
        if not str(p.get("id", "")).strip():
            import uuid
            p["id"] = str(uuid.uuid4())
        prompts.append({
            "id": str(p.get("id", "")).strip(),
            "title": str(p.get("title", "")).strip(),
            "content": str(p.get("content", "")).strip()
        })
    return prompts


def read_config() -> dict[str, Any]:
    """Read config: DB → overridden by env vars."""
    import db as _db
    db_settings = _db.get_all_settings()

    config: dict[str, Any] = DEFAULT_CONFIG.copy()
    for key, default_val in DEFAULT_CONFIG.items():
        if key in db_settings:
            try:
                config[key] = _coerce(key, db_settings[key])
            except (ValueError, TypeError):
                config[key] = default_val

    # Env overrides (highest priority)
    config.update(_env_overrides())

    # Normalize
    config["cameras"] = normalize_cameras(config)
    config["prompts"] = normalize_prompts(config)
    config["detection_mode"] = "yolo"
    return config


def write_config(new_config: dict[str, Any]) -> dict[str, Any]:
    """Validate, normalize, then persist config to DB."""
    import db as _db
    clean: dict[str, Any] = {}
    for key, default_val in DEFAULT_CONFIG.items():
        clean[key] = new_config.get(key, default_val)

    # Validate numerics
    clean["confidence"] = clamp_float(clean["confidence"], 0.01, 1.0, "confidence")
    clean["verify_interval"] = positive_int(clean["verify_interval"], "verify_interval")
    clean["alert_cooldown"] = positive_int(clean["alert_cooldown"], "alert_cooldown")
    clean["frame_skip"] = positive_int(clean["frame_skip"], "frame_skip")
    clean["yolo_imgsz"] = positive_int(clean["yolo_imgsz"], "yolo_imgsz")
    clean["teldrive_record_seconds"] = positive_int(clean["teldrive_record_seconds"], "teldrive_record_seconds")
    clean["teldrive_record_cooldown"] = positive_int(clean["teldrive_record_cooldown"], "teldrive_record_cooldown")
    clean["teldrive_enabled"] = _coerce("teldrive_enabled", clean["teldrive_enabled"])
    clean["teldrive_upload_images"] = _coerce("teldrive_upload_images", clean["teldrive_upload_images"])
    clean["teldrive_record_enabled"] = _coerce("teldrive_record_enabled", clean["teldrive_record_enabled"])
    clean["redis_enabled"] = _coerce("redis_enabled", clean["redis_enabled"])
    clean["redis_port"] = positive_int(clean["redis_port"], "redis_port")
    try:
        clean["redis_db"] = max(0, int(clean["redis_db"]))
    except (TypeError, ValueError):
        clean["redis_db"] = 0
    clean["loop_sleep"] = max(0.0, float(clean["loop_sleep"]))
    clean["cameras"] = normalize_cameras(clean)
    clean["prompts"] = normalize_prompts(clean)
    clean["detection_mode"] = "yolo"

    # Don't overwrite keys that are currently supplied by env (avoid empty overwrite)
    env_vals = _env_overrides()

    to_save: dict[str, str] = {}
    for key, val in clean.items():
        # If env provides this key and the submitted value matches env (or is empty), skip saving
        if key in env_vals:
            submitted = str(val).strip()
            if not submitted or submitted == str(env_vals[key]):
                continue
        to_save[key] = _serialize(key, val)

    _db.set_settings_bulk(to_save)
    return read_config()


def require_config(config: dict[str, Any], keys: list[str]) -> None:
    missing = [k for k in keys if not str(config.get(k, "")).strip()]
    if missing:
        raise ValueError(f"Missing required config: {', '.join(missing)}")


def get_camera(config: dict[str, Any], index: int) -> dict[str, Any]:
    cameras = normalize_cameras(config)
    if index < 0 or index >= len(cameras):
        raise ValueError("Invalid camera index")
    return cameras[index]


def has_camera_snapshot_source(config: dict[str, Any], camera: dict[str, Any]) -> bool:
    go2rtc_src = normalize_go2rtc_source(camera.get("go2rtc_src") or camera.get("name") or "")
    if (str(config.get("go2rtc_url", "")).strip() or is_url(camera.get("go2rtc_src"))) and go2rtc_src:
        return True
    return bool(str(camera.get("rtsp_url", "")).strip())
