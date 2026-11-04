"""
Test Suite for Realistic Edison Township Resident Inquiries:
1. Construct new house
2. Tree removal procedure
3. Sewer connection application
4. Excavation permit process
5. Documents needed for engineering/residential permit
6. Explicit form download request
7. Multi-turn context memory: follow-up request uses previous turn context to issue correct form
8. Out-of-context inquiry (cat adoption, etc.) -> returns out-of-context message with edisonnj.org URL
"""

import unittest
from backend.app.main import chat_endpoint
from backend.app.models import ChatRequest
from backend.app.config import OUT_OF_CONTEXT_MESSAGE

class TestEdisonResidentScenarios(unittest.TestCase):

    def test_scenario_01_construct_new_house(self):
        """Resident asks about construction permit requirements"""
        req = ChatRequest(
            session_id="scen_1_construct_house",
            message="I want to construct a new house on my property. Which permit do I need?",
            department_id="engineering"
        )
        res = chat_endpoint(req)
        self.assertTrue(len(res.message) > 20)
        self.assertTrue(any(w in res.message.lower() for w in ["permit", "survey", "schedule a", "edison"]))
        print("\n[SCENARIO 1 PASSED] Construction query answered with grounded municipal context")

    def test_scenario_02_tree_removal(self):
        """Resident asks: 'I need to remove a tree on my property. What is the procedure?'"""
        req = ChatRequest(
            session_id="scen_2_tree_removal",
            message="I need to remove a tree on my property. What is the procedure?",
            department_id="engineering"
        )
        res = chat_endpoint(req)
        self.assertTrue(len(res.message) > 20)
        self.assertTrue(any(w in res.message.lower() for w in ["tree", "removal", "clearance", "edison"]))
        print("[SCENARIO 2 PASSED] Tree removal query successfully answered")

    def test_scenario_03_sewer_connection(self):
        """Resident asks: 'How do I apply for a sewer connection in Edison?'"""
        req = ChatRequest(
            session_id="scen_3_sewer_connection",
            message="How do I apply for a sewer connection in Edison?",
            department_id="engineering"
        )
        res = chat_endpoint(req)
        self.assertTrue(any(w in res.message.lower() for w in ["sewer", "connection", "fixture", "charge"]))
        print("[SCENARIO 3 PASSED] Sewer inquiry successfully answered")

    def test_scenario_04_road_excavation(self):
        """Resident asks: 'I need a street excavation permit to connect underground utilities.'"""
        req = ChatRequest(
            session_id="scen_4_excavation",
            message="I need a street excavation permit to connect underground utilities.",
            department_id="engineering"
        )
        res = chat_endpoint(req)
        self.assertTrue(any(w in res.message.lower() for w in ["road", "street", "opening", "excavation", "811", "bond"]))
        print("[SCENARIO 4 PASSED] Road excavation query successfully answered")

    def test_scenario_05_documents_needed(self):
        """Resident asks: 'What documents do I need to attach for a residential permit?'"""
        req = ChatRequest(
            session_id="scen_5_documents_needed",
            message="What documents do I need to attach for a residential permit?",
            department_id="engineering"
        )
        res = chat_endpoint(req)
        self.assertEqual(res.mode, "rag")
        self.assertGreater(len(res.citations), 0)
        self.assertTrue(any("edisonnj" in c.url for c in res.citations))
        print("[SCENARIO 5 PASSED] Document checklist inquiry answered with grounded official citations")

    def test_scenario_06_official_form_download(self):
        """Resident explicitly asks: 'Can I download the official application form for road opening?'"""
        req = ChatRequest(
            session_id="scen_6_form_download",
            message="Can I download the official application form for road opening?",
            department_id="engineering"
        )
        res = chat_endpoint(req)
        self.assertIsNotNone(res.form_packet)
        self.assertEqual(res.form_packet.form_file, "RoadOpenApp.pdf")
        self.assertIn("Road", res.form_packet.form_title)
        print("[SCENARIO 6 PASSED] Road opening PDF packet attached upon explicit request")

    def test_scenario_07_multiturn_context_form_reference(self):
        """Multi-turn context: Turn 1 discusses road opening, Turn 2 asks 'Can you give me the application form?'"""
        sid = "scen_7_multiturn_test"
        # Turn 1: Discuss street opening
        req1 = ChatRequest(
            session_id=sid,
            message="I need information on street opening road excavation in Edison.",
            department_id="engineering"
        )
        res1 = chat_endpoint(req1)
        self.assertIsNone(res1.form_packet) # Should not blindly attach form card on general inquiry

        # Turn 2: Follow-up asking for the form without naming it
        req2 = ChatRequest(
            session_id=sid,
            message="Can you please give me the official application form for that?",
            department_id="engineering"
        )
        res2 = chat_endpoint(req2)
        # Using conversation history, it recognizes "that" means road opening and attaches RoadOpenApp.pdf!
        self.assertIsNotNone(res2.form_packet)
        self.assertEqual(res2.form_packet.form_file, "RoadOpenApp.pdf")
        print("[SCENARIO 7 PASSED] Multi-turn memory successfully resolved 'that' to RoadOpenApp.pdf")

    def test_scenario_08_out_of_context_inquiry(self):
        """Resident asks out-of-engineering question: 'I want to adopt a cat. What is the procedure?'"""
        req = ChatRequest(
            session_id="scen_8_out_of_context",
            message="I want to adopt a cat. What is the procedure?",
            department_id="engineering"
        )
        res = chat_endpoint(req)
        self.assertIn("sorry, this information is out of our context", res.message.lower())
        self.assertIn("https://www.edisonnj.org/document_center/index.php", res.message)
        print("[SCENARIO 8 PASSED] Out-of-context inquiry returned exact requested redirection message")

    def test_scenario_09_tree_removal_emergency_flowchart(self):
        """Resident asks for guidance on tree removal, reports urgency, provides dead/cracked hazard reason."""
        sid = "scen_9_tree_emergency_interactive"

        # Turn 1: Guidance request
        r1 = chat_endpoint(ChatRequest(
            session_id=sid,
            message="could you please guide me with tree removal",
            department_id="engineering"
        ))
        self.assertIn("planning to remove one or more trees", r1.message.lower())
        self.assertIsNone(r1.form_packet)
        self.assertEqual(r1.mode, "flow")

        # Turn 2: Urgency / emergency reported
        r2 = chat_endpoint(ChatRequest(
            session_id=sid,
            message="yes, it's an emergency, the tree is dead and cracked",
            department_id="engineering"
        ))
        self.assertTrue("photograph" in r2.message.lower() or "photo" in r2.message.lower())
        self.assertIn("concurrent", r2.message.lower())
        self.assertIsNotNone(r2.form_packet)
        self.assertEqual(r2.form_packet.form_file, "3.23.21 tree permit application.pdf")
        self.assertIn("document center", r2.message.lower())
        print("[SCENARIO 9 PASSED] Multi-turn tree removal flowchart: Page 3 flowchart verified with verified tree removal application")

    def test_scenario_10_soil_import_application(self):
        """Resident asks for soil importation application form."""
        req = ChatRequest(
            session_id="scen_10_soil_import",
            message="I need to import soil for grading my backyard. Can you give me the soil importation permit application?",
            department_id="engineering"
        )
        res = chat_endpoint(req)
        self.assertIsNotNone(res.form_packet)
        self.assertEqual(res.form_packet.form_file, "Forms_Soil_Importation_Appl.pdf")
        print("[SCENARIO 10 PASSED] Soil importation permit application packet correctly matched and returned")

    def test_scenario_11_soil_export_application(self):
        """Resident asks for soil export application form."""
        req = ChatRequest(
            session_id="scen_11_soil_export",
            message="I am digging a foundation and need to export soil off site. Where is the soil exportation application?",
            department_id="engineering"
        )
        res = chat_endpoint(req)
        self.assertIsNotNone(res.form_packet)
        self.assertEqual(res.form_packet.form_file, "Forms_Soil_Exportation_App.pdf")
        print("[SCENARIO 11 PASSED] Soil exportation permit application packet correctly matched and returned")

    def test_scenario_12_site_improvement_application(self):
        """Resident asks for site improvement permit application."""
        req = ChatRequest(
            session_id="scen_12_site_improvement",
            message="Can I get the site improvement permit application and checklist?",
            department_id="engineering"
        )
        res = chat_endpoint(req)
        self.assertIsNotNone(res.form_packet)
        self.assertEqual(res.form_packet.form_file, "SIP_Application.pdf")
        print("[SCENARIO 12 PASSED] Site improvement permit application packet correctly matched and returned")

if __name__ == "__main__":
    unittest.main()
