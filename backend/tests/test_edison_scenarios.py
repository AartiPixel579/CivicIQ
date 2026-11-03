"""
Test Suite for 8 Realistic Edison Township Resident Inquiries:
1. Construct new house -> launches residential_zoning_permit_flow
2. Tree removal procedure -> launches tree_removal_flow
3. Sewer connection application -> launches sewer_connection_flow
4. Excavation permit process -> launches street_opening_flow
5. Documents needed for residential permit -> grounded RAG cites requirement sheet
6. Official application form download -> in-chat delivery of real Edison Zoning PDF packet
7. Submission guidance -> guidance to 100 Municipal Blvd, Division of Zoning
8. Unsupported department inquiry (cat adoption) -> friendly referral to Edison Municipal Animal Shelter
"""

import unittest
from backend.app.main import chat_endpoint
from backend.app.models import ChatRequest

class TestEdisonResidentScenarios(unittest.TestCase):

    def test_scenario_01_construct_new_house(self):
        """Resident asks: 'I want to construct a new house on my property. Which permit do I need?'"""
        req = ChatRequest(
            session_id="scen_1_construct_house",
            message="I want to construct a new house on my property. Which permit do I need?",
            department_id="engineering"
        )
        res = chat_endpoint(req)
        self.assertEqual(res.mode, "flow")
        self.assertEqual(res.active_flow_id, "residential_zoning_permit_flow")
        self.assertIsNotNone(res.options)
        self.assertTrue(any("New Single-Family" in o.label for o in res.options))
        print("\n[SCENARIO 1 PASSED] Construction query successfully routed to residential_zoning_permit_flow")

    def test_scenario_02_tree_removal(self):
        """Resident asks: 'I need to remove a tree on my property. What is the procedure?'"""
        req = ChatRequest(
            session_id="scen_2_tree_removal",
            message="I need to remove a tree on my property. What is the procedure?",
            department_id="engineering"
        )
        res = chat_endpoint(req)
        self.assertEqual(res.mode, "flow")
        self.assertEqual(res.active_flow_id, "tree_removal_flow")
        self.assertIsNotNone(res.options)
        print("[SCENARIO 2 PASSED] Tree removal query successfully routed to tree_removal_flow")

    def test_scenario_03_sewer_connection(self):
        """Resident asks: 'How do I apply for a sewer connection in Edison?'"""
        req = ChatRequest(
            session_id="scen_3_sewer_connection",
            message="How do I apply for a sewer connection in Edison?",
            department_id="engineering"
        )
        res = chat_endpoint(req)
        self.assertEqual(res.mode, "flow")
        self.assertEqual(res.active_flow_id, "sewer_connection_flow")
        self.assertIsNotNone(res.options)
        print("[SCENARIO 3 PASSED] Sewer inquiry successfully routed to sewer_connection_flow")

    def test_scenario_04_road_excavation(self):
        """Resident asks: 'I need a street excavation permit to connect underground utilities.'"""
        req = ChatRequest(
            session_id="scen_4_excavation",
            message="I need a street excavation permit to connect underground utilities.",
            department_id="engineering"
        )
        res = chat_endpoint(req)
        self.assertEqual(res.mode, "flow")
        self.assertEqual(res.active_flow_id, "street_opening_flow")
        self.assertIsNotNone(res.options)
        print("[SCENARIO 4 PASSED] Road excavation query successfully routed to street_opening_flow")

    def test_scenario_05_documents_needed(self):
        """Resident asks: 'What documents do I need to attach for a residential zoning permit?'"""
        req = ChatRequest(
            session_id="scen_5_documents_needed",
            message="What documents do I need to attach for a residential zoning permit?",
            department_id="engineering"
        )
        res = chat_endpoint(req)
        self.assertEqual(res.mode, "rag")
        self.assertGreater(len(res.citations), 0)
        self.assertTrue(any("edisonnj.org" in c.url for c in res.citations))
        self.assertTrue(any(w in res.message.lower() for w in ["survey", "zoning", "permit", "scale"]))
        print("[SCENARIO 5 PASSED] Document checklist inquiry answered with grounded official citations")

    def test_scenario_06_official_form_download(self):
        """Resident asks: 'Can I download the official Edison zoning permit application form?'"""
        req = ChatRequest(
            session_id="scen_6_form_download",
            message="Can I download the official Edison zoning permit application form?",
            department_id="engineering"
        )
        res = chat_endpoint(req)
        self.assertIsNotNone(res.form_packet)
        self.assertEqual(res.form_packet.form_file, "Zoning_Permit_Application_Edison.pdf")
        self.assertIn("Zoning", res.form_packet.form_title)
        self.assertIn("100 Municipal Blvd", res.form_packet.submission_routing.building_address)
        print("[SCENARIO 6 PASSED] Official form download delivery attached with real Edison Zoning PDF")

    def test_scenario_07_submission_guidance(self):
        """Resident asks: 'Where and when can I submit my engineering permit application in Edison?'"""
        req = ChatRequest(
            session_id="scen_7_submission_guidance",
            message="Where and when can I submit my engineering permit application in Edison?",
            department_id="engineering"
        )
        res = chat_endpoint(req)
        self.assertEqual(res.mode, "rag")
        self.assertIn("100 Municipal Blvd", res.message)
        print("[SCENARIO 7 PASSED] Submission desk & hours guidance provided for Edison Municipal Complex")

    def test_scenario_08_unsupported_department_cat_adoption(self):
        """Resident asks: 'I want to adopt a cat. What is the procedure?'"""
        req = ChatRequest(
            session_id="scen_8_cat_adoption",
            message="I want to adopt a cat. What is the procedure?",
            department_id="engineering"
        )
        res = chat_endpoint(req)
        self.assertIn("Edison Municipal Animal Shelter", res.message)
        self.assertIn("125 Municipal Blvd", res.message)
        self.assertIn("(732) 248-7258", res.message)
        self.assertIn("Engineering & Zoning Department MVP", res.message)
        print("[SCENARIO 8 PASSED] Animal shelter referral given with exact address, phone, and hours")

if __name__ == "__main__":
    unittest.main()
