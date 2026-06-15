"""SQLite database layer — events and users."""

from __future__ import annotations

import json
import logging
import random
import shutil
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Generator
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "fall_detection.db"
EVENT_IMAGES_DIR = DATA_DIR / "event_images"
# Legacy JSONL path for one-time migration
LEGACY_EVENTS_PATH = DATA_DIR / "events.jsonl"

LOCAL_TZ = timezone(timedelta(hours=7))
MAX_EVENTS = 5000       # Maximum events to keep in DB
PRUNE_BATCH = 500       # How many to prune when over limit
IMAGE_MAX_AGE_SECONDS = 86400  # 24 hours

logger = logging.getLogger("fall_detection_web")


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    EVENT_IMAGES_DIR.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_conn() -> Generator[sqlite3.Connection, None, None]:
    ensure_data_dir()
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create tables if they don't exist and run one-time migrations."""
    ensure_data_dir()
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                time        TEXT NOT NULL,
                time_local  TEXT,
                status      TEXT NOT NULL,
                camera      TEXT,
                confidence  REAL,
                ai_result   TEXT,
                ai_raw      TEXT,
                ai_response TEXT,
                message     TEXT,
                error       TEXT,
                image_file  TEXT,
                teldrive_image_id TEXT,
                teldrive_image_name TEXT,
                teldrive_image_path TEXT,
                teldrive_video_id TEXT,
                teldrive_video_name TEXT,
                teldrive_video_path TEXT
            );

            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at    TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS settings (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_events_time ON events (time DESC);
        """)
        _ensure_column(conn, "events", "teldrive_image_id", "TEXT")
        _ensure_column(conn, "events", "teldrive_image_name", "TEXT")
        _ensure_column(conn, "events", "teldrive_image_path", "TEXT")
        _ensure_column(conn, "events", "teldrive_video_id", "TEXT")
        _ensure_column(conn, "events", "teldrive_video_name", "TEXT")
        _ensure_column(conn, "events", "teldrive_video_path", "TEXT")
    _migrate_jsonl()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, col_type: str) -> None:
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")


def _migrate_jsonl() -> None:
    """One-time migration: import legacy events.jsonl into SQLite."""
    if not LEGACY_EVENTS_PATH.exists():
        return
    migrated_path = LEGACY_EVENTS_PATH.with_suffix(".jsonl.migrated")
    if migrated_path.exists():
        return
    logger.info("[DB] Migrating legacy events.jsonl to SQLite…")
    rows: list[tuple] = []
    for line in LEGACY_EVENTS_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        rows.append((
            event.get("time", ""),
            event.get("time_local", ""),
            event.get("status", ""),
            event.get("camera", ""),
            event.get("confidence"),
            event.get("ai_result", ""),
            event.get("ai_raw", ""),
            event.get("ai_response", ""),
            event.get("message", ""),
            event.get("error", ""),
            event.get("image_file", ""),
        ))
    if rows:
        with get_conn() as conn:
            conn.executemany(
                "INSERT INTO events (time,time_local,status,camera,confidence,ai_result,ai_raw,ai_response,message,error,image_file) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                rows,
            )
        logger.info("[DB] Migrated %d events from JSONL", len(rows))
    # Mark migration done by renaming
    LEGACY_EVENTS_PATH.rename(migrated_path)


# ──────────────────────────────────────────────
# Events
# ──────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def local_iso() -> str:
    return datetime.now(LOCAL_TZ).isoformat(timespec="seconds")


def cleanup_event_images() -> None:
    ensure_data_dir()
    cutoff = time.time() - IMAGE_MAX_AGE_SECONDS
    for path in EVENT_IMAGES_DIR.glob("*.jpg"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            continue


def save_event_image(source_path: Path | None, status_name: str) -> str:
    if not source_path or not source_path.exists():
        return ""
    cleanup_event_images()
    # Thỉnh thoảng dọn dẹp các event quá 7 ngày
    if random.random() < 0.05:
        delete_old_events(7)
        
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    safe_status = "".join(ch for ch in status_name if ch.isalnum() or ch in ("_", "-")) or "event"
    target = EVENT_IMAGES_DIR / f"{stamp}_{safe_status}.jpg"
    
    # Nén ảnh bằng OpenCV để giảm dung lượng
    try:
        import cv2
        img = cv2.imread(str(source_path))
        if img is not None:
            h, w = img.shape[:2]
            if w > 1280:
                new_w = 1280
                new_h = int(h * (1280 / w))
                img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
            cv2.imwrite(str(target), img, [cv2.IMWRITE_JPEG_QUALITY, 70])
        else:
            shutil.copyfile(source_path, target)
    except Exception as e:
        logger.warning(f"[DB] Lỗi khi nén ảnh {source_path}, sẽ copy raw: {e}")
        shutil.copyfile(source_path, target)
        
    return target.name


def _prune_events(conn: sqlite3.Connection) -> None:
    count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    if count > MAX_EVENTS:
        to_delete = count - MAX_EVENTS + PRUNE_BATCH
        rows = conn.execute(
            "SELECT image_file FROM events ORDER BY id ASC LIMIT ?",
            (to_delete,),
        ).fetchall()
        for row in rows:
            img = str(row[0] or "").strip()
            if img:
                try:
                    (EVENT_IMAGES_DIR / img).unlink()
                except OSError:
                    pass
        conn.execute(
            "DELETE FROM events WHERE id IN (SELECT id FROM events ORDER BY id ASC LIMIT ?)",
            (to_delete,),
        )
        logger.info("[DB] Pruned %d old events", to_delete)


def invalidate_event_caches() -> None:
    try:
        import config as _config
        import redis_cache as _redis_cache
        c = _config.read_config()
        _redis_cache.clear_cache_pattern("events:list:*", c)
        _redis_cache.clear_cache_pattern("recordings:list:*", c)
        _redis_cache.delete_cache("events:trends", c)
    except Exception as exc:
        logger.warning("[DB] Failed to invalidate Redis caches: %s", exc)


def insert_event(status_name: str, image_path: Path | None = None, save_image: bool = True, **fields: Any) -> dict[str, Any]:
    image_file = save_event_image(image_path, status_name) if save_image else ""
    t = str(fields.get("event_time") or now_iso())
    t_local = str(fields.get("event_time_local") or local_iso())
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO events (time,time_local,status,camera,confidence,ai_result,ai_raw,ai_response,message,error,image_file,teldrive_image_id,teldrive_image_name,teldrive_image_path,teldrive_video_id,teldrive_video_name,teldrive_video_path) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                t,
                t_local,
                status_name,
                fields.get("camera", ""),
                fields.get("confidence"),
                fields.get("ai_result", ""),
                fields.get("ai_raw", ""),
                fields.get("ai_response", ""),
                fields.get("message", ""),
                fields.get("error", ""),
                image_file,
                fields.get("teldrive_image_id", ""),
                fields.get("teldrive_image_name", ""),
                fields.get("teldrive_image_path", ""),
                fields.get("teldrive_video_id", ""),
                fields.get("teldrive_video_name", ""),
                fields.get("teldrive_video_path", ""),
            ),
        )
        event_id = cur.lastrowid
        _prune_events(conn)
    invalidate_event_caches()
    return {"id": event_id, "image_file": image_file}


def update_event_teldrive_image(event_id: int, file_data: dict[str, Any]) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE events SET teldrive_image_id=?, teldrive_image_name=?, teldrive_image_path=? WHERE id=?",
            (
                str(file_data.get("id", "")),
                str(file_data.get("name", "")),
                str(file_data.get("path", "")),
                event_id,
            ),
        )
    invalidate_event_caches()


def update_event_image(event_id: int, image_path: Path, status_name: str = "recording_thumb") -> str:
    image_file = save_event_image(image_path, status_name)
    if not image_file:
        return ""
    with get_conn() as conn:
        conn.execute("UPDATE events SET image_file=? WHERE id=?", (image_file, event_id))
    invalidate_event_caches()
    return image_file


def get_events(
    limit: int = 100, 
    offset: int = 0, 
    ai_result: str | None = None, 
    camera: str | None = None,
    status: str | None = None
) -> list[dict[str, Any]]:
    query = "SELECT * FROM events"
    params = []
    conditions = []
    
    if ai_result:
        conditions.append("ai_result = ?")
        params.append(ai_result)
    if camera:
        conditions.append("camera = ?")
        params.append(camera)
    if status:
        conditions.append("status = ?")
        params.append(status)
        
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
        
    query += " ORDER BY time DESC, id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    events: list[dict[str, Any]] = []
    for row in rows:
        event = dict(row)
        image_file = str(event.get("image_file") or "").strip()
        if event.get("teldrive_image_id") and event.get("teldrive_image_name"):
            name = quote(str(event["teldrive_image_name"]), safe="")
            event["image_url"] = f"/api/teldrive/file/{event['teldrive_image_id']}/{name}"
        elif image_file and (EVENT_IMAGES_DIR / image_file).exists():
            event["image_url"] = f"/api/event-image/{image_file}"
        events.append(event)
    return events


def get_recordings(
    limit: int = 100,
    offset: int = 0,
    camera: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict[str, Any]]:
    query = "SELECT * FROM events WHERE teldrive_video_id IS NOT NULL AND teldrive_video_id != ''"
    params: list[Any] = []
    if camera:
        query += " AND camera = ?"
        params.append(camera)
    if date_from:
        query += " AND time >= ?"
        params.append(date_from)
    if date_to:
        query += " AND time <= ?"
        params.append(date_to)
    query += " ORDER BY time DESC, id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    recordings = [dict(row) for row in rows]
    for item in recordings:
        name = quote(str(item["teldrive_video_name"]), safe="")
        item["video_url"] = f"/api/teldrive/file/{item['teldrive_video_id']}/{name}"
        
        image_file = str(item.get("image_file") or "").strip()
        if item.get("teldrive_image_id") and item.get("teldrive_image_name"):
            img_name = quote(str(item["teldrive_image_name"]), safe="")
            item["image_url"] = f"/api/teldrive/file/{item['teldrive_image_id']}/{img_name}"
        elif image_file and (EVENT_IMAGES_DIR / image_file).exists():
            item["image_url"] = f"/api/event-image/{image_file}"
    return recordings


def get_recordings_total(camera: str | None = None, date_from: str | None = None, date_to: str | None = None) -> int:
    query = "SELECT COUNT(*) FROM events WHERE teldrive_video_id IS NOT NULL AND teldrive_video_id != ''"
    params: list[Any] = []
    if camera:
        query += " AND camera = ?"
        params.append(camera)
    if date_from:
        query += " AND time >= ?"
        params.append(date_from)
    if date_to:
        query += " AND time <= ?"
        params.append(date_to)
    with get_conn() as conn:
        return conn.execute(query, params).fetchone()[0]


def get_uploaded_video_records() -> list[dict[str, str]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, camera, message, image_file, teldrive_image_id, teldrive_video_name FROM events "
            "WHERE teldrive_video_id IS NOT NULL AND teldrive_video_id != ''"
        ).fetchall()
    return [
        {
            "id": str(row["id"] or ""),
            "camera": str(row["camera"] or ""),
            "message": str(row["message"] or ""),
            "image_file": str(row["image_file"] or ""),
            "teldrive_image_id": str(row["teldrive_image_id"] or ""),
            "teldrive_video_name": str(row["teldrive_video_name"] or ""),
        }
        for row in rows
    ]


def get_events_total(ai_result: str | None = None, camera: str | None = None, status: str | None = None) -> int:
    query = "SELECT COUNT(*) FROM events"
    params = []
    conditions = []
    
    if ai_result:
        conditions.append("ai_result = ?")
        params.append(ai_result)
    if camera:
        conditions.append("camera = ?")
        params.append(camera)
    if status:
        conditions.append("status = ?")
        params.append(status)
        
    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    with get_conn() as conn:
        count = conn.execute(query, params).fetchone()[0]
    return count


def count_events() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]


def clear_events(camera: str | None = None, recordings_only: bool = False, exclude_recordings: bool = False) -> int:
    conditions = []
    params: list[Any] = []
    if camera:
        conditions.append("camera = ?")
        params.append(camera)
    if recordings_only:
        conditions.append("teldrive_video_id IS NOT NULL AND teldrive_video_id != ''")
    if exclude_recordings:
        conditions.append("(teldrive_video_id IS NULL OR teldrive_video_id = '')")
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""

    with get_conn() as conn:
        rows = conn.execute(f"SELECT image_file FROM events{where}", params).fetchall()
        deleted = conn.execute(f"DELETE FROM events{where}", params).rowcount

        remaining_images = {
            str(row[0] or "").strip()
            for row in conn.execute("SELECT image_file FROM events WHERE image_file IS NOT NULL AND image_file != ''").fetchall()
        }

    for row in rows:
        image_file = str(row[0] or "").strip()
        if not image_file or image_file in remaining_images:
            continue
        path = EVENT_IMAGES_DIR / image_file
        try:
            path.unlink()
        except OSError:
            pass
    invalidate_event_caches()
    return deleted


def delete_old_events(days: int = 7) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    with get_conn() as conn:
        rows = conn.execute("SELECT image_file FROM events WHERE time < ?", (cutoff,)).fetchall()
        for row in rows:
            img = str(row[0] or "").strip()
            if img:
                try:
                    (EVENT_IMAGES_DIR / img).unlink()
                except OSError:
                    pass
        deleted = conn.execute("DELETE FROM events WHERE time < ?", (cutoff,)).rowcount
    
    # Clean up old cached teldrive files (images) to save space
    try:
        cache_dir = DATA_DIR / "teldrive_cache"
        if cache_dir.exists():
            cutoff_epoch = time.time() - (days * 86400)
            for path in cache_dir.iterdir():
                if path.is_file() and path.stat().st_mtime < cutoff_epoch:
                    try:
                        path.unlink()
                    except OSError:
                        pass
    except Exception as e:
        logger.warning(f"[DB] Lỗi khi dọn dẹp teldrive_cache: {e}")

    if deleted > 0:
        logger.info("[DB] Deleted %d events older than %d days", deleted, days)
    invalidate_event_caches()
    return deleted


def get_incident_trends(days: int = 7) -> list[dict[str, Any]]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    query = """
        SELECT 
            substr(coalesce(time_local, time), 1, 10) as date_str,
            upper(coalesce(ai_result, status)) as result,
            COUNT(*) as count
        FROM events
        WHERE time >= ?
        GROUP BY date_str, result
    """
    with get_conn() as conn:
        rows = conn.execute(query, (cutoff,)).fetchall()
    return [dict(row) for row in rows]


# ──────────────────────────────────────────────
# Users
# ──────────────────────────────────────────────

def get_user(username: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    return dict(row) if row else None


def create_user(username: str, password_hash: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?,?,?)",
            (username, password_hash, now_iso()),
        )


def update_user(old_username: str, new_username: str, password_hash: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE users SET username=?, password_hash=? WHERE username=?", (new_username, password_hash, old_username))


def list_users() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT id, username, created_at FROM users").fetchall()
    return [dict(r) for r in rows]


# ──────────────────────────────────────────────
# Settings (config storage in DB)
# ──────────────────────────────────────────────

def get_setting(key: str, default: str = "") -> str:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return str(row[0]) if row else default


def set_setting(key: str, value: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value, now_iso()),
        )


def set_settings_bulk(data: dict[str, str]) -> None:
    """Upsert multiple settings in one transaction."""
    ts = now_iso()
    rows = [(k, v, ts) for k, v in data.items()]
    with get_conn() as conn:
        conn.executemany(
            "INSERT INTO settings (key, value, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            rows,
        )


def get_all_settings() -> dict[str, str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {row[0]: row[1] for row in rows}


def delete_setting(key: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM settings WHERE key=?", (key,))
