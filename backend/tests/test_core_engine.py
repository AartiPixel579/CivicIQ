import unittest
from backend.app.department_loader import registry
from backend.app.rag_engine import rag_engine
from backend.app.flow_engine import flow_engine
from backend.app.vector_store import vector_store

class TestPixelvyneCoreEngine(unittest.TestCase):
    def test_department_registry(self):
        depts = registry.get_departments()
        self.assertGreaterEqual(len(depts), 2)
        eng = registry.get_department("engineering")
        self.assertIsNotNone(eng)
        self.assertEqual(eng.name, "Engineering & Public Works Department")
        
        forms = registry.list_forms_for_dept("engineering")
        self.assertIn("ENG-204_Residential_Permit_Application.pdf", forms)
        self.assertIn("ENG-102_Excavation_Right_of_Way_Permit.pdf", forms)

    def test_grounded_rag_query(self):
        # Query about setbacks
        res = rag_engine.answer_query("What are the setback distances for R-1 residential zone?", department_id="engineering")
        self.assertTrue(res.grounded)
        self.assertGreater(len(res.citations), 0)
        top_citation = res.citations[0]
        self.assertTrue("edisonnj.org" in top_citation.url or "pixelvyne.gov" in top_citation.url)
        self.assertTrue(any(k in top_citation.excerpt.lower() for k in ["setback", "survey", "zoning", "permit"]))
        print("\n[TEST RAG] Setbacks answer citation:", top_citation.url, "Score:", top_citation.relevance_score)

    def test_grounded_rag_refusal_for_unverified_content(self):
        # Query about something completely outside municipal knowledge base
        res = rag_engine.answer_query("What is the quantum mechanics formula for fusion reactors in space?", department_id="engineering")
        self.assertFalse(res.grounded)
        self.assertEqual(len(res.citations), 0)
        self.assertIn("Under strict municipal protocol", res.answer)
        print("[TEST RAG] Grounded refusal successfully enforced for unverified topic.")

    def test_deterministic_flowchart_execution(self):
        session_id = "test_citizen_session_001"
        # 1. Start residential building permit flow
        ok, msg, step1, form = flow_engine.start_flow(session_id, "engineering", "residential_building_permit")
        self.assertTrue(ok)
        self.assertEqual(step1.id, "check_zoning")
        self.assertTrue(step1.is_mandatory_prerequisite)

        # 2. Advance: select residential zone R-1
        ok, msg, step2, form = flow_engine.advance_step(session_id, "zone_residential")
        self.assertTrue(ok)
        self.assertEqual(step2.id, "check_ownership")

        # 3. Advance: select deed owner
        ok, msg, step3, form = flow_engine.advance_step(session_id, "owner_deed_holder")
        self.assertTrue(ok)
        self.assertEqual(step3.id, "check_project_scope")

        # 4. Advance: select structural home addition
        ok, msg, step4, form = flow_engine.advance_step(session_id, "scope_structural_addition")
        self.assertTrue(ok)
        self.assertEqual(step4.id, "check_setbacks")

        # 5. Advance: confirm setback compliance -> Reaches Form Issuance!
        ok, msg, step5, form_packet = flow_engine.advance_step(session_id, "setbacks_compliant")
        self.assertTrue(ok)
        self.assertEqual(step5.id, "issue_form_eng_204")
        self.assertIsNotNone(form_packet)
        self.assertEqual(form_packet.form_code, "Form ENG-204")
        self.assertEqual(form_packet.form_file, "ENG-204_Residential_Permit_Application.pdf")
        self.assertGreaterEqual(len(form_packet.required_attachments), 4)
        self.assertEqual(form_packet.submission_routing.desk, "Counter 3, Public Works Intake Annex")
        print("[TEST FLOW] Form packet successfully issued:", form_packet.form_code, "| Desk:", form_packet.submission_routing.desk)

if __name__ == "__main__":
    unittest.main()
