import time
import logging
from typing import List, Dict, Optional, Any
from .base import BaseLLMProvider, LLMResponse

logger = logging.getLogger("llm_provider.groq")

class GroqProvider(BaseLLMProvider):
    """First Backup: Groq API Provider (OpenAI-compatible free developer tier)."""

    def __init__(
        self,
        api_key: str = "",
        model: str = "llama-3.3-70b-versatile",
        base_url: str = "https://api.groq.com/openai/v1",
        timeout_seconds: int = 30,
        max_retries: int = 2
    ):
        super().__init__(
            name="groq",
            model=model or "llama-3.3-70b-versatile",
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries
        )
        self.base_url = base_url or "https://api.groq.com/openai/v1"

    def is_available(self) -> bool:
        return bool(self.api_key and len(self.api_key.strip()) > 8)

    def generate(
        self,
        prompt: str,
        system_prompt: str,
        history: Optional[List[Dict[str, str]]] = None,
        temperature: float = 0.1,
        max_tokens: int = 1000
    ) -> LLMResponse:
        if not self.is_available():
            return LLMResponse(
                content="",
                provider=self.name,
                model=self.model,
                success=False,
                error="Groq API key is not configured or invalid."
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
                    max_tokens=max_tokens
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
                last_error = f"Groq request error: {str(e)}"
                logger.warning(f"Groq attempt {attempt + 1} failed: {last_error}")

            if attempt < self.max_retries:
                time.sleep(1.0 * (attempt + 1))

        return LLMResponse(
            content="",
            provider=self.name,
            model=self.model,
            success=False,
            error=last_error
        )
