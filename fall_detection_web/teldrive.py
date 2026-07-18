"""Teldrive upload helpers for event images and short detection clips."""

from __future__ import annotations

import logging
import mimetypes
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

logger = logging.getLogger("fall_detection_web")

_session = requests.Session()
_session.headers.update({"User-Agent": "fall-detection-web/2.0"})


def enabled(config: dict[str, Any]) -> bool:
    return bool(config.get("teldrive_enabled")) and bool(str(config.get("teldrive_token", "")).strip())


def _api_base(config: dict[str, Any]) -> str:
    base = str(config.get("teldrive_base_url", "")).strip().rstrip("/")
    if not base:
        base = "https://teldrive.minhhungtsbd.me"
    if not base.endswith("/api"):
        base = f"{base}/api"
    return base


def _headers(config: dict[str, Any]) -> dict[str, str]:
    token = str(config.get("teldrive_token", "")).strip()
    return {
        "Authorization": f"Bearer {token}",
        "Cookie": f"user-session={token}; access_token={token}"
    }


def check_token(config: dict[str, Any], token: str | None = None, base_url: str | None = None) -> dict[str, Any]:
    cfg = config.copy()
    if token is not None:
        cfg["teldrive_token"] = token
    if base_url is not None:
        cfg["teldrive_base_url"] = base_url
    if not str(cfg.get("teldrive_token", "")).strip():
        raise ValueError("Missing Teldrive token")

    response = _session.get(
        f"{_api_base(cfg)}/auth/session",
        headers=_headers(cfg),
        timeout=15,
    )
    if response.status_code == 401:
        return {"ok": False, "status_code": 401, "message": "Token is expired or invalid"}
    if response.status_code == 403:
        return {"ok": False, "status_code": 403, "message": "Token is not allowed"}
    response.raise_for_status()

    data = response.json() if response.content else {}
    return {
        "ok": True,
        "status_code": response.status_code,
        "name": data.get("name", ""),
        "userName": data.get("userName", ""),
        "expires": data.get("expires", ""),
    }


def _clean_segment(value: str) -> str:
    value = "".join(ch if ch.isalnum() or ch in ("-", "_", " ") else "_" for ch in value)
    return value.strip().replace(" ", "_") or "camera"


def remote_folder(config: dict[str, Any], camera_name: str, kind: str) -> str:
    root = str(config.get("teldrive_root_path", "/Fall Detection")).strip() or "/Fall Detection"
    root = "/" + root.strip("/")
    return f"{root}/{_clean_segment(camera_name)}/{kind}"


def _date_folder_from_name(file_name: str) -> str:
    stamp = Path(file_name).stem[:15]
    try:
        return datetime.strptime(stamp, "%Y%m%dT%H%M%S").strftime("%Y-%m-%d")
    except ValueError:
        return datetime.now().strftime("%Y-%m-%d")


def _folder_path(folder: str) -> str:
    return "/" + folder.strip("/") + "/"


def _mime_type(file_name: str) -> str:
    suffix = Path(file_name).suffix.lower()
    explicit = {
        ".mp4": "video/mp4",
        ".avi": "video/x-msvideo",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
    }
    return explicit.get(suffix) or mimetypes.guess_type(file_name)[0] or "application/octet-stream"


def ensure_folder(config: dict[str, Any], folder: str) -> None:
    response = _session.post(
        f"{_api_base(config)}/files/mkdir",
        headers=_headers(config),
        json={"path": folder},
        timeout=30,
    )
    if response.status_code not in (200, 201, 204, 409):
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            err_msg = f"{exc}. Chi tiết: {response.text[:200]}"
            logger.error("[TELDRIVE] mkdir failed status=%s body=%s", response.status_code, response.text[:500])
            raise RuntimeError(err_msg) from exc


def upload_file(config: dict[str, Any], local_path: Path, folder: str, file_name: str | None = None) -> dict[str, Any]:
    if not enabled(config):
        return {}
    if not local_path.exists():
        raise FileNotFoundError(str(local_path))

    size = local_path.stat().st_size
    if size == 0:
        logger.warning("[TELDRIVE] skipping upload for 0-byte empty file: %s", local_path.name)
        return {"id": "skipped_empty", "name": file_name or local_path.name, "size": 0}

    ensure_folder(config, folder)
    file_name = file_name or local_path.name
    upload_id = uuid.uuid4().hex
    mime_type = _mime_type(file_name)
    channel_id = str(config.get("teldrive_channel_id", "")).strip()

    params: dict[str, Any] = {
        "partName": file_name,
        "fileName": file_name,
        "partNo": 1,
        "encrypted": "false",
        "hashing": "false",
    }
    if channel_id:
        params["channelId"] = int(channel_id)

    with local_path.open("rb") as fh:
        upload_response = _session.post(
            f"{_api_base(config)}/uploads/{upload_id}",
            headers={**_headers(config), "Content-Type": mime_type, "Content-Length": str(size)},
            params=params,
            data=fh,
            timeout=180,
        )
    try:
        upload_response.raise_for_status()
    except requests.HTTPError as exc:
        err_msg = f"{exc}. Chi tiết: {upload_response.text[:200]}"
        logger.error("[TELDRIVE] upload part failed status=%s body=%s", upload_response.status_code, upload_response.text[:500])
        raise RuntimeError(err_msg) from exc
    uploaded_part = upload_response.json()

    parts_response = _session.get(
        f"{_api_base(config)}/uploads/{upload_id}",
        headers=_headers(config),
        timeout=30,
    )
    try:
        parts_response.raise_for_status()
    except requests.HTTPError as exc:
        err_msg = f"{exc}. Chi tiết: {parts_response.text[:200]}"
        logger.error("[TELDRIVE] get parts failed status=%s body=%s", parts_response.status_code, parts_response.text[:500])
        raise RuntimeError(err_msg) from exc
    uploaded_parts = parts_response.json()
    if not uploaded_parts:
        uploaded_parts = [uploaded_part]

    parts = []
    for part in sorted(uploaded_parts, key=lambda item: int(item.get("partNo", 1))):
        file_part: dict[str, Any] = {"id": int(part["partId"])}
        if part.get("salt"):
            file_part["salt"] = part["salt"]
        parts.append(file_part)

    file_payload: dict[str, Any] = {
        "name": file_name,
        "type": "file",
        "path": _folder_path(folder),
        "mimeType": mime_type,
        "uploadId": upload_id,
        "parts": parts,
        "size": size,
        "encrypted": bool(uploaded_part.get("encrypted", False)),
    }
    if channel_id:
        file_payload["channelId"] = int(channel_id)

    file_response = _session.post(
        f"{_api_base(config)}/files",
        headers=_headers(config),
        json=file_payload,
        timeout=30,
    )
    try:
        file_response.raise_for_status()
    except requests.HTTPError as exc:
        err_msg = f"{exc}. Chi tiết: {file_response.text[:200]}"
        logger.error("[TELDRIVE] file commit failed status=%s body=%s", file_response.status_code, file_response.text[:500])
        raise RuntimeError(err_msg) from exc
    logger.info("[TELDRIVE] uploaded %s to %s", file_name, folder)
    return file_response.json()


def upload_event_image(config: dict[str, Any], local_path: Path, camera_name: str, file_name: str | None = None) -> dict[str, Any]:
    return upload_file(config, local_path, remote_folder(config, camera_name, "images"), file_name=file_name)


def upload_event_video(config: dict[str, Any], local_path: Path, camera_name: str) -> dict[str, Any]:
    folder = f"{remote_folder(config, camera_name, 'videos')}/{_date_folder_from_name(local_path.name)}"
    return upload_file(config, local_path, folder)


def file_url(config: dict[str, Any], file_id: str, file_name: str) -> str:
    return f"{_api_base(config)}/files/{file_id}/{quote(file_name, safe='')}"


def download_file(config: dict[str, Any], file_id: str, file_name: str, range_header: str = "") -> requests.Response:
    headers = {}
    if range_header:
        headers["Range"] = range_header
    response = _session.get(
        file_url(config, file_id, file_name),
        headers=headers,
        stream=True,
        timeout=60,
    )
    if response.status_code not in (401, 403) or not str(config.get("teldrive_token", "")).strip():
        response.raise_for_status()
        return response

    response.close()
    response = _session.get(
        file_url(config, file_id, file_name),
        headers={**_headers(config), **headers},
        stream=True,
        timeout=60,
    )
    response.raise_for_status()
    return response


def prewarm_file(config: dict[str, Any], file_id: str, file_name: str) -> None:
    """Pre-warm the file on Teldrive/Telegram in the background to avoid watchdog timeouts."""
    if not enabled(config):
        return
    try:
        logger.info("[TELDRIVE] Start pre-warming file_id=%s file_name=%s", file_id, file_name)
        # Request the first 512KB to wake up Telegram & Teldrive's stream cache
        response = download_file(config, file_id, file_name, range_header="bytes=0-524288")
        # Consume the content to force the download
        _ = response.content
        response.close()
        logger.info("[TELDRIVE] Successfully pre-warmed file file_id=%s file_name=%s", file_id, file_name)
    except Exception as exc:
        logger.warning("[TELDRIVE] Pre-warm failed for file_id=%s: %s", file_id, exc)
