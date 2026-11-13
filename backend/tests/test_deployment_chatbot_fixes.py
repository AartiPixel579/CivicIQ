"""
Regression and Verification Tests for Deployment Chatbot Fixes (Issue 1 to 5)
Covers:
1. Interactive form filling completely disabled across deployment:
   - "Can you fill the Tree Removal permit for me?" polite explanation + official blank PDF
   - Form session endpoints (/api/form-session/*) reject with HTTP 400
   - Official blank municipal PDFs accessible
   - Form-filling prompt ("Would you like help with the application?") removed from all templates
   - No opt_apply_yes or opt_apply_no action buttons
2. Wrong PDF selection fix:
   - Tree Removal -> emergency completed -> Soil Import -> "Give me the PDF to download the permit for Soil Import" -> Forms_Soil_Importation_Appl.pdf
   - Tree Removal -> emergency completed -> Soil Export -> "Give me the PDF to download the permit for Soil Export" -> Forms_Soil_Exportation_App.pdf
   - Ambiguous PDF download query uses most recent service from history
3. Soil quantity follow-up and correction:
   - Soil Import: < 10 cu. yds -> "Actually, it is 10 cubic yards or more" -> Soil Import Permit Required + Forms_Soil_Importation_Appl.pdf
   - Reverse correction: 10+ cu. yds -> "Wait, it is actually only 5 cubic yards" -> Soil Permit NOT required + no packet
   - Soil Export correction: < 10 -> >= 10 -> Forms_Soil_Exportation_App.pdf
4. Short street query ambiguity & road opening:
   - "street" or "streets" asks for clarification with options (never dumps raw docs)
   - Follow-up with "Street Opening" states unconfigured and provides RoadOpenApp.pdf
   - "Street Opening permit" or "Road excavation application" states unconfigured and provides RoadOpenApp.pdf
5. Verified services integrity:
   - Emergency tree removal guidance preserved
   - Standard soil flows preserved
"""

import unittest
from fastapi import HTTPException
from backend.app.main import (
    chat_endpoint, serve_official_form,
    start_form_session, answer_form_session,
    edit_form_session, review_form_session,
    generate_form_pdf
)
from backend.app.models.core import ChatRequest
from backend.app.models.form_session import (
    FormStartSessionRequest, FormAnswerRequest, FormEditRequest
)


from backend.tests.offline_llm_helper import OfflineLLMTestCase

class TestDeploymentChatbotFixes(OfflineLLMTestCase):

    # =========================================================================
    # 1. Completely Disable Interactive Form Filling in Deployment
    # =========================================================================

    def test_01_can_you_fill_tree_removal_permit(self):
        """Resident asking 'Can you fill the Tree Removal permit for me?' receives polite explanation and blank PDF link."""
        res = chat_endpoint(ChatRequest(
            session_id="test_fill_tree",
            message="Can you fill the Tree Removal permit for me?",
            department_id="engineering"
        ))
        self.assertNotEqual(res.mode, "form_fill")
        self.assertIn("CivicIQ currently provides official blank municipal applications and procedural guidance, not interactive form completion", res.message)
        self.assertIn("3.23.21%20tree%20permit%20application.pdf", res.message)
        self.assertIsNotNone(res.form_packet)
        self.assertEqual(res.form_packet.form_file, "3.23.21 tree permit application.pdf")

    def test_02_can_you_fill_soil_import_permit(self):
        """Resident asking to fill Soil Import permit receives polite explanation and blank PDF link."""
        res = chat_endpoint(ChatRequest(
            session_id="test_fill_soil_imp",
            message="Can you fill out the Soil Import application for me?",
            department_id="engineering"
        ))
        self.assertNotEqual(res.mode, "form_fill")
        self.assertIn("not interactive form completion", res.message)
        self.assertIn("Forms_Soil_Importation_Appl.pdf", res.message)
        self.assertIsNotNone(res.form_packet)
        self.assertEqual(res.form_packet.form_file, "Forms_Soil_Importation_Appl.pdf")

    def test_03_form_session_endpoints_disabled(self):
        """All /api/form-session/* endpoints must raise HTTPException with status_code=400 and disabled notice."""
        # 1. start
        with self.assertRaises(HTTPException) as ctx:
            start_form_session(FormStartSessionRequest(session_id="s1", form_id="tree_removal"))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("unavailable", ctx.exception.detail.lower())

        with self.assertRaises(HTTPException) as ctx:
            start_form_session(FormStartSessionRequest(session_id="s2", form_id="soil_import"))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("unavailable", ctx.exception.detail.lower())

        # 2. answer
        with self.assertRaises(HTTPException) as ctx:
            answer_form_session(FormAnswerRequest(session_id="s1", answer="John"))
        self.assertEqual(ctx.exception.status_code, 400)

        # 3. edit
        with self.assertRaises(HTTPException) as ctx:
            edit_form_session(FormEditRequest(session_id="s1", field_name="name", new_answer="Jane"))
        self.assertEqual(ctx.exception.status_code, 400)

        # 4. review
        with self.assertRaises(HTTPException) as ctx:
            review_form_session(session_id="s1")
        self.assertEqual(ctx.exception.status_code, 400)

        # 5. generate-pdf
        with self.assertRaises(HTTPException) as ctx:
            generate_form_pdf(session_id="s1")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_04_official_blank_pdfs_accessible(self):
        """Official blank municipal PDFs must remain downloadable and accessible."""
        # Tree removal application
        r_tree = serve_official_form("engineering", "3.23.21 tree permit application.pdf")
        self.assertEqual(r_tree.status_code, 200)
        self.assertEqual(r_tree.media_type, "application/pdf")

        # Soil importation application
        r_imp = serve_official_form("engineering", "Forms_Soil_Importation_Appl.pdf")
        self.assertEqual(r_imp.status_code, 200)
        self.assertEqual(r_imp.media_type, "application/pdf")

        # Soil exportation application
        r_exp = serve_official_form("engineering", "Forms_Soil_Exportation_App.pdf")
        self.assertEqual(r_exp.status_code, 200)
        self.assertEqual(r_exp.media_type, "application/pdf")

        # Road opening application
        r_road = serve_official_form("engineering", "RoadOpenApp.pdf")
        self.assertEqual(r_road.status_code, 200)
        self.assertEqual(r_road.media_type, "application/pdf")

    def test_05_no_form_filling_prompt_or_options(self):
        """Responses must never prompt 'Would you like help with the application?' or return opt_apply_yes/opt_apply_no."""
        # Soil fee inquiry
        res_fee = chat_endpoint(ChatRequest(
            session_id="test_no_prompt_fee",
            message="How much is a soil importation permit?",
            department_id="engineering"
        ))
        self.assertNotIn("Would you like help with the application?", res_fee.message)
        self.assertNotIn("Would you like me to help you fill out", res_fee.message)
        opt_ids = [o.id for o in (res_fee.options or [])]
        self.assertNotIn("opt_apply_yes", opt_ids)
        self.assertNotIn("opt_apply_no", opt_ids)

        # Soil documents inquiry
        res_docs = chat_endpoint(ChatRequest(
            session_id="test_no_prompt_docs",
            message="What documents do I need for soil importation?",
            department_id="engineering"
        ))
        self.assertNotIn("Would you like help with the application?", res_docs.message)
        opt_ids_docs = [o.id for o in (res_docs.options or [])]
        self.assertNotIn("opt_apply_yes", opt_ids_docs)
        self.assertNotIn("opt_apply_no", opt_ids_docs)

    # =========================================================================
    # 2. Fix Wrong PDF Selection
    # =========================================================================

    def test_06_tree_emergency_then_soil_import_pdf(self):
        """
        User flow:
        1. Tree removal emergency workflow completed
        2. Resident switches to Soil Import
        3. Resident asks: 'Give me the PDF to download the permit for Soil Import.'
        Must return Soil Importation Permit Application (Forms_Soil_Importation_Appl.pdf), NOT Tree Removal!
        """
        sid = "test_tree_to_soil_import_pdf"

        # Turn 1: Tree emergency
        r1 = chat_endpoint(ChatRequest(
            session_id=sid,
            message="I have an emergency tree leaning over my house and about to fall",
            department_id="engineering"
        ))
        self.assertIn("emergency", r1.message.lower())

        # Turn 2: Switch to Soil Import
        chat_endpoint(ChatRequest(
            session_id=sid,
            message="I also need to import soil to my yard",
            department_id="engineering"
        ))

        # Turn 3: Ask for PDF explicitly specifying Soil Import
        r3 = chat_endpoint(ChatRequest(
            session_id=sid,
            message="Give me the PDF to download the permit for Soil Import.",
            department_id="engineering"
        ))

        self.assertIsNotNone(r3.form_packet, "Should attach form packet for Soil Import")
        self.assertEqual(r3.form_packet.form_file, "Forms_Soil_Importation_Appl.pdf")
        self.assertIn("Forms_Soil_Importation_Appl.pdf", r3.form_packet.pdf_download_url)
        self.assertNotIn("tree permit application", r3.form_packet.form_title.lower())

    def test_07_tree_emergency_then_soil_export_pdf(self):
        """
        User flow:
        1. Tree removal discussed
        2. Resident switches to Soil Export
        3. Resident asks: 'Give me the PDF to download the permit for Soil Export.'
        Must return Soil Exportation Permit Application (Forms_Soil_Exportation_App.pdf).
        """
        sid = "test_tree_to_soil_export_pdf"

        # Turn 1: Tree inquiry
        chat_endpoint(ChatRequest(session_id=sid, message="Tree removal permit", department_id="engineering"))

        # Turn 2: Switch to Soil Export
        chat_endpoint(ChatRequest(session_id=sid, message="I am removing soil from property", department_id="engineering"))

        # Turn 3: Ask for PDF explicitly specifying Soil Export
        r3 = chat_endpoint(ChatRequest(
            session_id=sid,
            message="Give me the PDF to download the permit for Soil Export.",
            department_id="engineering"
        ))

        self.assertIsNotNone(r3.form_packet)
        self.assertEqual(r3.form_packet.form_file, "Forms_Soil_Exportation_App.pdf")

    def test_08_ambiguous_pdf_request_uses_most_recent_topic(self):
        """
        When query is ambiguous (e.g. 'Give me that PDF form'), it must resolve
        to the MOST RECENT service discussed in history, not earlier topics.
        """
        sid = "test_ambiguous_pdf_recent_topic"

        # Turn 1: Tree removal discussed first
        chat_endpoint(ChatRequest(session_id=sid, message="Tree removal permit fees", department_id="engineering"))

        # Turn 2: Soil Import discussed more recently
        chat_endpoint(ChatRequest(session_id=sid, message="How to import soil?", department_id="engineering"))

        # Turn 3: Ambiguous download query without naming the service
        r3 = chat_endpoint(ChatRequest(
            session_id=sid,
            message="Give me the PDF to download the permit.",
            department_id="engineering"
        ))

        self.assertIsNotNone(r3.form_packet)
        # Most recent topic was Soil Import, so it must return Soil Import!
        self.assertEqual(r3.form_packet.form_file, "Forms_Soil_Importation_Appl.pdf")

    # =========================================================================
    # 3. Fix Soil Quantity Follow-up and Correction
    # =========================================================================

    def test_09_soil_import_quantity_correction_under_to_over_10(self):
        """
        Soil Import follow-up/correction:
        1. Resident starts Soil Import
        2. Selects 'Less than 10 cubic yards' -> receives 'permit NOT required'
        3. Resident says: 'Actually, it is 10 cubic yards or more.'
        Must re-evaluate, return 'Soil Import Permit Required', attach Forms_Soil_Importation_Appl.pdf,
        and not repeat the old 'permit not required' result.
        """
        sid = "test_soil_corr_under_to_over"

        # Turn 1: Start Soil Import
        r1 = chat_endpoint(ChatRequest(session_id=sid, message="I want to import soil", department_id="engineering"))
        self.assertIn("10 cubic yards or more", r1.message)

        # Turn 2: Select < 10 cubic yards
        r2 = chat_endpoint(ChatRequest(session_id=sid, message="Less than 10 cubic yards", department_id="engineering"))
        self.assertIn("not required", r2.message.lower())
        self.assertIsNone(r2.form_packet)

        # Turn 3: Correct to >= 10 cubic yards
        r3 = chat_endpoint(ChatRequest(session_id=sid, message="Actually, it is 10 cubic yards or more.", department_id="engineering"))
        self.assertIn("requires an approved **Soil Importation Permit**", r3.message)
        self.assertNotIn("permit is not required", r3.message.lower())
        self.assertIsNotNone(r3.form_packet, "Should attach form packet upon volume correction to 10+")
        self.assertEqual(r3.form_packet.form_file, "Forms_Soil_Importation_Appl.pdf")

    def test_10_soil_import_quantity_reverse_correction_over_to_under_10(self):
        """
        Soil Import reverse correction:
        1. Resident starts Soil Import with 10+ cubic yards -> receives Permit Required + PDF
        2. Resident says: 'Wait, it is actually only 5 cubic yards'
        Must re-evaluate, return 'Permit NOT required', and remove the PDF packet.
        """
        sid = "test_soil_corr_over_to_under"

        # Turn 1: Start with 10+ cubic yards
        r1 = chat_endpoint(ChatRequest(session_id=sid, message="I am importing 20 cubic yards of soil", department_id="engineering"))
        self.assertIn("requires an approved **Soil Importation Permit**", r1.message)
        self.assertIsNotNone(r1.form_packet)

        # Turn 2: Reverse correction to 5 cubic yards
        r2 = chat_endpoint(ChatRequest(session_id=sid, message="Wait, it is actually only 5 cubic yards", department_id="engineering"))
        self.assertIn("not required", r2.message.lower())
        self.assertIsNone(r2.form_packet, "Form packet should be cleared for < 10 cubic yards")

    def test_11_soil_export_quantity_correction(self):
        """
        Soil Export follow-up/correction:
        1. Resident starts Soil Export with under 10 cu. yds -> Permit not required
        2. Corrects to 'Actually 15 cubic yards' -> Soil Export Permit Required + Forms_Soil_Exportation_App.pdf
        """
        sid = "test_soil_exp_corr"

        # Turn 1 & 2: Export under 10 cu. yds
        chat_endpoint(ChatRequest(session_id=sid, message="I need to remove soil from my yard", department_id="engineering"))
        r2 = chat_endpoint(ChatRequest(session_id=sid, message="Under 10 cubic yards", department_id="engineering"))
        self.assertIn("not required", r2.message.lower())
        self.assertIsNone(r2.form_packet)

        # Turn 3: Correct to 15 cubic yards
        r3 = chat_endpoint(ChatRequest(session_id=sid, message="Actually, it is 15 cubic yards.", department_id="engineering"))
        self.assertIn("requires an approved **Soil Exportation Permit**", r3.message)
        self.assertIsNotNone(r3.form_packet)
        self.assertEqual(r3.form_packet.form_file, "Forms_Soil_Exportation_App.pdf")

    # =========================================================================
    # 4. Improve Short Street Queries & Road Opening
    # =========================================================================

    def test_12_short_street_query_asks_clarification(self):
        """
        Resident typing only 'street' must receive a polite clarifying question with options,
        never a raw document dump or unconfigured rejection.
        """
        res = chat_endpoint(ChatRequest(
            session_id="test_street_ambiguity",
            message="street",
            department_id="engineering"
        ))
        self.assertIn("What would you like assistance with regarding township streets", res.message)
        self.assertIn("street opening/excavation", res.message.lower())
        self.assertIsNotNone(res.options)
        opt_ids = [o.id for o in res.options]
        self.assertIn("opt_street_opening", opt_ids)
        self.assertIn("opt_street_apron", opt_ids)
        self.assertIn("opt_street_other", opt_ids)

    def test_13_street_clarification_followup_street_opening(self):
        """
        After asking for street clarification, selecting 'Street Opening / Excavation'
        states interactive workflow is not configured, provides RoadOpenApp.pdf,
        and does not claim CivicIQ can process it.
        """
        sid = "test_street_followup"
        chat_endpoint(ChatRequest(session_id=sid, message="street", department_id="engineering"))

        res = chat_endpoint(ChatRequest(
            session_id=sid,
            message="Street Opening / Excavation",
            department_id="engineering"
        ))
        self.assertIsNotNone(res.form_packet)
        self.assertEqual(res.form_packet.form_file, "RoadOpenApp.pdf")
        self.assertIsNone(res.active_flow_id)

    def test_14_specific_road_excavation_query_provides_pdf_and_unconfigured_notice(self):
        """
        Specific query like 'Road excavation application' or 'Street Opening permit'
        must provide RoadOpenApp.pdf and grounded DPW guidance without starting a flow.
        """
        res1 = chat_endpoint(ChatRequest(
            session_id="test_road_open_specific_1",
            message="Street Opening permit",
            department_id="engineering"
        ))
        self.assertIsNotNone(res1.form_packet)
        self.assertEqual(res1.form_packet.form_file, "RoadOpenApp.pdf")
        self.assertIsNone(res1.active_flow_id)

        res2 = chat_endpoint(ChatRequest(
            session_id="test_road_open_specific_2",
            message="Road excavation application",
            department_id="engineering"
        ))
        self.assertIsNotNone(res2.form_packet)
        self.assertEqual(res2.form_packet.form_file, "RoadOpenApp.pdf")
        self.assertIsNone(res2.active_flow_id)

    # =========================================================================
    # 5. Existing Functionality Preserved
    # =========================================================================

    def test_15_emergency_tree_removal_preserved(self):
        """Emergency tree removal guidance must remain concise and attach official blank permit."""
        res = chat_endpoint(ChatRequest(
            session_id="test_emg_tree_pres",
            message="The tree is dead and about to fall on my driveway. Can I remove it?",
            department_id="engineering"
        ))
        self.assertIn("emergency", res.message.lower())
        self.assertIn("arborist", res.message.lower())
        self.assertIn("concurrently", res.message.lower())
        self.assertIsNotNone(res.form_packet)
        self.assertEqual(res.form_packet.form_file, "3.23.21 tree permit application.pdf")


if __name__ == "__main__":
    unittest.main()
