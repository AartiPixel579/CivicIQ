"""
Comprehensive Regression Test Suite for Phase 1.1:
Form PII Isolation, Draft Cancellation Security, Lifecycle Cleanup, and Bounded Expiration Tracking.
"""

import os
import shutil
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from fastapi import HTTPException
from starlette.responses import FileResponse

from backend.app.config import GENERATED_DRAFTS_DIR
from backend.app.main import chat_endpoint, download_draft_pdf, CHAT_HISTORIES
from backend.app.models import ChatRequest
from backend.app.services.form_session_service import form_session_service, BoundedIdTracker
from backend.app.services.form_lifecycle_store import form_lifecycle_store
from backend.app.services.pdf_filler import pdf_filler
from backend.app.services.draft_maintenance import draft_maintenance_service, DraftMaintenanceService
from backend.tests.offline_llm_helper import OfflineLLMTestCase


class TestFormPiiAndLifecycleSecurity(OfflineLLMTestCase):

    def setUp(self):
        super().setUp()
        form_session_service.sessions.clear()
        form_session_service.expired_session_ids.clear()
        form_session_service.cancelled_session_ids.clear()
        form_lifecycle_store.clear_all()
        CHAT_HISTORIES.clear()

    # =========================================================================
    # 1. PII Isolation Tests
    # =========================================================================

    def test_01_form_answers_not_appended_to_general_chat_history(self):
        """Verifies that answering form questions never stores resident PII in CHAT_HISTORIES."""
        sid = "pii_isolation_sess_1"
        form_session_service.start_session(sid, "road_opening")

        # Answer question 1 (name)
        res1 = chat_endpoint(ChatRequest(
            session_id=sid,
            message="Secret Resident Name",
            department_id="engineering"
        ))
        self.assertEqual(res1.mode, "form_fill")
        self.assertNotIn("Secret Resident Name", str(CHAT_HISTORIES.get(sid, [])))

        # Answer question 2 (phone)
        res2 = chat_endpoint(ChatRequest(
            session_id=sid,
            message="732-555-9999",
            department_id="engineering"
        ))
        self.assertEqual(res2.mode, "form_fill")
        self.assertNotIn("732-555-9999", str(CHAT_HISTORIES.get(sid, [])))

        # Chat history for this session must remain completely empty
        self.assertEqual(len(CHAT_HISTORIES.get(sid, [])), 0)

    def test_02_existing_history_cleared_when_form_mode_starts(self):
        """Verifies prior conversational history is purged when form filling is initiated."""
        sid = "pii_isolation_sess_2"

        # Turn 1: Regular greeting
        chat_endpoint(ChatRequest(session_id=sid, message="hello", department_id="engineering"))
        self.assertGreater(len(CHAT_HISTORIES.get(sid, [])), 0)

        # Start form filling via Case 0.5 offer
        # Simulate last bot message offering form fill
        CHAT_HISTORIES[sid] = [
            {"role": "user", "content": "I need road opening permit"},
            {"role": "assistant", "content": "I can help you fill out this application form step-by-step."}
        ]

        res = chat_endpoint(ChatRequest(session_id=sid, message="yes please", department_id="engineering"))
        self.assertEqual(res.mode, "form_fill")

        # Existing history must be completely purged upon entering form filling
        self.assertEqual(len(CHAT_HISTORIES.get(sid, [])), 0)

    def test_03_subsequent_general_question_cannot_send_prior_form_answers_to_llm(self):
        """
        Verifies that after form filling, a subsequent general question starts fresh
        and cannot leak any prior form answers to RAG or LLM history.
        """
        sid = "pii_isolation_sess_3"

        # 1. Run through form filling
        form_session_service.start_session(sid, "road_opening")
        chat_endpoint(ChatRequest(session_id=sid, message="Private Citizen", department_id="engineering"))
        chat_endpoint(ChatRequest(session_id=sid, message="732-555-0199", department_id="engineering"))

        # 2. Reset form session to unblock general queries
        chat_endpoint(ChatRequest(session_id=sid, message="/reset", department_id="engineering"))
        self.assertEqual(len(CHAT_HISTORIES.get(sid, [])), 0)

        # 3. Resident asks general question
        with patch("backend.app.rag_engine.rag_engine.answer_query") as mock_rag:
            mock_rag.return_value = MagicMock(
                answer="Engineering office is at 100 Municipal Blvd.",
                citations=[],
                form_packet=None
            )
            res = chat_endpoint(ChatRequest(
                session_id=sid,
                message="Where is the engineering office?",
                department_id="engineering"
            ))

            # Verify mock_rag was called with sanitized/empty prior history
            self.assertTrue(mock_rag.called)
            called_kwargs = mock_rag.call_args.kwargs
            called_history = called_kwargs.get("history", [])
            self.assertEqual(len(called_history), 0, "RAG history must contain zero form PII")

    def test_04_form_completion_cancellation_expiration_do_not_leave_form_answers_in_history(self):
        """Verifies session lifecycle events (complete, cancel, expire) leave no form answers in chat history."""
        # Case A: Cancellation
        sid_a = "pii_cancel_sess"
        form_session_service.start_session(sid_a, "tree_removal")
        CHAT_HISTORIES[sid_a] = [{"role": "user", "content": "Secret Owner"}]
        form_session_service.cancel_session(sid_a)
        self.assertNotIn(sid_a, CHAT_HISTORIES)

        # Case B: Expiration
        sid_b = "pii_expire_sess"
        form_session_service.start_session(sid_b, "tree_removal")
        CHAT_HISTORIES[sid_b] = [{"role": "user", "content": "Secret Tree Count"}]
        form_session_service.expire_session(sid_b)
        self.assertNotIn(sid_b, CHAT_HISTORIES)

        # Case C: Reset intent in chat_endpoint
        sid_c = "pii_reset_sess"
        form_session_service.start_session(sid_c, "tree_removal")
        chat_endpoint(ChatRequest(session_id=sid_c, message="cancel", department_id="engineering"))
        self.assertNotIn(sid_c, CHAT_HISTORIES)

    def test_05_mock_llm_manager_explicitly_asserted_not_called_during_form_operations(self):
        """Explicitly asserts that llm_manager.generate is NEVER called during any form session turns."""
        sid = "llm_isolation_sess"
        form_session_service.start_session(sid, "tree_removal")

        with patch("backend.app.llm_client.llm_manager.generate") as mock_gen:
            # 1. Answer question 1
            chat_endpoint(ChatRequest(session_id=sid, message="Resident X", department_id="engineering"))
            mock_gen.assert_not_called()

            # 2. Answer question 2
            chat_endpoint(ChatRequest(session_id=sid, message="100 Municipal Blvd", department_id="engineering"))
            mock_gen.assert_not_called()

            # 3. Direct service answer_question
            form_session_service.answer_question(sid, "732-555-1234")
            mock_gen.assert_not_called()

            # 4. Direct service edit_answer
            form_session_service.edit_answer(sid, "property_owner_name", "Resident Y")
            mock_gen.assert_not_called()

            # 5. Fee calculation
            form_session_service.get_applicable_fee({
                "fee_category": "$25.00 for single permit on a single residential lot without a variance",
                "is_owner_senior_citizen": "Yes, property owner is age 62 or older"
            })
            mock_gen.assert_not_called()

    # =========================================================================
    # 2. Cancellation Tests
    # =========================================================================

    def test_06_cancel_session_safely_deletes_generated_draft_directory(self):
        """Verifies cancelling a session deletes its generated draft files on disk."""
        sid = "cancel_delete_test_sess"
        answers = {"applicant_name": "Test User", "applicant_phone": "732-555-0100"}
        ok, msg, file_path, rel_url = pdf_filler.generate_draft_pdf(sid, "road_opening", answers)
        self.assertTrue(ok)
        self.assertTrue(Path(file_path).exists())

        session_folder = GENERATED_DRAFTS_DIR / sid
        self.assertTrue(session_folder.exists())

        # Cancel session
        form_session_service.cancel_session(sid)

        # On-disk folder must be completely removed
        self.assertFalse(session_folder.exists(), "Draft folder must be deleted on cancellation")

    def test_07_cancelled_session_cannot_download_draft(self):
        """Verifies download endpoint rejects cancelled sessions with HTTP 410."""
        sid = "cancel_download_test_sess"
        session_folder = GENERATED_DRAFTS_DIR / sid
        session_folder.mkdir(parents=True, exist_ok=True)
        draft_file = session_folder / "test_draft.pdf"
        draft_file.write_bytes(b"%PDF-1.4 sample")

        # Mark cancelled
        form_session_service.cancel_session(sid)

        # Attempt download
        with self.assertRaises(HTTPException) as ctx:
            download_draft_pdf(session_id=sid, filename="test_draft.pdf")
        self.assertEqual(ctx.exception.status_code, 410)
        self.assertIn("cancelled", ctx.exception.detail.lower())

    def test_08_cancelled_session_cannot_generate_another_draft(self):
        """Verifies generate_draft_pdf refuses generation for cancelled sessions."""
        sid = "cancel_gen_refuse_sess"
        form_session_service.start_session(sid, "road_opening")
        form_session_service.cancel_session(sid)

        ok, msg, path, url = pdf_filler.generate_draft_pdf(sid, "road_opening", {"applicant_name": "Ghost"})
        self.assertFalse(ok)
        self.assertIn("cancelled", msg.lower())

    def test_09_repeated_cancellation_is_safe_and_idempotent(self):
        """Verifies repeated calls to cancel_session do not throw or corrupt state."""
        sid = "repeat_cancel_sess"
        form_session_service.start_session(sid, "road_opening")

        # First cancellation
        form_session_service.cancel_session(sid)
        self.assertTrue(form_session_service.is_session_cancelled(sid))

        # Repeated cancellation
        form_session_service.cancel_session(sid)
        form_session_service.cancel_session(sid)
        self.assertTrue(form_session_service.is_session_cancelled(sid))

    # =========================================================================
    # 3. Cleanup Execution Tests
    # =========================================================================

    def test_10_draft_maintenance_service_lifecycle_startup_and_shutdown(self):
        """Verifies DraftMaintenanceService starts once, prevents duplicate loops, and stops cleanly."""
        service = DraftMaintenanceService(interval_seconds=3600, retention_seconds=86400)
        self.assertFalse(service.is_running)

        # Start service
        service.start()
        self.assertTrue(service.is_running)

        # Second start call is idempotent and does not create duplicate threads
        service.start()
        self.assertTrue(service.is_running)

        # Stop service
        service.stop()
        self.assertFalse(service.is_running)

    def test_11_draft_maintenance_service_preserves_active_and_removes_stale(self):
        """Verifies run_once() preserves active drafts and deletes stale ones older than 24 hours."""
        test_dir = GENERATED_DRAFTS_DIR / "maint_test_dir"
        test_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 1. Active session draft
            active_sid = "maint_active_sid"
            form_session_service.start_session(active_sid, "tree_removal")
            active_folder = test_dir / active_sid
            active_folder.mkdir(parents=True, exist_ok=True)
            active_file = active_folder / "active.pdf"
            active_file.write_bytes(b"%PDF active")

            # 2. Stale inactive draft (48 hours old)
            stale_folder = test_dir / "maint_stale_sid"
            stale_folder.mkdir(parents=True, exist_ok=True)
            stale_file = stale_folder / "stale.pdf"
            stale_file.write_bytes(b"%PDF stale")
            old_time = time.time() - (48 * 3600)
            os.utime(str(stale_file), (old_time, old_time))

            # Run maintenance with custom directory and 24-hr retention
            deleted = form_session_service.cleanup_expired_drafts(
                max_age_seconds=86400,
                base_dir=test_dir
            )

            self.assertEqual(deleted, 1)
            self.assertFalse(stale_file.exists(), "Stale draft must be deleted")
            self.assertTrue(active_file.exists(), "Active draft must be preserved")

        finally:
            shutil.rmtree(test_dir, ignore_errors=True)

    def test_12_cleanup_cannot_escape_approved_directory(self):
        """Verifies cleanup raises ValueError if given an external path."""
        outside_path = Path("C:/Windows/Temp" if os.name == "nt" else "/tmp")
        with self.assertRaises(ValueError) as ctx:
            form_session_service.cleanup_expired_drafts(
                max_age_seconds=3600,
                base_dir=outside_path
            )
        self.assertIn("Security violation", str(ctx.exception))

    # =========================================================================
    # 4. Bounded Expiration Tracking Tests
    # =========================================================================

    def test_13_bounded_id_tracker_enforces_capacity_limit(self):
        """Verifies BoundedIdTracker prevents unbounded memory growth."""
        tracker = BoundedIdTracker(max_capacity=50)

        # Add 120 items
        for i in range(120):
            tracker.add(f"session_{i}")

        # Capacity must be strictly bounded at 50
        self.assertEqual(len(tracker), 50)

        # Oldest items evicted
        self.assertFalse(tracker.contains("session_0"))
        self.assertFalse(tracker.contains("session_69"))

        # Most recent items present
        self.assertTrue(tracker.contains("session_119"))
        self.assertTrue(tracker.contains("session_100"))

    def test_14_fresh_session_can_restart_safely_after_expiration(self):
        """Verifies restarting with the same session ID unblocks the session."""
        sid = "restart_safety_sess"
        form_session_service.start_session(sid, "road_opening")
        form_session_service.expire_session(sid)

        self.assertTrue(form_session_service.is_session_expired(sid))

        # Restart fresh session with same ID
        ok, msg, resp = form_session_service.start_session(sid, "road_opening")
        self.assertTrue(ok)
        self.assertFalse(form_session_service.is_session_expired(sid))
        self.assertFalse(form_session_service.is_session_cancelled(sid))

    def test_15_expired_session_cannot_access_previous_draft(self):
        """Verifies expired session is blocked from download with HTTP 410."""
        sid = "expire_download_block_sess"
        session_folder = GENERATED_DRAFTS_DIR / sid
        session_folder.mkdir(parents=True, exist_ok=True)
        draft_file = session_folder / "expired_draft.pdf"
        draft_file.write_bytes(b"%PDF-1.4 expired")

        form_session_service.start_session(sid, "road_opening")
        form_session_service.expire_session(sid)

        with self.assertRaises(HTTPException) as ctx:
            download_draft_pdf(session_id=sid, filename="expired_draft.pdf")
        self.assertEqual(ctx.exception.status_code, 410)
        self.assertIn("expired", ctx.exception.detail.lower())


if __name__ == "__main__":
    import unittest
    unittest.main()
