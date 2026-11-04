"""
Unit and Integration Tests for CivicIQ Concise Responses, Intent Detection & Progressive Disclosure
Validates intent classification priority, fee retrieval, multi-turn context preservation,
and conversational flow across the verified Tree Removal, Soil Import/Export, and Unconfigured Service scenarios.
"""

import unittest
from backend.app.main import chat_endpoint, CHAT_HISTORIES
from backend.app.models import ChatRequest
from backend.app.flow_engine import flow_engine
from backend.app.services.form_session_service import form_session_service
from backend.app.services.service_intent_service import service_intent_service
from backend.app.rag_engine import rag_engine
from backend.app.config import UNCONFIGURED_SERVICE_MESSAGE, OUT_OF_CONTEXT_MESSAGE


class TestConciseProgressiveDisclosure(unittest.TestCase):

    def setUp(self):
        CHAT_HISTORIES.clear()
        flow_engine.sessions.clear()
        form_session_service.sessions.clear()

    # -------------------------------------------------------------
    # 1. INTENT CLASSIFICATION PRIORITY OVER KEYWORDS
    # -------------------------------------------------------------

    def test_standalone_tree_removal_cost(self):
        """
        'Tree removal cost' MUST answer the applicable Township permit fee directly.
        It MUST NOT start the tree-removal workflow or ask whether resident is removing trees!
        Must verify senior waiver is for age 62 or older (not 65).
        """
        res = chat_endpoint(ChatRequest(
            session_id="sess_cost_standalone",
            message="Tree removal cost"
        ))

        # Must NOT be a workflow initiation
        self.assertNotEqual(res.mode, "flow")
        self.assertNotIn("are you planning to remove", res.message.lower())
        
        # Must answer the fee directly with verified numbers
        msg = res.message
        self.assertIn("$25", msg)
        self.assertIn("senior citizens", msg.lower())
        self.assertIn("62 or older", msg)
        self.assertNotIn("65", msg)
        self.assertIn("$200", msg)

    def test_contextual_fee_inquiry(self):
        """
        'Is there any cost for this?' after discussing Tree Removal
        MUST answer the fee question using existing conversation context without restarting workflow.
        """
        # Turn 1: Discuss tree removal
        chat_endpoint(ChatRequest(
            session_id="sess_ctx_fee",
            message="I need help with tree removal"
        ))

        # Turn 2: Follow-up fee inquiry without mentioning 'tree'
        res = chat_endpoint(ChatRequest(
            session_id="sess_ctx_fee",
            message="Is there any cost for this?"
        ))

        msg = res.message
        self.assertIn("$25", msg)
        self.assertIn("62 or older", msg)

    def test_workflow_initiation_when_intended(self):
        """
        'I want to remove a tree' SHOULD start the tree-removal decision workflow.
        """
        res = chat_endpoint(ChatRequest(
            session_id="sess_workflow_init",
            message="I want to remove a tree"
        ))

        self.assertEqual(res.mode, "flow")
        self.assertEqual(res.active_flow_id, "tree_removal_flow")
        self.assertIn("planning to remove", res.message.lower())

    def test_active_flow_side_question_preserves_workflow(self):
        """
        If a resident is in the middle of a workflow and asks 'How much?' or 'What about documents?',
        CivicIQ answers the question directly while keeping workflow options intact without resetting.
        """
        # Start flow
        chat_endpoint(ChatRequest(
            session_id="sess_side_q",
            message="Help me with tree removal procedure."
        ))

        # Resident asks side question while flow is at Step 1
        res = chat_endpoint(ChatRequest(
            session_id="sess_side_q",
            message="How much?"
        ))

        # Should answer fee
        self.assertIn("$25", res.message)
        self.assertIn("62", res.message)
        # Should preserve active flow and options
        self.assertEqual(res.mode, "flow")
        self.assertIsNotNone(res.options)
        self.assertFalse(res.completed)

    # -------------------------------------------------------------
    # 2. EMERGENCY WORKFLOW CONVERSATIONAL RESPONSE
    # -------------------------------------------------------------

    def test_emergency_workflow_conversational_response(self):
        """
        Emergency tree removal response must be natural, brief, and conversational
        without dumping unrequested fees, surveys, ribbons, or turnaround.
        """
        # Step 1: Initialize tree removal flow
        chat_endpoint(ChatRequest(
            session_id="sess_emg",
            message="Help me with tree removal procedure."
        ))

        # Step 2: Resident selects emergency
        chat_endpoint(ChatRequest(
            session_id="sess_emg",
            message="Yes, I am planning to remove one or more trees",
            selected_option_id="opt_removing_trees_yes"
        ))

        res_emg = chat_endpoint(ChatRequest(
            session_id="sess_emg",
            message="Yes, it is an emergency (dead, dying, or imminent danger)",
            selected_option_id="opt_emergency_yes"
        ))

        msg = res_emg.message.lower()

        # Natural conversational checks
        self.assertIn("emergency removal is permitted", msg)
        self.assertTrue("photo" in msg or "photograph" in msg)
        self.assertIn("licensed arborist", msg)
        self.assertIn("concurrent", msg)
        self.assertIn("safely remove", msg)

        # Anti-bloat assertions: NO unasked details dumped
        self.assertNotIn("$25", res_emg.message)
        self.assertNotIn("filing fee", msg)
        self.assertNotIn("ribbon", msg)
        self.assertNotIn("red paint", msg)
        self.assertNotIn("turnaround", msg)

        # Verified official form packet must be attached
        self.assertIsNotNone(res_emg.form_packet)
        self.assertEqual(res_emg.form_packet.form_file, "3.23.21 tree permit application.pdf")

    # -------------------------------------------------------------
    # 3. OTHER INTENT-BASED DETAIL INQUIRIES
    # -------------------------------------------------------------

    def test_documents_needed_inquiry(self):
        """'What documents do I need for tree removal?' -> Checklist only."""
        res = chat_endpoint(ChatRequest(
            session_id="sess_docs",
            message="What documents do I need for tree removal?"
        ))

        msg = res.message.lower()
        self.assertIn("survey or tax map", msg)
        self.assertIn("written statement", msg)
        self.assertIn("site marking", msg)
        self.assertLess(len(res.message), 700)

    def test_submission_location_inquiry(self):
        """'Where do I submit the application?' -> Submission location & portal link only."""
        chat_endpoint(ChatRequest(
            session_id="sess_sub",
            message="Help me with tree removal"
        ))
        res = chat_endpoint(ChatRequest(
            session_id="sess_sub",
            message="Where do I submit the application?"
        ))

        msg = res.message
        self.assertIn("100 Municipal Boulevard", msg)
        self.assertIn("Division of Engineering", msg)
        self.assertIn("edisonnj.org/document_center", msg)
        self.assertLess(len(msg), 500)

    def test_complete_process_inquiry(self):
        """'Explain the complete tree-removal process.' -> Structured 5-step overview."""
        res = chat_endpoint(ChatRequest(
            session_id="sess_proc",
            message="Explain the complete tree-removal process."
        ))

        msg = res.message
        self.assertIn("Application Submission", msg)
        self.assertIn("Tree Marking", msg)
        self.assertIn("Inspection", msg)
        self.assertIn("Permit Decision", msg)
        self.assertIn("Tree Removal", msg)
        self.assertIn("62+", msg)

    # -------------------------------------------------------------
    # 4. UNCONFIGURED SERVICES (STREET OPENING, SEWER, ZONING)
    # -------------------------------------------------------------

    def test_street_opening_unconfigured_service(self):
        """
        Entering 'Street Opening' must NOT ask for 811 utility ticket number or start a workflow!
        Must respond with UNCONFIGURED_SERVICE_MESSAGE.
        """
        res = chat_endpoint(ChatRequest(
            session_id="sess_unsupported_road",
            message="Street Opening"
        ))

        self.assertIn("This service hasn't been configured yet", res.message)
        self.assertNotIn("811", res.message)
        self.assertNotEqual(res.mode, "flow")
        self.assertIsNone(res.active_flow_id)

    def test_sewer_connection_unconfigured_service(self):
        """'Sewer connection' must respond that service has not been configured yet."""
        res = chat_endpoint(ChatRequest(
            session_id="sess_unsupported_sewer",
            message="How do I connect to the sewer?"
        ))

        self.assertIn("This service hasn't been configured yet", res.message)
        self.assertNotEqual(res.mode, "flow")

    def test_zoning_unconfigured_service(self):
        """'Zoning permit' must respond that service has not been configured yet."""
        res = chat_endpoint(ChatRequest(
            session_id="sess_unsupported_zoning",
            message="How do I apply for a zoning permit?"
        ))

        self.assertIn("This service hasn't been configured yet", res.message)
        self.assertNotEqual(res.mode, "flow")

    # -------------------------------------------------------------
    # 5. SOIL IMPORT / EXPORT PROCEDURAL CONCISENESS
    # -------------------------------------------------------------

    def test_soil_import_cost_inquiry(self):
        """'How much does it cost to import soil?' -> Exact soil import fee."""
        res = chat_endpoint(ChatRequest(
            session_id="sess_soil_cost",
            message="How much does it cost to import soil?"
        ))

        msg = res.message
        self.assertIn("$50.00", msg)
        self.assertIn("Soil Importation", msg)

    def test_soil_import_procedural_conciseness(self):
        """Soil import (10+ yards) procedure must be exactly 3 numbered steps without bloat."""
        res = chat_endpoint(ChatRequest(
            session_id="sess_soil_import_steps",
            message="I want to import 20 cubic yards of soil"
        ))

        msg = res.message
        self.assertIn("1. **Submit application:**", msg)
        self.assertIn("2. **Provide documentation:**", msg)
        self.assertIn("3. **Await engineering approval:**", msg)
        self.assertNotIn("8:00 AM", msg)

    def test_soil_export_under_10_yards(self):
        """Soil export under 10 cubic yards requires NO permit."""
        res = chat_endpoint(ChatRequest(
            session_id="sess_soil_export_less",
            message="I want to remove less than 10 cubic yards of soil"
        ))

        self.assertIn("not required", res.message.lower())
        self.assertIsNone(res.form_packet)


if __name__ == "__main__":
    unittest.main()
