import logging
from typing import List, Dict, Optional, Any
from .base import BaseLLMProvider, LLMResponse
from .gemini import GeminiProvider
from .groq import GroqProvider
from ..config import (
    GEMINI_API_KEY, GEMINI_MODEL,
    GROQ_API_KEY, GROQ_BASE_URL, GROQ_MODEL,
    LLM_PRIMARY_PROVIDER, LLM_FALLBACK_PROVIDERS,
    LLM_TIMEOUT_SECONDS, LLM_MAX_RETRIES
)

logger = logging.getLogger("llm_provider.manager")

class LLMProviderManager:
    """
    Orchestrates LLM providers with automatic fallback priority:
    Google Gemini (Primary) -> Groq (Fallback)
    """

    def __init__(self):
        self.primary_name = LLM_PRIMARY_PROVIDER
        self.fallback_names = list(LLM_FALLBACK_PROVIDERS)
        self.providers: Dict[str, BaseLLMProvider] = {}
        self._init_providers()

    def _init_providers(self):
        # 1. Primary: Google Gemini
        self.providers["gemini"] = GeminiProvider(
            api_key=GEMINI_API_KEY,
            model=GEMINI_MODEL,
            timeout_seconds=LLM_TIMEOUT_SECONDS,
            max_retries=LLM_MAX_RETRIES
        )

        # 2. Fallback: Groq
        self.providers["groq"] = GroqProvider(
            api_key=GROQ_API_KEY,
            model=GROQ_MODEL,
            base_url=GROQ_BASE_URL,
            timeout_seconds=LLM_TIMEOUT_SECONDS,
            max_retries=LLM_MAX_RETRIES
        )

    def get_provider_priority(self) -> List[str]:
        """Returns the ordered list of provider names to attempt."""
        order = [LLM_PRIMARY_PROVIDER]
        for p in LLM_FALLBACK_PROVIDERS:
            if p not in order:
                order.append(p)
        # Ensure standard fallbacks are included
        for fallback in ["gemini", "groq"]:
            if fallback not in order:
                order.append(fallback)
        return [p for p in order if p in self.providers]

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        history: Optional[List[Dict[str, str]]] = None,
        temperature: float = 0.1,
        max_tokens: int = 1000
    ) -> LLMResponse:
        priority_list = self.get_provider_priority()
        last_error = None

        for p_name in priority_list:
            provider = self.providers.get(p_name)
            if not provider or not provider.is_available():
                logger.debug(f"Provider '{p_name}' not available or unconfigured; skipping.")
                continue

            logger.info(f"Attempting generation with provider '{p_name}' (model: {provider.model})")
            resp = provider.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                history=history,
                temperature=temperature,
                max_tokens=max_tokens
            )

            if resp.success and resp.content:
                logger.info(f"Provider '{p_name}' succeeded.")
                resp.is_fallback = (p_name != self.primary_name)
                return resp
            else:
                last_error = resp.error or f"Provider '{p_name}' returned empty response."
                logger.warning(f"Provider '{p_name}' failed: {last_error}. Trying next available provider...")

        return LLMResponse(
            content="",
            provider="none",
            model="none",
            success=False,
            error=last_error or "All configured LLM providers failed or are unconfigured."
        )

    def get_status(self) -> Dict[str, Any]:
        """Returns non-sensitive status information for all providers."""
        return {
            "primary": LLM_PRIMARY_PROVIDER,
            "priority": self.get_provider_priority(),
            "providers": {k: v.get_provider_info() for k, v in self.providers.items()}
        }

llm_manager = LLMProviderManager()
