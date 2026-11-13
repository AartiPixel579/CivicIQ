"""
Phase 1.2 Authoritative Security Regression Test Suite:
- Expired and Cancelled Form PII Interception (Zero RAG, Zero LLM, Zero Chat History Appends)
- Persistent SQLite Lifecycle Tracking Immune to 10,000+ LRU Evictions
- Positive Draft Authorization Whitelist
- Cryptographic Download Token Verification
- Draft Retention & Revocation on Cancellation
- Concurrent Generation & Maintenance Cleanup Race Guards
- Explicit Restart Fresh State Unblocking
"""

import os
import shutil
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

from fastapi import HTTPException
from starlette.responses import FileResponse

from backend.app.config import GENERATED_DRAFTS_DIR
from backend.app.main import chat_endpoint, download_draft_pdf, CHAT_HISTORIES
from backend.app.models import ChatRequest
from backend.app.services.form_session_service import form_session_service
from backend.app.services.form_lifecycle_store import form_lifecycle_store
from backend.app.services.pdf_filler import pdf_filler
from backend.tests.offline_llm_helper import OfflineLLMTestCase


class TestPhase12AuthoritativeSecurity(OfflineLLMTestCase):

    def setUp(self):
        super().setUp()
        form_session_service.sessions.clear()
        form_session_service.expired_session_ids.clear()
        form_session_service.cancelled_session_ids.clear()
        form_session_service._generating_sessions.clear()
        form_lifecycle_store.clear_all()
        CHAT_HISTORIES.clear()

    # -------------------------------------------------------------------------
    # Test 1: Expired form session receiving PII returns mode="form_fill", zero RAG, zero LLM
    # -------------------------------------------------------------------------
    def test_01_expired_session_receiving_pii_blocks_rag_and_llm(self):
        sid = "phase12_expired_pii_sess"
        form_session_service.start_session(sid, "road_opening")
        form_session_service.expire_session(sid)

        with patch("backend.app.rag_engine.rag_engine.answer_query") as mock_rag, \
             patch("backend.app.llm_client.llm_client.generate_answer") as mock_llm:

            resp = chat_endpoint(ChatRequest(
                session_id=sid,
                message="My address is 742 Evergreen Terrace, Phone 732-555-0199",
                department_id="engineering"
            ))

            # Must return mode="form_fill" with expiration notice
            self.assertEqual(resp.mode, "form_fill")
            self.assertIn("expired", resp.message.lower())
            self.assertFalse(resp.completed)

            # Zero RAG and zero LLM calls
            self.assertFalse(mock_rag.called, "RAG must NEVER be invoked for expired form session messages")
            self.assertFalse(mock_llm.called, "LLM must NEVER be invoked for expired form session messages")

            # Must never append PII to CHAT_HISTORIES
            self.assertNotIn(sid, CHAT_HISTORIES)

    # -------------------------------------------------------------------------
    # Test 2: Cancelled form session receiving message returns mode="form_fill", zero RAG, zero LLM
    # -------------------------------------------------------------------------
    def test_02_cancelled_session_receiving_message_blocks_rag_and_llm(self):
        sid = "phase12_cancelled_pii_sess"
        form_session_service.start_session(sid, "road_opening")
        form_session_service.cancel_session(sid)

        with patch("backend.app.rag_engine.rag_engine.answer_query") as mock_rag, \
             patch("backend.app.llm_client.llm_client.generate_answer") as mock_llm:

            resp = chat_endpoint(ChatRequest(
                session_id=sid,
                message="Cancel was a mistake, my name is John Doe",
                department_id="engineering"
            ))

            self.assertEqual(resp.mode, "form_fill")
            self.assertIn("cancelled", resp.message.lower())
            self.assertFalse(resp.completed)

            self.assertFalse(mock_rag.called, "RAG must NEVER be invoked for cancelled form session messages")
            self.assertFalse(mock_llm.called, "LLM must NEVER be invoked for cancelled form session messages")
            self.assertNotIn(sid, CHAT_HISTORIES)

    # -------------------------------------------------------------------------
    # Test 3: Expired/cancelled state persists and blocks after 10,000 tracker evictions
    # -------------------------------------------------------------------------
    def test_03_eviction_immunity_via_sqlite_persistence(self):
        expired_sid = "sess_to_evict_expired"
        cancelled_sid = "sess_to_evict_cancelled"

        # Record expired and cancelled sessions
        form_session_service.start_session(expired_sid, "road_opening")
        form_session_service.expire_session(expired_sid)

        form_session_service.start_session(cancelled_sid, "road_opening")
        form_session_service.cancel_session(cancelled_sid)

        # Confirm tracked initially
        self.assertTrue(form_session_service.is_session_expired(expired_sid))
        self.assertTrue(form_session_service.is_session_cancelled(cancelled_sid))

        # Evict from in-memory BoundedIdTracker by inserting 10,000 dummy IDs (capacity=5000)
        for i in range(10000):
            dummy = f"dummy_evict_sess_{i}"
            form_session_service.expired_session_ids.add(dummy)
            form_session_service.cancelled_session_ids.add(dummy)

        # In-memory trackers no longer contain the original IDs
        self.assertFalse(form_session_service.expired_session_ids.contains(expired_sid))
        self.assertFalse(form_session_service.cancelled_session_ids.contains(cancelled_sid))

        # Persistent authoritative checks STILL correctly report expired and cancelled
        self.assertTrue(form_session_service.is_session_expired(expired_sid), "Persistent SQLite must protect expired state")
        self.assertTrue(form_session_service.is_session_cancelled(cancelled_sid), "Persistent SQLite must protect cancelled state")
        self.assertEqual(form_session_service.get_session_lifecycle_status(expired_sid), "expired")
        self.assertEqual(form_session_service.get_session_lifecycle_status(cancelled_sid), "cancelled")

        # Incoming messages to evicted IDs are STILL blocked from RAG and LLM
        with patch("backend.app.rag_engine.rag_engine.answer_query") as mock_rag:
            resp_exp = chat_endpoint(ChatRequest(session_id=expired_sid, message="10 Oak Street"))
            self.assertEqual(resp_exp.mode, "form_fill")
            self.assertIn("expired", resp_exp.message.lower())
            self.assertFalse(mock_rag.called)

            resp_can = chat_endpoint(ChatRequest(session_id=cancelled_sid, message="10 Oak Street"))
            self.assertEqual(resp_can.mode, "form_fill")
            self.assertIn("cancelled", resp_can.message.lower())
            self.assertFalse(mock_rag.called)

    # -------------------------------------------------------------------------
    # Test 4: Positive Authorization - Files on disk without authorization record are rejected
    # -------------------------------------------------------------------------
    def test_04_positive_authorization_unregistered_file_rejected(self):
        sid = "unauth_file_test_sess"
        sess_dir = GENERATED_DRAFTS_DIR / sid
        sess_dir.mkdir(parents=True, exist_ok=True)
        ghost_pdf = sess_dir / "unauthorized_draft.pdf"
        ghost_pdf.write_bytes(b"%PDF-1.4 ghost content")

        try:
            # File exists on disk, but NO authorization record exists in form_lifecycle_store
            with self.assertRaises(HTTPException) as ctx:
                download_draft_pdf(session_id=sid, filename="unauthorized_draft.pdf")
            self.assertEqual(ctx.exception.status_code, 404)
            self.assertIn("unauthorized", ctx.exception.detail.lower())
        finally:
            shutil.rmtree(sess_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # Test 5: Session Isolation - Unauthorized session cannot download another session's draft
    # -------------------------------------------------------------------------
    def test_05_session_isolation_cross_session_download_blocked(self):
        sid_owner = "alice_legitimate_session"
        sid_attacker = "bob_malicious_session"

        answers = {"applicant_name": "Alice Resident", "applicant_phone": "732-555-0111"}
        ok, msg, file_path, download_url = pdf_filler.generate_draft_pdf(sid_owner, "road_opening", answers)
        self.assertTrue(ok)
        filename = Path(file_path).name

        try:
            # Owner can access with valid session_id
            resp = download_draft_pdf(session_id=sid_owner, filename=filename)
            self.assertIsInstance(resp, FileResponse)

            # Attacker attempting to download Alice's draft using their own session_id is blocked with 404
            with self.assertRaises(HTTPException) as ctx:
                download_draft_pdf(session_id=sid_attacker, filename=filename)
            self.assertEqual(ctx.exception.status_code, 404)
        finally:
            shutil.rmtree(GENERATED_DRAFTS_DIR / sid_owner, ignore_errors=True)

    # -------------------------------------------------------------------------
    # Test 6: Draft authorization expires after retention period (24 hours)
    # -------------------------------------------------------------------------
    def test_06_draft_authorization_retention_expiration(self):
        sid = "retention_test_sess"
        filename = "sample_road_draft.pdf"

        # Create authorization with 1-second retention
        token = form_lifecycle_store.create_draft_authorization(
            session_id=sid,
            filename=filename,
            retention_seconds=1
        )

        # Immediately valid
        auth_ok, _ = form_lifecycle_store.verify_draft_authorization(sid, filename, token=token)
        self.assertTrue(auth_ok)

        # Wait past retention window
        time.sleep(1.2)

        # Now expired
        auth_ok, auth_detail = form_lifecycle_store.verify_draft_authorization(sid, filename, token=token)
        self.assertFalse(auth_ok)
        self.assertIn("expired", auth_detail.lower())

        # Calling download endpoint raises HTTP 410
        with self.assertRaises(HTTPException) as ctx:
            download_draft_pdf(session_id=sid, filename=filename, token=token)
        self.assertEqual(ctx.exception.status_code, 410)
        self.assertIn("expired", ctx.exception.detail.lower())

    # -------------------------------------------------------------------------
    # Test 7: Token credential verification (valid token succeeds, tampered token returns 403)
    # -------------------------------------------------------------------------
    def test_07_download_token_verification_and_tampering_defense(self):
        sid = "token_defense_sess"
        answers = {"applicant_name": "Charlie", "applicant_phone": "732-555-0122"}
        ok, msg, file_path, download_url = pdf_filler.generate_draft_pdf(sid, "road_opening", answers)
        self.assertTrue(ok)
        filename = Path(file_path).name

        # Extract token from generated download URL
        self.assertIn("?token=", download_url)
        valid_token = download_url.split("?token=")[1]

        try:
            # 1. Valid token succeeds
            resp_valid = download_draft_pdf(session_id=sid, filename=filename, token=valid_token)
            self.assertIsInstance(resp_valid, FileResponse)

            # 2. Tampered / incorrect token returns HTTP 403 Forbidden
            with self.assertRaises(HTTPException) as ctx:
                download_draft_pdf(session_id=sid, filename=filename, token="tampered_forged_token_xyz")
            self.assertEqual(ctx.exception.status_code, 403)
            self.assertIn("invalid download authorization token", ctx.exception.detail.lower())
        finally:
            shutil.rmtree(GENERATED_DRAFTS_DIR / sid, ignore_errors=True)

    # -------------------------------------------------------------------------
    # Test 8: Concurrent generation and cleanup: cleanup does not delete directory during PDF canvas write
    # -------------------------------------------------------------------------
    def test_08_concurrent_pdf_generation_protected_from_cleanup(self):
        sid = "concurrent_active_gen_sess"
        sess_dir = GENERATED_DRAFTS_DIR / sid
        sess_dir.mkdir(parents=True, exist_ok=True)

        # Mark session in active generation
        form_session_service.begin_pdf_generation(sid)
        try:
            # Verify it is in protected session IDs
            self.assertIn(sid, form_session_service.get_protected_session_ids())

            # Attempt a cleanup sweep with max_age_seconds=0 (aggressive)
            deleted = form_session_service.cleanup_expired_drafts(max_age_seconds=0)

            # Session directory must NOT be deleted while generation is active
            self.assertTrue(sess_dir.exists(), "Active PDF generating directory must be preserved during cleanup")
        finally:
            form_session_service.end_pdf_generation(sid)
            shutil.rmtree(sess_dir, ignore_errors=True)

        # Also verify empty folder mtime race condition protection:
        # A folder created just now with standard retention (86400s) is NEVER deleted even if empty
        race_dir = GENERATED_DRAFTS_DIR / "newly_created_sess_folder"
        race_dir.mkdir(parents=True, exist_ok=True)
        try:
            form_session_service.cleanup_expired_drafts(max_age_seconds=86400)
            self.assertTrue(race_dir.exists(), "Newly created session folder (<24h) must not be deleted by cleanup")
        finally:
            shutil.rmtree(race_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # Test 9: Explicit restart unblocks session and creates fresh state without old answers or authorizations
    # -------------------------------------------------------------------------
    def test_09_explicit_restart_unblocks_session_with_clean_slate(self):
        sid = "restart_unblock_sess"

        # 1. Start session, answer question, and cancel it
        form_session_service.start_session(sid, "road_opening")
        form_session_service.answer_question(sid, "Old Answer Resident")
        form_session_service.cancel_session(sid)
        self.assertEqual(form_session_service.get_session_lifecycle_status(sid), "cancelled")

        # Blocked while cancelled
        resp_blocked = chat_endpoint(ChatRequest(session_id=sid, message="732-555-0100"))
        self.assertEqual(resp_blocked.mode, "form_fill")
        self.assertIn("cancelled", resp_blocked.message.lower())

        # 2. Explicitly restart a new session for the same session_id
        ok, start_msg, q_resp = form_session_service.start_session(sid, "road_opening")
        self.assertTrue(ok)
        self.assertEqual(form_session_service.get_session_lifecycle_status(sid), "in_progress")

        # Verify old answers were purged
        active_sess = form_session_service.get_session(sid)
        self.assertIsNotNone(active_sess)
        self.assertEqual(len(active_sess.answers), 0)

        # 3. Subsequent message is accepted as question 1 answer with fresh state
        resp_fresh = chat_endpoint(ChatRequest(session_id=sid, message="Fresh Citizen Name"))
        self.assertEqual(resp_fresh.mode, "form_fill")
        self.assertIn("Question 2 of", resp_fresh.message)
        self.assertEqual(active_sess.answers.get("applicant_name"), "Fresh Citizen Name")
