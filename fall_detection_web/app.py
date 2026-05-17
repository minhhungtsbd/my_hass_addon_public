"""Main FastAPI application — Fall Detection Web."""

from __future__ import annotations

import logging
import secrets
import psutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Body, Depends, FastAPI, Form, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
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
    
    # Init auth secret from config or env
    jwt_secret = current_config.get("jwt_secret")
    if not jwt_secret:
        # Fallback: check persistent file
        secret_file = DATA_DIR / ".secret_key"
        if secret_file.exists():
            jwt_secret = secret_file.read_text(encoding="utf-8").strip()
        else:
            jwt_secret = secrets.token_urlsafe(32)
            secret_file.write_text(jwt_secret, encoding="utf-8")
    
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

DATA_DIR.mkdir(parents=True, exist_ok=True)
db.EVENT_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

@app.get("/favicon.ico")
async def favicon():
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
        <rect width="100" height="100" rx="20" fill="#12a9f5"/>
        <text x="50" y="70" font-size="65" font-family="Arial" fill="#fff" text-anchor="middle">🛡️</text>
    </svg>'''
    return Response(content=svg, media_type="image/svg+xml")

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
    remember: bool = Form(False),
):
    user = db.get_user(username)
    if not user or not auth.verify_password(password, str(user["password_hash"])):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Sai tài khoản hoặc mật khẩu.", "username": username},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    
    expire_hours = 24 * 30 if remember else 8
    token = auth.create_token(username, expire_hours=expire_hours)
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="session",
        value=token,
        httponly=True,
        max_age=expire_hours * 3600,
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


@app.get("/api/event-image/{filename}")
async def event_image(filename: str, _: str = Depends(auth.require_auth)):
    safe_name = Path(filename).name
    if safe_name != filename or not safe_name.lower().endswith(".jpg"):
        raise HTTPException(status_code=404, detail="Image not found")
    path = db.EVENT_IMAGES_DIR / safe_name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(
        path,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, no-store"},
    )


# ──────────────────────────────────────────────
# API Routes
# ──────────────────────────────────────────────

@app.post("/api/user/update")
async def update_user_credentials(
    response: Response,
    payload: dict[str, str] = Body(...),
    username: str = Depends(auth.require_auth)
):
    new_user = payload.get("username", "").strip()
    new_pass = payload.get("password", "")
    if not new_user or not new_pass:
        raise HTTPException(status_code=400, detail="Username and password are required")
    
    try:
        db.update_user(username, new_user, auth.hash_password(new_pass))
        # Issuing new token since username changed
        new_token = auth.create_token(new_user)
        response.set_cookie(
            key="session",
            value=new_token,
            httponly=True,
            samesite="lax",
            max_age=auth._SESSION_HOURS * 3600
        )
        return {"success": True, "message": "Credentials updated"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Failed to update credentials. Username might already exist.")

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
async def get_events(
    page: int = 1,
    limit: int = 50,
    ai_result: str | None = None,
    camera: str | None = None,
    _: str = Depends(auth.require_auth)
):
    if page < 1:
        page = 1
    if limit < 1 or limit > 500:
        limit = 50
        
    # Clean up empty strings from query params
    if ai_result == "" or ai_result == "All":
        ai_result = None
    if camera == "" or camera == "All":
        camera = None
        
    offset = (page - 1) * limit
    events = db.get_events(limit=limit, offset=offset, ai_result=ai_result, camera=camera)
    total = db.get_events_total(ai_result=ai_result, camera=camera)
    
    return {
        "success": True, 
        "events": events,
        "total": total,
        "page": page,
        "limit": limit
    }

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
        result, desc, raw = ai.verify_scene(path, c, camera=None)
        return {"success": True, "result": result, "description": desc, "raw": raw}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.post("/api/test-ai-camera")
async def test_ai_camera(index: int, _: str = Depends(auth.require_auth)):
    try:
        c = config.read_config()
        camera = config.get_camera(c, index)
        path = monitor.capture_camera_snapshot(c, index)
        result, desc, raw = ai.verify_scene(path, c, camera=camera)
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
        result, desc, raw = ai.verify_scene(test_path, c, camera=None)
        return {"success": True, "result": result, "description": desc, "raw": raw}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
