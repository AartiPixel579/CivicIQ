"""
Reusable scoped offline LLM mock base class for application-level unit tests.
Prevents accidental live Gemini or Groq API calls while keeping provider-specific
tests (e.g., test_civiciq_full_suite.py, test_19, test_21) completely independent.
"""

import unittest
from unittest.mock import patch

from backend.app.llm_provider.base import LLMResponse


class OfflineLLMTestCase(unittest.TestCase):
    """Class-scoped offline LLM isolation for application-level tests."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._offline_llm_patcher = patch(
            "backend.app.llm_client.llm_manager.generate",
            return_value=LLMResponse(
                content="",
                provider="none",
                model="none",
                success=False,
                error="Offline test mock: live LLM disabled.",
            ),
        )
        cls._offline_llm_patcher.start()

    @classmethod
    def tearDownClass(cls):
        patcher = getattr(cls, "_offline_llm_patcher", None)
        if patcher is not None:
            patcher.stop()
        super().tearDownClass()
