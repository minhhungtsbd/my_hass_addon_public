"""Monitor loop — YOLO local inference for person detection."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

import requests

from ai import send_telegram, verify_scene
from config import get_camera, normalize_cameras, require_config
from db import insert_event, now_iso

logger = logging.getLogger("fall_detection_web")

DATA_DIR = Path(__file__).resolve().parent / "data"
SNAPSHOT_PATH = DATA_DIR / "latest.jpg"

state_lock = threading.Lock()
stop_event = threading.Event()
worker_thread: threading.Thread | None = None
monitor_lock = threading.Lock()


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
    base_url = str(config.get("go2rtc_url", "")).strip().rstrip("/")
    src = str(camera.get("go2rtc_src", "")).strip()
    if not base_url or not src:
        raise ValueError("go2rtc URL or camera src is empty")
    logger.info("[SNAPSHOT] go2rtc src=%s", src)
    response = requests.get(
        f"{base_url}/api/frame.jpeg",
        params={"src": src},
        timeout=10,
    )
    response.raise_for_status()
    if not response.content:
        raise ValueError("go2rtc returned empty snapshot")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(response.content)
    return output_path


def capture_camera_snapshot(config: dict[str, Any], index: int) -> Path:
    camera = get_camera(config, index)
    output_path = camera_snapshot_path(index)
    if str(config.get("go2rtc_url", "")).strip() and str(camera.get("go2rtc_src", "")).strip():
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
        insert_event(
            event_source,
            image_path=image_path,
            camera=camera_name,
            confidence=confidence,
            ai_result=ai_result,
            ai_raw=ai_description,
            ai_response=raw,
            message=ai_description,
        )
    except Exception as exc:
        set_state(last_error=str(exc), last_verify_at=now_iso(), last_camera=camera_name)
        insert_event("ai_error", image_path=image_path, camera=camera_name, confidence=confidence, error=str(exc))
        return {"success": False, "camera": camera_name, "error": str(exc), "result": ai_result}

    if ai_result == "EMERGENCY":
        now = time.time()
        if now - last_alert.get(alert_key, 0.0) > float(config["alert_cooldown"]):
            try:
                send_telegram(
                    image_path,
                    f"⚠️ AI phát hiện người có thể bị té ngã hoặc gặp nguy hiểm!\nCamera: {camera_name}",
                    config,
                )
                last_alert[alert_key] = now
                set_state(last_alert_at=now_iso())
                insert_event("telegram_sent", image_path=image_path, camera=camera_name, confidence=confidence, ai_result=ai_result)
            except Exception as exc:
                set_state(last_error=str(exc), last_camera=camera_name)
                insert_event("telegram_error", image_path=image_path, camera=camera_name, confidence=confidence, error=str(exc))
        else:
            insert_event("cooldown", image_path=image_path, camera=camera_name, confidence=confidence, ai_result=ai_result)

    return {
        "success": True,
        "camera": camera_name,
        "result": ai_result,
        "description": ai_description,
        "raw": raw,
    }


def capture_latest_frames(index: int, camera: dict[str, Any], holder: dict[str, Any], lock: threading.Lock) -> None:
    import cv2
    camera_name = str(camera["name"])
    rtsp_url = str(camera["rtsp_url"])
    cap = cv2.VideoCapture(rtsp_url)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    last_reconnect_event = 0.0

    try:
        while not stop_event.is_set():
            ok, frame = cap.read()
            if not ok:
                now = time.time()
                if now - last_reconnect_event > 30:
                    logger.warning("[RTSP] reconnect stream camera=%s", camera_name)
                    set_state(last_error=f"RTSP read failed for {camera_name}, reconnecting", last_camera=camera_name)
                    insert_event("rtsp_reconnect", camera=camera_name, message="RTSP read failed")
                    last_reconnect_event = now
                cap.release()
                time.sleep(0.5)
                cap = cv2.VideoCapture(rtsp_url)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                continue

            with lock:
                holder["frame"] = frame
                holder["time"] = time.time()
                holder["seq"] = int(holder.get("seq", 0)) + 1
    finally:
        cap.release()


def _monitor_loop(config: dict[str, Any]) -> None:
    all_cameras = [camera for camera in normalize_cameras(config) if camera.get("enabled")]
    cameras = [camera for camera in all_cameras if camera.get("rtsp_url")]
    
    if not cameras:
        raise ValueError("No enabled cameras with RTSP URLs")
        
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
            args=(index, camera, frame_holders[index], frame_locks[index]),
            daemon=True,
        )
        for index, camera in enumerate(cameras)
    ]
    frame_counts = [0 for _ in cameras]
    last_seen_seq = [0 for _ in cameras]
    last_verify = [0.0 for _ in cameras]
    last_alert: dict[int | str, float] = {index: 0.0 for index in range(len(cameras))}
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
                            best_confidence = max(best_confidence, float(box.conf[0]))

                if person_detected:
                    set_state(last_person_confidence=best_confidence, last_error="", last_camera=camera_name)
                    logger.info("[PERSON] camera=%s confidence=%.2f", camera_name, best_confidence)
                    
                    if now - last_verify[index] > float(config["verify_interval"]):
                        DATA_DIR.mkdir(parents=True, exist_ok=True)
                        verify_path = camera_snapshot_path(index)
                        cv2.imwrite(str(verify_path), frame)
                        cv2.imwrite(str(SNAPSHOT_PATH), frame)
                        try:
                            ai_result, ai_description, raw = verify_scene(verify_path, config, camera)
                            last_verify[index] = now
                            set_state(last_ai_result=ai_result, last_verify_at=now_iso(), last_error="")
                            insert_event(
                                "verified",
                                image_path=verify_path,
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
                            insert_event("ai_error", image_path=verify_path, camera=camera_name, confidence=best_confidence, error=str(exc))
                            ai_result = "SAFE"

                        if ai_result == "EMERGENCY":
                            if now - last_alert[index] > float(config["alert_cooldown"]):
                                try:
                                    send_telegram(
                                        verify_path,
                                        f"⚠️ AI phát hiện người có thể bị té ngã hoặc gặp nguy hiểm!\nCamera: {camera_name}",
                                        config,
                                    )
                                    last_alert[index] = now
                                    set_state(last_alert_at=now_iso())
                                    insert_event("telegram_sent", image_path=verify_path, camera=camera_name, confidence=best_confidence, ai_result=ai_result)
                                except Exception as exc:
                                    set_state(last_error=str(exc))
                                    insert_event("telegram_error", image_path=verify_path, camera=camera_name, confidence=best_confidence, error=str(exc))
                            else:
                                insert_event("cooldown", image_path=verify_path, camera=camera_name, confidence=best_confidence, ai_result=ai_result)

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
        stop_event.clear()
        new_thread = threading.Thread(target=_monitor_loop, args=(config,), daemon=True)
        globals()["worker_thread"] = new_thread
        new_thread.start()
        insert_event("config_applied", message="Monitor restarted with new settings")

