"""
Comprehensive Integration & Regression Tests for Conversational Intent Ambiguity & Chatbot Response Style
Validates Section 11 (Short, Ambiguous & Contextual Resident Messages) and
Section 12 (Chatbot Response Style Following Reference Presentation).
"""

import unittest
from backend.app.main import chat_endpoint, CHAT_HISTORIES
from backend.app.models import ChatRequest
from backend.app.flow_engine import flow_engine
from backend.app.services.form_session_service import form_session_service
from backend.app.services.service_intent_service import service_intent_service
from backend.app.config import UNCONFIGURED_SERVICE_MESSAGE


class TestConversationalIntentAmbiguity(unittest.TestCase):

    def setUp(self):
        CHAT_HISTORIES.clear()
        flow_engine.sessions.clear()
        form_session_service.sessions.clear()

    # =========================================================================
    # SECTION 11: SHORT, AMBIGUOUS & CONTEXTUAL RESIDENT MESSAGES
    # =========================================================================

    def test_01_ambiguous_query_removal(self):
        """'removal' -> Ask 'What would you like to remove — a tree or soil?' without dumping extracts."""
        res = chat_endpoint(ChatRequest(
            session_id="sess_ambig_removal",
            message="removal"
        ))

        self.assertIn("What would you like to remove — a tree or soil?", res.message)
        self.assertIsNotNone(res.options)
        labels = [opt.label for opt in res.options]
        self.assertIn("Tree", labels)
        self.assertIn("Soil", labels)
        self.assertIn("Something else", labels)

        # Must NOT dump document chunks or form packets prematurely
        self.assertIsNone(res.form_packet)
        self.assertEqual(len(res.citations or []), 0)

    def test_02_ambiguous_query_i_want_to_remove_something(self):
        """'I want to remove something' -> Ask 'What would you like to remove — a tree or soil?'"""
        res = chat_endpoint(ChatRequest(
            session_id="sess_ambig_remove_something",
            message="I want to remove something"
        ))

        self.assertIn("What would you like to remove — a tree or soil?", res.message)
        self.assertIsNotNone(res.options)
        self.assertIsNone(res.form_packet)

    def test_03_ambiguous_query_i_need_a_removal_permit(self):
        """'I need a removal permit' -> Ask 'What would you like to remove — a tree or soil?'"""
        res = chat_endpoint(ChatRequest(
            session_id="sess_ambig_need_removal_permit",
            message="I need a removal permit"
        ))

        self.assertIn("What would you like to remove — a tree or soil?", res.message)
        self.assertIsNotNone(res.options)
        self.assertIsNone(res.form_packet)

    def test_04_ambiguous_query_permit(self):
        """'permit' -> Clarify which engineering permit."""
        res = chat_endpoint(ChatRequest(
            session_id="sess_ambig_permit",
            message="permit"
        ))

        self.assertIn("Which Engineering permit are you looking for", res.message)
        self.assertIsNotNone(res.options)
        labels = [opt.label for opt in res.options]
        self.assertTrue(any("Tree" in l for l in labels))
        self.assertTrue(any("Soil" in l for l in labels))
        self.assertIsNone(res.form_packet)

    def test_05_ambiguous_query_application(self):
        """'application' -> Clarify which official application form."""
        res = chat_endpoint(ChatRequest(
            session_id="sess_ambig_application",
            message="application"
        ))

        self.assertIn("Which official application form do you need?", res.message)
        self.assertIsNotNone(res.options)
        labels = [opt.label for opt in res.options]
        self.assertTrue(any("Tree" in l for l in labels))
        self.assertTrue(any("Soil Import" in l for l in labels))
        self.assertTrue(any("Soil Export" in l for l in labels))
        self.assertIsNone(res.form_packet)

    def test_06_ambiguous_query_excavation(self):
        """'excavation' -> Ask whether property soil removal (export) or street/pavement."""
        res = chat_endpoint(ChatRequest(
            session_id="sess_ambig_excavation",
            message="excavation"
        ))

        self.assertIn("excavate and remove soil from your property (Soil Export)", res.message)
        self.assertIsNotNone(res.options)
        labels = [opt.label for opt in res.options]
        self.assertTrue(any("Soil Export" in l for l in labels))
        self.assertTrue(any("Street" in l for l in labels))
        self.assertIsNone(res.form_packet)

    def test_07_ambiguous_query_tree(self):
        """Standalone 'tree' -> Ask whether removing tree or inquiring about fees/rules."""
        res = chat_endpoint(ChatRequest(
            session_id="sess_ambig_tree",
            message="tree"
        ))

        self.assertIn("I can help with Edison Township tree regulations", res.message)
        self.assertIsNotNone(res.options)
        labels = [opt.label for opt in res.options]
        self.assertTrue(any("Remove a tree" in l for l in labels))
        self.assertTrue(any("fees" in l.lower() for l in labels))
        self.assertIsNone(res.form_packet)

    def test_08_ambiguous_query_soil(self):
        """Standalone 'soil' -> Clarify import vs export."""
        res = chat_endpoint(ChatRequest(
            session_id="sess_ambig_soil",
            message="soil"
        ))

        self.assertIn("bring soil onto your property (Soil Import) or remove soil from your property (Soil Export)", res.message)
        self.assertIsNotNone(res.options)
        labels = [opt.label for opt in res.options]
        self.assertTrue(any("Import" in l for l in labels))
        self.assertTrue(any("Export" in l for l in labels))
        self.assertIsNone(res.form_packet)

    # =========================================================================
    # MULTI-TURN RESOLUTION OF AMBIGUOUS FLOWS
    # =========================================================================

    def test_09_followup_removal_to_tree(self):
        """Resident says 'removal' -> CivicIQ clarifies -> Resident selects/types 'Tree' -> Tree workflow."""
        # Turn 1: 'removal'
        chat_endpoint(ChatRequest(
            session_id="sess_flow_removal_tree",
            message="removal"
        ))

        # Turn 2: 'Tree'
        res = chat_endpoint(ChatRequest(
            session_id="sess_flow_removal_tree",
            message="Tree",
            selected_option_id="opt_remove_tree"
        ))

        msg = res.message.lower()
        self.assertTrue("tree-removal" in msg or "tree removal" in msg)
        self.assertIn("planning to remove", msg)
        self.assertIsNotNone(res.options)

    def test_10_followup_removal_to_soil_routes_to_soil_export(self):
        """
        Resident says 'removal' -> CivicIQ clarifies -> Resident selects/types 'Soil'.
        Crucial requirement: Understand that the resident means Soil Export (removing soil)
        and continue with the Soil Export workflow (10+ cu. yds volume question).
        """
        # Turn 1: 'removal'
        chat_endpoint(ChatRequest(
            session_id="sess_flow_removal_soil",
            message="removal"
        ))

        # Turn 2: 'Soil'
        res = chat_endpoint(ChatRequest(
            session_id="sess_flow_removal_soil",
            message="Soil",
            selected_option_id="opt_remove_soil"
        ))

        msg = res.message.lower()
        # Must specifically be Soil Export!
        self.assertIn("soil export requirements", msg)
        self.assertIn("10 cubic yards or more", msg)
        self.assertIsNotNone(res.options)
        labels = [opt.label for opt in res.options]
        self.assertIn("10 cubic yards or more", labels)
        self.assertIn("Less than 10 cubic yards", labels)

    def test_11_followup_removal_to_something_else(self):
        """Resident says 'removal' -> CivicIQ clarifies -> Resident selects 'Something else'."""
        # Turn 1: 'removal'
        chat_endpoint(ChatRequest(
            session_id="sess_flow_removal_other",
            message="removal"
        ))

        # Turn 2: 'Something else'
        res = chat_endpoint(ChatRequest(
            session_id="sess_flow_removal_other",
            message="Something else",
            selected_option_id="opt_remove_other"
        ))

        msg = res.message.lower()
        self.assertIn("what type of municipal service", msg)
        self.assertIn("edison document center", msg)

    def test_12_followup_excavation_street_to_unconfigured(self):
        """Resident says 'excavation' -> selects 'Street / pavement excavation' -> provides blank RoadOpenApp.pdf and Public Works notice."""
        # Turn 1: 'excavation'
        chat_endpoint(ChatRequest(
            session_id="sess_flow_excav_street",
            message="excavation"
        ))

        # Turn 2: 'Street / pavement excavation'
        res = chat_endpoint(ChatRequest(
            session_id="sess_flow_excav_street",
            message="Street / pavement excavation",
            selected_option_id="opt_excavate_street"
        ))

        self.assertIn("RoadOpenApp.pdf", res.message)
        self.assertIn("Public Works", res.message)

    # =========================================================================
    # MULTI-TURN CONTEXT PRESERVATION
    # =========================================================================

    def test_13_multiturn_context_preservation_tree(self):
        """Preserve conversation context across 'How much?', 'What documents?', 'Where do I apply?'"""
        # Turn 1: Tree removal cost
        res1 = chat_endpoint(ChatRequest(
            session_id="sess_multi_ctx",
            message="Tree removal cost"
        ))
        self.assertIn("$25", res1.message)
        self.assertIn("62 or older", res1.message)

        # Turn 2: 'What documents do I need?' without mentioning tree
        res2 = chat_endpoint(ChatRequest(
            session_id="sess_multi_ctx",
            message="What documents do I need?"
        ))
        self.assertIn("Survey or Tax Map", res2.message)
        self.assertIn("Tree Removal Permit", res2.message)

        # Turn 3: 'Where do I apply?'
        res3 = chat_endpoint(ChatRequest(
            session_id="sess_multi_ctx",
            message="Where do I apply?"
        ))
        self.assertIn("Division of Engineering", res3.message)
        self.assertIn("100 Municipal Boulevard", res3.message)

        # Turn 4: 'Is it required?'
        res4 = chat_endpoint(ChatRequest(
            session_id="sess_multi_ctx",
            message="Is it required?"
        ))
        self.assertTrue(
            "tree removal" in res4.message.lower() or
            "permit is required" in res4.message.lower() or
            "permit" in res4.message.lower()
        )

    # =========================================================================
    # SECTION 12: CHATBOT RESPONSE STYLE & ACTION BUTTONS
    # =========================================================================

    def test_14_response_style_direct_first_sentence_and_bullets(self):
        """Responses must have direct first sentence, bullet points, clean source reference, and no form-filling prompt for Tree Removal."""
        res = chat_endpoint(ChatRequest(
            session_id="sess_style_direct",
            message="Tree removal cost"
        ))

        msg = res.message
        # 1. Direct answer in first sentence
        first_line = msg.strip().split("\n")[0]
        self.assertIn("$25", first_line)

        # 2. Bullet points
        self.assertIn("•", msg)

        # 3. Compact clickable source reference
        self.assertIn("Source: [Township of Edison Tree Permit Application](/api/forms/engineering/3.23.21%20tree%20permit%20application.pdf)", msg)

        # 4. Form-filling prompts and buttons must NOT be emitted for Tree Removal on deployment branch
        self.assertNotIn("Would you like help with the application?", msg)
        self.assertIsNone(res.options)

    def test_15_tree_removal_form_filling_disabled(self):
        """Verifies interactive Tree Removal form filling cannot be started and points to the official blank PDF."""
        # Setup context with Tree Removal
        chat_endpoint(ChatRequest(
            session_id="sess_apply_tree_disabled",
            message="Tree removal cost"
        ))

        # Resident attempts to start form filling
        res = chat_endpoint(ChatRequest(
            session_id="sess_apply_tree_disabled",
            message="Help me fill out tree removal application"
        ))

        # Must NOT enter form_fill mode
        self.assertNotEqual(res.mode, "form_fill")
        self.assertIsNone(res.form_session_info)
        self.assertIn("unavailable", res.message.lower())
        self.assertIn("3.23.21%20tree%20permit%20application.pdf", res.message)

        # Direct API endpoint call must also be blocked
        from fastapi import HTTPException
        from backend.app.main import start_form_session
        from backend.app.models.form_session import FormStartSessionRequest
        with self.assertRaises(HTTPException) as cm:
            start_form_session(FormStartSessionRequest(session_id="sess_api_block", form_id="tree_removal"))
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("unavailable", cm.exception.detail.lower())

    def test_16_action_button_no_thanks_returns_friendly_closure(self):
        """Clicking or sending 'No, thanks' returns a polite closure message."""
        # Setup context
        chat_endpoint(ChatRequest(
            session_id="sess_apply_no",
            message="Tree removal cost"
        ))

        # Resident clicks 'No, thanks'
        res = chat_endpoint(ChatRequest(
            session_id="sess_apply_no",
            message="No, thanks",
            selected_option_id="opt_apply_no"
        ))

        self.assertIn("No problem! Let me know if you need any other assistance", res.message)
        self.assertFalse(res.completed)

    def test_17_no_robotic_fallback_artifacts(self):
        """Verify fallback generation contains NO robotic phrases or score percentages."""
        from backend.app.llm_client import llm_client
        from backend.app.models import RagCitation

        dummy_citations = [
            RagCitation(
                url="/api/forms/engineering/3.23.21%20tree%20permit%20application.pdf",
                title="Tree Permit Application",
                category="Application Form",
                department_id="engineering",
                relevance_score=0.95,
                excerpt="The standard filing fee is $25 for a single residential lot. Senior citizens aged 62 or older are exempt from the filing fee upon presenting valid identification."
            )
        ]

        # Force fallback by passing invalid/offline manager prompt
        answer = llm_client.generate_answer(
            query="Tree removal fee",
            citations=dummy_citations,
            history=[],
            department_name="Department of Engineering"
        )

        # Must NOT contain old robotic artifacts
        self.assertNotIn("According to official", answer)
        self.assertNotIn("> \"", answer)
        self.assertNotIn("Match relevance:", answer)
        self.assertIn("Source: [Tree Permit Application]", answer)


if __name__ == "__main__":
    unittest.main()
