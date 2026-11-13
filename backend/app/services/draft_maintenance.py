import os
import time
import logging
import threading
from typing import Optional
from pathlib import Path

from ..config import GENERATED_DRAFTS_DIR
from .form_session_service import form_session_service

logger = logging.getLogger("services.draft_maintenance")

class DraftMaintenanceService:
    """
    Lifecycle-managed periodic maintenance runner:
    - Periodically executes cleanup of expired in-memory form sessions and stale draft PDF files.
    - Preserves active sessions and files newer than retention_seconds (default 24 hours / 86,400s).
    - Started once on FastAPI startup and cleanly stopped on FastAPI shutdown.
    - Prevents duplicate runner threads.
    - Catches all filesystem errors without interrupting application operation.
    """

    def __init__(self, interval_seconds: int = 3600, retention_seconds: int = 86400):
        self.interval_seconds = interval_seconds
        self.retention_seconds = retention_seconds
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._is_running = False

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._is_running

    def start(self):
        """Starts the maintenance worker thread (idempotent)."""
        with self._lock:
            if self._is_running:
                logger.info("DraftMaintenanceService is already running.")
                return
            self._stop_event.clear()
            self._is_running = True
            self._thread = threading.Thread(
                target=self._run_loop,
                name="DraftMaintenanceWorker",
                daemon=True
            )
            self._thread.start()
            logger.info(
                f"DraftMaintenanceService started (interval={self.interval_seconds}s, retention={self.retention_seconds}s)."
            )

    def stop(self, timeout: float = 2.0):
        """Stops the maintenance worker thread cleanly."""
        thread_to_join = None
        with self._lock:
            if not self._is_running:
                return
            self._stop_event.set()
            self._is_running = False
            thread_to_join = self._thread
            self._thread = None

        if thread_to_join and thread_to_join.is_alive():
            thread_to_join.join(timeout=timeout)
        logger.info("DraftMaintenanceService stopped cleanly.")

    def run_once(self) -> int:
        """Executes a single maintenance sweep (purging expired sessions and stale drafts)."""
        purged_sessions = 0
        deleted_drafts = 0
        try:
            purged_sessions = form_session_service.cleanup_expired_sessions()
        except Exception as e:
            logger.warning(f"Error purging expired form sessions during maintenance: {e}")

        try:
            deleted_drafts = form_session_service.cleanup_expired_drafts(
                max_age_seconds=self.retention_seconds
            )
        except Exception as e:
            logger.warning(f"Error cleaning stale drafts during maintenance: {e}")

        try:
            from .form_lifecycle_store import form_lifecycle_store
            form_lifecycle_store.purge_expired_authorizations(max_age_seconds=self.retention_seconds)
        except Exception as e:
            logger.warning(f"Error purging expired draft authorizations: {e}")

        logger.info(
            f"Draft maintenance sweep: {purged_sessions} expired sessions purged, {deleted_drafts} stale drafts deleted."
        )
        return deleted_drafts

    def _run_loop(self):
        """Internal background loop running maintenance sweep at interval_seconds."""
        # Initial maintenance sweep shortly after startup (e.g. 5 seconds)
        if not self._stop_event.wait(timeout=5.0):
            self.run_once()

        while not self._stop_event.is_set():
            if self._stop_event.wait(timeout=self.interval_seconds):
                break
            self.run_once()

draft_maintenance_service = DraftMaintenanceService()
