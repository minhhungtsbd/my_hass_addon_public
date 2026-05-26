"""Monitor loop — YOLO local inference for person detection."""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, parse_qsl, urlencode, urlparse, urlunparse

import requests

os.environ.setdefault("OPENCV_FFMPEG_LOGLEVEL", "-8")
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

from ai import send_telegram, verify_scene
from config import get_camera, normalize_cameras, require_config
import db
from db import insert_event, now_iso
import teldrive

logger = logging.getLogger("fall_detection_web")

DATA_DIR = Path(__file__).resolve().parent / "data"
SNAPSHOT_PATH = DATA_DIR / "latest.jpg"
CLIPS_DIR = DATA_DIR / "event_clips"

state_lock = threading.Lock()
stop_event = threading.Event()
worker_thread: threading.Thread | None = None
monitor_lock = threading.Lock()
cleanup_lock = threading.Lock()
cleanup_thread: threading.Thread | None = None


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
    "mode": "",
}


def set_state(**updates: Any) -> None:
    with state_lock:
        status.update(updates)


def read_state() -> dict[str, Any]:
    with state_lock:
        return status.copy()


def camera_snapshot_path(index: int) -> Path:
    return DATA_DIR / f"camera_{index}.jpg"


def capture_rtsp_snapshot(rtsp_url: str, output_path: Path) -> Path:
    import cv2
    if not rtsp_url:
        raise ValueError("Camera RTSP URL is empty")
    cap = cv2.VideoCapture(rtsp_url)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    try:
        ok, frame = cap.read()
        if not ok:
            raise RuntimeError("Could not read frame from RTSP source")
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(output_path), frame)
    finally:
        cap.release()
    return output_path


def log_event(config: dict[str, Any], status_name: str, image_path: Path | None = None, camera_config: dict[str, Any] | None = None, **fields: Any) -> None:
    save_local_images = True if camera_config is None else camera_config.get("local_save_images") is not False
    event = insert_event(status_name, image_path=image_path, save_image=save_local_images, **fields)
    image_file = str(event.get("image_file", ""))
    upload_images = True if camera_config is None else camera_config.get("teldrive_upload_images") is not False
    should_upload_image = status_name == "verified" and str(fields.get("ai_result", "")).upper() == "EMERGENCY"
    upload_path = DATA_DIR / "event_images" / image_file if image_file else image_path
    if upload_path and upload_path.exists() and upload_images and should_upload_image and teldrive.enabled(config):
        camera_name = str(fields.get("camera", "Camera") or "Camera")
        safe_status = "".join(ch for ch in status_name if ch.isalnum() or ch in ("_", "-")) or "event"
        upload_name = image_file or f"{time.strftime('%Y%m%dT%H%M%S')}_{safe_status}.jpg"
        threading.Thread(
            target=upload_event_image_safe,
            args=(config.copy(), upload_path, camera_name, int(event["id"]), upload_name),
            daemon=True,
        ).start()


def alert_message(camera_name: str, description: str = "") -> str:
    message = f"Emergency detected by AI vision.\nCamera: {camera_name}"
    if description:
        message += f"\nScene: {description}"
    return message


def upload_event_image_safe(config: dict[str, Any], image_path: Path, camera_name: str, event_id: int, file_name: str | None = None) -> None:
    try:
        file_data = teldrive.upload_event_image(config, image_path, camera_name, file_name=file_name)
        if file_data:
            import db
            db.update_event_teldrive_image(event_id, file_data)
    except Exception as exc:
        logger.warning("[TELDRIVE] image upload failed camera=%s: %s", camera_name, exc)
        insert_event("teldrive_image_error", camera=camera_name, error=str(exc))


def upload_recording_thumbnail_if_needed(
    config: dict[str, Any],
    camera_config: dict[str, Any] | None,
    camera_name: str,
    event_id: int,
    image_file: str,
) -> None:
    if not image_file:
        return
    upload_images = True if camera_config is None else camera_config.get("teldrive_upload_images") is not False
    save_local_images = True if camera_config is None else camera_config.get("local_save_images") is not False
    image_path = db.EVENT_IMAGES_DIR / Path(image_file).name
    if not image_path.exists() or not upload_images or not teldrive.enabled(config):
        return
    try:
        file_data = teldrive.upload_event_image(config, image_path, camera_name, file_name=image_path.name)
        if file_data:
            db.update_event_teldrive_image(event_id, file_data)
            if not save_local_images:
                try:
                    image_path.unlink()
                    logger.info("[RECORD] removed local recording thumbnail file=%s", image_path.name)
                except OSError as exc:
                    logger.warning("[RECORD] could not remove local recording thumbnail file=%s error=%s", image_path.name, exc)
    except Exception as exc:
        logger.warning("[TELDRIVE] recording thumbnail upload failed camera=%s: %s", camera_name, exc)
        insert_event("teldrive_image_error", camera=camera_name, error=str(exc))


def upload_event_video_safe(
    config: dict[str, Any],
    video_path: Path,
    camera_name: str,
    thumbnail_path: Path | None = None,
    camera_config: dict[str, Any] | None = None,
    event_time: str = "",
    event_time_local: str = "",
) -> bool:
    try:
        file_data = teldrive.upload_event_video(config, video_path, camera_name)
        video_id = str(file_data.get("id", ""))
        video_name = str(file_data.get("name", ""))
        if not video_id or not video_name:
            raise RuntimeError("Teldrive upload did not return file id/name")
        save_thumbnail = thumbnail_path is not None and thumbnail_path.exists()
        event = insert_event(
            "teldrive_video_uploaded",
            image_path=thumbnail_path if save_thumbnail else None,
            save_image=save_thumbnail,
            camera=camera_name,
            message=video_path.name,
            teldrive_video_id=video_id,
            teldrive_video_name=video_name,
            teldrive_video_path=str(file_data.get("path", "")),
            event_time=event_time,
            event_time_local=event_time_local,
        )
        upload_recording_thumbnail_if_needed(config, camera_config, camera_name, int(event["id"]), str(event.get("image_file", "")))
        return True
    except Exception as exc:
        logger.warning("[TELDRIVE] video upload failed camera=%s: %s", camera_name, exc)
        insert_event("teldrive_video_error", camera=camera_name, error=str(exc))
        return False


def cleanup_recording_if_needed(camera: dict[str, Any], video_path: Path, uploaded: bool) -> None:
    if uploaded:
        cleanup_temp_thumbnail(video_path)
    if camera.get("local_save_videos") is not False:
        return
    if not uploaded:
        logger.warning("[RECORD] keeping local clip after upload failure file=%s", video_path.name)
        return
    try:
        video_path.unlink()
        logger.info("[RECORD] removed local clip after upload file=%s", video_path.name)
    except OSError as exc:
        logger.warning("[RECORD] could not remove local clip file=%s error=%s", video_path.name, exc)


def clip_metadata_from_name(path: Path) -> dict[str, str]:
    stem = path.stem
    if len(stem) < 17 or stem[8:9] != "T" or stem[15:16] != "_":
        return {}
    try:
        dt = datetime.strptime(stem[:15], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return {}
    return {
        "camera_key": stem[16:],
        "event_time": dt.isoformat(timespec="seconds"),
        "event_time_local": dt.astimezone(db.LOCAL_TZ).isoformat(timespec="seconds"),
    }


def video_thumbnail_path(video_path: Path) -> Path:
    return video_path.with_name(f"{video_path.stem}_thumb.jpg")


def cleanup_temp_thumbnail(video_path: Path) -> None:
    thumb_path = video_thumbnail_path(video_path)
    try:
        if thumb_path.exists():
            thumb_path.unlink()
    except OSError as exc:
        logger.warning("[RECORD] could not remove thumbnail file=%s error=%s", thumb_path.name, exc)


def save_frame_thumbnail(frame: Any, output_path: Path) -> Path | None:
    try:
        import cv2
        if frame is None:
            return None
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(output_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 78])
        return output_path if output_path.exists() else None
    except Exception as exc:
        logger.warning("[RECORD] thumbnail write failed file=%s error=%s", output_path.name, exc)
        return None


def extract_video_thumbnail(video_path: Path) -> Path | None:
    try:
        import cv2
        thumb_path = video_thumbnail_path(video_path)
        cap = cv2.VideoCapture(str(video_path))
        try:
            ok, frame = cap.read()
        finally:
            cap.release()
        if not ok or frame is None:
            return None
        return save_frame_thumbnail(frame, thumb_path)
    except Exception as exc:
        logger.warning("[RECORD] thumbnail extract failed file=%s error=%s", video_path.name, exc)
        return None


def cleanup_uploaded_local_clips(config: dict[str, Any]) -> int:
    if not CLIPS_DIR.exists():
        return 0
    cameras = normalize_cameras(config)
    camera_by_safe_name = {safe_camera_name(str(camera.get("name", ""))): camera for camera in cameras}
    keep_local_by_camera = {str(camera.get("name", "")).strip(): camera.get("local_save_videos") is not False for camera in cameras}
    uploaded_records = db.get_uploaded_video_records()
    uploaded_by_name: dict[str, dict[str, str]] = {}
    for record in uploaded_records:
        for file_name in (record.get("message", ""), record.get("teldrive_video_name", "")):
            safe_name = Path(file_name).name
            if safe_name:
                uploaded_by_name[safe_name] = record
    uploaded_names = set(uploaded_by_name)
    deleted = 0
    for path in sorted(CLIPS_DIR.iterdir()):
        if not path.is_file() or path.suffix.lower() not in {".mp4", ".avi"}:
            continue
        meta = clip_metadata_from_name(path)
        camera = camera_by_safe_name.get(meta.get("camera_key", ""))
        if not camera:
            logger.info("[RECORD] keeping unmatched local clip file=%s", path.name)
            continue
        camera_name = str(camera.get("name", "")).strip()
        if path.name not in uploaded_names:
            if not teldrive.enabled(config):
                logger.info("[RECORD] keeping local clip without Teldrive config file=%s", path.name)
                continue
            logger.info("[RECORD] retrying Teldrive upload for local clip file=%s", path.name)
            uploaded = upload_event_video_safe(
                config,
                path,
                camera_name,
                thumbnail_path=extract_video_thumbnail(path),
                camera_config=camera,
                event_time=meta.get("event_time", ""),
                event_time_local=meta.get("event_time_local", ""),
            )
            if uploaded:
                uploaded_names.add(path.name)
            else:
                continue
        uploaded_record = uploaded_by_name.get(path.name)
        if uploaded_record and not uploaded_record.get("image_file"):
            thumb_path = extract_video_thumbnail(path)
            if thumb_path:
                try:
                    db.update_event_image(int(uploaded_record["id"]), thumb_path)
                except Exception as exc:
                    logger.warning("[RECORD] could not attach recording thumbnail file=%s error=%s", path.name, exc)
        if keep_local_by_camera.get(camera_name, True):
            cleanup_temp_thumbnail(path)
            continue
        try:
            path.unlink()
            cleanup_temp_thumbnail(path)
            deleted += 1
            logger.info("[RECORD] removed uploaded local clip file=%s", path.name)
        except OSError as exc:
            logger.warning("[RECORD] could not remove uploaded local clip file=%s error=%s", path.name, exc)
    return deleted


def schedule_uploaded_local_clips_cleanup(config: dict[str, Any], reason: str = "") -> str:
    global cleanup_thread
    with cleanup_lock:
        if cleanup_thread and cleanup_thread.is_alive():
            logger.info("[RECORD] local clip cleanup already running; skip schedule reason=%s", reason)
            return "already running"

        def run_cleanup() -> None:
            try:
                deleted = cleanup_uploaded_local_clips(config.copy())
                logger.info("[RECORD] local clip cleanup finished reason=%s deleted=%s", reason, deleted)
            except Exception as exc:
                logger.warning("[RECORD] local clip cleanup failed reason=%s error=%s", reason, exc)

        cleanup_thread = threading.Thread(target=run_cleanup, daemon=True, name="clip-cleanup")
        cleanup_thread.start()
        logger.info("[RECORD] scheduled local clip cleanup reason=%s", reason)
        return "scheduled"


def safe_camera_name(camera_name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in camera_name) or "camera"


def go2rtc_source(camera: dict[str, Any]) -> str:
    value = str(camera.get("go2rtc_src") or camera.get("name") or "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.query:
        query = parse_qs(parsed.query)
        src = query.get("src", [""])[0]
        if src:
            return src.strip()
    return value.rstrip("/").split("/")[-1] if parsed.scheme and parsed.path else value


def is_http_url(value: str) -> bool:
    parsed = urlparse(str(value or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def video_only_source(src: str) -> str:
    parsed = urlparse(str(src or "").strip())
    if parsed.scheme not in {"rtsp", "rtsps", "rtspx"}:
        return src
    flags = [item for item in parsed.fragment.split("#") if item]
    keys = {item.split("=", 1)[0] for item in flags}
    if "media" not in keys:
        flags.append("media=video")
    if "backchannel" not in keys:
        flags.append("backchannel=0")
    return urlunparse(parsed._replace(fragment="#".join(flags)))


def with_video_only_query(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    query = parse_qsl(parsed.query, keep_blank_values=True)
    keys = {key.lower() for key, _value in query}
    for key, value in (("video", ""), ("media", "video"), ("backchannel", "0")):
        if key not in keys:
            query.append((key, value))
    return urlunparse(parsed._replace(query=urlencode(query)))


def go2rtc_video_only_params(params: dict[str, str]) -> dict[str, str]:
    filtered = dict(params)
    keys = {key.lower() for key in filtered}
    for key, value in (("video", ""), ("media", "video"), ("backchannel", "0")):
        if key not in keys:
            filtered[key] = value
    return filtered


def go2rtc_frame_request(config: dict[str, Any], camera: dict[str, Any]) -> tuple[str, dict[str, str], str]:
    raw_source = str(camera.get("go2rtc_src") or "").strip()
    if is_http_url(raw_source):
        return with_video_only_query(raw_source), {}, go2rtc_source(camera)

    base_url = str(config.get("go2rtc_url", "")).strip().rstrip("/")
    src = go2rtc_source(camera)
    if not base_url or not src:
        raise ValueError("go2rtc URL or camera source is empty")
    request_src = video_only_source(src)
    return f"{base_url}/api/frame.jpeg", go2rtc_video_only_params({"src": request_src}), src


def fetch_go2rtc_frame_bytes(config: dict[str, Any], camera: dict[str, Any], timeout: int, attempts: int = 3) -> tuple[bytes, str]:
    frame_url, params, src = go2rtc_frame_request(config, camera)
    headers = {
        "Accept": "image/jpeg,image/*;q=0.9,*/*;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
    }
    last_error = ""
    for attempt in range(1, attempts + 1):
        request_params = dict(params)
        request_params["_ts"] = str(int(time.time() * 1000))
        try:
            response = requests.get(
                frame_url,
                params=request_params,
                headers=headers,
                timeout=timeout,
            )
            response.raise_for_status()
            if response.content:
                return response.content, src
            content_type = response.headers.get("content-type", "")
            last_error = f"empty response body status={response.status_code} content-type={content_type}"
        except requests.RequestException as exc:
            last_error = str(exc)
        if attempt < attempts:
            time.sleep(0.25 * attempt)
    raise ValueError(f"go2rtc returned empty frame after {attempts} attempts: {last_error}")


def go2rtc_api_base(config: dict[str, Any], camera: dict[str, Any]) -> str:
    base_url = str(config.get("go2rtc_url", "")).strip().rstrip("/")
    if base_url:
        return base_url
    raw_source = str(camera.get("go2rtc_src") or "").strip()
    parsed = urlparse(raw_source)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        path = parsed.path.rstrip("/")
        if path.endswith("/api/frame.jpeg"):
            return f"{parsed.scheme}://{parsed.netloc}{path[:-len('/api/frame.jpeg')]}"
        return f"{parsed.scheme}://{parsed.netloc}"
    return ""


def has_go2rtc_frame_source(config: dict[str, Any], camera: dict[str, Any]) -> bool:
    raw_source = str(camera.get("go2rtc_src") or "").strip()
    if is_http_url(raw_source):
        return True
    return bool(str(config.get("go2rtc_url", "")).strip() and go2rtc_source(camera))


def record_go2rtc_clip(config: dict[str, Any], camera: dict[str, Any], output_path: Path) -> Path | None:
    base_url = go2rtc_api_base(config, camera)
    src = go2rtc_source(camera)
    if not base_url or not src:
        return None

    seconds = int(camera.get("record_seconds", config.get("teldrive_record_seconds", 10)))
    # Add 6 seconds padding to compensate for initial Keyframe (I-frame) wait time
    request_seconds = seconds + 6
    response = requests.get(
        f"{base_url}/api/stream.mp4",
        params={
            "src": video_only_source(src),
            "duration": request_seconds,
            "filename": output_path.name,
            # Recordings are played by the browser <video> element, so keep
            # Teldrive clips in H.264 MP4 instead of HEVC/H.265.
            "video": "h264",
        },
        stream=True,
        timeout=request_seconds + 30,
    )
    response.raise_for_status()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as fh:
        for chunk in response.iter_content(chunk_size=1024 * 256):
            if chunk:
                fh.write(chunk)
    if output_path.exists() and output_path.stat().st_size > 0:
        logger.info("[RECORD] go2rtc mp4 clip saved src=%s file=%s", src, output_path.name)
        return output_path
    return None


def record_and_upload_clip(
    config: dict[str, Any],
    camera: dict[str, Any],
    holder: dict[str, Any],
    lock: threading.Lock,
) -> None:
    import cv2

    camera_name = str(camera["name"])
    seconds = int(camera.get("record_seconds", config.get("teldrive_record_seconds", 10)))
    fps = 8.0
    deadline = time.time() + seconds
    writer = None
    raw_path: Path | None = None
    last_seq = -1

    try:
        CLIPS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%dT%H%M%S")
        safe_camera = safe_camera_name(camera_name)
        base_path = CLIPS_DIR / f"{stamp}_{safe_camera}"
        final_path = base_path.with_suffix(".mp4")

        try:
            go2rtc_path = record_go2rtc_clip(config, camera, final_path)
            if go2rtc_path:
                with lock:
                    thumbnail_path = save_frame_thumbnail(holder.get("frame"), video_thumbnail_path(go2rtc_path))
                uploaded = upload_event_video_safe(config, go2rtc_path, camera_name, thumbnail_path=thumbnail_path, camera_config=camera)
                cleanup_recording_if_needed(camera, go2rtc_path, uploaded)
                return
        except Exception as exc:
            logger.warning("[RECORD] go2rtc clip failed camera=%s: %s", camera_name, exc)

        while time.time() < deadline and not stop_event.is_set():
            with lock:
                frame = holder.get("frame")
                seq = int(holder.get("seq", 0))
            if frame is None or seq == last_seq:
                time.sleep(0.05)
                continue
            last_seq = seq
            if writer is None:
                height, width = frame.shape[:2]
                candidates = (
                    (CLIPS_DIR / f"{base_path.name}_raw.mp4", "avc1"),
                    (CLIPS_DIR / f"{base_path.name}_raw.mp4", "H264"),
                    (CLIPS_DIR / f"{base_path.name}_raw.mp4", "mp4v"),
                    (CLIPS_DIR / f"{base_path.name}_raw.avi", "MJPG"),
                )
                for candidate, codec in candidates:
                    candidate_writer = cv2.VideoWriter(
                        str(candidate),
                        cv2.VideoWriter_fourcc(*codec),
                        fps,
                        (width, height),
                    )
                    if candidate_writer.isOpened():
                        raw_path = candidate
                        writer = candidate_writer
                        break
                    candidate_writer.release()
                if writer is None:
                    raise RuntimeError("Could not open video writer")
            writer.write(frame)
            time.sleep(1.0 / fps)
    except Exception as exc:
        logger.warning("[RECORD] failed camera=%s: %s", camera_name, exc)
        insert_event("record_error", camera=camera_name, error=str(exc))
        return
    finally:
        if writer is not None:
            writer.release()

    if raw_path and raw_path.exists() and raw_path.stat().st_size > 0:
        logger.info("[RECORD] raw clip saved file=%s", raw_path.name)
        uploaded = upload_event_video_safe(config, raw_path, camera_name, thumbnail_path=extract_video_thumbnail(raw_path), camera_config=camera)
        cleanup_recording_if_needed(camera, raw_path, uploaded)


def capture_snapshot(config: dict[str, Any], output_path: Path = SNAPSHOT_PATH) -> Path:
    """Capture a single snapshot. Uses top-level rtsp_url or first enabled camera."""
    rtsp_url = str(config.get("rtsp_url", "")).strip()
    if not rtsp_url:
        cameras = normalize_cameras(config)
        enabled = [c for c in cameras if c.get("enabled") and c.get("rtsp_url")]
        if enabled:
            rtsp_url = str(enabled[0]["rtsp_url"]).strip()
    if not rtsp_url:
        raise ValueError("No RTSP URL configured (set rtsp_url or add a camera with RTSP)")
    return capture_rtsp_snapshot(rtsp_url, output_path)


def capture_go2rtc_snapshot(config: dict[str, Any], camera: dict[str, Any], output_path: Path) -> Path:
    content, src = fetch_go2rtc_frame_bytes(config, camera, timeout=10, attempts=4)
    logger.info("[SNAPSHOT] go2rtc src=%s", src)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(content)
    return output_path


def read_go2rtc_frame(config: dict[str, Any], camera: dict[str, Any]):
    import cv2
    import numpy as np

    content, _src = fetch_go2rtc_frame_bytes(config, camera, timeout=8, attempts=3)
    image = np.frombuffer(content, dtype=np.uint8)
    frame = cv2.imdecode(image, cv2.IMREAD_COLOR)
    if frame is None:
        raise RuntimeError("Could not decode go2rtc JPEG frame")
    return frame


def capture_camera_snapshot(config: dict[str, Any], index: int) -> Path:
    camera = get_camera(config, index)
    output_path = camera_snapshot_path(index)
    if has_go2rtc_frame_source(config, camera):
        try:
            return capture_go2rtc_snapshot(config, camera, output_path)
        except (requests.RequestException, ValueError) as exc:
            if not str(camera.get("rtsp_url", "")).strip():
                raise
            logger.warning("[SNAPSHOT] go2rtc failed, falling back to RTSP: %s", exc)
    return capture_rtsp_snapshot(str(camera.get("rtsp_url", "")).strip(), output_path)


def mjpeg_frames(rtsp_url: str):
    import cv2
    cap = cv2.VideoCapture(rtsp_url)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
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


def process_camera_verification(
    config: dict[str, Any],
    index: int,
    image_path: Path,
    confidence: float,
    last_alert: dict[int | str, float],
    alert_key: int | str,
    event_source: str = "verified",
) -> dict[str, Any]:
    camera = get_camera(config, index)
    camera_name = str(camera["name"])
    ai_result = "SAFE"
    ai_description = ""
    raw = ""
    try:
        ai_result, ai_description, raw = verify_scene(image_path, config, camera)
        set_state(last_ai_result=ai_result, last_verify_at=now_iso(), last_error="", last_camera=camera_name)
        log_event(
            config,
            event_source,
            image_path=image_path,
            camera_config=camera,
            camera=camera_name,
            confidence=confidence,
            ai_result=ai_result,
            ai_raw=ai_description,
            ai_response=raw,
            message=ai_description,
        )
    except Exception as exc:
        set_state(last_error=str(exc), last_verify_at=now_iso(), last_camera=camera_name)
        log_event(config, "ai_error", image_path=image_path, camera_config=camera, camera=camera_name, confidence=confidence, error=str(exc))
        return {"success": False, "camera": camera_name, "error": str(exc), "result": ai_result}

    if ai_result == "EMERGENCY":
        now = time.time()
        if now - last_alert.get(alert_key, 0.0) > float(config["alert_cooldown"]):
            try:
                send_telegram(
                    image_path,
                    alert_message(camera_name, ai_description),
                    config,
                )
                last_alert[alert_key] = now
                set_state(last_alert_at=now_iso())
                log_event(config, "telegram_sent", image_path=image_path, camera_config=camera, camera=camera_name, confidence=confidence, ai_result=ai_result)
            except Exception as exc:
                set_state(last_error=str(exc), last_camera=camera_name)
                log_event(config, "telegram_error", image_path=image_path, camera_config=camera, camera=camera_name, confidence=confidence, error=str(exc))
        else:
            log_event(config, "cooldown", image_path=image_path, camera_config=camera, camera=camera_name, confidence=confidence, ai_result=ai_result)

    return {
        "success": True,
        "camera": camera_name,
        "result": ai_result,
        "description": ai_description,
        "raw": raw,
    }


def capture_latest_frames(index: int, config: dict[str, Any], camera: dict[str, Any], holder: dict[str, Any], lock: threading.Lock) -> None:
    import cv2
    camera_name = str(camera["name"])
    rtsp_url = str(camera.get("rtsp_url", ""))
    use_go2rtc = has_go2rtc_frame_source(config, camera)
    cap = None if use_go2rtc else cv2.VideoCapture(rtsp_url)
    if cap is not None:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    last_reconnect_event = 0.0
    go2rtc_frame_interval = max(float(config.get("go2rtc_frame_interval", 1.0) or 1.0), float(config.get("loop_sleep", 0.2) or 0.2))
    consecutive_failures = 0

    try:
        while not stop_event.is_set():
            if use_go2rtc:
                try:
                    frame = read_go2rtc_frame(config, camera)
                    ok = True
                except Exception as exc:
                    ok = False
                    frame = None
                    last_error = str(exc)
            else:
                ok, frame = cap.read()
                last_error = "RTSP read failed"
            if not ok:
                consecutive_failures += 1
                now = time.time()
                if now - last_reconnect_event > 30:
                    source = "go2rtc" if use_go2rtc else "RTSP"
                    logger.warning("[%s] reconnect stream camera=%s error=%s", source.upper(), camera_name, last_error)
                    set_state(last_error=f"{source} read failed for {camera_name}, reconnecting (consecutive_failures={consecutive_failures})", last_camera=camera_name)
                    insert_event("stream_reconnect", camera=camera_name, message=f"{last_error} (failures: {consecutive_failures})")
                    last_reconnect_event = now
                if cap is not None:
                    cap.release()
                
                # Exponential backoff: start at 2s, double each time up to a maximum of 30s
                backoff_sleep = min(2.0 ** consecutive_failures, 30.0)
                time.sleep(backoff_sleep)
                
                if not use_go2rtc:
                    cap = cv2.VideoCapture(rtsp_url)
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                continue

            consecutive_failures = 0
            with lock:
                holder["frame"] = frame
                holder["time"] = time.time()
                holder["seq"] = int(holder.get("seq", 0)) + 1

            if use_go2rtc:
                time.sleep(go2rtc_frame_interval)
    finally:
        if cap is not None:
            cap.release()


def _enabled_monitor_cameras(config: dict[str, Any]) -> list[dict[str, Any]]:
    all_cameras = [camera for camera in normalize_cameras(config) if camera.get("enabled")]
    return [
        camera
        for camera in all_cameras
        if camera.get("rtsp_url") or has_go2rtc_frame_source(config, camera)
    ]


def _enabled_rtsp_cameras(config: dict[str, Any]) -> list[dict[str, Any]]:
    return _enabled_monitor_cameras(config)


def has_enabled_rtsp_camera(config: dict[str, Any]) -> bool:
    return bool(_enabled_monitor_cameras(config))


def _monitor_loop(config: dict[str, Any]) -> None:
    cameras = _enabled_monitor_cameras(config)
    if not cameras:
        message = "No enabled cameras with RTSP URLs or go2rtc sources"
        set_state(running=False, last_error=message)
        logger.warning("[MONITOR] %s", message)
        return
        
    import cv2
    from ultralytics import YOLO

    require_config(config, ["yolo_model"])
    logger.info("[MONITOR] loading YOLO model=%s imgsz=%s", config["yolo_model"], config["yolo_imgsz"])
    model = YOLO(config["yolo_model"])
    
    frame_holders: list[dict[str, Any]] = [{"frame": None, "time": 0.0, "seq": 0} for _ in cameras]
    frame_locks = [threading.Lock() for _ in cameras]
    capture_threads = [
        threading.Thread(
            target=capture_latest_frames,
            args=(index, config, camera, frame_holders[index], frame_locks[index]),
            daemon=True,
        )
        for index, camera in enumerate(cameras)
    ]
    frame_counts = [0 for _ in cameras]
    last_seen_seq = [0 for _ in cameras]
    last_verify = [0.0 for _ in cameras]
    last_alert: dict[int | str, float] = {index: 0.0 for index in range(len(cameras))}
    last_record = [0.0 for _ in cameras]
    last_yolo_log = [0.0 for _ in cameras]
    total_frames = 0
    set_state(running=True, started_at=now_iso(), last_error="", mode="yolo")
    for thread in capture_threads:
        thread.start()
    insert_event("started", message=f"Monitor started for {len(cameras)} camera(s), mode=yolo")

    try:
        while not stop_event.is_set():
            for index, camera in enumerate(cameras):
                camera_name = str(camera["name"])
                with frame_locks[index]:
                    frame = frame_holders[index]["frame"]
                    seq = int(frame_holders[index].get("seq", 0))

                if frame is None or seq == last_seen_seq[index]:
                    continue

                last_seen_seq[index] = seq
                frame_counts[index] += 1
                total_frames += 1
                set_state(frames=total_frames, last_camera=camera_name)
                if frame_counts[index] % int(config["frame_skip"]) != 0:
                    continue

                now = time.time()
                person_detected = False
                best_confidence = 0.0
                person_count = 0
                infer_start = time.perf_counter()
                
                results = model.predict(
                    frame,
                    verbose=False,
                    conf=float(config["confidence"]),
                    imgsz=int(config["yolo_imgsz"]),
                    classes=[0],
                )
                for result in results:
                    for box in result.boxes:
                        if int(box.cls[0]) == 0:
                            person_detected = True
                            person_count += 1
                            best_confidence = max(best_confidence, float(box.conf[0]))
                infer_ms = (time.perf_counter() - infer_start) * 1000

                if person_detected or now - last_yolo_log[index] > 10:
                    logger.info(
                        "[YOLO] camera=%s people=%s best=%.2f infer=%.0fms frame=%s",
                        camera_name,
                        person_count,
                        best_confidence,
                        infer_ms,
                        frame_counts[index],
                    )
                    last_yolo_log[index] = now

                if person_detected:
                    set_state(last_person_confidence=best_confidence, last_error="", last_camera=camera_name)
                    logger.info("[PERSON] camera=%s confidence=%.2f", camera_name, best_confidence)
                    if (
                        teldrive.enabled(config)
                        and camera.get("teldrive_record_enabled")
                        and now - last_record[index] > float(camera.get("record_cooldown", config.get("teldrive_record_cooldown", 300)))
                    ):
                        last_record[index] = now
                        threading.Thread(
                            target=record_and_upload_clip,
                            args=(config.copy(), camera.copy(), frame_holders[index], frame_locks[index]),
                            daemon=True,
                        ).start()
                    
                    if now - last_verify[index] > float(config["verify_interval"]):
                        DATA_DIR.mkdir(parents=True, exist_ok=True)
                        verify_path = camera_snapshot_path(index)
                        cv2.imwrite(str(verify_path), frame)
                        cv2.imwrite(str(SNAPSHOT_PATH), frame)
                        try:
                            ai_result, ai_description, raw = verify_scene(verify_path, config, camera)
                            last_verify[index] = now
                            set_state(last_ai_result=ai_result, last_verify_at=now_iso(), last_error="")
                            log_event(
                                config,
                                "verified",
                                image_path=verify_path,
                                camera_config=camera,
                                camera=camera_name,
                                confidence=best_confidence,
                                ai_result=ai_result,
                                ai_raw=ai_description,
                                ai_response=raw,
                                message=ai_description,
                            )
                        except Exception as exc:
                            last_verify[index] = now
                            set_state(last_error=str(exc), last_verify_at=now_iso())
                            log_event(config, "ai_error", image_path=verify_path, camera_config=camera, camera=camera_name, confidence=best_confidence, error=str(exc))
                            ai_result = "SAFE"

                        if ai_result == "EMERGENCY":
                            if now - last_alert[index] > float(config["alert_cooldown"]):
                                try:
                                    send_telegram(
                                        verify_path,
                                        alert_message(camera_name, ai_description),
                                        config,
                                    )
                                    last_alert[index] = now
                                    set_state(last_alert_at=now_iso())
                                    log_event(config, "telegram_sent", image_path=verify_path, camera_config=camera, camera=camera_name, confidence=best_confidence, ai_result=ai_result)
                                except Exception as exc:
                                    set_state(last_error=str(exc))
                                    log_event(config, "telegram_error", image_path=verify_path, camera_config=camera, camera=camera_name, confidence=best_confidence, error=str(exc))
                            else:
                                log_event(config, "cooldown", image_path=verify_path, camera_config=camera, camera=camera_name, confidence=best_confidence, ai_result=ai_result)

            time.sleep(float(config["loop_sleep"]))
    except Exception as exc:
        logger.exception("[MONITOR] failed")
        set_state(last_error=str(exc))
        insert_event("monitor_error", error=str(exc))
    finally:
        stop_event.set()
        for thread in capture_threads:
            thread.join(timeout=2)
        set_state(running=False)
        insert_event("stopped", message="Monitor stopped")


def start_monitor(config: dict[str, Any]) -> str:
    global worker_thread
    with monitor_lock:
        if worker_thread and worker_thread.is_alive():
            return "already running"
        if not _enabled_monitor_cameras(config):
            message = "No enabled cameras with RTSP URLs or go2rtc sources"
            set_state(running=False, last_error=message)
            raise ValueError(message)
        stop_event.clear()
        worker_thread = threading.Thread(target=_monitor_loop, args=(config,), daemon=True)
        worker_thread.start()
        return "started"


def stop_monitor(wait: bool = False) -> None:
    global worker_thread
    stop_event.set()
    thread = worker_thread
    if wait and thread and thread.is_alive():
        thread.join(timeout=8)
    if thread and not thread.is_alive():
        worker_thread = None


def restart_monitor(config: dict[str, Any]) -> None:
    global worker_thread
    with monitor_lock:
        thread = worker_thread
        if not thread or not thread.is_alive():
            return
        stop_event.set()
        thread.join(timeout=8)
        if thread.is_alive():
            message = "Previous monitor did not stop within 8 seconds"
            set_state(last_error=message)
            insert_event("restart_error", error=message)
            raise RuntimeError(message)
        worker_thread = None
        cameras = _enabled_monitor_cameras(config)
        if not cameras:
            message = "Monitor stopped because no enabled cameras with RTSP URLs or go2rtc sources remain"
            set_state(running=False, last_error=message)
            insert_event("config_applied", message=message)
            return
        stop_event.clear()
        new_thread = threading.Thread(target=_monitor_loop, args=(config,), daemon=True)
        worker_thread = new_thread
        new_thread.start()
        insert_event("config_applied", message="Monitor restarted with new settings")
