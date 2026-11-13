"""
Targeted regression tests for the 9 Critical & High-severity audit findings and RAG/workflow grounding on feature/engineering-staging.
"""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from fastapi.responses import FileResponse

from backend.app.config import GENERATED_DRAFTS_DIR
from backend.app.crawler.ssrf_guard import PinnedIPAdapter, _is_unsafe_ip
from backend.app.crawler.web_crawler import ConfigurableWebCrawler, CrawlerConfig
from backend.app.flow_engine import FlowSession, FlowStep
from backend.app.llm_provider.base import LLMResponse
from backend.app.llm_provider.manager import llm_manager
from backend.app.main import BoundedChatHistories, chat_endpoint, download_draft_pdf
from backend.app.models import ChatRequest, RagCitation, RagResult
from backend.app.pgvector_store import PgVectorStore
from backend.app.rag_engine import rag_engine
from backend.app.rate_limiter import PersistentRateLimiter, RateLimiterUnavailableError
from backend.app.services.service_intent_service import service_intent_service
from backend.app.services.form_lifecycle_store import form_lifecycle_store
from backend.app.vector_store import KnowledgeDatabaseUnavailableError, vector_store
from backend.tests.offline_llm_helper import OfflineLLMTestCase


class TestAuditFixes(unittest.TestCase):
    # ------------------------------------------------------------------
    # Fix 1: Database failure handling (HTTP 503, no silent bypass)
    # ------------------------------------------------------------------
    def test_01_chat_returns_503_when_knowledge_db_unavailable(self):
        with patch("backend.app.main.rate_limiter.check_rate_limit", return_value=(True, 1)):
            with patch.object(
                rag_engine,
                "answer_query",
                side_effect=KnowledgeDatabaseUnavailableError("pgvector offline"),
            ):
                with self.assertRaises(HTTPException) as ctx:
                    chat_endpoint(
                        ChatRequest(session_id="audit_db_down_1", message="What are the plot grading rules?"),
                        request=None,
                    )
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertIn("unavailable", ctx.exception.detail.lower())

    def test_01b_chat_returns_503_when_rate_limiter_db_unavailable(self):
        with patch(
            "backend.app.main.rate_limiter.check_rate_limit",
            side_effect=RateLimiterUnavailableError("rate_limits pg offline"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                chat_endpoint(ChatRequest(session_id="audit_rl_down_1", message="hello"), request=None)
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertIn("rate limiting", ctx.exception.detail.lower())

    # ------------------------------------------------------------------
    # Fix 2: DNS rebinding / TOCTOU (PinnedIPAdapter mounted & used)
    # ------------------------------------------------------------------
    def test_02_crawler_mounts_pinned_ip_adapter_and_pins_validated_ip(self):
        cfg = CrawlerConfig(root_url="https://www.edisonnj.org/document_center/index.php")
        crawler = ConfigurableWebCrawler(cfg)
        self.assertIsInstance(crawler.session.get_adapter("https://www.edisonnj.org"), PinnedIPAdapter)
        self.assertIsInstance(crawler.session.get_adapter("http://www.edisonnj.org"), PinnedIPAdapter)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "text/html"}

        with patch("backend.app.crawler.web_crawler.resolve_and_validate_url", return_value=("https://www.edisonnj.org/page", "93.184.216.34")):
            with patch.object(crawler.session, "get", return_value=mock_resp):
                resp, final_url, err = crawler._fetch_with_ssrf_redirects("https://www.edisonnj.org/page")
        self.assertIsNone(err)
        self.assertEqual(final_url, "https://www.edisonnj.org/page")
        self.assertEqual(crawler._pinned_ips.get("www.edisonnj.org"), "93.184.216.34")
        self.assertTrue(_is_unsafe_ip("::ffff:127.0.0.1"))

    # ------------------------------------------------------------------
    # Fix 3: Redirect domain-scope bypass
    # ------------------------------------------------------------------
    def test_03_redirect_to_external_html_is_rejected(self):
        cfg = CrawlerConfig(
            root_url="https://www.edisonnj.org/document_center/index.php",
            allowed_domains=["edisonnj.org"],
            follow_external_pdfs=True,
            max_depth=1,
            delay_seconds=0,
        )
        crawler = ConfigurableWebCrawler(cfg, url_validator=lambda u: u)

        redirect_resp = MagicMock()
        redirect_resp.status_code = 302
        redirect_resp.headers = {"Location": "https://evil-external.example/fake.html"}

        external_html_resp = MagicMock()
        external_html_resp.status_code = 200
        external_html_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
        external_html_resp.iter_content.return_value = [b"<html><title>Fake</title><body>Untrusted external rules</body></html>"]

        with patch.object(crawler.session, "get", side_effect=[redirect_resp, external_html_resp]):
            res = crawler.crawl()

        self.assertEqual(len(res.documents), 0)
        self.assertTrue(any("redirected outside allowed_domains" in reason for _, reason in res.skipped_urls))

    # ------------------------------------------------------------------
    # Fix 4: PostgreSQL connection leak in PgVectorStore
    # ------------------------------------------------------------------
    def test_04_pgvector_store_closes_connections_on_success_and_error(self):
        pg = PgVectorStore("postgresql://postgres:secret@localhost:5432/civiciq")
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchall.return_value = []

        with patch("backend.app.pgvector_store.psycopg2.connect", return_value=mock_conn):
            with patch("backend.app.pgvector_store.register_vector"):
                self.assertTrue(pg.check_connection())
                pg.search("tree removal", department_id="engineering")
                pg.get_stats()

                mock_cur.execute.side_effect = RuntimeError("db write error")
                with self.assertRaises(RuntimeError):
                    pg.deactivate_document("engineering", "doc_1")

        self.assertEqual(mock_conn.close.call_count, 4)
        mock_conn.rollback.assert_called_once()

    # ------------------------------------------------------------------
    # Fix 5: Draft PDF path traversal
    # ------------------------------------------------------------------
    def test_05_download_draft_pdf_blocks_traversal_and_allows_valid_draft(self):
        with self.assertRaises(HTTPException) as ctx:
            download_draft_pdf(session_id="..", filename="vector_store.db")
        self.assertEqual(ctx.exception.status_code, 400)

        with self.assertRaises(HTTPException) as ctx2:
            download_draft_pdf(session_id="valid_sess", filename="../secret.pdf")
        self.assertEqual(ctx2.exception.status_code, 400)

        valid_dir = GENERATED_DRAFTS_DIR / "audit_valid_sess"
        valid_dir.mkdir(parents=True, exist_ok=True)
        valid_pdf = valid_dir / "sample_draft.pdf"
        try:
            valid_pdf.write_bytes(b"%PDF-1.4\n%test\n")
            form_lifecycle_store.create_draft_authorization("audit_valid_sess", "sample_draft.pdf")
            resp = download_draft_pdf(session_id="audit_valid_sess", filename="sample_draft.pdf")
            self.assertIsInstance(resp, FileResponse)
            self.assertEqual(Path(resp.path).resolve(), valid_pdf.resolve())
        finally:
            shutil.rmtree(valid_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Fix 6: Chat rate-limit bypass & bounded CHAT_HISTORIES
    # ------------------------------------------------------------------
    def test_06_rate_limit_cannot_be_bypassed_by_rotating_session_id(self):
        tmp_dir = Path(tempfile.mkdtemp())
        try:
            limiter = PersistentRateLimiter(db_path=tmp_dir / "rl.db", db_url="", force_sqlite=True)
            with patch("backend.app.main.rate_limiter", limiter):
                with patch("backend.app.main.CHAT_RATE_LIMIT_PER_MIN", 2):
                    r1 = chat_endpoint(ChatRequest(session_id="rot_1", message="hi"), request=None)
                    r2 = chat_endpoint(ChatRequest(session_id="rot_2", message="hi"), request=None)
                    with self.assertRaises(HTTPException) as ctx:
                        chat_endpoint(ChatRequest(session_id="rot_3", message="hi"), request=None)
            self.assertTrue(r1.message)
            self.assertTrue(r2.message)
            self.assertEqual(ctx.exception.status_code, 429)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_06b_bounded_chat_histories_evicts_lru(self):
        histories = BoundedChatHistories(max_sessions=2, ttl_seconds=3600, max_messages=4)
        histories.setdefault("s1", []).append({"role": "user", "content": "1"})
        histories.setdefault("s2", []).append({"role": "user", "content": "2"})
        histories.setdefault("s3", []).append({"role": "user", "content": "3"})
        self.assertEqual(len(histories), 2)
        self.assertNotIn("s1", histories)
        self.assertIn("s2", histories)
        self.assertIn("s3", histories)

    def test_06c_render_yaml_enables_proxy_headers(self):
        render_text = (Path(__file__).resolve().parents[2] / "render.yaml").read_text(encoding="utf-8")
        self.assertIn("--proxy-headers", render_text)

    # ------------------------------------------------------------------
    # Fix 7: None service TypeError in RagEngine.answer_query
    # ------------------------------------------------------------------
    def test_07_answer_query_handles_citation_with_none_service(self):
        cit = RagCitation(
            url="https://www.edisonnj.org/document_center/Schedule_A.pdf",
            title="Schedule A Yard Requirements",
            category="Zoning",
            department_id="engineering",
            relevance_score=0.9,
            excerpt="Minimum side yard setback is 10 feet in R-A zone.",
            visibility="public",
            service=None,
        )
        with patch.object(vector_store, "search", return_value=[cit]):
            with patch("backend.app.llm_client.llm_manager.generate", return_value=LLMResponse(success=False, content="", error="offline", provider="none", model="none")):
                res = rag_engine.answer_query("What is the side yard setback?", department_id="engineering", history=[])
        self.assertTrue(res.grounded)
        self.assertGreaterEqual(len(res.citations), 1)

    # ------------------------------------------------------------------
    # Fix 8: Emergency tree-removal evidence bypasses
    # ------------------------------------------------------------------
    def test_08_emergency_detail_path_blocked_without_verified_evidence(self):
        with patch.object(rag_engine, "_has_verified_emergency_tree_evidence", return_value=False):
            res = rag_engine.answer_query(
                "Is a dead tree an emergency?",
                department_id="engineering",
                history=[],
            )
        self.assertFalse(res.grounded)
        self.assertNotIn("concurrently", res.answer.lower())
        self.assertIn("could not verify", res.answer.lower())

    def test_08b_upfront_flow_emergency_path_blocked_without_verified_evidence(self):
        with patch("backend.app.main.rate_limiter.check_rate_limit", return_value=(True, 1)):
            with patch.object(rag_engine, "_has_verified_emergency_tree_evidence", return_value=False):
                resp = chat_endpoint(
                    ChatRequest(session_id="audit_emerg_upfront", message="My dead tree is falling and an emergency"),
                    request=None,
                )
        self.assertEqual(resp.mode, "rag")
        self.assertIsNone(resp.form_packet)
        self.assertIn("could not verify", resp.message.lower())

    # ------------------------------------------------------------------
    # Fix 9: Incorrect _build_form_packet argument in chat_endpoint
    # ------------------------------------------------------------------
    def test_09_start_flow_fallback_passes_flow_session_to_build_form_packet(self):
        fake_step = FlowStep(
            id="step_custom_form",
            type="form_issuance",
            title="Test Engineering Form",
            message="Download your form below.",
            form_code="TEST-1",
            form_title="Test Engineering Form",
            form_file="3.23.21 tree permit application.pdf",
        )
        fake_flow = MagicMock()
        fake_flow.steps = {"step_custom_form": fake_step}
        fake_sess = FlowSession("audit_pkt_sess", "engineering", "tree_removal_flow")
        fake_sess.current_step_id = "step_custom_form"
        fake_sess.completed = True

        with patch("backend.app.main.rate_limiter.check_rate_limit", return_value=(True, 1)):
            with patch("backend.app.main.rag_engine.match_official_form_packet", return_value=None):
                with patch("backend.app.main.rag_engine.detect_flow_intent", return_value=("engineering", "tree_removal_flow")):
                    with patch("backend.app.main.flow_engine.start_flow", return_value=(True, "ok", fake_step, None)):
                        with patch("backend.app.main.flow_engine.get_session", side_effect=[None, fake_sess]):
                            with patch("backend.app.main.registry.get_flow", return_value=fake_flow):
                                resp = chat_endpoint(
                                    ChatRequest(session_id="audit_pkt_sess", message="I want to remove a tree"),
                                    request=None,
                                )
        self.assertEqual(resp.mode, "flow")
        self.assertIsNotNone(resp.form_packet)
        self.assertIn("3.23.21%20tree%20permit%20application.pdf", resp.form_packet.pdf_download_url)


class TestRawRetrievalAndWorkflowInterruption(unittest.TestCase):
    def test_10_no_raw_metadata_and_no_plot_grading_in_tree_removal_rag(self):
        raw_tree = RagCitation(
            url="https://www.edisonnj.org/document_center/3.23.21%20tree%20permit%20application.pdf?t=202409111411050",
            title="Tree Removal Permit Application",
            category="Application Form",
            department_id="engineering",
            relevance_score=0.92,
            excerpt=(
                "DOCUMENT: Tree Removal Permit Application  MUNICIPALITY: Township of Edison, New Jersey  "
                "DEPARTMENT: Engineering & Zoning  DOCUMENT TYPE: Application form  SERVICE: tree_removal  "
                "OFFICIAL URL: https://www.edisonnj.org/document_center/3.23.21%20tree%20permit%20application.pdf  "
                "SUBMISSION INTAKE: Division of Engineering  FEE STRUCTURE: $25"
            ),
            visibility="public",
            service="tree_removal",
        )
        raw_tree_dup = RagCitation(
            url="https://www.edisonnj.org/document_center/3.23.21%20tree%20permit%20application.pdf",
            title="Tree Removal Permit Application",
            category="Application Form",
            department_id="engineering",
            relevance_score=0.88,
            excerpt="DOCUMENT: Tree Removal Permit Application  FEE STRUCTURE: $25",
            visibility="public",
            service="tree_removal",
        )
        plot_grading = RagCitation(
            url="https://www.edisonnj.org/document_center/Requirments_for_plot_grading_plans.pdf",
            title="Requirements for Plot Grading Plans – Minor Development",
            category="Engineering",
            department_id="engineering",
            relevance_score=0.85,
            excerpt="Plot grading plan requirements for minor development.",
            visibility="public",
            service="plot_grading",
        )
        with patch.object(vector_store, "search", return_value=[raw_tree, raw_tree_dup, plot_grading]):
            with patch("backend.app.llm_client.llm_manager.generate", return_value=LLMResponse(success=False, content="", error="offline", provider="none", model="none")):
                res = rag_engine.answer_query("I want to remove a tree from my residential property in Edison. What should I do?", department_id="engineering", history=[])
        for forbidden in ["DOCUMENT:", "MUNICIPALITY:", "SUBMISSION INTAKE:", "FEE STRUCTURE:", "Plot Grading"]:
            self.assertNotIn(forbidden, res.answer)
        self.assertEqual(len(res.citations), 1)
        self.assertNotIn("Plot Grading", res.citations[0].title)

    def test_11_active_workflow_answers_application_request_and_preserves_state(self):
        sid = "audit_tree_interruption_1"
        with patch("backend.app.main.rate_limiter.check_rate_limit", return_value=(True, 1)):
            r1 = chat_endpoint(ChatRequest(session_id=sid, message="I want to remove a tree from my residential property in Edison. What should I do?"), request=None)
            self.assertEqual(r1.current_step.id, "step_removing_trees_check")

            r2 = chat_endpoint(ChatRequest(session_id=sid, message="Yes, I am planning to remove one or more trees."), request=None)
            self.assertEqual(r2.current_step.id, "step_emergency_check")

            # Interruption: ask for the application during active flow
            r3 = chat_endpoint(ChatRequest(session_id=sid, message="Where can I get the official Tree Removal Permit Application?"), request=None)
            self.assertIsNotNone(r3.form_packet)
            self.assertIn("3.23.21%20tree%20permit%20application.pdf", r3.form_packet.pdf_download_url)
            self.assertEqual(r3.current_step.id, "step_emergency_check")
            self.assertFalse(r3.completed)

            # Continue workflow: answer emergency question
            r4 = chat_endpoint(ChatRequest(session_id=sid, message="Yes, it is an emergency (dead, dying, or imminent danger)."), request=None)
            self.assertEqual(r4.current_step.id, "step_emergency_protocol_result")
            self.assertNotIn("$25.00", r4.form_packet.fee_info.amount)
            self.assertNotIn("$200", r4.form_packet.fee_info.amount)

    def test_12_active_workflow_answers_fee_question_and_preserves_state(self):
        sid = "audit_tree_fee_interrupt"
        with patch("backend.app.main.rate_limiter.check_rate_limit", return_value=(True, 1)):
            with patch("backend.app.llm_client.llm_manager.generate", return_value=LLMResponse(success=False, content="", error="offline", provider="none", model="none")):
                chat_endpoint(ChatRequest(session_id=sid, message="I need to remove a tree"), request=None)
                r_fee = chat_endpoint(ChatRequest(session_id=sid, message="What is the application fee?"), request=None)
        self.assertEqual(r_fee.current_step.id, "step_removing_trees_check")
        self.assertFalse(r_fee.completed)

    def test_13_missing_official_evidence_returns_honest_limitation(self):
        with patch.object(vector_store, "search", return_value=[]):
            res = rag_engine.answer_query("What is the fee for removing a tree?", department_id="engineering", history=[])
        self.assertFalse(res.grounded)
        self.assertEqual(res.citations, [])
        self.assertIn("could not verify", res.answer.lower())

    def test_14_three_trees_question_does_not_guess_application_count(self):
        # Without explicit official evidence about application count -> grounded=False, honest limitation + form preview
        res = rag_engine.answer_query("I am removing three trees. Do I need three separate applications?", department_id="engineering", history=[])
        self.assertFalse(res.grounded)
        self.assertEqual(res.citations, [])
        self.assertIn("could not verify", res.answer.lower())
        self.assertNotIn("three separate applications are required", res.answer.lower())
        self.assertNotIn("one application covers all", res.answer.lower())
        self.assertIsNotNone(res.form_packet)
        self.assertEqual(res.form_packet.form_file, "3.23.21 tree permit application.pdf")

    def test_14b_three_trees_with_explicit_official_evidence(self):
        explicit_cit = RagCitation(
            url="https://www.edisonnj.org/document_center/3.23.21%20tree%20permit%20application.pdf?t=202409111411050",
            title="Tree Removal Permit Application",
            category="Application Form",
            department_id="engineering",
            relevance_score=0.95,
            excerpt="One application may list multiple trees on the same residential parcel; specify the number of trees to be removed.",
            visibility="public",
            service="tree_removal",
        )
        with patch.object(vector_store, "search", return_value=[explicit_cit]):
            with patch("backend.app.llm_client.llm_manager.generate", return_value=LLMResponse(success=False, content="", error="offline", provider="none", model="none")):
                res = rag_engine.answer_query("I am removing three trees. Do I need three separate applications?", department_id="engineering", history=[])
        self.assertTrue(res.grounded)
        self.assertEqual(len(res.citations), 1)
        self.assertIn("one application", res.answer.lower())
        self.assertIsNotNone(res.form_packet)

    def test_14c_three_trees_during_active_workflow_preserves_step(self):
        sid = "audit_three_trees_active_flow"
        r1 = chat_endpoint(ChatRequest(session_id=sid, message="I want to remove a tree from my residential property."), request=None)
        self.assertEqual(r1.current_step.id, "step_removing_trees_check")

        r2 = chat_endpoint(ChatRequest(session_id=sid, message="I am removing three trees. Do I need three separate applications?"), request=None)
        self.assertEqual(r2.mode, "flow")
        self.assertEqual(r2.current_step.id, "step_removing_trees_check")
        self.assertFalse(r2.completed)
        self.assertIn("could not verify", r2.message.lower())
        self.assertIsNotNone(r2.form_packet)
        self.assertEqual(r2.form_packet.form_file, "3.23.21 tree permit application.pdf")

    def test_15_emergency_definition_uses_permit_flow_charts_evidence(self):
        with patch("backend.app.llm_client.llm_manager.generate", return_value=LLMResponse(success=False, content="", error="offline", provider="none", model="none")):
            res = rag_engine.answer_query("What qualifies as an emergency?", department_id="engineering", history=[])
        self.assertTrue(res.grounded)
        self.assertTrue(any("permit_flow_charts" in c.url.lower() or "permit%20flow%20charts" in c.url.lower() for c in res.citations))

    def test_16_unrelated_to_engineering_refused_without_plot_grading_leak(self):
        with patch("backend.app.main.rate_limiter.check_rate_limit", return_value=(True, 1)):
            resp = chat_endpoint(ChatRequest(session_id="audit_unrelated_1", message="Can you tell me something unrelated to Engineering?"), request=None)
        self.assertEqual(resp.mode, "rag")
        self.assertIn("out of our context", resp.message.lower())
        self.assertEqual(resp.citations, [])

    def test_17_generic_fee_question_without_service_does_not_leak_flood_zone(self):
        with patch("backend.app.main.rate_limiter.check_rate_limit", return_value=(True, 1)):
            resp = chat_endpoint(ChatRequest(session_id="audit_generic_fee_1", message="What is the current filing fee?"), request=None)
        self.assertEqual(resp.citations, [])
        self.assertIn("which edison township engineering permit", resp.message.lower())
        self.assertNotIn("flood_zone_determination_letter", resp.message.lower())

    def test_18_soil_import_and_road_opening_grounding(self):
        with patch("backend.app.llm_client.llm_manager.generate", return_value=LLMResponse(success=False, content="", error="offline", provider="none", model="none")) as mock_gen:
            soil_res = rag_engine.answer_query("What are the requirements for soil import?", department_id="engineering", history=[])
            road_res = rag_engine.answer_query("What are the requirements for a road opening permit?", department_id="engineering", history=[])
        self.assertEqual(mock_gen.call_count, 2)
        self.assertTrue(soil_res.grounded)
        self.assertTrue(any("soil" in c.title.lower() for c in soil_res.citations))

        self.assertTrue(road_res.grounded)
        self.assertGreater(len(road_res.citations), 0)
        self.assertNotIn("$150", road_res.answer)
        self.assertNotIn("$5,000", road_res.answer)
        self.assertTrue(any("roadopenapp" in c.url.lower() or "permit%20flow%20charts" in c.url.lower() for c in road_res.citations))

    def test_18b_road_opening_without_evidence_returns_unverified(self):
        with patch.object(vector_store, "search", return_value=[]):
            road_res = rag_engine.answer_query("What are the requirements for a road opening permit?", department_id="engineering", history=[])
        self.assertFalse(road_res.grounded)
        self.assertEqual(road_res.citations, [])
        self.assertIn("could not verify", road_res.answer.lower())

    def test_19_gemini_groq_fallback_and_transparent_offline_fallback(self):
        cit = RagCitation(
            url="https://www.edisonnj.org/document_center/Forms_Soil_Importation_Appl.pdf",
            title="Soil Importation Permit Application",
            category="Application Form",
            department_id="engineering",
            relevance_score=0.9,
            excerpt="Subsection 32-2.3 soil importation application fee is $200.00.",
            visibility="public",
            service="soil_import",
        )
        with patch.object(vector_store, "search", return_value=[cit]):
            with patch.object(llm_manager.providers["gemini"], "is_available", return_value=True):
                with patch.object(llm_manager.providers["gemini"], "generate", return_value=LLMResponse(success=False, content="", error="429", provider="gemini", model="gemini-3.8-flash")):
                    with patch.object(llm_manager.providers["groq"], "is_available", return_value=True):
                        with patch.object(llm_manager.providers["groq"], "generate", return_value=LLMResponse(success=True, content="Per Soil Importation Permit Application, the fee is $200.00.", provider="groq", model="qwen/qwen3.8-27b")):
                            res = rag_engine.answer_query("What is the soil import fee?", department_id="engineering", history=[])
        self.assertTrue(res.grounded)
        self.assertIn("$200.00", res.answer)

    def test_20_root_dotenv_loading_and_env_precedence(self):
        import os
        from dotenv import load_dotenv
        from backend.app.llm_provider.gemini import GeminiProvider
        from backend.app.llm_provider.groq import GroqProvider

        tmp_dir = Path(tempfile.mkdtemp())
        try:
            fake_env = tmp_dir / ".env"
            fake_env.write_text(
                "CIVICIQ_TEST_DOTENV_ONLY=from_dotenv_file_123\n"
                "CIVICIQ_TEST_PRECEDENCE=from_dotenv_file_override_attempt\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"CIVICIQ_TEST_PRECEDENCE": "from_render_env"}, clear=False):
                os.environ.pop("CIVICIQ_TEST_DOTENV_ONLY", None)
                load_dotenv(dotenv_path=fake_env, override=False)
                self.assertEqual(os.environ.get("CIVICIQ_TEST_DOTENV_ONLY"), "from_dotenv_file_123")
                self.assertEqual(os.environ.get("CIVICIQ_TEST_PRECEDENCE"), "from_render_env")
        finally:
            os.environ.pop("CIVICIQ_TEST_DOTENV_ONLY", None)
            shutil.rmtree(tmp_dir, ignore_errors=True)

        self.assertTrue(GeminiProvider(api_key="test-key-valid-12345").is_available())
        self.assertTrue(GroqProvider(api_key="test-key-valid-12345").is_available())
        self.assertFalse(GeminiProvider(api_key="").is_available())
        self.assertFalse(GroqProvider(api_key="short").is_available())

    def test_21_gemini_sdk_receives_timeout_and_falls_back_on_timeout(self):
        import requests
        from backend.app.llm_provider.gemini import GeminiProvider

        provider = GeminiProvider(api_key="test-key-valid-12345", timeout_seconds=17, max_retries=0)
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = requests.Timeout("SDK timed out")

        with patch("google.generativeai.configure") as mock_configure:
            with patch("google.generativeai.GenerativeModel", return_value=mock_model):
                with patch("backend.app.llm_provider.gemini.requests.post", side_effect=requests.Timeout("REST timed out")) as mock_post:
                    resp = provider.generate(prompt="Test prompt", system_prompt="System")

        mock_configure.assert_called_once_with(api_key="test-key-valid-12345", transport="rest")
        mock_model.generate_content.assert_called_once()
        mock_post.assert_called_once()
        _, kwargs = mock_model.generate_content.call_args
        req_opts = kwargs.get("request_options", {})
        self.assertIsNone(req_opts.get("retry"))
        self.assertIn("retry", req_opts)
        self.assertGreater(req_opts.get("timeout", 0), 0)
        self.assertLessEqual(req_opts.get("timeout", 999), 17.0)
        self.assertFalse(resp.success)
        self.assertIn("timed out", resp.error.lower())

        # Verify LLMProviderManager falls back Gemini -> Groq on Gemini timeout
        with patch.object(llm_manager.providers["gemini"], "is_available", return_value=True):
            with patch.object(llm_manager.providers["gemini"], "generate", return_value=resp):
                with patch.object(llm_manager.providers["groq"], "is_available", return_value=True):
                    with patch.object(
                        llm_manager.providers["groq"],
                        "generate",
                        return_value=LLMResponse(content="Groq fallback ok", provider="groq", model="qwen/qwen3.8-27b", success=True),
                    ):
                        mgr_resp = llm_manager.generate(prompt="Test prompt", system_prompt="System")
        self.assertTrue(mgr_resp.success)
        self.assertEqual(mgr_resp.provider, "groq")
        self.assertTrue(mgr_resp.is_fallback)

    def test_22_offline_llm_helper_blocks_real_sdk_calls(self):
        from backend.tests.offline_llm_helper import OfflineLLMTestCase

        class _SampleAppTest(OfflineLLMTestCase):
            def runTest(self):
                pass

        _SampleAppTest.setUpClass()
        try:
            with patch("google.generativeai.GenerativeModel", side_effect=AssertionError("Real Gemini SDK must not be called")):
                with patch("openai.OpenAI", side_effect=AssertionError("Real Groq/OpenAI SDK must not be called")):
                    res = rag_engine.answer_query("What are the setback distances?", department_id="engineering", history=[])
            self.assertTrue(res.grounded)
        finally:
            _SampleAppTest.tearDownClass()

    def test_23_gemini_successful_response_uses_rest_and_no_sdk_retry(self):
        from backend.app.llm_provider.gemini import GeminiProvider

        provider = GeminiProvider(api_key="test-key-valid-12345", timeout_seconds=15, max_retries=2)
        mock_model = MagicMock()
        mock_model.generate_content.return_value = MagicMock(text="  Emergency removal covers immediate hazards.  ")

        with patch("google.generativeai.configure") as mock_configure:
            with patch("google.generativeai.GenerativeModel", return_value=mock_model):
                with patch("backend.app.llm_provider.gemini.requests.post") as mock_post:
                    resp = provider.generate(prompt="What is emergency tree removal?", system_prompt="System")

        mock_configure.assert_called_once_with(api_key="test-key-valid-12345", transport="rest")
        mock_model.generate_content.assert_called_once()
        mock_post.assert_not_called()
        _, kwargs = mock_model.generate_content.call_args
        req_opts = kwargs.get("request_options", {})
        self.assertIn("retry", req_opts)
        self.assertIsNone(req_opts["retry"])
        self.assertTrue(resp.success)
        self.assertEqual(resp.provider, "gemini")
        self.assertEqual(resp.model, "gemini-3.8-flash")
        self.assertEqual(resp.content, "Emergency removal covers immediate hazards.")

    def test_24_gemini_deadline_prevents_rest_fallback_and_extra_retries(self):
        from backend.app.llm_provider.gemini import GeminiProvider

        provider = GeminiProvider(api_key="test-key-valid-12345", timeout_seconds=10, max_retries=2)
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = RuntimeError("SDK stalled")

        # Monotonic clock: deadline = 100 + 10 = 110; attempt 0 starts at 100, SDK finishes at 111 (expired)
        monotonic_values = iter([100.0, 100.0, 111.0, 111.0])
        with patch("backend.app.llm_provider.gemini.time.monotonic", side_effect=lambda: next(monotonic_values)):
            with patch("backend.app.llm_provider.gemini.time.sleep") as mock_sleep:
                with patch("google.generativeai.configure"):
                    with patch("google.generativeai.GenerativeModel", return_value=mock_model):
                        with patch("backend.app.llm_provider.gemini.requests.post") as mock_post:
                            resp = provider.generate(prompt="Test", system_prompt="System")

        self.assertFalse(resp.success)
        self.assertIn("timed out", resp.error.lower())
        mock_model.generate_content.assert_called_once()
        mock_post.assert_not_called()
        mock_sleep.assert_not_called()

    def test_25_both_providers_failing_allows_deterministic_fallback(self):
        cit = RagCitation(
            url="https://www.edisonnj.org/document_center/Forms_Soil_Importation_Appl.pdf",
            title="Soil Importation Permit Application",
            category="Application Form",
            department_id="engineering",
            relevance_score=0.9,
            excerpt="Subsection 32-2.3 soil importation application fee is $200.00.",
            visibility="public",
            service="soil_import",
        )
        failed_gemini = LLMResponse(success=False, content="", error="Gemini timed out", provider="gemini", model="gemini-3.8-flash")
        failed_groq = LLMResponse(success=False, content="", error="Groq timed out", provider="groq", model="qwen/qwen3.8-27b")

        with patch.object(llm_manager.providers["gemini"], "is_available", return_value=True):
            with patch.object(llm_manager.providers["gemini"], "generate", return_value=failed_gemini):
                with patch.object(llm_manager.providers["groq"], "is_available", return_value=True):
                    with patch.object(llm_manager.providers["groq"], "generate", return_value=failed_groq):
                        mgr_resp = llm_manager.generate(prompt="Test", system_prompt="System")
                        self.assertFalse(mgr_resp.success)

                        with patch.object(vector_store, "search", return_value=[cit]):
                            rag_res = rag_engine.answer_query("What is the soil import fee?", department_id="engineering", history=[])
        self.assertTrue(rag_res.grounded)
        self.assertIn("$200.00", rag_res.answer)

    def test_26_gemini_diagnostics_connect_and_read_timeout_sanitized(self):
        import requests
        from backend.app.llm_provider.gemini import GeminiProvider

        secret_key = "AIzaTestSecretKey987654321"
        resident_prompt = "My name is Jane Doe at 123 Main St removing 3 trees"
        provider = GeminiProvider(api_key=secret_key, timeout_seconds=15, max_retries=0)
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = RuntimeError(
            f"POST https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key={secret_key} failed"
        )

        # ConnectTimeout case
        with self.assertLogs("llm_provider.gemini", level="INFO") as cm_conn:
            with patch("google.generativeai.configure"):
                with patch("google.generativeai.GenerativeModel", return_value=mock_model):
                    with patch(
                        "backend.app.llm_provider.gemini.requests.post",
                        side_effect=requests.ConnectTimeout(f"Connect timed out for key={secret_key}"),
                    ):
                        resp_conn = provider.generate(prompt=resident_prompt, system_prompt="System")

        self.assertFalse(resp_conn.success)
        self.assertIn("connect timed out", resp_conn.error.lower())
        conn_logs = "\n".join(cm_conn.output)
        self.assertIn("stage=connect_timeout", conn_logs)
        self.assertIn("error_type=ConnectTimeout", conn_logs)
        self.assertIn("attempts_executed=1", conn_logs)
        self.assertNotIn(secret_key, conn_logs)
        self.assertNotIn("Jane Doe", conn_logs)
        self.assertNotIn("123 Main St", conn_logs)

        # ReadTimeout case
        with self.assertLogs("llm_provider.gemini", level="INFO") as cm_read:
            with patch("google.generativeai.configure"):
                with patch("google.generativeai.GenerativeModel", return_value=mock_model):
                    with patch(
                        "backend.app.llm_provider.gemini.requests.post",
                        side_effect=requests.ReadTimeout(f"Read timed out for key={secret_key}"),
                    ):
                        resp_read = provider.generate(prompt=resident_prompt, system_prompt="System")

        self.assertFalse(resp_read.success)
        self.assertIn("read timed out", resp_read.error.lower())
        read_logs = "\n".join(cm_read.output)
        self.assertIn("stage=read_timeout", read_logs)
        self.assertIn("error_type=ReadTimeout", read_logs)
        self.assertNotIn(secret_key, read_logs)
        self.assertNotIn("Jane Doe", read_logs)

    def test_27_gemini_diagnostics_sdk_failure_then_rest_success(self):
        from backend.app.llm_provider.gemini import GeminiProvider

        secret_key = "AIzaTestSecretKey987654321"
        provider = GeminiProvider(api_key=secret_key, timeout_seconds=15, max_retries=0)
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = RuntimeError("SDK failed")
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "REST fallback succeeded."}]}}]
        }

        with self.assertLogs("llm_provider.gemini", level="INFO") as cm:
            with patch("google.generativeai.configure"):
                with patch("google.generativeai.GenerativeModel", return_value=mock_model):
                    with patch("backend.app.llm_provider.gemini.requests.post", return_value=mock_resp):
                        resp = provider.generate(prompt="Test prompt", system_prompt="System")

        self.assertTrue(resp.success)
        self.assertEqual(resp.content, "REST fallback succeeded.")
        logs = "\n".join(cm.output)
        self.assertIn("event=sdk_start", logs)
        self.assertIn("event=sdk_failure", logs)
        self.assertIn("event=rest_start", logs)
        self.assertIn("event=rest_success", logs)
        self.assertIn("status=200", logs)
        self.assertNotIn(secret_key, logs)
        self.assertNotIn("Test prompt", logs)

    def test_28_gemini_diagnostics_deadline_exhaustion_actual_attempts(self):
        from backend.app.llm_provider.gemini import GeminiProvider

        provider = GeminiProvider(api_key="test-key-valid-12345", timeout_seconds=10, max_retries=2)
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = RuntimeError("SDK stalled")

        monotonic_values = iter([100.0, 100.0, 111.0])
        with self.assertLogs("llm_provider.gemini", level="INFO") as cm:
            with patch("backend.app.llm_provider.gemini.time.monotonic", side_effect=lambda: next(monotonic_values)):
                with patch("google.generativeai.configure"):
                    with patch("google.generativeai.GenerativeModel", return_value=mock_model):
                        with patch("backend.app.llm_provider.gemini.requests.post") as mock_post:
                            resp = provider.generate(prompt="Test", system_prompt="System")

        self.assertFalse(resp.success)
        mock_post.assert_not_called()
        logs = "\n".join(cm.output)
        self.assertIn("event=provider_failed", logs)
        self.assertIn("attempts_executed=1", logs)
        self.assertIn("max_attempts=3", logs)
        self.assertIn("remaining_s=0.000", logs)

    def test_29_gemini_http_429_and_5xx_diagnostics_header_auth(self):
        from backend.app.llm_provider.gemini import GeminiProvider

        secret_key = "AIzaTestSecretKey987654321"
        provider = GeminiProvider(api_key=secret_key, timeout_seconds=15, max_retries=0)
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = RuntimeError("SDK failed")

        for status_code, body_text in [(429, "RATE_LIMIT_RAW_BODY_SECRET"), (503, "BACKEND_503_RAW_BODY_SECRET")]:
            mock_resp = MagicMock(status_code=status_code, text=body_text)
            with self.assertLogs("llm_provider.gemini", level="INFO") as cm:
                with patch("google.generativeai.configure"):
                    with patch("google.generativeai.GenerativeModel", return_value=mock_model):
                        with patch("backend.app.llm_provider.gemini.requests.post", return_value=mock_resp) as mock_post:
                            resp = provider.generate(prompt="Test prompt", system_prompt="System")

            self.assertFalse(resp.success)
            self.assertIn(str(status_code), resp.error)
            self.assertNotIn(body_text, resp.error)

            called_url = mock_post.call_args.args[0]
            called_kwargs = mock_post.call_args.kwargs
            self.assertNotIn("key=", called_url)
            self.assertNotIn(secret_key, called_url)
            self.assertEqual(called_kwargs.get("headers", {}).get("x-goog-api-key"), secret_key)
            self.assertIsInstance(called_kwargs.get("timeout"), tuple)
            self.assertEqual(len(called_kwargs.get("timeout")), 2)

            logs = "\n".join(cm.output)
            self.assertIn(f"stage=http_error status={status_code}", logs)
            self.assertNotIn(body_text, logs)
            self.assertNotIn(secret_key, logs)

    def test_30_gemini_error_truncation_and_sanitization(self):
        from backend.app.llm_provider.gemini import GeminiProvider

        secret_key = "AIzaTestSecretKey987654321"
        provider = GeminiProvider(api_key=secret_key, timeout_seconds=15, max_retries=0)
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = RuntimeError("SDK failed")
        long_err = f"Unexpected failure at https://example.com?key={secret_key} " + ("X" * 300)

        with self.assertLogs("llm_provider.gemini", level="INFO") as cm:
            with patch("google.generativeai.configure"):
                with patch("google.generativeai.GenerativeModel", return_value=mock_model):
                    with patch("backend.app.llm_provider.gemini.requests.post", side_effect=RuntimeError(long_err)):
                        resp = provider.generate(prompt="Test", system_prompt="System")

        self.assertFalse(resp.success)
        self.assertNotIn(secret_key, resp.error)
        self.assertLessEqual(len(resp.error), 190)
        self.assertTrue(resp.error.endswith("..."))
        logs = "\n".join(cm.output)
        self.assertNotIn(secret_key, logs)
        self.assertIn("[REDACTED]", logs)

    def test_31_gemini_retry_within_deadline_and_skip_short_backoff(self):
        from backend.app.llm_provider.gemini import GeminiProvider

        provider = GeminiProvider(api_key="test-key-valid-12345", timeout_seconds=10, max_retries=2)
        mock_model = MagicMock()
        # Attempt 1 fails, attempt 2 succeeds
        mock_model.generate_content.side_effect = [
            RuntimeError("Transient SDK error"),
            MagicMock(text="Recovered on attempt 2."),
        ]
        mock_resp_503 = MagicMock(status_code=503, text="Unavailable")

        # start=100 (deadline=110), attempt1=100, after_sdk1=101, after_rest1=102, backoff_check=102 (rem=8 > 1), attempt2=103, after_sdk2=104
        monotonic_values = iter([100.0, 100.0, 101.0, 102.0, 102.0, 103.0, 104.0])
        with self.assertLogs("llm_provider.gemini", level="INFO") as cm:
            with patch("backend.app.llm_provider.gemini.time.monotonic", side_effect=lambda: next(monotonic_values)):
                with patch("backend.app.llm_provider.gemini.time.sleep") as mock_sleep:
                    with patch("google.generativeai.configure"):
                        with patch("google.generativeai.GenerativeModel", return_value=mock_model):
                            with patch("backend.app.llm_provider.gemini.requests.post", return_value=mock_resp_503):
                                resp = provider.generate(prompt="Test", system_prompt="System")

        self.assertTrue(resp.success)
        self.assertEqual(resp.content, "Recovered on attempt 2.")
        mock_sleep.assert_called_once_with(1.0)
        logs = "\n".join(cm.output)
        self.assertIn("event=sdk_success model=gemini-3.8-flash attempt=2", logs)

        # Now verify short remaining (< backoff=1.0) skips sleep and breaks without starting attempt 2
        mock_model2 = MagicMock()
        mock_model2.generate_content.side_effect = RuntimeError("SDK error")
        # start=200 (deadline=210), attempt1=200, after_sdk1=205, after_rest1=209.5, backoff_check=209.5 (rem=0.5 <= 1.0 -> break)
        monotonic_short = iter([200.0, 200.0, 205.0, 209.5, 209.5])
        with self.assertLogs("llm_provider.gemini", level="INFO") as cm2:
            with patch("backend.app.llm_provider.gemini.time.monotonic", side_effect=lambda: next(monotonic_short)):
                with patch("backend.app.llm_provider.gemini.time.sleep") as mock_sleep2:
                    with patch("google.generativeai.configure"):
                        with patch("google.generativeai.GenerativeModel", return_value=mock_model2):
                            with patch("backend.app.llm_provider.gemini.requests.post", return_value=mock_resp_503):
                                resp2 = provider.generate(prompt="Test", system_prompt="System")

        self.assertFalse(resp2.success)
        mock_sleep2.assert_not_called()
        self.assertIn("attempts_executed=1", "\n".join(cm2.output))

    def test_32_gemini_sdk_empty_response_falls_back_to_rest(self):
        from backend.app.llm_provider.gemini import GeminiProvider

        provider = GeminiProvider(api_key="test-key-valid-12345", timeout_seconds=15, max_retries=0)
        mock_model = MagicMock()
        mock_model.generate_content.return_value = MagicMock(text="")
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "REST answered after empty SDK."}]}}]
        }

        with self.assertLogs("llm_provider.gemini", level="INFO") as cm:
            with patch("google.generativeai.configure"):
                with patch("google.generativeai.GenerativeModel", return_value=mock_model):
                    with patch("backend.app.llm_provider.gemini.requests.post", return_value=mock_resp) as mock_post:
                        resp = provider.generate(prompt="Test", system_prompt="System")

        self.assertTrue(resp.success)
        self.assertEqual(resp.content, "REST answered after empty SDK.")
        mock_post.assert_called_once()
        logs = "\n".join(cm.output)
        self.assertIn("stage=empty_response", logs)
        self.assertIn("event=rest_success", logs)

    def test_33_gemini_sdk_429_no_rest_no_retry_and_groq_fallback(self):
        import google.api_core.exceptions as gexc
        from backend.app.llm_provider.gemini import GeminiProvider

        provider = GeminiProvider(api_key="test-key-valid-12345", timeout_seconds=30, max_retries=2)
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = gexc.TooManyRequests("Quota exceeded")

        with self.assertLogs("llm_provider.gemini", level="INFO") as cm:
            with patch("backend.app.llm_provider.gemini.time.sleep") as mock_sleep:
                with patch("google.generativeai.configure"):
                    with patch("google.generativeai.GenerativeModel", return_value=mock_model):
                        with patch("backend.app.llm_provider.gemini.requests.post") as mock_post:
                            resp = provider.generate(prompt="Test", system_prompt="System")

        self.assertFalse(resp.success)
        self.assertIn("429", resp.error)
        mock_model.generate_content.assert_called_once()
        mock_post.assert_not_called()
        mock_sleep.assert_not_called()
        logs = "\n".join(cm.output)
        self.assertIn("stage=http_error status=429", logs)
        self.assertIn("attempts_executed=1", logs)

        # Gemini 429 -> Groq fallback
        with patch.object(llm_manager.providers["gemini"], "is_available", return_value=True):
            with patch.object(llm_manager.providers["gemini"], "generate", return_value=resp):
                with patch.object(llm_manager.providers["groq"], "is_available", return_value=True):
                    with patch.object(
                        llm_manager.providers["groq"],
                        "generate",
                        return_value=LLMResponse(content="Groq ok", provider="groq", model="qwen/qwen3.8-27b", success=True),
                    ):
                        mgr_resp = llm_manager.generate(prompt="Test", system_prompt="System")
        self.assertTrue(mgr_resp.success)
        self.assertEqual(mgr_resp.provider, "groq")

    def test_34_gemini_sdk_503_no_rest_duplicate_and_at_most_one_retry(self):
        import google.api_core.exceptions as gexc
        from backend.app.llm_provider.gemini import GeminiProvider

        provider = GeminiProvider(api_key="test-key-valid-12345", timeout_seconds=30, max_retries=2)
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = gexc.ServiceUnavailable("Backend overloaded")

        with self.assertLogs("llm_provider.gemini", level="INFO") as cm:
            with patch("backend.app.llm_provider.gemini.time.sleep") as mock_sleep:
                with patch("google.generativeai.configure"):
                    with patch("google.generativeai.GenerativeModel", return_value=mock_model):
                        with patch("backend.app.llm_provider.gemini.requests.post") as mock_post:
                            resp = provider.generate(prompt="Test", system_prompt="System")

        self.assertFalse(resp.success)
        self.assertIn("503", resp.error)
        self.assertEqual(mock_model.generate_content.call_count, 2)
        mock_post.assert_not_called()
        mock_sleep.assert_called_once()
        logs = "\n".join(cm.output)
        self.assertIn("attempts_executed=2", logs)
        self.assertIn("stage=http_error status=503", logs)

    def test_35_gemini_sdk_400_403_404_no_rest_fallback(self):
        import google.api_core.exceptions as gexc
        from backend.app.llm_provider.gemini import GeminiProvider

        provider = GeminiProvider(api_key="test-key-valid-12345", timeout_seconds=30, max_retries=2)
        for exc_cls, expected_status in [
            (gexc.BadRequest, 400),
            (gexc.PermissionDenied, 403),
            (gexc.NotFound, 404),
        ]:
            mock_model = MagicMock()
            mock_model.generate_content.side_effect = exc_cls("API error")
            with self.assertLogs("llm_provider.gemini", level="INFO") as cm:
                with patch("backend.app.llm_provider.gemini.time.sleep") as mock_sleep:
                    with patch("google.generativeai.configure"):
                        with patch("google.generativeai.GenerativeModel", return_value=mock_model):
                            with patch("backend.app.llm_provider.gemini.requests.post") as mock_post:
                                resp = provider.generate(prompt="Test", system_prompt="System")

            self.assertFalse(resp.success)
            self.assertIn(str(expected_status), resp.error)
            mock_model.generate_content.assert_called_once()
            mock_post.assert_not_called()
            mock_sleep.assert_not_called()
            self.assertIn(f"stage=http_error status={expected_status}", "\n".join(cm.output))
            self.assertIn("attempts_executed=1", "\n".join(cm.output))

    def test_36_gemini_transport_failure_and_sdk_unavailable_use_rest_fallback(self):
        import builtins
        import requests
        from backend.app.llm_provider.gemini import GeminiProvider

        provider = GeminiProvider(api_key="test-key-valid-12345", timeout_seconds=15, max_retries=0)
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "REST succeeded."}]}}]
        }

        # 1. Transport failure in SDK -> REST fallback succeeds
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = requests.ConnectionError("Socket reset before response")
        with patch("google.generativeai.configure"):
            with patch("google.generativeai.GenerativeModel", return_value=mock_model):
                with patch("backend.app.llm_provider.gemini.requests.post", return_value=mock_resp) as mock_post:
                    resp_transport = provider.generate(prompt="Test", system_prompt="System")
        self.assertTrue(resp_transport.success)
        mock_post.assert_called_once()

        # 2. SDK unavailable (ImportError) -> REST fallback succeeds
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "google.generativeai":
                raise ImportError("No module named google.generativeai")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            with patch("backend.app.llm_provider.gemini.requests.post", return_value=mock_resp) as mock_post2:
                resp_import = provider.generate(prompt="Test", system_prompt="System")
        self.assertTrue(resp_import.success)
        mock_post2.assert_called_once()

    def test_37_gemini_retry_after_respected_and_cannot_exceed_deadline(self):
        import google.api_core.exceptions as gexc
        from backend.app.llm_provider.gemini import GeminiProvider

        provider = GeminiProvider(api_key="test-key-valid-12345", timeout_seconds=10, max_retries=2)

        # Case 1: Retry-After=2.5 fits inside 10s deadline
        exc_fit = gexc.ServiceUnavailable("503", response=MagicMock(headers={"Retry-After": "2.5"}))
        mock_model1 = MagicMock()
        mock_model1.generate_content.side_effect = [exc_fit, MagicMock(text="Recovered after Retry-After.")]
        with patch("backend.app.llm_provider.gemini.time.sleep") as mock_sleep1:
            with patch("google.generativeai.configure"):
                with patch("google.generativeai.GenerativeModel", return_value=mock_model1):
                    with patch("backend.app.llm_provider.gemini.requests.post") as mock_post1:
                        resp1 = provider.generate(prompt="Test", system_prompt="System")
        self.assertTrue(resp1.success)
        mock_sleep1.assert_called_once_with(2.5)
        mock_post1.assert_not_called()

        # Case 2: Retry-After=15 exceeds 10s deadline -> no sleep, no retry
        exc_too_long = gexc.ServiceUnavailable("503", response=MagicMock(headers={"Retry-After": "15"}))
        mock_model2 = MagicMock()
        mock_model2.generate_content.side_effect = exc_too_long
        with patch("backend.app.llm_provider.gemini.time.sleep") as mock_sleep2:
            with patch("google.generativeai.configure"):
                with patch("google.generativeai.GenerativeModel", return_value=mock_model2):
                    with patch("backend.app.llm_provider.gemini.requests.post") as mock_post2:
                        resp2 = provider.generate(prompt="Test", system_prompt="System")
        self.assertFalse(resp2.success)
        mock_sleep2.assert_not_called()
        mock_post2.assert_not_called()
        mock_model2.generate_content.assert_called_once()

    def test_38_gemini_consecutive_503_falls_back_to_groq(self):
        import google.api_core.exceptions as gexc
        from backend.app.llm_provider.gemini import GeminiProvider

        gemini_prov = GeminiProvider(api_key="test-key-valid-12345", timeout_seconds=30, max_retries=2)
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = [
            gexc.ServiceUnavailable("503 attempt 1"),
            gexc.ServiceUnavailable("503 attempt 2"),
        ]
        groq_model = llm_manager.providers["groq"].model

        with patch.dict(llm_manager.providers, {"gemini": gemini_prov}):
            with patch("backend.app.llm_provider.gemini.time.sleep") as mock_sleep:
                with patch("google.generativeai.configure"):
                    with patch("google.generativeai.GenerativeModel", return_value=mock_model):
                        with patch("backend.app.llm_provider.gemini.requests.post") as mock_post:
                            with patch.object(llm_manager.providers["groq"], "is_available", return_value=True):
                                with patch.object(
                                    llm_manager.providers["groq"],
                                    "generate",
                                    return_value=LLMResponse(
                                        content="Groq handled after 503",
                                        provider="groq",
                                        model=groq_model,
                                        success=True,
                                    ),
                                ) as mock_groq:
                                    mgr_resp = llm_manager.generate(prompt="Test", system_prompt="System")

        self.assertEqual(mock_model.generate_content.call_count, 2)
        mock_post.assert_not_called()
        mock_sleep.assert_called_once()
        mock_groq.assert_called_once()
        self.assertTrue(mgr_resp.success)
        self.assertTrue(mgr_resp.is_fallback)
        self.assertEqual(mgr_resp.provider, "groq")
        self.assertEqual(mgr_resp.model, groq_model)

    def test_39_gemini_rest_fallback_503_retry_then_success(self):
        import requests
        from backend.app.llm_provider.gemini import GeminiProvider

        provider = GeminiProvider(api_key="test-key-valid-12345", timeout_seconds=10, max_retries=2)
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = [
            requests.ConnectionError("Socket reset before response"),
            MagicMock(text="Recovered after REST 503."),
        ]
        mock_rest_503 = MagicMock(status_code=503, headers={"Retry-After": "1.5"}, text="Overloaded")

        # start=100 (deadline=110), att1=100, after_sdk1=101, after_rest1=102, att2=103.5, after_sdk2=104
        monotonic_values = iter([100.0, 100.0, 101.0, 102.0, 103.5, 104.0])
        with patch("backend.app.llm_provider.gemini.time.monotonic", side_effect=lambda: next(monotonic_values)):
            with patch("backend.app.llm_provider.gemini.time.sleep") as mock_sleep:
                with patch("google.generativeai.configure"):
                    with patch("google.generativeai.GenerativeModel", return_value=mock_model):
                        with patch("backend.app.llm_provider.gemini.requests.post", return_value=mock_rest_503) as mock_post:
                            resp = provider.generate(prompt="Test", system_prompt="System")

        self.assertTrue(resp.success)
        self.assertEqual(resp.content, "Recovered after REST 503.")
        self.assertEqual(mock_model.generate_content.call_count, 2)
        mock_post.assert_called_once()
        mock_sleep.assert_called_once_with(1.5)

    def test_40_gemini_http_date_retry_after_falls_back_to_bounded_backoff(self):
        import google.api_core.exceptions as gexc
        from backend.app.llm_provider.gemini import GeminiProvider

        provider = GeminiProvider(api_key="test-key-valid-12345", timeout_seconds=10, max_retries=2)
        exc_http_date = gexc.ServiceUnavailable(
            "503",
            response=MagicMock(headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}),
        )
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = [
            exc_http_date,
            MagicMock(text="Recovered with bounded numeric backoff."),
        ]

        monotonic_values = iter([100.0, 100.0, 101.0, 102.0, 103.0])
        with patch("backend.app.llm_provider.gemini.time.monotonic", side_effect=lambda: next(monotonic_values)):
            with patch("backend.app.llm_provider.gemini.time.sleep") as mock_sleep:
                with patch("google.generativeai.configure"):
                    with patch("google.generativeai.GenerativeModel", return_value=mock_model):
                        with patch("backend.app.llm_provider.gemini.requests.post") as mock_post:
                            resp = provider.generate(prompt="Test", system_prompt="System")

        self.assertTrue(resp.success)
        self.assertEqual(resp.content, "Recovered with bounded numeric backoff.")
        self.assertEqual(mock_model.generate_content.call_count, 2)
        mock_post.assert_not_called()
        mock_sleep.assert_called_once_with(1.0)

    def test_41_groq_404_model_not_found_fails_fast_single_request(self):
        import openai
        from backend.app.llm_provider.groq import GroqProvider

        provider = GroqProvider(api_key="test-key-valid-12345", timeout_seconds=30, max_retries=2)
        mock_create = MagicMock(
            side_effect=openai.NotFoundError(
                message="The model does not exist",
                response=MagicMock(status_code=404, headers={}),
                body={"error": {"code": "model_not_found"}},
            )
        )
        mock_client = MagicMock()
        mock_client.chat.completions.create = mock_create

        with patch("openai.OpenAI", return_value=mock_client):
            with patch("backend.app.llm_provider.groq.time.sleep") as mock_sleep:
                resp = provider.generate(prompt="Test prompt", system_prompt="System")

        self.assertFalse(resp.success)
        self.assertIn("404", resp.error)
        self.assertEqual(mock_create.call_count, 1)
        mock_sleep.assert_not_called()

    def test_42_groq_401_403_permanent_client_error_fails_fast(self):
        import openai
        from backend.app.llm_provider.groq import GroqProvider

        provider = GroqProvider(api_key="test-key-valid-12345", timeout_seconds=30, max_retries=2)

        for exc_cls, status in [(openai.AuthenticationError, 401), (openai.PermissionDeniedError, 403)]:
            mock_create = MagicMock(
                side_effect=exc_cls(
                    message="Client error",
                    response=MagicMock(status_code=status, headers={}),
                    body=None,
                )
            )
            mock_client = MagicMock()
            mock_client.chat.completions.create = mock_create

            with patch("openai.OpenAI", return_value=mock_client):
                with patch("backend.app.llm_provider.groq.time.sleep") as mock_sleep:
                    resp = provider.generate(prompt="Test prompt", system_prompt="System")

            self.assertFalse(resp.success)
            self.assertIn(str(status), resp.error)
            self.assertEqual(mock_create.call_count, 1)
            mock_sleep.assert_not_called()

    def test_43_groq_transient_error_retries_and_succeeds_within_deadline(self):
        import openai
        from backend.app.llm_provider.groq import GroqProvider

        provider = GroqProvider(api_key="test-key-valid-12345", timeout_seconds=10, max_retries=2)
        mock_success_resp = MagicMock()
        mock_success_resp.choices = [MagicMock(message=MagicMock(content="Groq recovered after 429"), finish_reason="stop")]

        rate_limit_err = openai.RateLimitError(
            message="Rate limit reached",
            response=MagicMock(status_code=429, headers={"Retry-After": "1.5"}),
            body=None,
        )
        mock_create = MagicMock(side_effect=[rate_limit_err, mock_success_resp])
        mock_client = MagicMock()
        mock_client.chat.completions.create = mock_create

        with patch("openai.OpenAI", return_value=mock_client):
            with patch("backend.app.llm_provider.groq.time.sleep") as mock_sleep:
                resp = provider.generate(prompt="Test prompt", system_prompt="System")

        self.assertTrue(resp.success)
        self.assertEqual(resp.content, "Groq recovered after 429")
        self.assertEqual(mock_create.call_count, 2)
        mock_sleep.assert_called_once_with(1.5)

    def test_44_gemini_failure_groq_success_using_qwen_model(self):
        from backend.app.llm_provider.groq import GroqProvider

        groq_prov = GroqProvider(api_key="test-key-valid-12345", model="qwen/qwen3.8-27b", timeout_seconds=30, max_retries=2)
        mock_success_resp = MagicMock()
        mock_success_resp.choices = [MagicMock(message=MagicMock(content="Grounded answer from Qwen"), finish_reason="stop")]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_success_resp

        with patch.dict(llm_manager.providers, {"groq": groq_prov}):
            with patch.object(
                llm_manager.providers["gemini"],
                "generate",
                return_value=LLMResponse(success=False, content="", error="Gemini 503", provider="gemini", model="gemini-3.8-flash"),
            ):
                with patch("openai.OpenAI", return_value=mock_client):
                    mgr_resp = llm_manager.generate(prompt="Explain emergency tree removal", system_prompt="System")

        self.assertTrue(mgr_resp.success)
        self.assertTrue(mgr_resp.is_fallback)
        self.assertEqual(mgr_resp.provider, "groq")
        self.assertEqual(mgr_resp.model, "qwen/qwen3.8-27b")
        self.assertEqual(mgr_resp.content, "Grounded answer from Qwen")

    def test_45_gemini_failure_groq_failure_triggers_deterministic_grounded_synthesis(self):
        cit = RagCitation(
            url="https://www.edisonnj.org/document_center/Forms_Soil_Importation_Appl.pdf",
            title="Soil Importation Permit Application",
            category="Application Form",
            department_id="engineering",
            relevance_score=0.9,
            excerpt="Subsection 32-2.3 soil importation application fee is $200.00.",
            visibility="public",
            service="soil_import",
        )
        gemini_fail = LLMResponse(success=False, content="", error="Gemini 429", provider="gemini", model="gemini-3.8-flash")
        groq_fail = LLMResponse(success=False, content="", error="Groq model not found (404): qwen/qwen3.8-27b", provider="groq", model="qwen/qwen3.8-27b")

        with patch.object(llm_manager.providers["gemini"], "is_available", return_value=True):
            with patch.object(llm_manager.providers["gemini"], "generate", return_value=gemini_fail):
                with patch.object(llm_manager.providers["groq"], "is_available", return_value=True):
                    with patch.object(llm_manager.providers["groq"], "generate", return_value=groq_fail):
                        mgr_resp = llm_manager.generate(prompt="What is the soil import fee?", system_prompt="System")
                        self.assertFalse(mgr_resp.success)

                        with patch.object(vector_store, "search", return_value=[cit]):
                            rag_res = rag_engine.answer_query("What is the soil import fee?", department_id="engineering", history=[])

        self.assertTrue(rag_res.grounded)
        self.assertIn("$200.00", rag_res.answer)

    # ------------------------------------------------------------------
    # Fix 10: Public flowchart citation preservation and safety filtering
    # ------------------------------------------------------------------
    def test_46_public_permit_flowchart_retained_in_chat_citations(self):
        """Public Permit Flow Charts citation remains in the final /api/chat citations array."""
        flowchart_cit = RagCitation(
            url="https://www.edisonnj.org/document_center/Permit%20Flow%20Charts.pdf",
            title="Permit Flow Chart to Help Determine What Permit is Needed",
            category="Guidance flowchart",
            department_id="engineering",
            relevance_score=0.95,
            excerpt="Soil Import / Export Permits: Importing or exporting 10 cubic yards or more requires a permit.",
            visibility="public",
            document_type="guidance_flowchart",
            service="permit_flowchart",
            verification_status="verified",
        )
        fake_rag_result = RagResult(
            answer="A Soil Export Permit is required for 10 cubic yards or more.",
            citations=[flowchart_cit],
            grounded=True,
            query="When is a soil export permit required?",
            form_packet=None,
            options=[],
        )

        with patch("backend.app.main.rate_limiter.check_rate_limit", return_value=(True, 1)):
            with patch.object(rag_engine, "detect_flow_intent", return_value=None):
                with patch.object(rag_engine, "match_official_form_packet", return_value=None):
                    with patch.object(rag_engine, "answer_query", return_value=fake_rag_result):
                        req = ChatRequest(
                            session_id="test_sess_flowchart_pub",
                            message="When is a soil export permit required?",
                            department_id="engineering",
                        )
                        res = chat_endpoint(req)

        self.assertEqual(res.mode, "rag")
        self.assertEqual(len(res.citations), 1)
        self.assertEqual(res.citations[0].url, "https://www.edisonnj.org/document_center/Permit%20Flow%20Charts.pdf")
        self.assertEqual(res.citations[0].title, "Permit Flow Chart to Help Determine What Permit is Needed")

    def test_47_internal_flowchart_citation_still_excluded(self):
        """Internal flowchart citation (visibility='internal') is still excluded from ChatResponse."""
        internal_cit = RagCitation(
            url="https://www.edisonnj.org/internal/staff_flowchart.pdf",
            title="Internal Engineering Staff Decision Flowchart",
            category="Internal flowchart",
            department_id="engineering",
            relevance_score=0.9,
            excerpt="Staff intake guidelines.",
            visibility="internal",
            document_type="internal_guideline",
            service="internal_service",
            verification_status="verified",
        )
        public_cit = RagCitation(
            url="https://www.edisonnj.org/document_center/Forms_Soil_Exportation_App.pdf",
            title="Soil Exportation Permit Application",
            category="Application Form",
            department_id="engineering",
            relevance_score=0.85,
            excerpt="Official application form for soil export.",
            visibility="public",
            document_type="application_form",
            service="soil_export",
            verification_status="verified",
        )
        fake_rag_result = RagResult(
            answer="Here is the application.",
            citations=[internal_cit, public_cit],
            grounded=True,
            query="Where is the soil export application?",
            form_packet=None,
            options=[],
        )

        with patch("backend.app.main.rate_limiter.check_rate_limit", return_value=(True, 1)):
            with patch.object(rag_engine, "detect_flow_intent", return_value=None):
                with patch.object(rag_engine, "match_official_form_packet", return_value=None):
                    with patch.object(rag_engine, "answer_query", return_value=fake_rag_result):
                        req = ChatRequest(
                            session_id="test_sess_internal_excl",
                            message="Where is the soil export application?",
                            department_id="engineering",
                        )
                        res = chat_endpoint(req)

        self.assertEqual(res.mode, "rag")
        self.assertEqual(len(res.citations), 1)
        self.assertEqual(res.citations[0].url, "https://www.edisonnj.org/document_center/Forms_Soil_Exportation_App.pdf")
        for c in res.citations:
            self.assertNotEqual(getattr(c, "visibility", "public"), "internal")
            self.assertNotIn("staff_flowchart", c.url)

    def test_48_citations_url_deduplicated(self):
        """Duplicate URLs with different fragments or query parameters are deduplicated."""
        cit1 = RagCitation(
            url="https://www.edisonnj.org/document_center/Permit%20Flow%20Charts.pdf#page=1",
            title="Permit Flow Chart Page 1",
            category="Guidance flowchart",
            department_id="engineering",
            relevance_score=0.95,
            excerpt="Overview flowchart.",
            visibility="public",
            document_type="guidance_flowchart",
            service="permit_flowchart",
            verification_status="verified",
        )
        cit2 = RagCitation(
            url="https://www.edisonnj.org/document_center/Permit%20Flow%20Charts.pdf#page=4",
            title="Permit Flow Chart Page 4",
            category="Guidance flowchart",
            department_id="engineering",
            relevance_score=0.90,
            excerpt="Soil import/export flowchart.",
            visibility="public",
            document_type="guidance_flowchart",
            service="permit_flowchart",
            verification_status="verified",
        )
        fake_rag_result = RagResult(
            answer="Flowchart overview.",
            citations=[cit1, cit2],
            grounded=True,
            query="Show flowcharts",
            form_packet=None,
            options=[],
        )

        with patch("backend.app.main.rate_limiter.check_rate_limit", return_value=(True, 1)):
            with patch.object(rag_engine, "detect_flow_intent", return_value=None):
                with patch.object(rag_engine, "match_official_form_packet", return_value=None):
                    with patch.object(rag_engine, "answer_query", return_value=fake_rag_result):
                        req = ChatRequest(
                            session_id="test_sess_dedup",
                            message="Show flowcharts",
                            department_id="engineering",
                        )
                        res = chat_endpoint(req)

        self.assertEqual(res.mode, "rag")
        self.assertEqual(len(res.citations), 1)
        self.assertIn("Permit%20Flow%20Charts.pdf", res.citations[0].url)

    def test_49_soil_export_10_cu_yd_response_retains_supporting_flowchart_citation(self):
        """Soil export 10-cubic-yard threshold response retains supporting flowchart citation through chat_endpoint."""
        flowchart_cit = RagCitation(
            url="https://www.edisonnj.org/document_center/Permit%20Flow%20Charts.pdf",
            title="Permit Flow Chart to Help Determine What Permit is Needed",
            category="Guidance flowchart",
            department_id="engineering",
            relevance_score=0.402,
            excerpt="[Page 4] Soil Import / Export Permits Are you importing or exporting 10 cubic yards or more of Soil to/from your site?",
            visibility="public",
            document_type="guidance_flowchart",
            service="permit_flowchart",
            verification_status="verified",
        )
        app_cit = RagCitation(
            url="https://www.edisonnj.org/document_center/Forms_Soil_Exportation_App.pdf",
            title="Requirements for Plot Grading Plans – Minor Development / Soil Exportation Permit Application",
            category="Application form",
            department_id="engineering",
            relevance_score=0.350,
            excerpt="Requirements for Plot Grading Plans – Minor Development / Soil Exportation Permit Application.",
            visibility="public",
            document_type="application_form",
            service="soil_export",
            verification_status="verified",
        )

        with patch("backend.app.main.rate_limiter.check_rate_limit", return_value=(True, 1)):
            with patch.object(vector_store, "search", return_value=[flowchart_cit, app_cit]):
                with patch("backend.app.llm_client.llm_client.generate_answer", return_value="A Soil Export Permit is required if exporting 10 cubic yards or more."):
                    req = ChatRequest(
                        session_id="test_sess_soil_export_thresh",
                        message="When is a soil export permit required in Edison, and what documents are needed?",
                        department_id="engineering",
                    )
                    res = chat_endpoint(req)

        self.assertEqual(res.mode, "rag")
        citation_urls = [c.url for c in res.citations]
        self.assertIn("https://www.edisonnj.org/document_center/Permit%20Flow%20Charts.pdf", citation_urls)
        self.assertIn("https://www.edisonnj.org/document_center/Forms_Soil_Exportation_App.pdf", citation_urls)
        self.assertGreaterEqual(len(res.citations), 2)


class TestTypoRecognitionAndTreeFlowRouting(OfflineLLMTestCase):
    """Regression tests for conservative typo recognition and tree removal routing."""

    def test_50_tree_removal_typos_detect_tree_intent(self):
        """1 & 2: Typo queries like 'how to remove gtress' and 'how to remove tress' detect tree_removal."""
        for query in ["how to remove gtress", "how to remove tress", "how to remove tre"]:
            intent = service_intent_service.detect_intent(query)
            self.assertEqual(intent.service_id, "tree_removal", f"Failed for query {query}")
            self.assertGreaterEqual(intent.confidence, 0.90)

    def test_51_valid_tree_queries_continue_working(self):
        """3 & 4: Valid tree queries continue working properly."""
        for query in ["how to remove trees", "I want to remove a tree from my property"]:
            intent = service_intent_service.detect_intent(query)
            self.assertEqual(intent.service_id, "tree_removal", f"Failed for query {query}")
            self.assertGreaterEqual(intent.confidence, 0.90)

    def test_52_unrelated_queries_do_not_become_tree_removal(self):
        """5: Unrelated queries do not become tree-removal queries."""
        unrelated = [
            "how to remove distress",
            "how to remove mattress",
            "how to remove stress",
            "how to deal with distress",
            "how to remove actress from video",
        ]
        for query in unrelated:
            intent = service_intent_service.detect_intent(query)
            self.assertNotEqual(intent.service_id, "tree_removal", f"Query {query} incorrectly matched tree_removal")

    def test_53_substring_preservation(self):
        """6: Words containing typo sequences as substrings are not modified."""
        test_words = [
            ("distress", "distress"),
            ("mattress", "mattress"),
            ("actress", "actress"),
            ("buttress", "buttress"),
            ("waitress", "waitress"),
            ("mistress", "mistress"),
            ("fortress", "fortress"),
            ("stress", "stress"),
            ("extreme", "extreme"),
            ("genre", "genre"),
            ("street", "street"),
            ("theatre", "theatre"),
            ("entrepreneur", "entrepreneur"),
        ]
        for word, expected in test_words:
            normalized = service_intent_service.normalize_typos(f"check {word} please")
            self.assertEqual(normalized, f"check {expected} please")

    def test_54_typo_starts_deterministic_flow_without_llm(self):
        """7 & 8: 'how to remove gtress' starts tree_removal_flow without invoking LLM or RAG."""
        with patch("backend.app.main.rate_limiter.check_rate_limit", return_value=(True, 1)):
            with patch("backend.app.llm_client.llm_manager.generate", side_effect=AssertionError("LLM should not be called!")):
                with patch("backend.app.llm_client.llm_client.generate_answer", side_effect=AssertionError("LLMClient.generate_answer should not be called!")):
                    req = ChatRequest(
                        session_id="test_sess_gtress_flow_1",
                        message="how to remove gtress",
                        department_id="engineering",
                    )
                    res = chat_endpoint(req)

        self.assertEqual(res.mode, "flow")
        self.assertEqual(res.active_flow_id, "tree_removal_flow")
        self.assertIsNotNone(res.options)
        self.assertGreater(len(res.options), 0)

    def test_55_original_resident_message_preserved_in_history(self):
        """9: The original resident message remains unchanged in conversation history."""
        session_id = "test_sess_gtress_hist_1"
        with patch("backend.app.main.rate_limiter.check_rate_limit", return_value=(True, 1)):
            req = ChatRequest(
                session_id=session_id,
                message="how to remove gtress",
                department_id="engineering",
            )
            chat_endpoint(req)

        from backend.app.main import CHAT_HISTORIES
        history = CHAT_HISTORIES.get(session_id, [])
        self.assertGreaterEqual(len(history), 1)
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[0]["content"], "how to remove gtress")


if __name__ == "__main__":
    unittest.main()
