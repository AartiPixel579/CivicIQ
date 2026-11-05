"""
Comprehensive Regression Test Suite for Official Document Mapping & Conversational Precision:
Tests A through J, multi-turn street removal disambiguation, Public Works categorization,
and canonical 8-document Engineering inventory.
"""

import json
import unittest
from pathlib import Path
from backend.app.main import chat_endpoint
from backend.app.models import ChatRequest
from backend.app.rag_engine import rag_engine
from backend.app.services.service_intent_service import service_intent_service


class TestOfficialDocumentsAndFormMapping(unittest.TestCase):

    def test_official_engineering_document_inventory(self):
        """
        Requirement 5: Verify the official Engineering document inventory.
        - Exactly 8 canonical documents in Engineering:
          1. Flood Zone Determination Letter (Flood_Zone_Determination_Letter_REQUEST.pdf)
          2. Permit Flow Chart to Help Determine What Permit is Needed (Permit_Flow_Charts.pdf)
          3. Requirements for Plot Grading Plans-Minor Development (Requirements_for_Plot_Grading_Plans_Minor_Development.pdf)
          4. Requirements for Plot Grading Plans-Minor Development Soil Exportation Permit Application (Forms_Soil_Exportation_App.pdf)
          5. Sewer Connection Charge Application (Sewer_Connection_Charge_Applications.pdf)
          6. Site Improvement Permit with Checklist (SIP_Application.pdf)
          7. Soil Importation Permit Application (Forms_Soil_Importation_Appl.pdf)
          8. Tree Removal Permit Application (3.23.21 tree permit application.pdf)
        - Street Opening (RoadOpenApp.pdf) is in Public Works, not Engineering.
        """
        inv_path = Path("departments/engineering/document_inventory.json")
        with open(inv_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        docs = data.get("documents", [])
        eng_docs = [d for d in docs if d.get("department") == "engineering" and d.get("local_filename")]
        self.assertEqual(len(eng_docs), 8, f"Expected 8 engineering documents, got {len(eng_docs)}")
        filenames = {d.get("local_filename") for d in eng_docs}
        expected_filenames = {
            "Flood_Zone_Determination_Letter_REQUEST.pdf",
            "Permit_Flow_Charts.pdf",
            "Requirements_for_Plot_Grading_Plans_Minor_Development.pdf",
            "Forms_Soil_Exportation_App.pdf",
            "Sewer_Connection_Charge_Applications.pdf",
            "SIP_Application.pdf",
            "Forms_Soil_Importation_Appl.pdf",
            "3.23.21 tree permit application.pdf"
        }
        self.assertEqual(filenames, expected_filenames)

        # Confirm RoadOpenApp.pdf is listed under public_works
        pw_docs = [d for d in docs if d.get("local_filename") == "RoadOpenApp.pdf"]
        self.assertEqual(len(pw_docs), 1)
        self.assertEqual(pw_docs[0].get("department"), "public_works")
        self.assertEqual(pw_docs[0].get("original_url"), "https://www.edisonnj.org/document_center/RoadOpenApp.pdf?t=202409111411520")

    def test_a_greeting_hlo(self):
        """Test A: User 'hlo' -> Returns friendly welcome without RAG retrieval or fabricated curb/drainage advice."""
        for greeting in ["hlo", "hi", "hello", "hey", "good morning", "good afternoon"]:
            res = chat_endpoint(ChatRequest(
                session_id=f"sess_greeting_{greeting.replace(' ', '_')}",
                message=greeting,
                department_id="engineering"
            ))
            self.assertEqual(res.message, "Hello! Welcome to CivicIQ. How can I help you with an Edison Township municipal service today?")
            self.assertEqual(len(res.citations or []), 0)
            self.assertNotIn("curb", res.message.lower())
            self.assertNotIn("driveway", res.message.lower())
            self.assertNotIn("drainage", res.message.lower())

    def test_b_street_removal_ambiguity(self):
        """
        Test B: User 'street removal' is ambiguous.
        Must ask: 'Do you mean opening or excavating a street, or removing a tree near a street?'
        Must NOT return Tree Removal automatically.
        """
        res = chat_endpoint(ChatRequest(
            session_id="sess_street_remov_b",
            message="street removal",
            department_id="engineering"
        ))
        self.assertIn("Do you mean opening or excavating a street, or removing a tree near a street?", res.message)
        self.assertIsNotNone(res.options)
        opt_ids = [o.id for o in res.options]
        self.assertIn("opt_street_open", opt_ids)
        self.assertIn("opt_tree_near_street", opt_ids)
        self.assertIsNone(res.form_packet)

    def test_b_multiturn_removal_something_else_street_removal(self):
        """
        Specific test sequence from prompt:
        - User: removal
        - User: something else
        - User: street removal
        Must NEVER return Tree Removal Permit Application!
        """
        sid = "sess_removal_chain"
        # Turn 1: removal
        r1 = chat_endpoint(ChatRequest(session_id=sid, message="removal", department_id="engineering"))
        self.assertIn("What would you like to remove — a tree or soil?", r1.message)

        # Turn 2: something else
        r2 = chat_endpoint(ChatRequest(session_id=sid, message="something else", department_id="engineering"))
        self.assertIn("What type of municipal service or work are you planning", r2.message)

        # Turn 3: street removal
        r3 = chat_endpoint(ChatRequest(session_id=sid, message="street removal", department_id="engineering"))
        self.assertIn("Do you mean opening or excavating a street, or removing a tree near a street?", r3.message)
        self.assertNotIn("tree permit application", r3.message.lower())
        self.assertIsNone(r3.form_packet)

    def test_b_street_removal_followup_options(self):
        """Selecting options from street removal ambiguity question routes properly."""
        # Follow-up Branch 1: Street Opening
        sid1 = "sess_street_opt_1"
        chat_endpoint(ChatRequest(session_id=sid1, message="street removal", department_id="engineering"))
        r_open = chat_endpoint(ChatRequest(session_id=sid1, message="street opening", department_id="engineering"))
        self.assertIn("Public Works", r_open.message)
        self.assertIn("RoadOpenApp.pdf", r_open.message)
        self.assertNotIn("3.23.21 tree permit", r_open.message)

        # Follow-up Branch 2: Tree near street
        sid2 = "sess_street_opt_2"
        chat_endpoint(ChatRequest(session_id=sid2, message="street removal", department_id="engineering"))
        r_tree = chat_endpoint(ChatRequest(session_id=sid2, message="removing a tree near a street", department_id="engineering"))
        self.assertTrue("tree-removal" in r_tree.message.lower() or "tree removal" in r_tree.message.lower())
        self.assertNotIn("RoadOpenApp.pdf", r_tree.message)

    def test_c_street_opening(self):
        """
        Test C: User 'street opening' -> Identifies official Street Opening Application from Public Works (RoadOpenApp.pdf).
        Explains listed under Department of Public Works, no interactive form filling.
        """
        res = chat_endpoint(ChatRequest(
            session_id="sess_street_open_c",
            message="street opening",
            department_id="engineering"
        ))
        self.assertIn("Department of Public Works", res.message)
        self.assertIn("RoadOpenApp.pdf", res.message)
        self.assertIn("interactive workflow is not currently configured", res.message)
        self.assertNotIn("3.23.21 tree permit application.pdf", res.message)

    def test_d_road_opening(self):
        """
        Test D: User 'road opening' -> Same official Street Opening Application from Public Works.
        """
        res = chat_endpoint(ChatRequest(
            session_id="sess_road_open_d",
            message="road opening",
            department_id="engineering"
        ))
        self.assertIn("Department of Public Works", res.message)
        self.assertIn("RoadOpenApp.pdf", res.message)
        self.assertIn("interactive workflow is not currently configured", res.message)
        self.assertNotIn("3.23.21 tree permit application.pdf", res.message)

    def test_e_tree_removal(self):
        """
        Test E: User 'tree removal' -> Tree Removal Permit Application only.
        """
        res = chat_endpoint(ChatRequest(
            session_id="sess_tree_remov_e",
            message="tree removal",
            department_id="engineering"
        ))
        self.assertTrue("tree-removal" in res.message.lower() or "tree removal" in res.message.lower())
        self.assertNotIn("RoadOpenApp.pdf", res.message)
        self.assertNotIn("Flood_Zone", res.message)
        # Explicit form request attaches Tree Removal application
        res_form = chat_endpoint(ChatRequest(
            session_id="sess_tree_remov_form",
            message="Give me the tree removal application form",
            department_id="engineering"
        ))
        self.assertIsNotNone(res_form.form_packet)
        self.assertEqual(res_form.form_packet.form_file, "3.23.21 tree permit application.pdf")

    def test_f_flood_zone_determination(self):
        """
        Test F: User 'flood zone determination' -> Exact official Flood Zone Determination Letter Request PDF.
        Contains Block, Lot, property address, contact details, and $25 Flood Letter Fee.
        Never returns Zoning, Schedule A, Plot Grading, Tree Removal.
        Does not claim CivicIQ can determine flood status directly.
        """
        res = chat_endpoint(ChatRequest(
            session_id="sess_flood_f",
            message="flood zone determination",
            department_id="engineering"
        ))
        self.assertIn("Flood_Zone_Determination_Letter_REQUEST.pdf", res.message)
        self.assertIn("$25.00", res.message)
        self.assertIn("Block and Lot", res.message)
        self.assertIn("CivicIQ cannot determine your property's flood-zone status directly", res.message)
        self.assertNotIn("Zoning", res.message)
        self.assertNotIn("Schedule A", res.message)
        self.assertNotIn("Plot Grading", res.message)
        self.assertNotIn("Tree Removal", res.message)
        self.assertIsNotNone(res.form_packet)
        self.assertEqual(res.form_packet.form_file, "Flood_Zone_Determination_Letter_REQUEST.pdf")
        self.assertEqual(res.form_packet.department_id, "engineering")
        self.assertIn("Flood_Zone_Determination_Letter_REQUEST.pdf?t=202409111411240", res.citations[0].url)

    def test_g_i_need_a_flood_zone_letter(self):
        """
        Test G: User 'I need a flood zone letter' -> Same exact Flood Zone document.
        """
        res = chat_endpoint(ChatRequest(
            session_id="sess_flood_g",
            message="I need a flood zone letter",
            department_id="engineering"
        ))
        self.assertIn("Flood_Zone_Determination_Letter_REQUEST.pdf", res.message)
        self.assertIn("$25.00", res.message)
        self.assertIsNotNone(res.form_packet)
        self.assertEqual(res.form_packet.form_file, "Flood_Zone_Determination_Letter_REQUEST.pdf")

    def test_h_sewer_connection_charge_application(self):
        """
        Test H: User 'sewer connection charge application' -> Sewer_Connection_Charge_Applications.pdf.
        """
        res = chat_endpoint(ChatRequest(
            session_id="sess_sewer_h",
            message="sewer connection charge application",
            department_id="engineering"
        ))
        self.assertIn("Sewer_Connection_Charge_Applications.pdf", res.message)
        self.assertIsNotNone(res.form_packet)
        self.assertEqual(res.form_packet.form_file, "Sewer_Connection_Charge_Applications.pdf")

    def test_i_site_improvement_permit(self):
        """
        Test I: User 'site improvement permit' -> SIP_Application.pdf with checklist.
        """
        res = chat_endpoint(ChatRequest(
            session_id="sess_site_i",
            message="site improvement permit",
            department_id="engineering"
        ))
        self.assertIn("SIP_Application.pdf", res.message)
        self.assertIsNotNone(res.form_packet)
        self.assertEqual(res.form_packet.form_file, "SIP_Application.pdf")

    def test_j_plot_grading_plans(self):
        """
        Test J: User 'plot grading plans' -> Requirements_for_Plot_Grading_Plans_Minor_Development.pdf.
        """
        res = chat_endpoint(ChatRequest(
            session_id="sess_plot_j",
            message="plot grading plans",
            department_id="engineering"
        ))
        self.assertIn("Requirements_for_Plot_Grading_Plans_Minor_Development.pdf", res.message)
        self.assertIsNotNone(res.form_packet)
        self.assertEqual(res.form_packet.form_file, "Requirements_for_Plot_Grading_Plans_Minor_Development.pdf")

    def test_cross_topic_history_chain(self):
        """
        Multi-turn cross-topic history test:
        Turn 1: Tree Removal -> Tree Removal Guidance
        Turn 2: Street Opening -> Street Opening Application (DPW)
        Turn 3: Flood Zone Determination -> Flood Zone Request (Engineering)
        """
        sid = "sess_cross_topic_chain"
        # Turn 1: Tree Removal
        r1 = chat_endpoint(ChatRequest(session_id=sid, message="I need tree removal", department_id="engineering"))
        self.assertTrue("tree-removal" in r1.message.lower() or "tree removal" in r1.message.lower())

        # Turn 2: Street Opening
        r2 = chat_endpoint(ChatRequest(session_id=sid, message="street opening", department_id="engineering"))
        self.assertIn("Public Works", r2.message)
        self.assertIn("RoadOpenApp.pdf", r2.message)
        self.assertNotIn("3.23.21 tree permit application.pdf", r2.message)

        # Turn 3: Flood Zone Determination
        r3 = chat_endpoint(ChatRequest(session_id=sid, message="flood zone determination", department_id="engineering"))
        self.assertIn("Flood_Zone_Determination_Letter_REQUEST.pdf", r3.message)
        self.assertIsNotNone(r3.form_packet)
        self.assertEqual(r3.form_packet.form_file, "Flood_Zone_Determination_Letter_REQUEST.pdf")


if __name__ == "__main__":
    unittest.main()
