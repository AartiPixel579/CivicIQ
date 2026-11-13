import json
import unittest
from pathlib import Path
from backend.app.rag_engine import rag_engine
from backend.app.services.service_intent_service import service_intent_service


from backend.tests.offline_llm_helper import OfflineLLMTestCase

class TestConversationalContextEngineeringServices(OfflineLLMTestCase):
    """
    Comprehensive regression test suite for:
    1. Conversational age and fee follow-up handling
    2. Canonical 8 Engineering Department services configuration
    3. Service-specific grounded guidance (Flood Zone, Plot Grading, Permit Flow Chart, Sewer, SIP)
    4. Multi-turn cross-topic switching priority
    5. Standalone number context safety
    """

    def test_official_document_inventory(self):
        """Verifies exactly the 8 canonical Township Engineering documents are indexed."""
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

    def test_tree_removal_age_and_fee_followup_under_62(self):
        """
        User asks for tree removal cost -> bot explains fee and senior waiver -> user says 'i am 26'
        CivicIQ should directly explain that the waiver does not apply and state the $25 residential / $200 board fee.
        CivicIQ must NOT retrieve unrelated Zoning documents.
        """
        # Turn 1: Fee explanation (grounded tree-removal evidence, no unverified hardcoded $25)
        res1 = rag_engine.answer_query("cost for it", history=[
            {"role": "user", "content": "I want to remove a tree from my backyard"},
            {"role": "assistant", "content": "Under Township of Edison Tree Protection regulations, an approved permit is required."}
        ])
        self.assertTrue(res1.grounded)
        self.assertGreater(len(res1.citations), 0)
        self.assertNotIn("$25", res1.answer)

        # Turn 2: Age reply 'i am 26' -> remains scoped to tree removal, no zoning leak
        history_turn2 = [
            {"role": "user", "content": "cost for it"},
            {"role": "assistant", "content": res1.answer}
        ]
        res2 = rag_engine.answer_query("i am 26", history=history_turn2)
        self.assertNotIn("Zoning Permit Application", res2.answer)
        self.assertNotIn("Schedule A", res2.answer)

        # Turn 3: Follow-up fee inquiry 'how much do I need to pay?'
        history_turn3 = history_turn2 + [
            {"role": "user", "content": "i am 26"},
            {"role": "assistant", "content": res2.answer}
        ]
        res3 = rag_engine.answer_query("how much do I need to pay?", history=history_turn3)
        self.assertTrue(res3.grounded)
        self.assertNotIn("Zoning Permit Application", res3.answer)

    def test_tree_removal_age_and_fee_followup_senior_62_plus(self):
        """
        User provides age 65 -> remains scoped to tree removal without inventing unverified fee waivers.
        """
        history = [
            {"role": "user", "content": "cost for it"},
            {"role": "assistant", "content": "Please confirm current fees with the Division of Engineering."}
        ]
        res = rag_engine.answer_query("i am 65", history=history)
        self.assertNotIn("Zoning Permit Application", res.answer)
        self.assertNotIn("Schedule A", res.answer)

    def test_combined_age_and_fee_query(self):
        """
        User says: 'i am 26 year old how much cost required'
        CivicIQ responds without inventing unverified hardcoded fees.
        """
        res = rag_engine.answer_query("i am 26 year old how much cost required", history=[])
        self.assertNotIn("Zoning Permit Application", res.answer)

    def test_standalone_number_context_safety(self):
        """
        If user inputs a standalone number without prior age or fee context, CivicIQ asks for clarification.
        """
        res = rag_engine.answer_query("26", history=[])
        self.assertIn("clarify what this number refers to", res.answer)
        self.assertNotIn("Zoning", res.answer)

    def test_flood_zone_determination(self):
        """
        Recognizes 'Flood zone determination.' and 'Is my property in a flood zone?'
        Grounds with Flood_Zone_Determination_Letter_REQUEST.pdf.
        """
        res1 = rag_engine.answer_query("Flood zone determination.", history=[])
        self.assertTrue(res1.grounded)
        self.assertIsNotNone(res1.form_packet)
        self.assertEqual(res1.form_packet.form_file, "Flood_Zone_Determination_Letter_REQUEST.pdf")
        self.assertGreater(len(res1.citations), 0)

        res2 = rag_engine.answer_query("Is my property in a flood zone?", history=[])
        self.assertTrue(res2.grounded)
        self.assertIsNotNone(res2.form_packet)

    def test_plot_grading_plans(self):
        """
        Recognizes 'I need plot grading plans.' and grounds with Requirements_for_Plot_Grading_Plans_Minor_Development.pdf.
        """
        res = rag_engine.answer_query("I need plot grading plans.", history=[])
        self.assertTrue(res.grounded)
        self.assertIsNotNone(res.form_packet)
        self.assertEqual(res.form_packet.form_file, "Requirements_for_Plot_Grading_Plans_Minor_Development.pdf")
        self.assertGreater(len(res.citations), 0)

    def test_permit_flowchart(self):
        """
        Recognizes 'Which permit do I need?' and grounds with Permit_Flow_Charts.pdf.
        """
        res = rag_engine.answer_query("Which permit do I need?", history=[])
        self.assertTrue(res.grounded)
        self.assertIsNotNone(res.form_packet)
        self.assertEqual(res.form_packet.form_file, "Permit_Flow_Charts.pdf")
        self.assertGreater(len(res.citations), 0)

    def test_sewer_connection(self):
        """
        Recognizes 'I need a sewer connection charge application.' and grounds with Sewer_Connection_Charge_Applications.pdf (no wrong 'fixture unit' claim).
        """
        res = rag_engine.answer_query("I need a sewer connection charge application.", history=[])
        self.assertTrue(res.grounded)
        self.assertNotIn("fixture unit", res.answer.lower())
        self.assertIsNotNone(res.form_packet)
        self.assertEqual(res.form_packet.form_file, "Sewer_Connection_Charge_Applications.pdf")

    def test_site_improvement_permit(self):
        """
        Recognizes 'I need a site improvement permit.' and grounds with SIP_Application.pdf.
        """
        res = rag_engine.answer_query("I need a site improvement permit.", history=[])
        self.assertTrue(res.grounded)
        self.assertIsNotNone(res.form_packet)
        self.assertEqual(res.form_packet.form_file, "SIP_Application.pdf")
        self.assertGreater(len(res.citations), 0)

    def test_soil_import_quantity_correction(self):
        """
        User asks for Soil Import -> says 'Less than 10 cubic yards' -> permit not required.
        User corrects: 'Actually, 10 cubic yards or more' -> permit required with clean fill lab analysis.
        """
        history_t1 = [
            {"role": "user", "content": "I want to import soil"},
            {"role": "assistant", "content": "Are you planning to bring 10 cubic yards or more?"}
        ]
        res_under = rag_engine.answer_query("Less than 10 cubic yards.", history=history_t1)
        self.assertIn("NOT required", res_under.answer)
        self.assertIsNone(res_under.form_packet)

        history_t2 = history_t1 + [
            {"role": "user", "content": "Less than 10 cubic yards."},
            {"role": "assistant", "content": res_under.answer}
        ]
        res_over = rag_engine.answer_query("Actually, 10 cubic yards or more.", history=history_t2)
        self.assertIn("Soil Importation Permit", res_over.answer)
        self.assertIn("clean fill", res_over.answer.lower())
        self.assertIsNotNone(res_over.form_packet)
        self.assertEqual(res_over.form_packet.form_file, "Forms_Soil_Importation_Appl.pdf")

    def test_cross_topic_switching_priority(self):
        """
        Current explicit request takes absolute priority over older history:
        1. Resident discussed Tree Removal, then says 'Can I get the Soil Import application?' -> returns Soil Import application only.
        2. Resident discussed Plot Grading, then asks 'Flood zone determination' -> returns Flood Zone document, not grading.
        """
        # Test 1: Tree -> Soil Import
        history_tree = [
            {"role": "user", "content": "I need to remove a tree from my yard"},
            {"role": "assistant", "content": "Under Township regulations, you need a Tree Removal Permit."}
        ]
        res_soil = rag_engine.answer_query("Can I get the Soil Import application?", history=history_tree)
        self.assertIsNotNone(res_soil.form_packet)
        self.assertEqual(res_soil.form_packet.form_file, "Forms_Soil_Importation_Appl.pdf")
        self.assertNotIn("tree", res_soil.form_packet.form_title.lower())

        # Test 2: Grading -> Flood Zone
        history_grading = [
            {"role": "user", "content": "I need plot grading plans"},
            {"role": "assistant", "content": "Plot grading plans require a NJ licensed PE or PLS seal."}
        ]
        res_flood = rag_engine.answer_query("Flood zone determination", history=history_grading)
        self.assertIsNotNone(res_flood.form_packet)
        self.assertEqual(res_flood.form_packet.form_file, "Flood_Zone_Determination_Letter_REQUEST.pdf")
        self.assertNotIn("grading", res_flood.form_packet.form_title.lower())


if __name__ == "__main__":
    unittest.main()
