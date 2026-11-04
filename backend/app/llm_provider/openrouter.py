import time
import logging
from typing import List, Dict, Optional, Any
from .base import BaseLLMProvider, LLMResponse

logger = logging.getLogger("llm_provider.openrouter")

class OpenRouterProvider(BaseLLMProvider):
    """Optional Second Backup: OpenRouter API Provider (Free models only)."""

    def __init__(
        self,
        api_key: str = "",
        model: str = "meta-llama/llama-3.2-3b-instruct:free",
        base_url: str = "https://openrouter.ai/api/v1",
        allow_free_only: bool = True,
        timeout_seconds: int = 30,
        max_retries: int = 2
    ):
        super().__init__(
            name="openrouter",
            model=model or "meta-llama/llama-3.2-3b-instruct:free",
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries
        )
        self.base_url = base_url or "https://openrouter.ai/api/v1"
        self.allow_free_only = allow_free_only

        if self.allow_free_only and not self._is_free_model(self.model):
            raise ValueError(
                f"OpenRouter model '{self.model}' is not a free-tier model. "
                f"Free-first policy requires models ending with ':free'."
            )

    def is_available(self) -> bool:
        if not (self.api_key and len(self.api_key.strip()) > 8):
            return False
        # Guard: If free only is enforced, ensure model is explicitly free
        if self.allow_free_only and not self._is_free_model(self.model):
            return False
        return True

    def _is_free_model(self, model_name: str) -> bool:
        """Verifies whether the OpenRouter model identifier is explicitly free."""
        m = (model_name or "").lower().strip()
        return m.endswith(":free") or ":free" in m

    def generate(
        self,
        prompt: str,
        system_prompt: str,
        history: Optional[List[Dict[str, str]]] = None,
        temperature: float = 0.1,
        max_tokens: int = 1000
    ) -> LLMResponse:
        # Enforce free-tier security guard
        if self.allow_free_only and not self._is_free_model(self.model):
            return LLMResponse(
                content="",
                provider=self.name,
                model=self.model,
                success=False,
                error=f"Paid model '{self.model}' rejected by OPENROUTER_ALLOW_FREE_MODELS_ONLY policy. Only free models (ending with ':free') are permitted."
            )

        if not (self.api_key and len(self.api_key.strip()) > 8):
            return LLMResponse(
                content="",
                provider=self.name,
                model=self.model,
                success=False,
                error="OpenRouter API key is not configured or invalid."
            )

        messages = [{"role": "system", "content": system_prompt}]
        if history:
            for h in history[-6:]:
                role = "user" if h.get("role") == "user" else "assistant"
                messages.append({"role": role, "content": h.get("content", "")})
        messages.append({"role": "user", "content": prompt})

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                import openai
                client = openai.OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    timeout=self.timeout_seconds
                )

                resp = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    extra_headers={
                        "HTTP-Referer": "https://github.com/AartiGoyal16/CivicIQ",
                        "X-Title": "CivicIQ Edison Township Assistant"
                    }
                )

                if resp.choices and len(resp.choices) > 0:
                    text = resp.choices[0].message.content or ""
                    return LLMResponse(
                        content=text.strip(),
                        provider=self.name,
                        model=self.model,
                        success=True,
                        finish_reason=resp.choices[0].finish_reason
                    )
            except Exception as e:
                last_error = f"OpenRouter request error: {str(e)}"
                logger.warning(f"OpenRouter attempt {attempt + 1} failed: {last_error}")

            if attempt < self.max_retries:
                time.sleep(1.0 * (attempt + 1))

        return LLMResponse(
            content="",
            provider=self.name,
            model=self.model,
            success=False,
            error=last_error
        )


OpenRouterFreeProvider = OpenRouterProvider
