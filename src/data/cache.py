"""Two-tier cache: L1 (in-memory dict) + L2 (SQLite file).

TTL-aware per data type. Cache keys are strings (prefix:symbol:params).
"""

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from loguru import logger


class TieredCache:
    """L1 (in-memory, fast) + L2 (SQLite, persistent) cache."""

    def __init__(self, db_path: str = "./data/cache/cache.db"):
        self._l1: dict[str, tuple[float, Any]] = {}  # key -> (expiry_ts, value)
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    expiry_ts REAL NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_expiry ON cache(expiry_ts)")
            conn.commit()

    def get(self, key: str) -> Any | None:
        """Get value from cache (L1 first, then L2). Returns None if miss/expired."""
        now = time.time()

        # Check L1
        if key in self._l1:
            expiry, value = self._l1[key]
            if now < expiry:
                return value
            del self._l1[key]  # Expired

        # Check L2
        try:
            with sqlite3.connect(str(self._db_path)) as conn:
                row = conn.execute(
                    "SELECT value, expiry_ts FROM cache WHERE key = ?", (key,)
                ).fetchone()

            if row is None:
                return None
            value_str, expiry_ts = row
            if now < expiry_ts:
                value = json.loads(value_str)
                self._l1[key] = (expiry_ts, value)  # Promote to L1
                return value
            # Expired — delete
            self._delete(key)
        except Exception as e:
            logger.warning(f"Cache L2 read error: {e}")

        return None

    def get_stale(self, key: str) -> Any | None:
        """Return an expired value when it exists.

        This is used as a degraded fallback when every upstream provider fails.
        """
        if key in self._l1:
            return self._l1[key][1]

        try:
            with sqlite3.connect(str(self._db_path)) as conn:
                row = conn.execute(
                    "SELECT value FROM cache WHERE key = ?", (key,)
                ).fetchone()
            if row is None:
                return None
            return json.loads(row[0])
        except Exception as e:
            logger.warning(f"Cache stale read error: {e}")
            return None

    def set(self, key: str, value: Any, ttl_seconds: int = 900):
        """Set cache value with TTL (seconds)."""
        now = time.time()
        expiry_ts = now + ttl_seconds

        # L1
        self._l1[key] = (expiry_ts, value)

        # L2
        try:
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO cache (key, value, expiry_ts) VALUES (?, ?, ?)",
                    (key, json.dumps(value, default=str), expiry_ts),
                )
                conn.commit()
        except Exception as e:
            logger.warning(f"Cache L2 write error: {e}")

    def _delete(self, key: str):
        try:
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                conn.commit()
        except Exception:
            pass

    def clear_expired(self):
        """Remove all expired entries from L2."""
        now = time.time()
        try:
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.execute("DELETE FROM cache WHERE expiry_ts < ?", (now,))
                conn.commit()
        except Exception as e:
            logger.warning(f"Cache cleanup error: {e}")

    def clear_all(self):
        """Clear both L1 and L2."""
        self._l1.clear()
        try:
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.execute("DELETE FROM cache")
                conn.commit()
        except Exception:
            pass


# Global cache instance
_cache: TieredCache | None = None


def get_cache() -> TieredCache:
    global _cache
    if _cache is None:
        _cache = TieredCache()
    return _cache
