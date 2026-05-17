"""Teldrive upload helpers for event images and short detection clips."""

from __future__ import annotations

import logging
import mimetypes
import uuid
from pathlib import Path
from typing import Any

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
    return {"Authorization": f"Bearer {config['teldrive_token']}"}


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


def _folder_path(folder: str) -> str:
    return "/" + folder.strip("/") + "/"


def ensure_folder(config: dict[str, Any], folder: str) -> None:
    response = _session.post(
        f"{_api_base(config)}/files/mkdir",
        headers=_headers(config),
        json={"path": folder},
        timeout=30,
    )
    if response.status_code not in (200, 201, 204, 409):
        response.raise_for_status()


def upload_file(config: dict[str, Any], local_path: Path, folder: str, file_name: str | None = None) -> dict[str, Any]:
    if not enabled(config):
        return {}
    if not local_path.exists():
        raise FileNotFoundError(str(local_path))

    ensure_folder(config, folder)
    file_name = file_name or local_path.name
    upload_id = uuid.uuid4().hex
    size = local_path.stat().st_size
    mime_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
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
    upload_response.raise_for_status()
    uploaded_part = upload_response.json()

    parts_response = _session.get(
        f"{_api_base(config)}/uploads/{upload_id}",
        headers=_headers(config),
        timeout=30,
    )
    parts_response.raise_for_status()
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
    except requests.HTTPError:
        logger.error("[TELDRIVE] file commit failed status=%s body=%s", file_response.status_code, file_response.text[:500])
        raise
    logger.info("[TELDRIVE] uploaded %s to %s", file_name, folder)
    return file_response.json()


def upload_event_image(config: dict[str, Any], local_path: Path, camera_name: str) -> None:
    if not config.get("teldrive_upload_images", True):
        return
    upload_file(config, local_path, remote_folder(config, camera_name, "images"))


def upload_event_video(config: dict[str, Any], local_path: Path, camera_name: str) -> None:
    upload_file(config, local_path, remote_folder(config, camera_name, "videos"))
