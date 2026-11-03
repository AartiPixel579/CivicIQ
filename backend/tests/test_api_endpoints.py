"""
End-to-end integration tests for FastAPI endpoints
Tests health, department loading, grounded RAG queries, flowchart steps,
official PDF serving, and anti-hallucination guardrails.
"""

import unittest
from backend.app.main import (
    health_check, list_departments, get_department, 
    chat_endpoint, start_flow_endpoint, advance_flow_step, 
    serve_official_form, get_document_center
)
from backend.app.models import ChatRequest, FlowStartRequest, FlowStepRequest

class TestApiEndpoints(unittest.TestCase):
    def test_01_health_check(self):
        res = health_check()
        self.assertEqual(res["status"], "healthy")
        self.assertGreaterEqual(res["departments_loaded"], 2)
        self.assertGreaterEqual(res["vector_store_chunks"], 10)
        print("\n[API TEST] Health check passed:", res)

    def test_02_departments_endpoints(self):
        depts = list_departments()
        self.assertGreaterEqual(len(depts), 2)
        dept_ids = [d["id"] for d in depts]
        self.assertIn("engineering", dept_ids)
        self.assertIn("healthcare", dept_ids)

        eng = get_department("engineering")
        self.assertEqual(eng["config"]["id"], "engineering")
        self.assertGreaterEqual(len(eng["flows"]), 2)
        self.assertGreaterEqual(len(eng["forms"]), 2)
        self.assertGreaterEqual(len(eng["links"]), 5)
        print("[API TEST] Department discovery passed. Engineering forms:", eng["forms"])

    def test_03_rag_chat_setbacks(self):
        req = ChatRequest(
            session_id="test_sess_rag_1",
            message="What are the setback distances for single-family residential R-1 zoning?",
            department_id="engineering"
        )
        res = chat_endpoint(req)
        self.assertEqual(res.mode, "rag")
        self.assertIsNotNone(res.citations)
        self.assertGreater(len(res.citations), 0)
        self.assertTrue(any("edisonnj.org" in c.url or "pixelvyne.gov" in c.url for c in res.citations))
        print("[API TEST] RAG query passed. Citation URL:", res.citations[0].url)

    def test_04_rag_chat_unverified_guardrail(self):
        req = ChatRequest(
            session_id="test_sess_rag_2",
            message="What are the rules for space shuttle orbital docking in Pixelvyne?",
            department_id="engineering"
        )
        res = chat_endpoint(req)
        self.assertEqual(res.mode, "rag")
        # Ensure refusal is returned and no fabricated citation is created
        self.assertEqual(len(res.citations), 0)
        self.assertIn("strict municipal protocol", res.message.lower())
        print("[API TEST] Anti-hallucination guardrail passed. Refusal message returned.")

    def test_05_deterministic_flow_completion_and_pdf_issuance(self):
        sid = "test_sess_flow_e2e"
        
        # 1. Start flow
        start_req = FlowStartRequest(
            session_id=sid,
            department_id="engineering",
            flow_id="residential_building_permit"
        )
        r1 = start_flow_endpoint(start_req)
        self.assertEqual(r1.mode, "flow")
        self.assertEqual(r1.current_step.id, "check_zoning")

        # 2. Step 1: Confirm Residential
        r2 = advance_flow_step(FlowStepRequest(session_id=sid, option_id="zone_residential"))
        self.assertEqual(r2.current_step.id, "check_ownership")

        # 3. Step 2: Confirm Deed Holder
        r3 = advance_flow_step(FlowStepRequest(session_id=sid, option_id="owner_deed_holder"))
        self.assertEqual(r3.current_step.id, "check_project_scope")

        # 4. Step 3: Structural Addition
        r4 = advance_flow_step(FlowStepRequest(session_id=sid, option_id="scope_structural_addition"))
        self.assertEqual(r4.current_step.id, "check_setbacks")

        # 5. Step 4: Confirm Setbacks Compliant -> Official PDF Issuance!
        r5 = advance_flow_step(FlowStepRequest(session_id=sid, option_id="setbacks_compliant"))
        self.assertTrue(r5.completed)
        self.assertIsNotNone(r5.form_packet)
        self.assertEqual(r5.form_packet.form_code, "Form ENG-204")
        self.assertEqual(r5.form_packet.form_file, "ENG-204_Residential_Permit_Application.pdf")
        self.assertEqual(r5.form_packet.submission_routing.desk, "Counter 3, Public Works Intake Annex")
        self.assertGreaterEqual(len(r5.form_packet.required_attachments), 5)
        print("[API TEST] Deterministic Flowchart successfully completed and issued Form ENG-204 packet.")

    def test_06_official_pdf_serving(self):
        res = serve_official_form(dept_id="engineering", filename="ENG-204_Residential_Permit_Application.pdf")
        self.assertEqual(res.media_type, "application/pdf")
        self.assertEqual(res.status_code, 200)
        self.assertIn("inline; filename=", res.headers["content-disposition"])
        print("[API TEST] Official PDF file served correctly:", res.filename)

    def test_07_edison_document_center(self):
        dc = get_document_center()
        self.assertIn("edisonnj.org", dc["portal_url"])
        self.assertGreaterEqual(dc["total_documents"], 10)
        self.assertIn("Engineering & Zoning", dc["categories"])
        
        # Test search filter
        dc_filtered = get_document_center(search="zoning")
        self.assertGreater(dc_filtered["total_documents"], 0)
        for d in dc_filtered["documents"]:
            self.assertTrue("zoning" in d["title"].lower() or "zoning" in d["description"].lower() or "zoning" in d["category"].lower())
        print(f"[API TEST] Edison Document Center catalog loaded: {dc['total_documents']} official forms available.")

if __name__ == "__main__":
    unittest.main()
