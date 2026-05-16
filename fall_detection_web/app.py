"""Main FastAPI application — Fall Detection Web."""

from __future__ import annotations

import logging
import secrets
import shutil
import psutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Body, Depends, FastAPI, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import ai
import auth
import config
import db
import monitor

logger = logging.getLogger("fall_detection_web")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"

# Setup Jinja2 templates
templates = Jinja2Templates(directory=str(ROOT / "templates"))

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    db.init_db()
    db.delete_old_events(7)        # clean up old events/images at startup
    config.migrate_config_json()   # one-time: config.json → DB
    current_config = config.read_config()
    
    # Init auth secret
    jwt_secret = secrets.token_urlsafe(32)
    auth.configure_secret(jwt_secret)
    
    # Create default admin if no users
    if not db.list_users():
        logger.info("No users found. Creating default admin: admin/admin")
        db.create_user("admin", auth.hash_password("admin"))
    
    # Auto-start monitor
    try:
        if monitor.start_monitor(current_config) == "started":
            logger.info("Auto-started YOLO monitor on boot.")
    except Exception as exc:
        logger.error("Could not auto-start monitor: %s", exc)
        
    yield
    # Shutdown
    monitor.stop_monitor(wait=True)


app = FastAPI(title="Fall Detection Web", lifespan=lifespan)

# Mount static files
DATA_DIR.mkdir(parents=True, exist_ok=True)
db.EVENT_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/api/event-image", StaticFiles(directory=str(db.EVENT_IMAGES_DIR)), name="event-image")

# ──────────────────────────────────────────────
# UI Routes
# ──────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/auth/login")
async def login(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
):
    user = db.get_user(username)
    if not user or not auth.verify_password(password, str(user["password_hash"])):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Sai tài khoản hoặc mật khẩu.", "username": username},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    token = auth.create_token(username)
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="session",
        value=token,
        httponly=True,
        max_age=8 * 3600,
        samesite="lax",
    )
    return response

@app.post("/auth/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("session")
    return response

@app.get("/", response_class=HTMLResponse)
async def index_page(request: Request, _: str = Depends(auth.require_auth)):
    return templates.TemplateResponse("index.html", {"request": request})


# ──────────────────────────────────────────────
# API Routes
# ──────────────────────────────────────────────

@app.get("/api/config")
async def get_config(_: str = Depends(auth.require_auth)):
    return {"success": True, "config": config.read_config()}

@app.post("/api/config")
async def save_config(new_config: dict[str, Any] = Body(...), _: str = Depends(auth.require_auth)):
    try:
        updated = config.write_config(new_config)
        monitor.restart_monitor(updated)
        return {"success": True, "config": updated, "message": "Settings saved and monitor restarted"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/api/status")
async def get_status(_: str = Depends(auth.require_auth)):
    disk = psutil.disk_usage('/')
    return {
        "success": True,
        "status": monitor.read_state(),
        "event_count": db.count_events(),
        "system": {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "ram_percent": psutil.virtual_memory().percent,
            "disk_percent": disk.percent,
            "disk_used_gb": round(disk.used / (1024**3), 1),
            "disk_total_gb": round(disk.total / (1024**3), 1),
        }
    }

@app.post("/api/start")
async def api_start_monitor(_: str = Depends(auth.require_auth)):
    try:
        result = monitor.start_monitor(config.read_config())
        return {"success": True, "message": f"Monitor {result}"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.post("/api/stop")
async def api_stop_monitor(_: str = Depends(auth.require_auth)):
    monitor.stop_monitor()
    return {"success": True, "message": "Monitor stopped"}

@app.get("/api/events")
async def get_events(_: str = Depends(auth.require_auth)):
    return {"success": True, "events": db.get_events()}

@app.delete("/api/events")
async def clear_events(_: str = Depends(auth.require_auth)):
    deleted = db.clear_events()
    return {"success": True, "message": f"Deleted {deleted} events"}

@app.post("/api/capture")
async def capture(_: str = Depends(auth.require_auth)):
    try:
        c = config.read_config()
        monitor.capture_snapshot(c)
        return {"success": True, "message": "Captured snapshot"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/api/camera/snapshot")
async def get_camera_snapshot(index: int, _: str = Depends(auth.require_auth)):
    try:
        c = config.read_config()
        path = monitor.capture_camera_snapshot(c, index)
        return Response(content=path.read_bytes(), media_type="image/jpeg")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/api/camera/video")
async def get_camera_video(index: int, _: str = Depends(auth.require_auth)):
    try:
        c = config.read_config()
        camera = config.get_camera(c, index)
        rtsp_url = str(camera.get("rtsp_url", "")).strip()
        if not rtsp_url:
            raise ValueError("No RTSP URL configured for this camera")
        from fastapi.responses import StreamingResponse
        return StreamingResponse(
            monitor.mjpeg_frames(rtsp_url),
            media_type="multipart/x-mixed-replace; boundary=frame"
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.post("/api/test-ai")
async def test_ai(_: str = Depends(auth.require_auth)):
    try:
        c = config.read_config()
        path = monitor.SNAPSHOT_PATH
        if not path.exists():
            monitor.capture_snapshot(c, path)
        result, desc, raw = ai.verify_scene(path, c)
        return {"success": True, "result": result, "description": desc, "raw": raw}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.post("/api/test-ai-camera")
async def test_ai_camera(index: int, _: str = Depends(auth.require_auth)):
    try:
        c = config.read_config()
        path = monitor.capture_camera_snapshot(c, index)
        result, desc, raw = ai.verify_scene(path, c)
        camera_name = str(config.get_camera(c, index).get("name", f"Camera {index}"))
        return {"success": True, "camera": camera_name, "result": result, "description": desc, "raw": raw}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.post("/api/test-telegram")
async def test_telegram(_: str = Depends(auth.require_auth)):
    try:
        c = config.read_config()
        path = monitor.SNAPSHOT_PATH
        if not path.exists():
            monitor.capture_snapshot(c, path)
        ai.send_telegram(path, "🔧 Test notification from Fall Detection Web", c)
        return {"success": True, "message": "Telegram message sent"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.post("/api/test-ai-upload")
async def test_ai_upload(request: Request, _: str = Depends(auth.require_auth)):
    try:
        form = await request.form()
        upload = form.get("file")
        if not hasattr(upload, "read"):
            raise ValueError("No file uploaded")
        content = await upload.read()
        if len(content) > 10 * 1024 * 1024:
            raise ValueError("File exceeds 10MB limit")
        
        test_path = DATA_DIR / "upload_test.jpg"
        test_path.write_bytes(content)
        
        c = config.read_config()
        result, desc, raw = ai.verify_scene(test_path, c)
        return {"success": True, "result": result, "description": desc, "raw": raw}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
