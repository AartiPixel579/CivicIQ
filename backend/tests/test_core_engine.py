import unittest
from backend.app.department_loader import registry
from backend.app.rag_engine import rag_engine
from backend.app.flow_engine import flow_engine
from backend.app.vector_store import vector_store

from backend.tests.offline_llm_helper import OfflineLLMTestCase

class TestEdisonCoreEngine(OfflineLLMTestCase):
    def test_department_registry(self):
        depts = registry.get_departments()
        self.assertGreaterEqual(len(depts), 1)
        eng = registry.get_department("engineering")
        self.assertIsNotNone(eng)
        self.assertIn("Engineering", eng.name)
        
        forms = registry.list_forms_for_dept("engineering")
        self.assertIn("Zoning_Permit_Application_Edison.pdf", forms)
        self.assertIn("RoadOpenApp.pdf", forms)

    def test_grounded_rag_query(self):
        # Query about setbacks
        res = rag_engine.answer_query("What are the setback distances for residential zone in Edison?", department_id="engineering")
        self.assertTrue(res.grounded)
        self.assertGreater(len(res.citations), 0)
        top_citation = res.citations[0]
        self.assertIn("edisonnj.org", top_citation.url)
        self.assertTrue(any(k in top_citation.excerpt.lower() for k in ["setback", "survey", "zoning", "permit", "yard"]))
        print("\n[TEST RAG] Setbacks answer citation:", top_citation.url, "Score:", top_citation.relevance_score)

    def test_grounded_rag_refusal_for_unverified_content(self):
        # Query about something completely outside municipal knowledge base
        res = rag_engine.answer_query("What is the quantum mechanics formula for fusion reactors in space?", department_id="engineering")
        self.assertFalse(res.grounded)
        self.assertEqual(len(res.citations), 0)
        self.assertIn("out of our context", res.answer.lower())
        self.assertIn("https://www.edisonnj.org/document_center/index.php", res.answer)
        print("[TEST RAG] Grounded out-of-context redirection successfully enforced.")

    def test_deterministic_flowchart_execution(self):
        session_id = "test_citizen_session_edison_001"
        # 1. Start residential zoning permit flow
        ok, msg, step1, form = flow_engine.start_flow(session_id, "engineering", "residential_zoning_permit_flow")
        self.assertTrue(ok)
        self.assertEqual(step1.id, "step_scope_selection")

        # 2. Advance: select new single family dwelling
        ok, msg, step2, form = flow_engine.advance_step(session_id, "scope_new_home")
        self.assertTrue(ok)
        self.assertEqual(step2.id, "step_survey_verification")

        # 3. Advance: survey ready
        ok, msg, step3, form = flow_engine.advance_step(session_id, "survey_ready")
        self.assertTrue(ok)
        self.assertEqual(step3.id, "step_setback_compliance")

        # 4. Advance: setbacks conform -> Reaches Form Issuance!
        ok, msg, step4, form_packet = flow_engine.advance_step(session_id, "setbacks_conform")
        self.assertTrue(ok)
        self.assertEqual(step4.id, "issue_edison_zoning_packet")
        self.assertIsNotNone(form_packet)
        self.assertEqual(form_packet.form_file, "Zoning_Permit_Application_Edison.pdf")
        self.assertGreaterEqual(len(form_packet.required_attachments), 3)
        self.assertIn("Edison", form_packet.submission_routing.building_address)
        print("[TEST FLOW] Form packet successfully issued:", form_packet.form_title, "| Desk:", form_packet.submission_routing.desk)

if __name__ == "__main__":
    unittest.main()
