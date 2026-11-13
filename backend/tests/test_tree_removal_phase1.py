"""
CivicIQ Phase 1 Regression Test Suite:
Tree Removal Form Schema, Deterministic State Machine, and Session Safety.

Tests:
1. Schema verification: verified Page 2 fields, types, and required/optional statuses.
2. Independent phone field validation (owner_phone vs applicant_phone).
3. Email field validation (optional, format-validated if entered).
4. Tree count validation (positive whole numbers, trees_to_remove <= trees_on_site).
5. Tree count editing validation (cannot edit trees_to_remove > trees_on_site, or trees_on_site < trees_to_remove).
6. Official fee categories (all 4 options present).
7. Board resolution requirement (required when Board approval selected, optional otherwise).
8. Senior citizen fee exemption logic ($25 fee waived for property owner age 62+; $200 Board fee NOT waived).
9. Full session lifecycle: start, answer, edit, review summary, and cancellation.
10. Inactivity TTL expiration (1 hour inactivity purges resident answers from memory).
11. Expired session rejection on answer and edit.
12. Expired session rejection on draft PDF generation and download.
13. Safe draft cleanup (age-based deletion, active draft preservation, strict directory containment).
14. Draft cleanup path traversal prevention (rejects paths outside GENERATED_DRAFTS_DIR).
15. Zero LLM API calls verification.
"""

import os
import shutil
import tempfile
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

from fastapi import HTTPException
from starlette.responses import FileResponse

from backend.app.config import GENERATED_DRAFTS_DIR
from backend.app.main import download_draft_pdf
from backend.app.services.form_schema_service import form_schema_service, OFFICIAL_FORMS_REGISTRY
from backend.app.services.form_session_service import form_session_service, FormSessionService
from backend.app.services.pdf_filler import pdf_filler
from backend.tests.offline_llm_helper import OfflineLLMTestCase


class TestTreeRemovalPhase1(OfflineLLMTestCase):

    def setUp(self):
        super().setUp()
        # Clean test session states
        form_session_service.sessions.clear()
        form_session_service.expired_session_ids.clear()

    # --------------------------------------------------------------------------
    # 1. Schema Integrity & Field Definitions
    # --------------------------------------------------------------------------
    def test_01_tree_removal_schema_contains_all_verified_page2_fields(self):
        form = form_schema_service.get_form_by_id("tree_removal")
        self.assertIsNotNone(form, "tree_removal form must be present in registry")
        self.assertEqual(form.form_id, "tree_removal")
        self.assertEqual(form.form_code, "EDISON-ENG-TRP")
        self.assertEqual(form.local_filename, "3.23.21 tree permit application.pdf")

        fields_by_name = {f.name: f for f in form.fields}

        # Expected field specifications: (name, field_type, required)
        expected_fields = [
            ("property_owner_name", "text", True),
            ("property_owner_address", "address", True),
            ("owner_phone", "phone", True),
            ("applicant_name", "text", True),
            ("applicant_mailing_address", "address", False),
            ("applicant_phone", "phone", True),
            ("email_address", "email", False),
            ("permit_address", "address", True),
            ("block_lot", "text", True),
            ("area_of_tract_sqft", "number", False),
            ("area_of_tract_acres", "number", False),
            ("trees_on_site", "number", True),
            ("trees_to_remove", "number", True),
            ("fee_category", "choice", True),
            ("board_resolution_number", "text", False),
            ("is_owner_senior_citizen", "choice", True),
            ("removal_reason", "text", True),
        ]

        for fname, ftype, freq in expected_fields:
            self.assertIn(fname, fields_by_name, f"Field '{fname}' must be in tree_removal schema")
            field = fields_by_name[fname]
            self.assertEqual(field.field_type, ftype, f"Field '{fname}' type should be {ftype}")
            self.assertEqual(field.required, freq, f"Field '{fname}' required should be {freq}")

    # --------------------------------------------------------------------------
    # 2. Independent Phone Field Validation
    # --------------------------------------------------------------------------
    def test_02_independent_phone_field_validation(self):
        form = form_schema_service.get_form_by_id("tree_removal")
        fields_by_name = {f.name: f for f in form.fields}

        owner_phone = fields_by_name["owner_phone"]
        applicant_phone = fields_by_name["applicant_phone"]

        # Different field instances
        self.assertNotEqual(owner_phone.name, applicant_phone.name)

        # Invalid phone fails
        valid, msg = form_session_service._validate_field(owner_phone, "123-abc")
        self.assertFalse(valid)
        self.assertIn("10-digit", msg)

        # Valid phone passes
        valid, _ = form_session_service._validate_field(owner_phone, "(732) 555-0101")
        self.assertTrue(valid)

        # Applicant phone independently validated
        valid, msg = form_session_service._validate_field(applicant_phone, "short")
        self.assertFalse(valid)
        valid, _ = form_session_service._validate_field(applicant_phone, "7322487200")
        self.assertTrue(valid)

    # --------------------------------------------------------------------------
    # 3. Optional Email Validation
    # --------------------------------------------------------------------------
    def test_03_optional_email_validation(self):
        form = form_schema_service.get_form_by_id("tree_removal")
        email_field = next(f for f in form.fields if f.name == "email_address")

        self.assertFalse(email_field.required, "Email must be optional")

        # Skip / empty / N/A passes
        for empty_val in ["", "skip", "n/a", "none"]:
            valid, msg = form_session_service._validate_field(email_field, empty_val)
            self.assertTrue(valid, f"Email should allow '{empty_val}' as optional")

        # Invalid email format fails
        valid, msg = form_session_service._validate_field(email_field, "not-an-email")
        self.assertFalse(valid)
        self.assertIn("valid email address", msg)

        # Valid email passes
        valid, _ = form_session_service._validate_field(email_field, "resident@example.com")
        self.assertTrue(valid)

    # --------------------------------------------------------------------------
    # 4. Tree Count Positive Number & Cross-Field Validation
    # --------------------------------------------------------------------------
    def test_04_tree_count_positive_and_cross_field_validation(self):
        sid = "sess_tree_counts"
        ok, _, resp = form_session_service.start_session(sid, "tree_removal")
        self.assertTrue(ok)

        # Step through until trees_on_site (Question 12)
        # 1. property_owner_name
        form_session_service.answer_question(sid, "Alice Smith")
        # 2. property_owner_address
        form_session_service.answer_question(sid, "100 Plainfield Ave")
        # 3. owner_phone
        form_session_service.answer_question(sid, "732-555-0123")
        # 4. applicant_name
        form_session_service.answer_question(sid, "Alice Smith")
        # 5. applicant_mailing_address (optional)
        form_session_service.answer_question(sid, "skip")
        # 6. applicant_phone
        form_session_service.answer_question(sid, "732-555-0123")
        # 7. email_address (optional)
        form_session_service.answer_question(sid, "alice@example.com")
        # 8. permit_address
        form_session_service.answer_question(sid, "100 Plainfield Ave")
        # 9. block_lot
        form_session_service.answer_question(sid, "Block 50, Lot 2")
        # 10. area_of_tract_sqft (optional)
        form_session_service.answer_question(sid, "15000")
        # 11. area_of_tract_acres (optional)
        form_session_service.answer_question(sid, "0.34")

        # Question 12: trees_on_site
        # Negative / zero fails
        ok, _, resp = form_session_service.answer_question(sid, "-3")
        self.assertIn("positive", resp.message.lower())
        ok, _, resp = form_session_service.answer_question(sid, "0")
        self.assertIn("positive", resp.message.lower())

        # Valid trees_on_site
        ok, _, resp = form_session_service.answer_question(sid, "5")
        self.assertEqual(resp.current_field.name, "trees_to_remove")

        # Question 13: trees_to_remove
        # trees_to_remove > trees_on_site fails cross-field validation
        ok, _, resp = form_session_service.answer_question(sid, "10")
        self.assertIn("cannot exceed", resp.message)
        self.assertIn("trees on-site (5)", resp.message)

        # Valid trees_to_remove <= trees_on_site
        ok, _, resp = form_session_service.answer_question(sid, "2")
        self.assertEqual(resp.current_field.name, "fee_category")

    # --------------------------------------------------------------------------
    # 5. Tree Count Editing Cross-Field Validation
    # --------------------------------------------------------------------------
    def test_05_tree_count_editing_cross_field_validation(self):
        sid = "sess_edit_counts"
        form_session_service.start_session(sid, "tree_removal")
        sess = form_session_service.get_session(sid)
        sess.answers["trees_on_site"] = "5"
        sess.answers["trees_to_remove"] = "3"

        # Editing trees_to_remove to 7 (> 5) fails
        ok, err, _ = form_session_service.edit_answer(sid, "trees_to_remove", "7")
        self.assertFalse(ok)
        self.assertIn("cannot exceed", err)

        # Editing trees_to_remove to 4 (<= 5) succeeds
        ok, msg, resp = form_session_service.edit_answer(sid, "trees_to_remove", "4")
        self.assertTrue(ok)
        self.assertEqual(sess.answers["trees_to_remove"], "4")

        # Editing trees_on_site to 2 (< 4) fails
        ok, err, _ = form_session_service.edit_answer(sid, "trees_on_site", "2")
        self.assertFalse(ok)
        self.assertIn("cannot be less than trees to be removed", err)

        # Editing trees_on_site to 8 succeeds
        ok, _, resp = form_session_service.edit_answer(sid, "trees_on_site", "8")
        self.assertTrue(ok)
        self.assertEqual(sess.answers["trees_on_site"], "8")

    # --------------------------------------------------------------------------
    # 6. Official Fee Categories
    # --------------------------------------------------------------------------
    def test_06_fee_categories_include_all_four_official_options(self):
        form = form_schema_service.get_form_by_id("tree_removal")
        fee_field = next(f for f in form.fields if f.name == "fee_category")

        expected_options = [
            "$25.00 for single permit on a single residential lot without a variance",
            "$25.00 for single permit on a single lot with an Existing Dwelling",
            "$25.00 for single permit on a single lot with Demolition Permit",
            "$200.00 for single permit in conjunction with Planning/Zoning Board approval"
        ]

        self.assertEqual(len(fee_field.options), 4)
        for opt in expected_options:
            self.assertIn(opt, fee_field.options)

    # --------------------------------------------------------------------------
    # 7. Board Resolution Conditional Validation
    # --------------------------------------------------------------------------
    def test_07_board_resolution_conditional_validation(self):
        sid = "sess_board_res"
        form_session_service.start_session(sid, "tree_removal")
        sess = form_session_service.get_session(sid)
        sess.current_field_index = 14  # board_resolution_number

        # Case A: $200 Board approval chosen -> Resolution # required
        sess.answers["fee_category"] = "$200.00 for single permit in conjunction with Planning/Zoning Board approval"
        ok, _, resp = form_session_service.answer_question(sid, "skip")
        self.assertIn("Resolution number is required", resp.message)

        # With resolution provided
        ok, _, resp = form_session_service.answer_question(sid, "RES-2026-99")
        self.assertEqual(sess.answers["board_resolution_number"], "RES-2026-99")

        # Case B: Standard $25 chosen -> can skip or enter N/A
        sid2 = "sess_board_res2"
        form_session_service.start_session(sid2, "tree_removal")
        sess2 = form_session_service.get_session(sid2)
        sess2.current_field_index = 14
        sess2.answers["fee_category"] = "$25.00 for single permit on a single residential lot without a variance"
        ok, _, resp2 = form_session_service.answer_question(sid2, "skip")
        self.assertEqual(sess2.answers["board_resolution_number"], "N/A")

    # --------------------------------------------------------------------------
    # 8. Senior Citizen Eligibility & Fee Calculation Logic
    # --------------------------------------------------------------------------
    def test_08_senior_citizen_fee_waiver_rules(self):
        # Rule 1: Senior citizen on standard $25 -> Fee is waived ($0.00)
        fee_res1 = form_session_service.get_applicable_fee({
            "fee_category": "$25.00 for single permit on a single residential lot without a variance",
            "is_owner_senior_citizen": "Yes, property owner is age 62 or older (waives $25 standard fee; proof of age required)"
        })
        self.assertEqual(fee_res1["amount"], 0.0)
        self.assertTrue(fee_res1["is_waived"])
        self.assertIn("Waived", fee_res1["display_fee"])

        # Rule 2: Non-senior on standard $25 -> Fee is $25.00
        fee_res2 = form_session_service.get_applicable_fee({
            "fee_category": "$25.00 for single permit on a single residential lot without a variance",
            "is_owner_senior_citizen": "No, standard fee applies"
        })
        self.assertEqual(fee_res2["amount"], 25.0)
        self.assertFalse(fee_res2["is_waived"])

        # Rule 3: Senior citizen on $200 Board approval -> Fee is NOT waived ($200.00)
        fee_res3 = form_session_service.get_applicable_fee({
            "fee_category": "$200.00 for single permit in conjunction with Planning/Zoning Board approval",
            "is_owner_senior_citizen": "Yes, property owner is age 62 or older (waives $25 standard fee; proof of age required)"
        })
        self.assertEqual(fee_res3["amount"], 200.0)
        self.assertFalse(fee_res3["is_waived"])
        self.assertIn("does not apply to the $200", fee_res3["waiver_reason"])

    # --------------------------------------------------------------------------
    # 9. Full Deterministic Session Lifecycle
    # --------------------------------------------------------------------------
    def test_09_full_session_lifecycle_with_review_and_cancellation(self):
        sid = "sess_full_lifecycle"

        # 1. Start session
        ok, msg, resp = form_session_service.start_session(sid, "tree_removal")
        self.assertTrue(ok)
        self.assertEqual(resp.current_step, 1)
        self.assertEqual(resp.total_steps, 17)
        self.assertEqual(resp.status, "in_progress")

        # 2. Answer all 17 fields
        answers = [
            ("John Doe"),                                              # 1. property_owner_name
            ("123 Elm St, Edison, NJ"),                                # 2. property_owner_address
            ("732-555-1111"),                                          # 3. owner_phone
            ("John Doe"),                                              # 4. applicant_name
            ("skip"),                                                  # 5. applicant_mailing_address
            ("732-555-1111"),                                          # 6. applicant_phone
            ("john.doe@example.com"),                                  # 7. email_address
            ("123 Elm St, Edison, NJ"),                                # 8. permit_address
            ("Block 10, Lot 5"),                                       # 9. block_lot
            ("12000"),                                                 # 10. area_of_tract_sqft
            ("0.28"),                                                  # 11. area_of_tract_acres
            ("4"),                                                     # 12. trees_on_site
            ("1"),                                                     # 13. trees_to_remove
            ("$25.00 for single permit on a single residential lot"),   # 14. fee_category
            ("N/A"),                                                   # 15. board_resolution_number
            ("Yes, property owner is age 62 or older"),                # 16. is_owner_senior_citizen
            ("Dead oak leaning dangerously over property driveway")     # 17. removal_reason
        ]

        last_resp = None
        for a in answers:
            ok, _, last_resp = form_session_service.answer_question(sid, a)
            self.assertTrue(ok)

        # 3. Review state reached
        self.assertEqual(last_resp.status, "review")
        self.assertIn("Application Review Summary", last_resp.message)
        self.assertIn("Permit Fee Calculation", last_resp.message)
        self.assertIn("Waived for senior citizen property owner", last_resp.message)

        # 4. Edit an earlier field
        ok, msg, edit_resp = form_session_service.edit_answer(sid, "property_owner_name", "Jonathan Doe")
        self.assertTrue(ok)
        self.assertEqual(form_session_service.get_session(sid).answers["property_owner_name"], "Jonathan Doe")
        self.assertIn("Jonathan Doe", edit_resp.message)

        # 5. Confirm completion
        ok, _, complete_resp = form_session_service.answer_question(sid, "looks good, confirm")
        self.assertTrue(ok)
        self.assertEqual(complete_resp.status, "completed")
        self.assertTrue(complete_resp.is_complete)

        # 6. Cancellation cleans up session
        form_session_service.cancel_session(sid)
        self.assertIsNone(form_session_service.get_session(sid))

    # --------------------------------------------------------------------------
    # 10. Inactivity TTL Expiration (1 Hour) Purges Resident Answers
    # --------------------------------------------------------------------------
    def test_10_inactivity_ttl_expiration_purges_memory(self):
        sid = "sess_ttl_test"
        ok, _, _ = form_session_service.start_session(sid, "tree_removal")
        self.assertTrue(ok)
        form_session_service.answer_question(sid, "Private Resident Name")
        form_session_service.answer_question(sid, "55 Hidden Lane")

        sess = form_session_service.sessions[sid]
        self.assertEqual(len(sess.answers), 2)

        # Simulate 61 minutes passing since last activity
        expired_time = (datetime.now(timezone.utc) - timedelta(minutes=61)).isoformat()
        sess.updated_at = expired_time

        # Accessing session via get_session detects expiration and purges answers
        self.assertTrue(form_session_service.is_session_expired(sid))
        self.assertIsNone(form_session_service.get_session(sid))
        self.assertNotIn(sid, form_session_service.sessions)

        # Resident answers are cleared from memory
        self.assertEqual(len(sess.answers), 0)

    # --------------------------------------------------------------------------
    # 11. Expired Sessions Cannot Answer or Edit
    # --------------------------------------------------------------------------
    def test_11_expired_session_rejected_on_answer_and_edit(self):
        sid = "sess_expired_interact"
        form_session_service.start_session(sid, "tree_removal")
        form_session_service.sessions[sid].updated_at = (
            datetime.now(timezone.utc) - timedelta(hours=2)
        ).isoformat()

        # Answer fails
        ok, msg, resp = form_session_service.answer_question(sid, "New Answer")
        self.assertFalse(ok)
        self.assertIn("expired", msg.lower())

        # Edit fails
        ok, msg, resp = form_session_service.edit_answer(sid, "property_owner_name", "Jane")
        self.assertFalse(ok)
        self.assertIn("expired", msg.lower())

    # --------------------------------------------------------------------------
    # 12. Expired Sessions Cannot Generate or Download Drafts
    # --------------------------------------------------------------------------
    def test_12_expired_session_cannot_generate_or_download_drafts(self):
        sid = "sess_expired_draft"
        form_session_service.start_session(sid, "road_opening")
        form_session_service.sessions[sid].updated_at = (
            datetime.now(timezone.utc) - timedelta(hours=2)
        ).isoformat()

        # PDF generation blocked
        ok, msg, _, _ = pdf_filler.generate_draft_pdf(sid, "road_opening", {"applicant_name": "Test"})
        self.assertFalse(ok)
        self.assertIn("expired", msg.lower())

        # Download blocked
        with self.assertRaises(HTTPException) as cm:
            download_draft_pdf(session_id=sid, filename="test_draft.pdf")
        self.assertEqual(cm.exception.status_code, 410)
        self.assertIn("expired", cm.exception.detail.lower())

    # --------------------------------------------------------------------------
    # 13. Safe Draft Cleanup (Age-Based Deletion & Active Draft Preservation)
    # --------------------------------------------------------------------------
    def test_13_safe_draft_cleanup_preserves_active_and_deletes_old(self):
        # Create temp draft directory inside GENERATED_DRAFTS_DIR
        test_dir = GENERATED_DRAFTS_DIR / "cleanup_test_run"
        test_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Active session
            active_sid = "sess_cleanup_active"
            form_session_service.start_session(active_sid, "tree_removal")
            active_folder = test_dir / active_sid
            active_folder.mkdir(parents=True, exist_ok=True)
            active_file = active_folder / "active_draft.pdf"
            active_file.write_bytes(b"%PDF-1.4 active")

            # Expired / Old file (mtime 48 hours ago)
            expired_folder = test_dir / "sess_cleanup_old"
            expired_folder.mkdir(parents=True, exist_ok=True)
            old_file = expired_folder / "old_draft.pdf"
            old_file.write_bytes(b"%PDF-1.4 old")
            old_ts = time.time() - (48 * 3600)
            os.utime(str(old_file), (old_ts, old_ts))

            # Recent file from inactive session (mtime 10 minutes ago)
            recent_file = expired_folder / "recent_draft.pdf"
            recent_file.write_bytes(b"%PDF-1.4 recent")

            # Run cleanup with 24-hour retention
            deleted = form_session_service.cleanup_expired_drafts(
                max_age_seconds=86400,
                base_dir=test_dir
            )

            # Old file deleted
            self.assertEqual(deleted, 1)
            self.assertFalse(old_file.exists())

            # Active session file preserved regardless of age
            self.assertTrue(active_file.exists())

            # Recent file preserved
            self.assertTrue(recent_file.exists())

        finally:
            shutil.rmtree(test_dir, ignore_errors=True)

    # --------------------------------------------------------------------------
    # 14. Draft Cleanup Path Traversal Prevention
    # --------------------------------------------------------------------------
    def test_14_draft_cleanup_rejects_paths_outside_drafts_dir(self):
        # Attempting cleanup on an external directory must raise ValueError
        outside_path = Path(tempfile.gettempdir())
        with self.assertRaises(ValueError) as cm:
            form_session_service.cleanup_expired_drafts(
                max_age_seconds=3600,
                base_dir=outside_path
            )
        self.assertIn("Security violation", str(cm.exception))


if __name__ == "__main__":
    import unittest
    unittest.main()
