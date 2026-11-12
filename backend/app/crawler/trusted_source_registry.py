"""
Trusted Source Registry & Crawl Run Audit Store for CivicIQ.
Separates administrator-configured trusted sources from resident chat inputs.
Persists in PostgreSQL when DATABASE_URL is configured (mandatory in production),
with SQLite fallback only in local development.
"""

import json
import logging
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from backend.app.config import DATABASE_URL, IS_PRODUCTION, VECTOR_DB_PATH
from .ssrf_guard import canonicalize_url_for_dedup, normalize_url

logger = logging.getLogger("crawler.trusted_source_registry")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class TrustedSourceRegistry:
    """
    Manages approved municipal source URLs, HTTP conditional headers (ETag/Last-Modified),
    content hashes, miss counters, and crawl run reports.
    """

    def __init__(self, db_path: Path = VECTOR_DB_PATH, db_url: str = DATABASE_URL, force_sqlite: bool = False):
        self.db_path = Path(db_path)
        self.db_url = db_url
        self.force_sqlite = force_sqlite
        self._pg_schema_initialized = False
        self._init_sqlite()

    def _get_sqlite_conn(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        return closing(sqlite3.connect(str(self.db_path)))

    def _init_sqlite(self):
        with self._get_sqlite_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS trusted_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id TEXT DEFAULT 'default',
                    department_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    canonical_url TEXT NOT NULL,
                    source_domain TEXT,
                    referring_url TEXT,
                    source_type TEXT DEFAULT 'html',
                    discovered_via TEXT DEFAULT 'admin_config',
                    is_approved INTEGER DEFAULT 1,
                    is_active INTEGER DEFAULT 1,
                    consecutive_misses INTEGER DEFAULT 0,
                    last_checked_at TEXT,
                    last_status_code INTEGER,
                    etag TEXT,
                    last_modified TEXT,
                    content_hash TEXT,
                    active_version_id INTEGER DEFAULT 1,
                    last_error TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    UNIQUE(department_id, canonical_url)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS crawl_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id TEXT DEFAULT 'default',
                    department_id TEXT NOT NULL,
                    root_url TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    status TEXT NOT NULL,
                    pages_discovered INTEGER DEFAULT 0,
                    pdfs_discovered INTEGER DEFAULT 0,
                    new_docs INTEGER DEFAULT 0,
                    updated_docs INTEGER DEFAULT 0,
                    unchanged_docs INTEGER DEFAULT 0,
                    inactive_docs INTEGER DEFAULT 0,
                    failed_docs INTEGER DEFAULT 0,
                    error_summary TEXT
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ts_dept_canon ON trusted_sources(department_id, canonical_url)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_cr_dept_time ON crawl_runs(department_id, started_at DESC)")
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
                raise RuntimeError("DATABASE_URL is required in production for TrustedSourceRegistry; SQLite fallback is disabled.")
            return None

        try:
            import psycopg2
            conn = psycopg2.connect(db_url, connect_timeout=10)
            if not self._pg_schema_initialized:
                self._ensure_pg_schema(conn)
                self._pg_schema_initialized = True
            return conn
        except Exception as exc:
            if is_prod:
                raise RuntimeError(f"PostgreSQL TrustedSourceRegistry unavailable in production: {exc}") from exc
            logger.warning(f"PostgreSQL TrustedSourceRegistry unreachable in dev; falling back to SQLite: {exc}")
            return None

    def _ensure_pg_schema(self, conn):
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS trusted_sources (
                    id SERIAL PRIMARY KEY,
                    client_id VARCHAR(64) DEFAULT 'default',
                    department_id VARCHAR(64) NOT NULL,
                    url TEXT NOT NULL,
                    canonical_url TEXT NOT NULL,
                    source_domain VARCHAR(255),
                    referring_url TEXT,
                    source_type VARCHAR(32) DEFAULT 'html',
                    discovered_via VARCHAR(64) DEFAULT 'admin_config',
                    is_approved BOOLEAN DEFAULT TRUE,
                    is_active BOOLEAN DEFAULT TRUE,
                    consecutive_misses INT DEFAULT 0,
                    last_checked_at TIMESTAMP,
                    last_status_code INT,
                    etag TEXT,
                    last_modified TEXT,
                    content_hash VARCHAR(64),
                    active_version_id INT DEFAULT 1,
                    last_error TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(department_id, canonical_url)
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_trusted_dept_active ON trusted_sources(department_id, is_active, is_approved);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_trusted_canonical ON trusted_sources(canonical_url);")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS crawl_runs (
                    id SERIAL PRIMARY KEY,
                    client_id VARCHAR(64) DEFAULT 'default',
                    department_id VARCHAR(64) NOT NULL,
                    root_url TEXT NOT NULL,
                    started_at TIMESTAMP NOT NULL,
                    completed_at TIMESTAMP,
                    status VARCHAR(32) NOT NULL,
                    pages_discovered INT DEFAULT 0,
                    pdfs_discovered INT DEFAULT 0,
                    new_docs INT DEFAULT 0,
                    updated_docs INT DEFAULT 0,
                    unchanged_docs INT DEFAULT 0,
                    inactive_docs INT DEFAULT 0,
                    failed_docs INT DEFAULT 0,
                    error_summary JSONB
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_crawl_runs_dept_time ON crawl_runs(department_id, started_at DESC);")
        conn.commit()

    def seed_from_config(
        self,
        department_id: str,
        root_url: str,
        client_id: str = "default",
        seed_urls: Optional[List[Dict[str, str]]] = None,
    ):
        """
        Seeds administrator-configured root URL and optional known seed URLs.
        Never called from resident chat endpoints.
        """
        if root_url:
            self.record_discovered_source(
                department_id=department_id,
                url=root_url,
                source_type="html",
                referring_url=root_url,
                discovered_via="admin_config",
                client_id=client_id,
                is_approved=True,
                is_active=True,
            )
        for item in (seed_urls or []):
            u = item.get("url")
            if u:
                self.record_discovered_source(
                    department_id=department_id,
                    url=u,
                    source_type=item.get("source_type", "pdf"),
                    referring_url=item.get("referring_url") or root_url,
                    discovered_via=item.get("discovered_via", "admin_seed_catalog"),
                    client_id=client_id,
                    is_approved=True,
                    is_active=True,
                )

    def record_discovered_source(
        self,
        department_id: str,
        url: str,
        source_type: str = "html",
        referring_url: Optional[str] = None,
        discovered_via: str = "crawler",
        client_id: str = "default",
        is_approved: bool = True,
        is_active: bool = True,
        last_status_code: Optional[int] = None,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
        content_hash: Optional[str] = None,
        active_version_id: Optional[int] = None,
        last_error: Optional[str] = None,
    ):
        norm = normalize_url(url)
        canon = canonicalize_url_for_dedup(url)
        domain = (urlparse(norm).hostname or "").lower()
        now = _utcnow_iso()

        pg_conn = self._get_pg_conn()
        if pg_conn is not None:
            with closing(pg_conn) as conn:
                try:
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO trusted_sources
                            (client_id, department_id, url, canonical_url, source_domain, referring_url,
                             source_type, discovered_via, is_approved, is_active, consecutive_misses,
                             last_checked_at, last_status_code, etag, last_modified, content_hash,
                             active_version_id, last_error, created_at, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (department_id, canonical_url) DO UPDATE SET
                                url = EXCLUDED.url,
                                referring_url = COALESCE(EXCLUDED.referring_url, trusted_sources.referring_url),
                                source_type = EXCLUDED.source_type,
                                is_approved = EXCLUDED.is_approved,
                                is_active = EXCLUDED.is_active,
                                consecutive_misses = 0,
                                last_checked_at = EXCLUDED.last_checked_at,
                                last_status_code = COALESCE(EXCLUDED.last_status_code, trusted_sources.last_status_code),
                                etag = COALESCE(EXCLUDED.etag, trusted_sources.etag),
                                last_modified = COALESCE(EXCLUDED.last_modified, trusted_sources.last_modified),
                                content_hash = COALESCE(EXCLUDED.content_hash, trusted_sources.content_hash),
                                active_version_id = COALESCE(%s, trusted_sources.active_version_id),
                                last_error = EXCLUDED.last_error,
                                updated_at = EXCLUDED.updated_at;
                        """, (
                            client_id, department_id, norm, canon, domain, referring_url,
                            source_type, discovered_via, bool(is_approved), bool(is_active),
                            now, last_status_code, etag, last_modified, content_hash,
                            active_version_id or 1, last_error, now, now,
                            active_version_id,
                        ))
                    conn.commit()
                    return
                except Exception:
                    conn.rollback()
                    raise

        with self._get_sqlite_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, active_version_id FROM trusted_sources WHERE department_id = ? AND canonical_url = ?",
                (department_id, canon),
            )
            existing = cur.fetchone()
            if existing:
                ver = active_version_id if active_version_id is not None else (existing[1] or 1)
                cur.execute("""
                    UPDATE trusted_sources
                    SET url = ?,
                        referring_url = COALESCE(?, referring_url),
                        source_type = ?,
                        is_approved = ?,
                        is_active = ?,
                        consecutive_misses = 0,
                        last_checked_at = ?,
                        last_status_code = COALESCE(?, last_status_code),
                        etag = COALESCE(?, etag),
                        last_modified = COALESCE(?, last_modified),
                        content_hash = COALESCE(?, content_hash),
                        active_version_id = ?,
                        last_error = ?,
                        updated_at = ?
                    WHERE id = ?
                """, (
                    norm, referring_url, source_type,
                    1 if is_approved else 0, 1 if is_active else 0,
                    now, last_status_code, etag, last_modified, content_hash,
                    ver, last_error, now, existing[0]
                ))
            else:
                cur.execute("""
                    INSERT INTO trusted_sources
                    (client_id, department_id, url, canonical_url, source_domain, referring_url,
                     source_type, discovered_via, is_approved, is_active, consecutive_misses,
                     last_checked_at, last_status_code, etag, last_modified, content_hash,
                     active_version_id, last_error, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    client_id, department_id, norm, canon, domain, referring_url,
                    source_type, discovered_via, 1 if is_approved else 0, 1 if is_active else 0,
                    now, last_status_code, etag, last_modified, content_hash,
                    active_version_id or 1, last_error, now, now
                ))
            conn.commit()

    def record_temporary_failure(self, department_id: str, url: str, status_code: Optional[int], error: str):
        canon = canonicalize_url_for_dedup(url)
        now = _utcnow_iso()

        pg_conn = self._get_pg_conn()
        if pg_conn is not None:
            with closing(pg_conn) as conn:
                try:
                    with conn.cursor() as cur:
                        cur.execute("""
                            UPDATE trusted_sources
                            SET last_checked_at = %s, last_status_code = %s, last_error = %s, updated_at = %s
                            WHERE department_id = %s AND canonical_url = %s;
                        """, (now, status_code, error, now, department_id, canon))
                    conn.commit()
                    return
                except Exception:
                    conn.rollback()
                    raise

        with self._get_sqlite_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE trusted_sources
                SET last_checked_at = ?, last_status_code = ?, last_error = ?, updated_at = ?
                WHERE department_id = ? AND canonical_url = ?
            """, (now, status_code, error, now, department_id, canon))
            conn.commit()

    def increment_miss_and_check_deactivation(
        self,
        department_id: str,
        url: str,
        miss_threshold: int = 2,
    ) -> bool:
        """
        Increments consecutive_misses for a URL missing from a healthy crawl.
        Returns True if misses >= miss_threshold and the source should be marked inactive.
        """
        canon = canonicalize_url_for_dedup(url)
        now = _utcnow_iso()

        pg_conn = self._get_pg_conn()
        if pg_conn is not None:
            with closing(pg_conn) as conn:
                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT id, consecutive_misses FROM trusted_sources WHERE department_id = %s AND canonical_url = %s;",
                            (department_id, canon),
                        )
                        row = cur.fetchone()
                        if not row:
                            return False
                        new_misses = (row[1] or 0) + 1
                        should_deactivate = new_misses >= miss_threshold
                        cur.execute("""
                            UPDATE trusted_sources
                            SET consecutive_misses = %s,
                                is_active = %s,
                                last_checked_at = %s,
                                updated_at = %s
                            WHERE id = %s;
                        """, (new_misses, not should_deactivate, now, now, row[0]))
                    conn.commit()
                    return should_deactivate
                except Exception:
                    conn.rollback()
                    raise

        with self._get_sqlite_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, consecutive_misses FROM trusted_sources WHERE department_id = ? AND canonical_url = ?",
                (department_id, canon),
            )
            row = cur.fetchone()
            if not row:
                return False
            new_misses = (row[1] or 0) + 1
            should_deactivate = new_misses >= miss_threshold
            cur.execute("""
                UPDATE trusted_sources
                SET consecutive_misses = ?,
                    is_active = ?,
                    last_checked_at = ?,
                    updated_at = ?
                WHERE id = ?
            """, (new_misses, 0 if should_deactivate else 1, now, now, row[0]))
            conn.commit()
            return should_deactivate

    def get_known_sources(self, department_id: str, active_only: bool = True) -> List[Dict[str, Any]]:
        pg_conn = self._get_pg_conn()
        if pg_conn is not None:
            with closing(pg_conn) as conn:
                with conn.cursor() as cur:
                    sql = """
                        SELECT url, canonical_url, source_domain, referring_url, source_type,
                               discovered_via, is_approved, is_active, consecutive_misses,
                               last_checked_at, last_status_code, etag, last_modified,
                               content_hash, active_version_id, last_error
                        FROM trusted_sources
                        WHERE department_id = %s
                    """
                    if active_only:
                        sql += " AND is_active = TRUE"
                    cur.execute(sql, (department_id,))
                    rows = cur.fetchall()
            return [
                {
                    "url": r[0],
                    "canonical_url": r[1],
                    "source_domain": r[2],
                    "referring_url": r[3],
                    "source_type": r[4],
                    "discovered_via": r[5],
                    "is_approved": bool(r[6]),
                    "is_active": bool(r[7]),
                    "consecutive_misses": r[8] or 0,
                    "last_checked_at": str(r[9]) if r[9] else None,
                    "last_status_code": r[10],
                    "etag": r[11],
                    "last_modified": r[12],
                    "content_hash": r[13],
                    "active_version_id": r[14] or 1,
                    "last_error": r[15],
                }
                for r in rows
            ]

        with self._get_sqlite_conn() as conn:
            cur = conn.cursor()
            sql = """
                SELECT url, canonical_url, source_domain, referring_url, source_type,
                       discovered_via, is_approved, is_active, consecutive_misses,
                       last_checked_at, last_status_code, etag, last_modified,
                       content_hash, active_version_id, last_error
                FROM trusted_sources
                WHERE department_id = ?
            """
            if active_only:
                sql += " AND is_active = 1"
            cur.execute(sql, (department_id,))
            rows = cur.fetchall()

        return [
            {
                "url": r[0],
                "canonical_url": r[1],
                "source_domain": r[2],
                "referring_url": r[3],
                "source_type": r[4],
                "discovered_via": r[5],
                "is_approved": bool(r[6]),
                "is_active": bool(r[7]),
                "consecutive_misses": r[8] or 0,
                "last_checked_at": r[9],
                "last_status_code": r[10],
                "etag": r[11],
                "last_modified": r[12],
                "content_hash": r[13],
                "active_version_id": r[14] or 1,
                "last_error": r[15],
            }
            for r in rows
        ]

    def is_url_trusted(
        self,
        url: str,
        department_id: str = "engineering",
    ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """
        Verifies whether a URL (e.g. shared by a resident in chat) belongs to an already
        approved active source or was discovered from the client's trusted website.
        NEVER adds the URL to the registry.
        """
        if not url:
            return False, None, "Empty URL"

        canon = canonicalize_url_for_dedup(url)

        pg_conn = self._get_pg_conn()
        if pg_conn is not None:
            with closing(pg_conn) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT url, canonical_url, referring_url, source_type, discovered_via, is_approved, is_active
                        FROM trusted_sources
                        WHERE department_id = %s AND canonical_url = %s AND is_approved = TRUE AND is_active = TRUE
                        LIMIT 1;
                    """, (department_id, canon))
                    row = cur.fetchone()
        else:
            with self._get_sqlite_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT url, canonical_url, referring_url, source_type, discovered_via, is_approved, is_active
                    FROM trusted_sources
                    WHERE department_id = ? AND canonical_url = ? AND is_approved = 1 AND is_active = 1
                    LIMIT 1
                """, (department_id, canon))
                row = cur.fetchone()

        if row:
            return True, {
                "url": row[0],
                "canonical_url": row[1],
                "referring_url": row[2],
                "source_type": row[3],
                "discovered_via": row[4],
            }, "Verified against approved trusted source registry."

        return False, None, "URL is not in the approved trusted sources registry."

    def record_crawl_run(
        self,
        department_id: str,
        root_url: str,
        started_at: str,
        completed_at: str,
        status: str,
        pages_discovered: int = 0,
        pdfs_discovered: int = 0,
        new_docs: int = 0,
        updated_docs: int = 0,
        unchanged_docs: int = 0,
        inactive_docs: int = 0,
        failed_docs: int = 0,
        error_summary: Optional[List[str]] = None,
        client_id: str = "default",
    ) -> int:
        err_json = json.dumps(error_summary or [])

        pg_conn = self._get_pg_conn()
        if pg_conn is not None:
            with closing(pg_conn) as conn:
                try:
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO crawl_runs
                            (client_id, department_id, root_url, started_at, completed_at, status,
                             pages_discovered, pdfs_discovered, new_docs, updated_docs, unchanged_docs,
                             inactive_docs, failed_docs, error_summary)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                            RETURNING id;
                        """, (
                            client_id, department_id, root_url, started_at, completed_at, status,
                            pages_discovered, pdfs_discovered, new_docs, updated_docs, unchanged_docs,
                            inactive_docs, failed_docs, err_json
                        ))
                        run_id = cur.fetchone()[0]
                    conn.commit()
                    return int(run_id or 0)
                except Exception:
                    conn.rollback()
                    raise

        with self._get_sqlite_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO crawl_runs
                (client_id, department_id, root_url, started_at, completed_at, status,
                 pages_discovered, pdfs_discovered, new_docs, updated_docs, unchanged_docs,
                 inactive_docs, failed_docs, error_summary)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                client_id, department_id, root_url, started_at, completed_at, status,
                pages_discovered, pdfs_discovered, new_docs, updated_docs, unchanged_docs,
                inactive_docs, failed_docs, err_json
            ))
            run_id = cur.lastrowid
            conn.commit()
        return int(run_id or 0)

    def get_latest_crawl_status(self, department_id: str = "engineering", limit: int = 5) -> Dict[str, Any]:
        pg_conn = self._get_pg_conn()
        if pg_conn is not None:
            with closing(pg_conn) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT id, root_url, started_at, completed_at, status,
                               pages_discovered, pdfs_discovered, new_docs, updated_docs,
                               unchanged_docs, inactive_docs, failed_docs, error_summary
                        FROM crawl_runs
                        WHERE department_id = %s
                        ORDER BY id DESC
                        LIMIT %s;
                    """, (department_id, limit))
                    runs = cur.fetchall()

                    cur.execute(
                        "SELECT count(*) FROM trusted_sources WHERE department_id = %s AND is_active = TRUE AND is_approved = TRUE;",
                        (department_id,),
                    )
                    active_sources = cur.fetchone()[0]

                    cur.execute(
                        "SELECT count(*) FROM trusted_sources WHERE department_id = %s AND is_active = FALSE;",
                        (department_id,),
                    )
                    inactive_sources = cur.fetchone()[0]

            history = [
                {
                    "id": r[0],
                    "root_url": r[1],
                    "started_at": str(r[2]) if r[2] else None,
                    "completed_at": str(r[3]) if r[3] else None,
                    "status": r[4],
                    "pages_discovered": r[5],
                    "pdfs_discovered": r[6],
                    "new_docs": r[7],
                    "updated_docs": r[8],
                    "unchanged_docs": r[9],
                    "inactive_docs": r[10],
                    "failed_docs": r[11],
                    "error_summary": r[12] if isinstance(r[12], list) else (json.loads(r[12]) if r[12] else []),
                }
                for r in runs
            ]
            return {
                "department_id": department_id,
                "backend": "postgresql",
                "active_trusted_sources": active_sources,
                "inactive_trusted_sources": inactive_sources,
                "latest_run": history[0] if history else None,
                "recent_runs": history,
            }

        with self._get_sqlite_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, root_url, started_at, completed_at, status,
                       pages_discovered, pdfs_discovered, new_docs, updated_docs,
                       unchanged_docs, inactive_docs, failed_docs, error_summary
                FROM crawl_runs
                WHERE department_id = ?
                ORDER BY id DESC
                LIMIT ?
            """, (department_id, limit))
            runs = cur.fetchall()

            cur.execute(
                "SELECT count(*) FROM trusted_sources WHERE department_id = ? AND is_active = 1 AND is_approved = 1",
                (department_id,),
            )
            active_sources = cur.fetchone()[0]

            cur.execute(
                "SELECT count(*) FROM trusted_sources WHERE department_id = ? AND is_active = 0",
                (department_id,),
            )
            inactive_sources = cur.fetchone()[0]

        history = [
            {
                "id": r[0],
                "root_url": r[1],
                "started_at": r[2],
                "completed_at": r[3],
                "status": r[4],
                "pages_discovered": r[5],
                "pdfs_discovered": r[6],
                "new_docs": r[7],
                "updated_docs": r[8],
                "unchanged_docs": r[9],
                "inactive_docs": r[10],
                "failed_docs": r[11],
                "error_summary": json.loads(r[12]) if r[12] else [],
            }
            for r in runs
        ]
        return {
            "department_id": department_id,
            "backend": "sqlite",
            "active_trusted_sources": active_sources,
            "inactive_trusted_sources": inactive_sources,
            "latest_run": history[0] if history else None,
            "recent_runs": history,
        }


trusted_source_registry = TrustedSourceRegistry()
