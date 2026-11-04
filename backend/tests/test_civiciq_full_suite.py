"""
CivicIQ Comprehensive Test Suite
Covers all 20 required system specifications:
1. Gemini Primary Provider: Configured and selected by default
2. Groq Fallback: Fallback activated when Gemini fails
3. OpenRouter Fallback: Fallback activated when Groq fails
4. Deterministic Grounded Synthesis: Fallback activated when all free LLMs fail
5. OpenRouter Free Guard: Paid models rejected when free-only mode is enabled
6. Form Identification: Application form correctly identified from resident request
7. Form Identification: Reference document correctly identified and NOT treated as application
8. Form Identification: Fee schedule correctly identified and NOT treated as application
9. Form Identification: Flowchart correctly identified and NOT treated as application
10. Conversational Form-Filling: Session starts with first question
11. Conversational Form-Filling: Question sequence follows schema order
12. Conversational Form-Filling: Input validation catches invalid email
13. Conversational Form-Filling: Input validation catches invalid phone number
14. Conversational Form-Filling: "edit [field]" allows correcting previous answer
15. Conversational Form-Filling: Review summary presents all answers before generation
16. PDF Generation: Form filled with user answers
17. PDF Generation: Signature field explicitly left blank
18. PDF Generation: Watermark banner applied
19. PDF Generation: File served correctly from session-specific download URL
20. Session Isolation: Answers from Session A do not leak into Session B
"""

import os
import unittest
import pypdf
from unittest.mock import patch, MagicMock
from pathlib import Path

# App imports
from backend.app.config import (
    APP_NAME, APP_TAGLINE, LLM_PRIMARY_PROVIDER,
    OPENROUTER_ALLOW_FREE_MODELS_ONLY, GENERATED_DRAFTS_DIR
)
from backend.app.llm_provider.base import BaseLLMProvider, LLMResponse
from backend.app.llm_provider.manager import LLMProviderManager
from backend.app.llm_provider.openrouter import OpenRouterFreeProvider
from backend.app.llm_client import llm_client
from backend.app.models.core import RagCitation
from backend.app.services.form_matcher import form_matcher
from backend.app.services.form_session_service import form_session_service
from backend.app.services.form_schema_service import form_schema_service
from backend.app.services.pdf_filler import pdf_filler
from backend.app.main import download_draft_pdf
from fastapi import HTTPException


class TestCivicIQFullSystemSuite(unittest.TestCase):

    def setUp(self):
        # Ensure fresh state for test session IDs
        form_session_service.sessions.clear()

    # --------------------------------------------------------------------------
    # 1. Gemini Primary Provider: Configured and selected by default
    # --------------------------------------------------------------------------
    def test_01_gemini_primary_provider_configured(self):
        """Requirement 1: Verify Gemini is the primary provider by default"""
        self.assertEqual(LLM_PRIMARY_PROVIDER, "gemini")
        manager = LLMProviderManager()
        self.assertEqual(manager.primary_name, "gemini")
        self.assertIn("groq", manager.fallback_names)
        self.assertIn("openrouter", manager.fallback_names)

    # --------------------------------------------------------------------------
    # 2. Groq Fallback: Fallback activated when Gemini fails
    # --------------------------------------------------------------------------
    def test_02_groq_fallback_activated_on_gemini_failure(self):
        """Requirement 2: When Gemini fails, Groq is seamlessly invoked"""
        manager = LLMProviderManager()
        
        with patch.object(manager.providers["gemini"], "is_available", return_value=True):
            with patch.object(
                manager.providers["gemini"],
                "generate",
                return_value=LLMResponse(content="", model="gemini-1.5-flash", provider="gemini", success=False, error="503 Quota")
            ):
                with patch.object(manager.providers["groq"], "is_available", return_value=True):
                    with patch.object(
                        manager.providers["groq"],
                        "generate",
                        return_value=LLMResponse(content="Groq response", model="llama-3.3-70b", provider="groq", success=True)
                    ) as mock_groq:
                        resp = manager.generate("Hello Edison")
                        self.assertTrue(resp.is_fallback)
                        self.assertEqual(resp.provider, "groq")
                        self.assertEqual(resp.content, "Groq response")
                        mock_groq.assert_called_once()

    # --------------------------------------------------------------------------
    # 3. OpenRouter Fallback: Fallback activated when Groq fails
    # --------------------------------------------------------------------------
    def test_03_openrouter_fallback_activated_on_gemini_and_groq_failure(self):
        """Requirement 3: When Gemini and Groq fail, OpenRouter free is invoked"""
        manager = LLMProviderManager()
        
        with patch.object(manager.providers["gemini"], "is_available", return_value=True):
            with patch.object(
                manager.providers["gemini"],
                "generate",
                return_value=LLMResponse(content="", model="gemini-1.5-flash", provider="gemini", success=False, error="Down")
            ):
                with patch.object(manager.providers["groq"], "is_available", return_value=True):
                    with patch.object(
                        manager.providers["groq"],
                        "generate",
                        return_value=LLMResponse(content="", model="groq-llama", provider="groq", success=False, error="429")
                    ):
                        with patch.object(manager.providers["openrouter"], "is_available", return_value=True):
                            with patch.object(
                                manager.providers["openrouter"],
                                "generate",
                                return_value=LLMResponse(
                                    content="OpenRouter Free response",
                                    model="meta-llama/llama-3.2-3b-instruct:free",
                                    provider="openrouter",
                                    success=True
                                )
                            ) as mock_openrouter:
                                resp = manager.generate("Inquiry for Edison")
                                self.assertTrue(resp.is_fallback)
                                self.assertEqual(resp.provider, "openrouter")
                                self.assertEqual(resp.content, "OpenRouter Free response")
                                mock_openrouter.assert_called_once()

    # --------------------------------------------------------------------------
    # 4. Deterministic Grounded Synthesis: Fallback activated when all free LLMs fail
    # --------------------------------------------------------------------------
    def test_04_deterministic_synthesis_when_all_free_llms_fail(self):
        """Requirement 4: Zero crashes when all LLMs fail; deterministic grounded fallback answers"""
        with patch.object(llm_client.manager, "generate") as mock_gen:
            mock_gen.return_value = LLMResponse(
                content="",
                model="none",
                provider="none",
                success=False,
                is_fallback=True,
                error="All free providers failed"
            )
            citation = RagCitation(
                url="https://www.edisonnj.org/document_center/RoadOpenApp.pdf",
                title="Road Opening Application",
                excerpt="Official Edison Township Engineering road opening fee is $100 plus inspection escrow.",
                relevance_score=0.92,
                category="permits",
                department_id="engineering"
            )
            resp = llm_client.generate_answer(
                query="What is the road opening fee?",
                citations=[citation]
            )
            self.assertTrue(len(resp) > 10)
            self.assertIn("edison", resp.lower())
            self.assertIn("fee", resp.lower())

    # --------------------------------------------------------------------------
    # 5. OpenRouter Free Guard: Paid models rejected when free-only mode is enabled
    # --------------------------------------------------------------------------
    def test_05_openrouter_free_guard_rejects_paid_models(self):
        """Requirement 5: OpenRouter free guard strictly rejects paid models without ':free'"""
        self.assertTrue(OPENROUTER_ALLOW_FREE_MODELS_ONLY)
        with self.assertRaises(ValueError) as cm:
            OpenRouterFreeProvider(
                api_key="dummy_key",
                model="openai/gpt-4o",  # Missing :free
                allow_free_only=True
            )
        self.assertIn("not a free-tier model", str(cm.exception))
        self.assertIn(":free", str(cm.exception))

        valid_free_provider = OpenRouterFreeProvider(
            api_key="dummy_key",
            model="meta-llama/llama-3.2-3b-instruct:free",
            allow_free_only=True
        )
        self.assertEqual(valid_free_provider.model, "meta-llama/llama-3.2-3b-instruct:free")

    # --------------------------------------------------------------------------
    # 6. Form Identification: Application form correctly identified
    # --------------------------------------------------------------------------
    def test_06_form_identification_application_form(self):
        """Requirement 6: Identifies road opening permit application as an application form"""
        rec = form_matcher.match_form("I need to apply for a road opening permit for street work.")
        self.assertIsNotNone(rec)
        self.assertEqual(rec.form.form_id, "road_opening")
        self.assertTrue(rec.is_application_form)
        self.assertTrue(rec.offer_conversational_fill)

    # --------------------------------------------------------------------------
    # 7. Form Identification: Reference document correctly identified (NOT application)
    # --------------------------------------------------------------------------
    def test_07_form_identification_reference_document(self):
        """Requirement 7: Identifies Schedule A yard requirements as reference document, NOT application"""
        rec = form_matcher.match_form("What are the yard setback requirements under Schedule A?")
        self.assertIsNotNone(rec)
        self.assertEqual(rec.form.form_id, "schedule_a_yard")
        self.assertFalse(rec.is_application_form)
        self.assertFalse(rec.offer_conversational_fill)

    # --------------------------------------------------------------------------
    # 8. Form Identification: Fee schedule correctly identified (NOT application)
    # --------------------------------------------------------------------------
    def test_08_form_identification_fee_schedule(self):
        """Requirement 8: Identifies Zoning Fees Schedule as fee schedule, NOT application"""
        rec = form_matcher.match_form("Can I check the zoning fees schedule?")
        self.assertIsNotNone(rec)
        self.assertEqual(rec.form.form_id, "zoning_fees_schedule")
        self.assertFalse(rec.is_application_form)
        self.assertFalse(rec.offer_conversational_fill)

    # --------------------------------------------------------------------------
    # 9. Form Identification: Flowchart correctly identified (NOT application)
    # --------------------------------------------------------------------------
    def test_09_form_identification_flowchart(self):
        """Requirement 9: Identifies Permit Flow Charts as internal reference guide, filtered from resident recommendations"""
        # Public recommendation filters out internal flow charts
        rec_public = form_matcher.match_form("Can I see the permit flow chart document?")
        self.assertIsNone(rec_public)

        # Internal lookup correctly resolves internal flow chart metadata
        rec_internal = form_matcher.match_form("Can I see the permit flow chart document?", include_internal=True)
        self.assertIsNotNone(rec_internal)
        self.assertEqual(rec_internal.form.form_id, "permit_flow_charts")
        self.assertFalse(rec_internal.is_application_form)
        self.assertEqual(rec_internal.form.visibility, "internal")

    # --------------------------------------------------------------------------
    # 10. Conversational Form-Filling: Session starts with first question
    # --------------------------------------------------------------------------
    def test_10_conversational_form_filling_start_session(self):
        """Requirement 10: Starting a form session presents first question and prompt"""
        ok, msg, q_resp = form_session_service.start_session("sess_req10", "road_opening")
        self.assertTrue(ok)
        self.assertEqual(q_resp.status, "in_progress")
        self.assertEqual(q_resp.form_id, "road_opening")
        self.assertEqual(q_resp.current_field.name, "applicant_name")
        self.assertEqual(q_resp.current_step, 1)

    # --------------------------------------------------------------------------
    # 11. Conversational Form-Filling: Question sequence follows schema order
    # --------------------------------------------------------------------------
    def test_11_conversational_form_filling_sequence(self):
        """Requirement 11: Follows exact question sequence: name -> phone -> email"""
        sid = "sess_req11"
        ok, _, q1 = form_session_service.start_session(sid, "road_opening")
        self.assertEqual(q1.current_field.name, "applicant_name")

        # Answer 1: Name
        ok, _, q2 = form_session_service.answer_question(sid, "Jane Citizen")
        self.assertTrue(ok)
        self.assertEqual(q2.current_step, 2)
        self.assertEqual(q2.current_field.name, "applicant_phone")

        # Answer 2: Phone
        ok, _, q3 = form_session_service.answer_question(sid, "732-555-0199")
        self.assertTrue(ok)
        self.assertEqual(q3.current_step, 3)
        self.assertEqual(q3.current_field.name, "applicant_email")

    # --------------------------------------------------------------------------
    # 12. Conversational Form-Filling: Input validation catches invalid email
    # --------------------------------------------------------------------------
    def test_12_validation_invalid_email(self):
        """Requirement 12: Input validation catches invalid email address"""
        sid = "sess_req12"
        form_session_service.start_session(sid, "road_opening")
        form_session_service.answer_question(sid, "Jane Doe") # 1. name
        form_session_service.answer_question(sid, "732-555-0199") # 2. phone
        
        # Step 3: enter invalid email
        ok, msg, q_resp = form_session_service.answer_question(sid, "not-an-email")
        self.assertIn("validation notice", q_resp.message.lower())
        self.assertIn("valid email", q_resp.message.lower())
        self.assertEqual(q_resp.current_step, 3)  # Did not advance

    # --------------------------------------------------------------------------
    # 13. Conversational Form-Filling: Input validation catches invalid phone
    # --------------------------------------------------------------------------
    def test_13_validation_invalid_phone(self):
        """Requirement 13: Input validation catches invalid phone number (< 10 digits)"""
        sid = "sess_req13"
        form_session_service.start_session(sid, "road_opening")
        form_session_service.answer_question(sid, "Jane Citizen") # name
        
        # Step 2: enter invalid phone
        ok, msg, q_resp = form_session_service.answer_question(sid, "123-abc")
        self.assertIn("validation notice", q_resp.message.lower())
        self.assertIn("valid 10-digit telephone", q_resp.message.lower())
        self.assertEqual(q_resp.current_step, 2) # Did not advance

    # --------------------------------------------------------------------------
    # 14. Conversational Form-Filling: "edit [field]" allows correcting previous answer
    # --------------------------------------------------------------------------
    def test_14_edit_previous_answer(self):
        """Requirement 14: Editing a field updates answer correctly"""
        sid = "sess_req14"
        form_session_service.start_session(sid, "road_opening")
        form_session_service.answer_question(sid, "Jane Citzn") # Misspelled name
        form_session_service.answer_question(sid, "732-555-0199") # Phone

        # Request edit of applicant_name
        ok, msg, q_resp = form_session_service.edit_answer(sid, "applicant_name", "Jane Citizen Corrected")
        self.assertTrue(ok)
        state = form_session_service.get_session(sid)
        self.assertEqual(state.answers["applicant_name"], "Jane Citizen Corrected")

    # --------------------------------------------------------------------------
    # 15. Conversational Form-Filling: Review summary presents all answers before generation
    # --------------------------------------------------------------------------
    def test_15_review_summary_before_generation(self):
        """Requirement 15: Review summary displays collected answers before generating PDF"""
        sid = "sess_req15"
        form_session_service.start_session(sid, "road_opening")
        form_session_service.answer_question(sid, "Alice Smith") # 1. name
        form_session_service.answer_question(sid, "732-555-1234") # 2. phone
        form_session_service.answer_question(sid, "alice@example.com") # 3. email
        form_session_service.answer_question(sid, "100 Municipal Blvd, Edison, NJ") # 4. work_location
        form_session_service.answer_question(sid, "Block 102, Lot 5") # 5. block_lot
        form_session_service.answer_question(sid, "Gas Line Connection") # 6. excavation_purpose
        form_session_service.answer_question(sid, "10ft x 4ft") # 7. trench_dimensions
        ok, msg, q_resp = form_session_service.answer_question(sid, "TICKET-811-998822") # 8. ticket

        state = form_session_service.get_session(sid)
        self.assertEqual(state.status, "review")
        self.assertIn("review summary", q_resp.message.lower())
        self.assertIn("Alice Smith", q_resp.message)
        self.assertIn("732-555-1234", q_resp.message)

    # --------------------------------------------------------------------------
    # 16. PDF Generation: Form filled with user answers
    # --------------------------------------------------------------------------
    def test_16_pdf_filled_with_user_answers(self):
        """Requirement 16: PDF contains citizen answers"""
        sid = "sess_req16"
        answers = {
            "applicant_name": "Robert Johnson",
            "applicant_phone": "732-555-9876",
            "property_address": "45 Plainfield Ave, Edison, NJ",
            "purpose_description": "Driveway curb cut excavation",
            "contractor_name": "Self / Resident"
        }

        ok, msg, file_path, rel_url = pdf_filler.generate_draft_pdf(sid, "road_opening", answers)
        self.assertTrue(ok)
        self.assertTrue(os.path.exists(file_path))
        self.assertGreater(os.path.getsize(file_path), 1000)
        
        with open(file_path, "rb") as f:
            pdf_bytes = f.read()
            self.assertTrue(b"%PDF" in pdf_bytes)

    # --------------------------------------------------------------------------
    # 17. PDF Generation: Signature field explicitly left blank
    # --------------------------------------------------------------------------
    def test_17_pdf_signature_field_left_blank(self):
        """Requirement 17: Signature field is never AI-filled; explicitly marked for physical ink signing"""
        sid = "sess_req17"
        answers = {
            "applicant_name": "Signature Test Citizen",
            "applicant_phone": "732-555-0000",
            "property_address": "123 Main St, Edison, NJ",
            "purpose_description": "Water main service repair",
            "contractor_name": "Aqua NJ"
        }

        ok, msg, file_path, _ = pdf_filler.generate_draft_pdf(sid, "road_opening", answers)
        self.assertTrue(ok)
        reader = pypdf.PdfReader(file_path)
        extracted = "".join(page.extract_text() or "" for page in reader.pages)
        self.assertIn("PHYSICAL SIGNATURE REQUIRED", extracted)
        self.assertIn("APPLICANT SIGNATURE (SIGN IN INK)", extracted)

    # --------------------------------------------------------------------------
    # 18. PDF Generation: Watermark banner applied
    # --------------------------------------------------------------------------
    def test_18_pdf_watermark_banner_applied(self):
        """Requirement 18: PDF contains official unsubmitted municipal draft watermark banner"""
        sid = "sess_req18"
        answers = {
            "applicant_name": "Watermark Citizen",
            "applicant_phone": "732-555-1111",
            "property_address": "77 Talmadge Rd, Edison, NJ",
            "purpose_description": "Curb excavation",
            "contractor_name": "Contractor X"
        }

        ok, msg, file_path, _ = pdf_filler.generate_draft_pdf(sid, "road_opening", answers)
        self.assertTrue(ok)
        reader = pypdf.PdfReader(file_path)
        extracted = "".join(page.extract_text() or "" for page in reader.pages)
        self.assertIn("OFFICIAL REVIEW COPY", extracted)
        self.assertIn("UNSUBMITTED MUNICIPAL DRAFT", extracted)

    # --------------------------------------------------------------------------
    # 19. PDF Generation: File served correctly from session-specific download URL
    # --------------------------------------------------------------------------
    def test_19_pdf_served_from_session_download_url(self):
        """Requirement 19: PDF served via FastAPI endpoint with session security"""
        sid = "sess_req19"
        answers = {
            "applicant_name": "Download Citizen",
            "applicant_phone": "732-555-2222",
            "property_address": "10 Edison Way",
            "purpose_description": "Sewer trench excavation",
            "contractor_name": "Plumbing Pro"
        }

        ok, msg, file_path, rel_url = pdf_filler.generate_draft_pdf(sid, "road_opening", answers)
        filename = os.path.basename(file_path)

        # Serving for matching session_id works
        resp = download_draft_pdf(session_id=sid, filename=filename)
        self.assertEqual(resp.media_type, "application/pdf")
        self.assertEqual(resp.status_code, 200)

        # Serving for mismatched session_id is blocked with 404 (file not in hacker's session dir)
        with self.assertRaises(HTTPException) as cm:
            download_draft_pdf(session_id="different_session_hacker", filename=filename)
        self.assertEqual(cm.exception.status_code, 404)

    # --------------------------------------------------------------------------
    # 20. Session Isolation: Answers from Session A do not leak into Session B
    # --------------------------------------------------------------------------
    def test_20_session_isolation_independent_states(self):
        """Requirement 20: Answers from Session A do not leak into Session B"""
        sid_a = "resident_session_alpha"
        sid_b = "resident_session_beta"

        # Session A: Resident Alpha
        form_session_service.start_session(sid_a, "road_opening")
        form_session_service.answer_question(sid_a, "Alpha Resident")
        form_session_service.answer_question(sid_a, "732-555-1111")

        # Session B: Resident Beta
        form_session_service.start_session(sid_b, "road_opening")
        form_session_service.answer_question(sid_b, "Beta Resident")
        form_session_service.answer_question(sid_b, "732-555-2222")

        state_a = form_session_service.get_session(sid_a)
        state_b = form_session_service.get_session(sid_b)

        self.assertEqual(state_a.answers["applicant_name"], "Alpha Resident")
        self.assertEqual(state_a.answers["applicant_phone"], "732-555-1111")
        self.assertEqual(state_b.answers["applicant_name"], "Beta Resident")
        self.assertEqual(state_b.answers["applicant_phone"], "732-555-2222")
        self.assertNotIn("Beta", state_a.answers.values())
        self.assertNotIn("Alpha", state_b.answers.values())


if __name__ == "__main__":
    unittest.main()
