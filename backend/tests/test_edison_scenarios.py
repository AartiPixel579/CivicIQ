"""
Test Suite for Realistic Edison Township Resident Inquiries (Source-Aligned & Scope-Enforced):
1. Construct new house (Unconfigured service check)
2. Tree removal procedure
3. Sewer connection application (Unconfigured service check)
4. Excavation permit process (Unconfigured service check)
5. Documents needed for tree removal permit
6. Explicit form download request (Tree removal application)
7. Multi-turn context memory: follow-up request uses previous turn context to issue correct form
8. Out-of-context inquiry (cat adoption, etc.) -> returns out-of-context message with edisonnj.org URL
9. Tree removal emergency multi-turn interaction
"""

import unittest
from backend.app.main import chat_endpoint
from backend.app.models import ChatRequest
from backend.app.config import OUT_OF_CONTEXT_MESSAGE, UNCONFIGURED_SERVICE_MESSAGE

class TestEdisonResidentScenarios(unittest.TestCase):

    def test_scenario_01_construct_new_house(self):
        """Resident asks about construction/zoning permit requirements -> Unconfigured service."""
        req = ChatRequest(
            session_id="scen_1_construct_house",
            message="I want to construct a new house on my property. Which permit do I need?",
            department_id="engineering"
        )
        res = chat_endpoint(req)
        self.assertIn("This service hasn't been configured yet", res.message)
        print("\n[SCENARIO 1 PASSED] Construction query correctly identified as unconfigured service")

    def test_scenario_02_tree_removal(self):
        """Resident asks: 'I need to remove a tree on my property. What is the procedure?'"""
        req = ChatRequest(
            session_id="scen_2_tree_removal",
            message="I need to remove a tree on my property. What is the procedure?",
            department_id="engineering"
        )
        res = chat_endpoint(req)
        self.assertTrue(len(res.message) > 20)
        self.assertTrue(any(w in res.message.lower() for w in ["tree", "removal", "planning to remove"]))
        print("[SCENARIO 2 PASSED] Tree removal query successfully answered")

    def test_scenario_03_sewer_connection(self):
        """Resident asks: 'How do I apply for a sewer connection in Edison?' -> Unconfigured service."""
        req = ChatRequest(
            session_id="scen_3_sewer_connection",
            message="How do I apply for a sewer connection in Edison?",
            department_id="engineering"
        )
        res = chat_endpoint(req)
        self.assertIn("This service hasn't been configured yet", res.message)
        print("[SCENARIO 3 PASSED] Sewer inquiry identified as unconfigured service")

    def test_scenario_04_road_excavation(self):
        """Resident asks: 'I need a street excavation permit to connect underground utilities.' -> Unconfigured service."""
        req = ChatRequest(
            session_id="scen_4_excavation",
            message="I need a street excavation permit to connect underground utilities.",
            department_id="engineering"
        )
        res = chat_endpoint(req)
        self.assertIn("This service hasn't been configured yet", res.message)
        self.assertNotIn("811", res.message)
        print("[SCENARIO 4 PASSED] Road excavation query identified as unconfigured service without asking for 811")

    def test_scenario_05_documents_needed(self):
        """Resident asks: 'What documents do I need to attach for a tree removal permit?'"""
        req = ChatRequest(
            session_id="scen_5_documents_needed",
            message="What documents do I need to attach for a tree removal permit?",
            department_id="engineering"
        )
        res = chat_endpoint(req)
        self.assertTrue(any(w in res.message.lower() for w in ["survey or tax map", "written statement", "sketch"]))
        print("[SCENARIO 5 PASSED] Document checklist inquiry answered directly")

    def test_scenario_06_official_form_download(self):
        """Resident explicitly asks: 'Can I download the official application form for tree removal?'"""
        req = ChatRequest(
            session_id="scen_6_form_download",
            message="Can I download the official application form for tree removal?",
            department_id="engineering"
        )
        res = chat_endpoint(req)
        self.assertIsNotNone(res.form_packet)
        self.assertEqual(res.form_packet.form_file, "3.23.21 tree permit application.pdf")
        self.assertIn("Tree", res.form_packet.form_title)
        print("[SCENARIO 6 PASSED] Tree removal PDF packet attached upon explicit request")

    def test_scenario_07_multiturn_context_form_reference(self):
        """Multi-turn context: Turn 1 discusses tree removal, Turn 2 asks 'Can you give me the application form?'"""
        sid = "scen_7_multiturn_test"
        # Turn 1: Discuss tree removal
        req1 = ChatRequest(
            session_id=sid,
            message="I need help understanding tree removal rules in Edison.",
            department_id="engineering"
        )
        chat_endpoint(req1)

        # Turn 2: Follow-up asking for the form using pronoun/reference
        req2 = ChatRequest(
            session_id=sid,
            message="Can you give me that application form?",
            department_id="engineering"
        )
        res2 = chat_endpoint(req2)
        # Using conversation history, it recognizes "that" means tree removal and attaches 3.23.21 tree permit application.pdf!
        self.assertIsNotNone(res2.form_packet)
        self.assertEqual(res2.form_packet.form_file, "3.23.21 tree permit application.pdf")
        print("[SCENARIO 7 PASSED] Multi-turn memory successfully resolved 'that' to 3.23.21 tree permit application.pdf")

    def test_scenario_08_out_of_context_inquiry(self):
        """Resident asks out-of-engineering question: 'I want to adopt a cat. What is the procedure?'"""
        req = ChatRequest(
            session_id="scen_8_out_of_context",
            message="I want to adopt a cat. What is the procedure?",
            department_id="engineering"
        )
        res = chat_endpoint(req)
        self.assertIn("sorry, this information is out of our context", res.message.lower())
        self.assertIn("Township of Edison Engineering services", res.message)
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

        # Turn 2: User responds "no" to standard permit / urgency
        r2 = chat_endpoint(ChatRequest(
            session_id=sid,
            message="Yes, I am removing a tree",
            department_id="engineering"
        ))
        self.assertIn("emergency situation", r2.message.lower())
        self.assertIsNone(r2.form_packet)

        # Turn 3: User explains urgent emergency
        r3 = chat_endpoint(ChatRequest(
            session_id=sid,
            message="The tree is dead, cracked, and leaning dangerously over my house in this severe storm",
            department_id="engineering"
        ))
        self.assertEqual(r3.current_step.id, "step_emergency_protocol_result")
        self.assertTrue("immediate removal" in r3.message.lower() or "safely remove" in r3.message.lower())
        self.assertIsNotNone(r3.form_packet)
        self.assertEqual(r3.form_packet.form_file, "3.23.21 tree permit application.pdf")
        print("[SCENARIO 9 PASSED] Tree removal emergency workflow correctly concluded with official form packet")


if __name__ == "__main__":
    unittest.main()
