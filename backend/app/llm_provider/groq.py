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
        model: str = "qwen/qwen3.8-27b",
        base_url: str = "https://api.groq.com/openai/v1",
        timeout_seconds: int = 30,
        max_retries: int = 2
    ):
        super().__init__(
            name="groq",
            model=model or "qwen/qwen3.8-27b",
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries
        )
        self.base_url = base_url or "https://api.groq.com/openai/v1"

    def is_available(self) -> bool:
        return bool(self.api_key and len(self.api_key.strip()) > 8)

    def _extract_status_code(self, exc: Exception) -> Optional[int]:
        """Extract HTTP status code from openai/httpx exception if present."""
        code = getattr(exc, "status_code", None)
        if isinstance(code, int) and 400 <= code <= 599:
            return code
        resp = getattr(exc, "response", None)
        if resp is not None:
            code = getattr(resp, "status_code", None)
            if isinstance(code, int) and 400 <= code <= 599:
                return code
        return None

    def _extract_retry_after(self, exc: Exception) -> Optional[float]:
        """Extract numeric Retry-After seconds from an exception or its response headers."""
        resp = getattr(exc, "response", None)
        headers = getattr(resp, "headers", None) if resp is not None else getattr(exc, "headers", None)
        if not headers or not hasattr(headers, "get"):
            return None
        raw = headers.get("Retry-After") or headers.get("retry-after")
        if raw is None:
            return None
        try:
            return max(float(str(raw).strip()), 0.0)
        except (TypeError, ValueError):
            return None

    def _sanitize_text(self, text: str, max_len: int = 160) -> str:
        """Redact API key and truncate diagnostic error text."""
        cleaned = text or ""
        if self.api_key:
            cleaned = cleaned.replace(self.api_key, "[REDACTED]")
        if len(cleaned) > max_len:
            return cleaned[:max_len] + "..."
        return cleaned

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
        total_budget = max(float(self.timeout_seconds), 0.1)
        deadline = time.monotonic() + total_budget

        for attempt in range(self.max_retries + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                last_error = last_error or f"Groq request timed out after {self.timeout_seconds}s."
                break

            try:
                import openai
                client = openai.OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    timeout=remaining
                )

                resp = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=remaining
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
                status_code = self._extract_status_code(e)
                if status_code == 404:
                    last_error = f"Groq model not found (404): {self.model}"
                    logger.warning(f"Groq attempt {attempt + 1} failed: {last_error}")
                    break
                elif status_code in (400, 401, 403):
                    last_error = f"Groq client error ({status_code}): {self._sanitize_text(str(e))}"
                    logger.warning(f"Groq attempt {attempt + 1} failed: {last_error}")
                    break
                else:
                    last_error = f"Groq request error: {self._sanitize_text(str(e))}"
                    logger.warning(f"Groq attempt {attempt + 1} failed: {last_error}")

                if attempt < self.max_retries:
                    retry_after = self._extract_retry_after(e)
                    backoff = retry_after if retry_after is not None else min(1.0 * (attempt + 1), 2.0)
                    remaining = deadline - time.monotonic()
                    if remaining <= backoff:
                        last_error = last_error or f"Groq request timed out after {self.timeout_seconds}s."
                        break
                    if backoff > 0:
                        time.sleep(backoff)

        return LLMResponse(
            content="",
            provider=self.name,
            model=self.model,
            success=False,
            error=last_error
        )
