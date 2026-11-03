"""
End-to-end integration tests for Edison Township CivicIQ FastAPI endpoints
Tests health, department loading, grounded RAG queries, flowchart steps,
official PDF serving, admin authentication, and anti-hallucination guardrails.
"""

import unittest
from backend.app.main import (
    health_check, list_departments, get_department, 
    chat_endpoint, start_flow_endpoint, advance_flow_step, 
    serve_official_form, get_document_center, get_document_inventory_endpoint,
    trigger_ingestion
)
from backend.app.models import ChatRequest, FlowStartRequest, FlowStepRequest
from backend.app.config import ADMIN_API_KEY
from fastapi import HTTPException

class TestApiEndpoints(unittest.TestCase):
    def test_01_health_check(self):
        res = health_check()
        self.assertEqual(res["status"], "healthy")
        self.assertGreaterEqual(res["departments_loaded"], 1)
        self.assertGreaterEqual(res["vector_store_chunks"], 10)
        print("\n[API TEST] Health check passed:", res)

    def test_02_departments_endpoints(self):
        depts = list_departments()
        self.assertGreaterEqual(len(depts), 1)
        dept_ids = [d["id"] for d in depts]
        self.assertIn("engineering", dept_ids)

        eng = get_department("engineering")
        self.assertEqual(eng["config"]["id"], "engineering")
        self.assertGreaterEqual(len(eng["flows"]), 2)
        self.assertGreaterEqual(len(eng["forms"]), 2)
        print("[API TEST] Department discovery passed. Engineering forms:", eng["forms"])

    def test_03_rag_chat_setbacks(self):
        req = ChatRequest(
            session_id="test_sess_rag_1",
            message="What are the setback distances for residential zoning in Edison?",
            department_id="engineering"
        )
        res = chat_endpoint(req)
        self.assertEqual(res.mode, "rag")
        self.assertIsNotNone(res.citations)
        self.assertGreater(len(res.citations), 0)
        self.assertTrue(any("edisonnj.org" in c.url for c in res.citations))
        print("[API TEST] RAG query passed. Citation URL:", res.citations[0].url)

    def test_04_rag_chat_unverified_guardrail(self):
        req = ChatRequest(
            session_id="test_sess_rag_2",
            message="What are the rules for space shuttle orbital docking in Edison?",
            department_id="engineering"
        )
        res = chat_endpoint(req)
        self.assertEqual(res.mode, "rag")
        # Ensure refusal is returned and no fabricated citation is created
        self.assertEqual(len(res.citations), 0)
        self.assertIn("official municipal protocols", res.message.lower())
        print("[API TEST] Anti-hallucination guardrail passed. Refusal message returned.")

    def test_05_deterministic_flow_completion_and_pdf_issuance(self):
        sid = "test_sess_flow_e2e_edison"
        
        # 1. Start flow
        start_req = FlowStartRequest(
            session_id=sid,
            department_id="engineering",
            flow_id="residential_zoning_permit_flow"
        )
        r1 = start_flow_endpoint(start_req)
        self.assertEqual(r1.mode, "flow")
        self.assertEqual(r1.current_step.id, "step_scope_selection")

        # 2. Step 1: Select New Home
        r2 = advance_flow_step(FlowStepRequest(session_id=sid, option_id="scope_new_home"))
        self.assertEqual(r2.current_step.id, "step_survey_verification")

        # 3. Step 2: Survey Ready
        r3 = advance_flow_step(FlowStepRequest(session_id=sid, option_id="survey_ready"))
        self.assertEqual(r3.current_step.id, "step_setback_compliance")

        # 4. Step 3: Setbacks Conform -> Reaches Official Form Issuance!
        r4 = advance_flow_step(FlowStepRequest(session_id=sid, option_id="setbacks_conform"))
        self.assertTrue(r4.completed)
        self.assertIsNotNone(r4.form_packet)
        self.assertEqual(r4.form_packet.form_file, "Zoning_Permit_Application_Edison.pdf")
        self.assertIn("100 Municipal Blvd", r4.form_packet.submission_routing.building_address)
        self.assertGreaterEqual(len(r4.form_packet.required_attachments), 3)
        print("[API TEST] Deterministic Flowchart successfully completed and issued real Edison Zoning PDF packet.")

    def test_06_official_pdf_serving(self):
        res = serve_official_form(dept_id="engineering", filename="Zoning_Permit_Application_Edison.pdf")
        self.assertEqual(res.media_type, "application/pdf")
        self.assertEqual(res.status_code, 200)
        self.assertIn("inline; filename=", res.headers["content-disposition"])
        print("[API TEST] Official PDF file served correctly:", res.filename)

    def test_07_edison_document_center_and_inventory(self):
        dc = get_document_center()
        self.assertIn("edisonnj.org", dc["portal_url"])
        self.assertGreaterEqual(dc["total_documents"], 5)
        
        # Test inventory endpoint
        inv = get_document_inventory_endpoint()
        self.assertGreaterEqual(inv["total_documents"], 5)
        print(f"[API TEST] Edison Document Center catalog loaded: {dc['total_documents']} official documents.")

    def test_08_admin_ingest_protection(self):
        # Missing key should raise 403
        with self.assertRaises(HTTPException) as cm:
            trigger_ingestion(x_admin_key="invalid-key")
        self.assertEqual(cm.exception.status_code, 403)

        # Valid key succeeds
        res = trigger_ingestion(x_admin_key=ADMIN_API_KEY)
        self.assertEqual(res["status"], "success")
        print("[API TEST] Admin ingest key protection verified.")

if __name__ == "__main__":
    unittest.main()
