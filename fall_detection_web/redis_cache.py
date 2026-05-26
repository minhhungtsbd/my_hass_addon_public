"""Redis cache helper module for Fall Detection Web."""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger("fall_detection_web")

_redis_ok = True
try:
    import redis
except ImportError:
    _redis_ok = False
    logger.warning("[REDIS] redis-py library not installed. Caching is disabled.")

# Connection pool cache
_pool: redis.ConnectionPool | None = None
_pool_lock = threading.Lock()
_last_config_key: tuple[str, int, int, str, bool] | None = None


def _get_connection_pool(config: dict[str, Any]) -> redis.ConnectionPool | None:
    """Get or create a thread-safe connection pool, adjusting if configuration changes."""
    global _pool, _last_config_key
    if not _redis_ok:
        return None

    enabled = bool(config.get("redis_enabled"))
    if not enabled:
        # Silently release pool if disabled
        with _pool_lock:
            if _pool:
                try:
                    _pool.disconnect()
                except Exception:
                    pass
                _pool = None
            _last_config_key = None
        return None

    host = str(config.get("redis_host", "127.0.0.1")).strip()
    port = int(config.get("redis_port", 6379))
    db = int(config.get("redis_db", 0))
    password = str(config.get("redis_password", "")).strip()

    config_key = (host, port, db, password, enabled)

    with _pool_lock:
        if _pool is not None and _last_config_key == config_key:
            return _pool

        # Clean old pool if config changed
        if _pool:
            try:
                _pool.disconnect()
            except Exception:
                pass
            _pool = None

        try:
            logger.info("[REDIS] Initializing connection pool to %s:%s (db=%s)", host, port, db)
            _pool = redis.ConnectionPool(
                host=host,
                port=port,
                db=db,
                password=password or None,
                socket_timeout=2.0,
                socket_connect_timeout=2.0,
                decode_responses=True,
            )
            _last_config_key = config_key
            return _pool
        except Exception as exc:
            logger.error("[REDIS] Could not initialize connection pool: %s", exc)
            _pool = None
            _last_config_key = None
            return None


def get_client(config: dict[str, Any]) -> redis.Redis | None:
    """Return a Redis client instance if Redis is enabled and connected, else None."""
    if not _redis_ok:
        return None

    pool = _get_connection_pool(config)
    if not pool:
        return None

    try:
        client = redis.Redis(connection_pool=pool)
        # Test connection (ping)
        client.ping()
        return client
    except Exception as exc:
        # Gracefully handle connection errors (e.g. Redis server not running)
        # Only log connection failures periodically to prevent spamming
        import random
        if random.random() < 0.05:
            logger.warning("[REDIS] Connection failed (server might be down): %s", exc)
        return None


# ──────────────────────────────────────────────
# Public Cache API
# ──────────────────────────────────────────────

def get_cache(key: str, config: dict[str, Any]) -> str | None:
    """Get value from Redis cache. Returns None if cache miss or Redis disabled."""
    client = get_client(config)
    if not client:
        return None
    try:
        return client.get(key)
    except Exception as exc:
        logger.debug("[REDIS] get_cache error: %s", exc)
        return None


def set_cache(key: str, value: str, expire_seconds: int | None, config: dict[str, Any]) -> bool:
    """Set value in Redis cache with optional expiration."""
    client = get_client(config)
    if not client:
        return False
    try:
        if expire_seconds:
            client.set(key, value, ex=expire_seconds)
        else:
            client.set(key, value)
        return True
    except Exception as exc:
        logger.warning("[REDIS] set_cache error: %s", exc)
        return False


def delete_cache(key: str, config: dict[str, Any]) -> bool:
    """Delete a key from Redis cache."""
    client = get_client(config)
    if not client:
        return False
    try:
        client.delete(key)
        return True
    except Exception as exc:
        logger.warning("[REDIS] delete_cache error: %s", exc)
        return False


def clear_cache_pattern(pattern: str, config: dict[str, Any]) -> int:
    """Find and delete all keys matching a pattern (e.g., 'events:list:*')."""
    client = get_client(config)
    if not client:
        return 0
    try:
        deleted = 0
        # Use SCAN instead of KEYS to prevent blocking the Redis server
        cursor = 0
        while True:
            cursor, keys = client.scan(cursor=cursor, match=pattern, count=100)
            if keys:
                client.delete(*keys)
                deleted += len(keys)
            if cursor == 0:
                break
        if deleted > 0:
            logger.info("[REDIS] Cleared %d keys matching pattern %s", deleted, pattern)
        return deleted
    except Exception as exc:
        logger.warning("[REDIS] clear_cache_pattern error: %s", exc)
        return 0
