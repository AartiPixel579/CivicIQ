import os
import time
import sqlite3
import secrets
import logging
import threading
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

from ..config import DATA_DIR, GENERATED_DRAFTS_DIR

logger = logging.getLogger("services.form_lifecycle_store")

DB_PATH = DATA_DIR / "form_lifecycle.db"

class FormLifecycleStore:
    """
    Authoritative, persistent SQLite store for form session lifecycle states
    and cryptographic draft authorization records.

    Guarantees:
    - Authoritative lifecycle state tracking that never evicts or forgets expired/cancelled sessions.
    - Positive authorization whitelist: a draft is downloadable ONLY if an explicit active authorization
      record exists for the exact session and filename.
    - Revocation on cancellation: cancelling a session revokes all associated draft authorizations.
    - Retention enforcement: authorizations automatically expire after retention_seconds (default 24h).
    - Thread-safe transactions using a threading lock.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                cur.execute("PRAGMA journal_mode=WAL;")
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS form_sessions (
                        session_id TEXT PRIMARY KEY,
                        form_id TEXT NOT NULL,
                        status TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL
                    );
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS draft_authorizations (
                        authorization_id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        filename TEXT NOT NULL,
                        download_token TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        expires_at REAL NOT NULL,
                        status TEXT NOT NULL,
                        UNIQUE(session_id, filename)
                    );
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_draft_session_file ON draft_authorizations(session_id, filename);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_form_sessions_status ON form_sessions(status);")
                conn.commit()
            finally:
                conn.close()

    def record_session_start(self, session_id: str, form_id: str):
        """Records a new or restarted form session and revokes prior authorizations."""
        now = time.time()
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO form_sessions (session_id, form_id, status, created_at, updated_at)
                    VALUES (?, ?, 'in_progress', ?, ?)
                    ON CONFLICT(session_id) DO UPDATE SET
                        form_id = excluded.form_id,
                        status = 'in_progress',
                        updated_at = excluded.updated_at;
                """, (session_id, form_id, now, now))
                # Revoke any prior draft authorizations for this session
                cur.execute("""
                    UPDATE draft_authorizations
                    SET status = 'revoked'
                    WHERE session_id = ? AND status = 'active';
                """, (session_id,))
                conn.commit()
            finally:
                conn.close()

    def record_session_status(self, session_id: str, status: str):
        """Updates the status and timestamp of an active session."""
        now = time.time()
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                cur.execute("""
                    UPDATE form_sessions
                    SET status = ?, updated_at = ?
                    WHERE session_id = ?;
                """, (status, now, session_id))
                conn.commit()
            finally:
                conn.close()

    def record_session_cancelled(self, session_id: str):
        """Authoritatively marks a session as cancelled and revokes all draft authorizations."""
        now = time.time()
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO form_sessions (session_id, form_id, status, created_at, updated_at)
                    VALUES (?, 'unknown', 'cancelled', ?, ?)
                    ON CONFLICT(session_id) DO UPDATE SET
                        status = 'cancelled',
                        updated_at = excluded.updated_at;
                """, (session_id, now, now))
                cur.execute("""
                    UPDATE draft_authorizations
                    SET status = 'revoked'
                    WHERE session_id = ?;
                """, (session_id,))
                conn.commit()
            finally:
                conn.close()

    def record_session_expired(self, session_id: str):
        """Authoritatively marks a session as expired and expires draft authorizations."""
        now = time.time()
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO form_sessions (session_id, form_id, status, created_at, updated_at)
                    VALUES (?, 'unknown', 'expired', ?, ?)
                    ON CONFLICT(session_id) DO UPDATE SET
                        status = 'expired',
                        updated_at = excluded.updated_at;
                """, (session_id, now, now))
                cur.execute("""
                    UPDATE draft_authorizations
                    SET status = 'expired'
                    WHERE session_id = ? AND status = 'active';
                """, (session_id,))
                conn.commit()
            finally:
                conn.close()

    def get_session_lifecycle_status(self, session_id: str) -> Optional[str]:
        """Returns the authoritative lifecycle status for session_id, or None if never started."""
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                cur.execute("SELECT status FROM form_sessions WHERE session_id = ?;", (session_id,))
                row = cur.fetchone()
                return row["status"] if row else None
            finally:
                conn.close()

    def create_draft_authorization(
        self,
        session_id: str,
        filename: str,
        retention_seconds: int = 86400
    ) -> str:
        """
        Creates an explicit positive authorization record for a generated draft.
        Returns a secure download token credential.
        """
        now = time.time()
        expires_at = now + retention_seconds
        token = secrets.token_urlsafe(32)
        auth_id = f"{session_id}_{filename}"

        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO draft_authorizations (
                        authorization_id, session_id, filename, download_token, created_at, expires_at, status
                    ) VALUES (?, ?, ?, ?, ?, ?, 'active')
                    ON CONFLICT(session_id, filename) DO UPDATE SET
                        download_token = excluded.download_token,
                        created_at = excluded.created_at,
                        expires_at = excluded.expires_at,
                        status = 'active';
                """, (auth_id, session_id, filename, token, now, expires_at))
                # Also mark session completed
                cur.execute("""
                    UPDATE form_sessions
                    SET status = 'completed', updated_at = ?
                    WHERE session_id = ?;
                """, (now, session_id))
                conn.commit()
            finally:
                conn.close()

        logger.info(f"Created positive draft authorization for session '{session_id}', file '{filename}' (expires in {retention_seconds}s).")
        return token

    def verify_draft_authorization(
        self,
        session_id: str,
        filename: str,
        token: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Positive Authorization Check:
        Verifies that an active, non-expired, non-revoked authorization record exists
        for the exact session_id and filename.
        """
        now = time.time()
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                cur.execute("""
                    SELECT download_token, expires_at, status
                    FROM draft_authorizations
                    WHERE session_id = ? AND filename = ?;
                """, (session_id, filename))
                row = cur.fetchone()
                if not row:
                    return False, "Unauthorized: No draft authorization record exists for this session and document."

                auth_status = row["status"]
                expires_at = row["expires_at"]
                expected_token = row["download_token"]

                if auth_status == "revoked":
                    return False, "Revoked: Draft access has been revoked because the session was cancelled."

                if auth_status == "expired" or now >= expires_at:
                    cur.execute("""
                        UPDATE draft_authorizations
                        SET status = 'expired'
                        WHERE session_id = ? AND filename = ?;
                    """, (session_id, filename))
                    conn.commit()
                    return False, "Expired: Draft authorization has expired (retention period exceeded)."

                if token is not None and token != expected_token:
                    return False, "Forbidden: Invalid download authorization token."

                return True, "Authorized"
            finally:
                conn.close()

    def revoke_draft_authorization(self, session_id: str, filename: Optional[str] = None):
        """Revokes draft authorization upon cancellation or deletion."""
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                if filename:
                    cur.execute("""
                        UPDATE draft_authorizations
                        SET status = 'revoked'
                        WHERE session_id = ? AND filename = ?;
                    """, (session_id, filename))
                else:
                    cur.execute("""
                        UPDATE draft_authorizations
                        SET status = 'revoked'
                        WHERE session_id = ?;
                    """, (session_id,))
                conn.commit()
            finally:
                conn.close()

    def purge_expired_authorizations(self, max_age_seconds: int = 86400) -> int:
        """Purges old expired/revoked authorization records from the database."""
        threshold = time.time() - max_age_seconds
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                cur.execute("""
                    DELETE FROM draft_authorizations
                    WHERE status IN ('expired', 'revoked') AND expires_at < ?;
                """, (threshold,))
                deleted = cur.rowcount
                conn.commit()
                return deleted
            finally:
                conn.close()

    def delete_session(self, session_id: str):
        """Completely resets session lifecycle state (e.g. upon user /reset command)."""
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                cur.execute("DELETE FROM form_sessions WHERE session_id = ?;", (session_id,))
                cur.execute("""
                    UPDATE draft_authorizations
                    SET status = 'revoked'
                    WHERE session_id = ?;
                """, (session_id,))
                conn.commit()
            finally:
                conn.close()

    def clear_all(self):
        """Clears all session and authorization records (primarily for testing)."""
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                cur.execute("DELETE FROM draft_authorizations;")
                cur.execute("DELETE FROM form_sessions;")
                conn.commit()
            finally:
                conn.close()

form_lifecycle_store = FormLifecycleStore()
