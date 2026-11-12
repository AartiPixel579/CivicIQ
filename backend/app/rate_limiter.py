"""
Production-Compatible Rate Limiter & Distributed Crawl Lock for CivicIQ.
Uses PostgreSQL when DATABASE_URL is configured (mandatory in production)
so limits and crawl locks are shared across multiple instances/workers without
introducing a paid external cache service. Falls back to SQLite in local dev.
"""

import logging
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Optional, Tuple

from .config import DATABASE_URL, IS_PRODUCTION, VECTOR_DB_PATH

logger = logging.getLogger("rate_limiter")


class PersistentRateLimiter:
    def __init__(self, db_path: Path = VECTOR_DB_PATH, db_url: str = DATABASE_URL, force_sqlite: bool = False):
        self.db_path = Path(db_path)
        self.db_url = db_url
        self.force_sqlite = force_sqlite
        self._pg_schema_ready = False
        self._init_sqlite()

    def _get_sqlite_conn(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        return closing(sqlite3.connect(str(self.db_path)))

    def _init_sqlite(self):
        with self._get_sqlite_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS rate_limits (
                    bucket_key TEXT PRIMARY KEY,
                    count INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS crawl_locks (
                    lock_name TEXT PRIMARY KEY,
                    owner TEXT,
                    expires_at INTEGER NOT NULL
                )
            """)
            conn.commit()

    def _normalize_pg_url(self, raw_url: str) -> str:
        url = (raw_url or "").strip()
        if not url:
            return ""
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        if "sslmode=" not in url.lower() and not any(h in url.lower() for h in ("localhost", "127.0.0.1", "host.docker.internal")):
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}sslmode=require"
        return url

    def _get_pg_conn(self):
        if self.force_sqlite:
            return None
        is_prod = os.getenv("ENVIRONMENT", "development").lower().strip() == "production" or IS_PRODUCTION
        db_url = self._normalize_pg_url(os.getenv("DATABASE_URL", "") or self.db_url or "")
        if not db_url:
            if is_prod:
                raise RuntimeError("DATABASE_URL is required in production for rate limiting and crawl locks.")
            return None
        try:
            import psycopg2
            conn = psycopg2.connect(db_url, connect_timeout=10)
            if not self._pg_schema_ready:
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS rate_limits (
                            bucket_key TEXT PRIMARY KEY,
                            count INT NOT NULL,
                            expires_at BIGINT NOT NULL
                        );
                    """)
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS crawl_locks (
                            lock_name TEXT PRIMARY KEY,
                            owner TEXT,
                            expires_at BIGINT NOT NULL
                        );
                    """)
                conn.commit()
                self._pg_schema_ready = True
            return conn
        except Exception as exc:
            if is_prod:
                raise RuntimeError(f"PostgreSQL rate_limiter unavailable in production: {exc}") from exc
            logger.warning(f"PostgreSQL rate_limiter unreachable in dev; using SQLite: {exc}")
            return None

    def check_rate_limit(self, key: str, max_requests: int, window_seconds: int = 60) -> Tuple[bool, int]:
        """
        Increments the counter for the current time window.
        Returns (allowed: bool, current_count: int).
        """
        now = int(time.time())
        bucket_start = (now // window_seconds) * window_seconds
        expires_at = bucket_start + window_seconds
        bucket_key = f"{key}:{bucket_start}"

        pg_conn = self._get_pg_conn()
        if pg_conn is not None:
            with closing(pg_conn) as conn:
                try:
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM rate_limits WHERE expires_at < %s;", (now,))
                        cur.execute("""
                            INSERT INTO rate_limits (bucket_key, count, expires_at)
                            VALUES (%s, 1, %s)
                            ON CONFLICT (bucket_key) DO UPDATE SET
                                count = rate_limits.count + 1
                            RETURNING count;
                        """, (bucket_key, expires_at))
                        count = int(cur.fetchone()[0])
                    conn.commit()
                    return count <= max_requests, count
                except Exception:
                    conn.rollback()
                    raise

        with self._get_sqlite_conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM rate_limits WHERE expires_at < ?", (now,))
            cur.execute("""
                INSERT INTO rate_limits (bucket_key, count, expires_at)
                VALUES (?, 1, ?)
                ON CONFLICT(bucket_key) DO UPDATE SET
                    count = count + 1
            """, (bucket_key, expires_at))
            cur.execute("SELECT count FROM rate_limits WHERE bucket_key = ?", (bucket_key,))
            count = int(cur.fetchone()[0])
            conn.commit()
        return count <= max_requests, count

    def acquire_crawl_lock(self, lock_name: str, owner: str = "admin", ttl_seconds: int = 300) -> bool:
        """
        Acquires an exclusive lease lock for expensive crawl/ingestion operations.
        Returns True if acquired, False if another crawl is currently active.
        """
        now = int(time.time())
        expires_at = now + ttl_seconds

        pg_conn = self._get_pg_conn()
        if pg_conn is not None:
            with closing(pg_conn) as conn:
                try:
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO crawl_locks (lock_name, owner, expires_at)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (lock_name) DO UPDATE SET
                                owner = EXCLUDED.owner,
                                expires_at = EXCLUDED.expires_at
                            WHERE crawl_locks.expires_at < %s
                            RETURNING lock_name;
                        """, (lock_name, owner, expires_at, now))
                        acquired = cur.fetchone() is not None
                    conn.commit()
                    return acquired
                except Exception:
                    conn.rollback()
                    raise

        with self._get_sqlite_conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM crawl_locks WHERE lock_name = ? AND expires_at < ?", (lock_name, now))
            cur.execute(
                "INSERT OR IGNORE INTO crawl_locks (lock_name, owner, expires_at) VALUES (?, ?, ?)",
                (lock_name, owner, expires_at),
            )
            acquired = cur.rowcount > 0
            conn.commit()
        return acquired

    def release_crawl_lock(self, lock_name: str):
        pg_conn = self._get_pg_conn()
        if pg_conn is not None:
            with closing(pg_conn) as conn:
                try:
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM crawl_locks WHERE lock_name = %s;", (lock_name,))
                    conn.commit()
                    return
                except Exception:
                    conn.rollback()
                    raise

        with self._get_sqlite_conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM crawl_locks WHERE lock_name = ?", (lock_name,))
            conn.commit()


rate_limiter = PersistentRateLimiter()
