"""
Tests for Strict RAG Grounding, Anti-Hallucination Guardrails,
and Resident-Provided External URL Verification.
"""

import unittest
from unittest.mock import patch

from backend.app.crawler import trusted_source_registry
from backend.app.rag_engine import rag_engine


class TestRagGroundingAndTrust(unittest.TestCase):
    def test_01_untrusted_resident_url_rejected_and_not_registered(self):
        untrusted_url = "https://untrusted-external-blog.example.com/fake-edison-fees.pdf"
        res = rag_engine.answer_query(
            f"According to {untrusted_url}, is the tree fee $500?",
            department_id="engineering",
        )
        self.assertFalse(res.grounded)
        self.assertEqual(len(res.citations), 0)
        self.assertIn("cannot verify", res.answer.lower())

        # Must NEVER add resident-supplied URL to TrustedSourceRegistry
        is_trusted, _, _ = trusted_source_registry.is_url_trusted(untrusted_url, department_id="engineering")
        self.assertFalse(is_trusted)

    def test_02_unverified_engineering_query_returns_grounded_false(self):
        # When vector store finds no evidence for an engineering question, must NOT fabricate or mark grounded=True
        with patch("backend.app.rag_engine.vector_store.search", return_value=[]):
            res = rag_engine.answer_query(
                "What is the exact Edison engineering surcharge for subterranean geothermal loops?",
                department_id="engineering",
            )
            self.assertFalse(res.grounded)
            self.assertEqual(len(res.citations), 0)
            self.assertIn("could not verify", res.answer.lower())
            self.assertIn("edisonnj.org/document_center/index.php", res.answer.lower())

    def test_03_approved_official_url_does_not_fail_url_guard(self):
        # Ensure official Document Center URL is seeded and accepted by trust check
        trusted_source_registry.seed_from_config(
            department_id="engineering",
            root_url="https://www.edisonnj.org/document_center/index.php",
        )
        is_trusted, _, _ = trusted_source_registry.is_url_trusted(
            "https://www.edisonnj.org/document_center/index.php",
            department_id="engineering",
        )
        self.assertTrue(is_trusted)

    def test_04_supported_engineering_services_require_real_citations_never_generic_index(self):
        queries = [
            "What are the requirements and fee for a Tree Removal permit?",
            "What are the requirements for Plot Grading Plans for Minor Development?",
            "When is a Minor Development Plot Grading Plan required?",
            "What is a Site Improvement Permit in Edison?",
            "How do I apply for a Sewer Connection Charge?",
            "How do I apply for a Soil Importation permit for 20 cubic yards?",
            "I need to export 15 cubic yards of soil from my property.",
        ]
        for q in queries:
            res = rag_engine.answer_query(q, department_id="engineering")
            self.assertTrue(res.grounded, f"Expected grounded=True for {q}")
            self.assertGreater(len(res.citations), 0, f"Expected non-empty citations for {q}")
            for c in res.citations:
                self.assertFalse(
                    c.url.rstrip("/").endswith("document_center/index.php"),
                    f"Citation URL must not be generic Document Center index.php: {c.url}",
                )

    def test_05_historical_2018_tree_fee_not_answered_with_current_hardcoded_fee(self):
        res = rag_engine.answer_query(
            "What was the 2018 residential tree removal fee schedule?",
            department_id="engineering",
        )
        self.assertFalse(res.grounded)
        self.assertEqual(len(res.citations), 0)
        self.assertIn("could not verify", res.answer.lower())

    def test_06_major_subdivision_variance_timeline_not_hijacked_by_tree_turnaround(self):
        res = rag_engine.answer_query(
            "What is the exact guaranteed approval timeline for a major subdivision variance?",
            department_id="engineering",
        )
        self.assertFalse(res.grounded)
        self.assertEqual(len(res.citations), 0)
        self.assertNotIn("tree removal", res.answer.lower())

    def test_07_small_talk_greetings_and_general_questions_never_trigger_permits(self):
        from backend.app.main import chat_endpoint
        from backend.app.models.core import ChatRequest

        small_talk_inputs = [
            "hi",
            "hello",
            "how are you?",
            "how are you doing?",
            "thanks",
            "thank you",
            "bye",
            "good morning",
        ]
        for idx, msg in enumerate(small_talk_inputs):
            res = chat_endpoint(ChatRequest(
                session_id=f"test_smalltalk_{idx}",
                message=msg,
                department_id="engineering",
            ))
            self.assertEqual(res.mode, "rag", f"Unexpected mode for {msg!r}")
            self.assertEqual(len(res.citations or []), 0, f"Small talk {msg!r} must not return citations")
            self.assertIsNone(res.form_packet, f"Small talk {msg!r} must not attach a permit packet")
            self.assertNotIn("tree removal", res.message.lower())
            self.assertNotIn("$25", res.message)
            self.assertNotIn("localhost:3000", res.message)

        # Exact reproduction: 'hi' -> 'how are you' in the same session
        sid = "test_hi_then_how_are_you"
        r1 = chat_endpoint(ChatRequest(session_id=sid, message="hi", department_id="engineering"))
        self.assertIn("welcome to civiciq", r1.message.lower())
        r2 = chat_endpoint(ChatRequest(session_id=sid, message="how are you", department_id="engineering"))
        self.assertIsNone(r2.form_packet)
        self.assertEqual(len(r2.citations or []), 0)
        self.assertNotIn("tree removal", r2.message.lower())
        self.assertNotIn("$25", r2.message)

        # Unrelated general questions must not retrieve or display Engineering permits
        for g_idx, gen_q in enumerate(["What is the capital of France?", "Tell me a funny joke"]):
            rg = chat_endpoint(ChatRequest(session_id=f"test_gen_{g_idx}", message=gen_q, department_id="engineering"))
            self.assertIsNone(rg.form_packet)
            self.assertEqual(len(rg.citations or []), 0)
            self.assertNotIn("localhost:3000", rg.message)

        # Actual Engineering query still activates Tree Removal workflow
        rt = chat_endpoint(ChatRequest(
            session_id="test_tree_workflow_still_works",
            message="How do I remove a tree?",
            department_id="engineering",
        ))
        self.assertEqual(rt.mode, "flow")
        self.assertEqual(rt.active_flow_id, "tree_removal_flow")


if __name__ == "__main__":
    unittest.main()
