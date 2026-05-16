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
                image_file  TEXT
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
    _migrate_jsonl()


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


def insert_event(status_name: str, image_path: Path | None = None, **fields: Any) -> None:
    image_file = save_event_image(image_path, status_name)
    t = now_iso()
    t_local = local_iso()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO events (time,time_local,status,camera,confidence,ai_result,ai_raw,ai_response,message,error,image_file) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
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
            ),
        )
        _prune_events(conn)


def get_events(limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM events ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    events: list[dict[str, Any]] = []
    for row in rows:
        event = dict(row)
        image_file = str(event.get("image_file") or "").strip()
        if image_file and (EVENT_IMAGES_DIR / image_file).exists():
            event["image_url"] = f"/api/event-image/{image_file}"
        events.append(event)
    return events


def count_events() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]


def clear_events() -> int:
    with get_conn() as conn:
        deleted = conn.execute("DELETE FROM events").rowcount
    # Delete all image files
    for path in EVENT_IMAGES_DIR.glob("*.jpg"):
        try:
            path.unlink()
        except OSError:
            pass
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
    if deleted > 0:
        logger.info("[DB] Deleted %d events older than %d days", deleted, days)
    return deleted


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


def update_password(username: str, password_hash: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE users SET password_hash=? WHERE username=?", (password_hash, username))


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
