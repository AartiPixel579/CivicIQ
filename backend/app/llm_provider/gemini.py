import re
import time
import logging
import requests
from typing import List, Dict, Optional, Any
from .base import BaseLLMProvider, LLMResponse

logger = logging.getLogger("llm_provider.gemini")

_KEY_PARAM_RE = re.compile(r"([?&]key=)[^&\s]+")


class GeminiProvider(BaseLLMProvider):
    """Primary Google Gemini API Provider (Free-tier supported models)."""

    def __init__(
        self,
        api_key: str = "",
        model: str = "gemini-3.8-flash",
        timeout_seconds: int = 30,
        max_retries: int = 2
    ):
        super().__init__(
            name="gemini",
            model=model or "gemini-3.8-flash",
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries
        )

    def is_available(self) -> bool:
        return bool(self.api_key and len(self.api_key.strip()) > 8)

    def _sanitize_text(self, text: str, max_len: int = 160) -> str:
        """Redact API keys/query params and bound diagnostic error text."""
        cleaned = text or ""
        if self.api_key:
            cleaned = cleaned.replace(self.api_key, "[REDACTED]")
        cleaned = _KEY_PARAM_RE.sub(r"\1[REDACTED]", cleaned)
        if len(cleaned) > max_len:
            return cleaned[:max_len] + "..."
        return cleaned

    @staticmethod
    def _classify_exception(exc: Exception) -> str:
        if isinstance(exc, requests.ConnectTimeout):
            return "connect_timeout"
        if isinstance(exc, requests.ReadTimeout):
            return "read_timeout"
        if isinstance(exc, requests.Timeout):
            return "timeout"
        return "exception"

    @staticmethod
    def _extract_sdk_http_status(exc: Exception) -> Optional[int]:
        """Return HTTP status code if the SDK exception represents an API-level response."""
        code = getattr(exc, "code", None)
        if code is not None:
            try:
                status = int(code)
                if 400 <= status <= 599:
                    return status
            except (TypeError, ValueError):
                pass
        resp = getattr(exc, "response", None)
        if resp is not None:
            status = getattr(resp, "status_code", None)
            if isinstance(status, int) and 400 <= status <= 599:
                return status
        return None

    @staticmethod
    def _extract_retry_after(source: Any) -> Optional[float]:
        """Extract numeric Retry-After seconds from a response or SDK exception if present."""
        headers = getattr(source, "headers", None)
        if headers is None:
            resp = getattr(source, "response", None)
            headers = getattr(resp, "headers", None) if resp is not None else None
        if not headers or not hasattr(headers, "get"):
            return None
        raw = headers.get("Retry-After") or headers.get("retry-after")
        if raw is None:
            return None
        try:
            return max(float(str(raw).strip()), 0.0)
        except (TypeError, ValueError):
            return None

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
                error="Gemini API key is not configured or invalid."
            )

        last_error = None
        total_budget = max(float(self.timeout_seconds), 0.1)
        last_ts = time.monotonic()
        deadline = last_ts + total_budget
        attempts_executed = 0
        service_unavailable_retries = 0

        for attempt in range(self.max_retries + 1):
            attempt_start = time.monotonic()
            last_ts = attempt_start
            remaining = deadline - attempt_start
            if remaining <= 0:
                last_error = last_error or f"Gemini request timed out after {self.timeout_seconds}s."
                break

            attempts_executed += 1
            after_sdk = attempt_start
            try:
                # 1. Try with google.generativeai SDK if available (REST transport, no internal 600s retry)
                try:
                    import google.generativeai as genai
                    genai.configure(api_key=self.api_key, transport="rest")
                    model_inst = genai.GenerativeModel(
                        model_name=self.model,
                        system_instruction=system_prompt,
                        generation_config={
                            "temperature": temperature,
                            "max_output_tokens": max_tokens
                        }
                    )

                    contents = []
                    if history:
                        for h in history[-6:]:
                            role = "user" if h.get("role") == "user" else "model"
                            contents.append({"role": role, "parts": [h.get("content", "")]})
                    contents.append({"role": "user", "parts": [prompt]})

                    logger.info(
                        "gemini_diag event=sdk_start model=%s attempt=%d remaining_s=%.3f",
                        self.model,
                        attempts_executed,
                        remaining,
                    )
                    res = model_inst.generate_content(
                        contents,
                        request_options={"timeout": remaining, "retry": None},
                    )
                    after_sdk = time.monotonic()
                    last_ts = after_sdk
                    sdk_elapsed = max(after_sdk - attempt_start, 0.0)
                    if res and res.text:
                        logger.info(
                            "gemini_diag event=sdk_success model=%s attempt=%d elapsed_s=%.3f remaining_s=%.3f",
                            self.model,
                            attempts_executed,
                            sdk_elapsed,
                            max(deadline - after_sdk, 0.0),
                        )
                        return LLMResponse(
                            content=res.text.strip(),
                            provider=self.name,
                            model=self.model,
                            success=True
                        )
                    logger.warning(
                        "gemini_diag event=sdk_failure model=%s attempt=%d stage=empty_response elapsed_s=%.3f remaining_s=%.3f",
                        self.model,
                        attempts_executed,
                        sdk_elapsed,
                        max(deadline - after_sdk, 0.0),
                    )
                except Exception as sdk_err:
                    after_sdk = time.monotonic()
                    last_ts = after_sdk
                    sdk_elapsed = max(after_sdk - attempt_start, 0.0)
                    sdk_status = self._extract_sdk_http_status(sdk_err)
                    if sdk_status is not None:
                        logger.warning(
                            "gemini_diag event=sdk_failure model=%s attempt=%d stage=http_error status=%d error_type=%s elapsed_s=%.3f remaining_s=%.3f",
                            self.model,
                            attempts_executed,
                            sdk_status,
                            type(sdk_err).__name__,
                            sdk_elapsed,
                            max(deadline - after_sdk, 0.0),
                        )
                        if sdk_status == 429:
                            last_error = "Gemini Rate Limit (429)."
                            break
                        if sdk_status == 503:
                            last_error = "Gemini API returned status 503."
                            if service_unavailable_retries < 1 and attempt < self.max_retries:
                                retry_after = self._extract_retry_after(sdk_err)
                                backoff = retry_after if retry_after is not None else min(1.0 * (attempt + 1), 2.0)
                                remaining = deadline - after_sdk
                                if remaining <= backoff:
                                    break
                                service_unavailable_retries += 1
                                if backoff > 0:
                                    time.sleep(backoff)
                                continue
                            break
                        last_error = f"Gemini API returned status {sdk_status}."
                        break

                    sdk_stage = self._classify_exception(sdk_err)
                    logger.warning(
                        "gemini_diag event=sdk_failure model=%s attempt=%d stage=%s error_type=%s elapsed_s=%.3f remaining_s=%.3f",
                        self.model,
                        attempts_executed,
                        sdk_stage,
                        type(sdk_err).__name__,
                        sdk_elapsed,
                        max(deadline - after_sdk, 0.0),
                    )

                remaining = deadline - after_sdk
                if remaining <= 0:
                    last_error = f"Gemini request timed out after {self.timeout_seconds}s."
                    break

                # 2. Resilient REST API fallback directly to Google's v1beta endpoint
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
                headers = {
                    "x-goog-api-key": self.api_key,
                    "Content-Type": "application/json",
                }
                contents_rest = []
                if history:
                    for h in history[-6:]:
                        role = "user" if h.get("role") == "user" else "model"
                        contents_rest.append({"role": role, "parts": [{"text": h.get("content", "")}]})
                contents_rest.append({"role": "user", "parts": [{"text": prompt}]})

                payload = {
                    "contents": contents_rest,
                    "systemInstruction": {"parts": [{"text": system_prompt}]},
                    "generationConfig": {
                        "temperature": temperature,
                        "maxOutputTokens": max_tokens
                    }
                }

                rest_timeout = (min(5.0, remaining), remaining)
                logger.info(
                    "gemini_diag event=rest_start model=%s attempt=%d remaining_s=%.3f",
                    self.model,
                    attempts_executed,
                    remaining,
                )
                resp = requests.post(url, headers=headers, json=payload, timeout=rest_timeout)
                after_rest = time.monotonic()
                last_ts = after_rest
                rest_elapsed = max(after_rest - after_sdk, 0.0)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            text = parts[0].get("text", "").strip()
                            if text:
                                logger.info(
                                    "gemini_diag event=rest_success model=%s attempt=%d status=200 elapsed_s=%.3f remaining_s=%.3f",
                                    self.model,
                                    attempts_executed,
                                    rest_elapsed,
                                    max(deadline - after_rest, 0.0),
                                )
                                return LLMResponse(
                                    content=text,
                                    provider=self.name,
                                    model=self.model,
                                    success=True
                                )
                    last_error = "Gemini REST API returned empty response."
                    logger.warning(
                        "gemini_diag event=rest_failure model=%s attempt=%d stage=empty_response status=200 elapsed_s=%.3f remaining_s=%.3f",
                        self.model,
                        attempts_executed,
                        rest_elapsed,
                        max(deadline - after_rest, 0.0),
                    )
                elif resp.status_code == 429:
                    last_error = "Gemini Rate Limit (429)."
                    logger.warning(
                        "gemini_diag event=rest_failure model=%s attempt=%d stage=http_error status=429 elapsed_s=%.3f remaining_s=%.3f",
                        self.model,
                        attempts_executed,
                        rest_elapsed,
                        max(deadline - after_rest, 0.0),
                    )
                    break
                elif resp.status_code == 503:
                    last_error = "Gemini API returned status 503."
                    logger.warning(
                        "gemini_diag event=rest_failure model=%s attempt=%d stage=http_error status=503 elapsed_s=%.3f remaining_s=%.3f",
                        self.model,
                        attempts_executed,
                        rest_elapsed,
                        max(deadline - after_rest, 0.0),
                    )
                    if service_unavailable_retries < 1 and attempt < self.max_retries:
                        retry_after = self._extract_retry_after(resp)
                        backoff = retry_after if retry_after is not None else min(1.0 * (attempt + 1), 2.0)
                        remaining = deadline - after_rest
                        if remaining <= backoff:
                            break
                        service_unavailable_retries += 1
                        if backoff > 0:
                            time.sleep(backoff)
                        continue
                    break
                else:
                    last_error = f"Gemini API returned status {resp.status_code}."
                    logger.warning(
                        "gemini_diag event=rest_failure model=%s attempt=%d stage=http_error status=%d elapsed_s=%.3f remaining_s=%.3f",
                        self.model,
                        attempts_executed,
                        resp.status_code,
                        rest_elapsed,
                        max(deadline - after_rest, 0.0),
                    )
                    if 400 <= resp.status_code < 500:
                        break

            except requests.ConnectTimeout as e:
                after_rest = time.monotonic()
                last_ts = after_rest
                rest_elapsed = max(after_rest - after_sdk, 0.0)
                last_error = f"Gemini connect timed out after {self.timeout_seconds}s."
                logger.warning(
                    "gemini_diag event=rest_failure model=%s attempt=%d stage=connect_timeout error_type=%s elapsed_s=%.3f remaining_s=%.3f",
                    self.model,
                    attempts_executed,
                    type(e).__name__,
                    rest_elapsed,
                    max(deadline - after_rest, 0.0),
                )
            except requests.ReadTimeout as e:
                after_rest = time.monotonic()
                last_ts = after_rest
                rest_elapsed = max(after_rest - after_sdk, 0.0)
                last_error = f"Gemini read timed out after {self.timeout_seconds}s."
                logger.warning(
                    "gemini_diag event=rest_failure model=%s attempt=%d stage=read_timeout error_type=%s elapsed_s=%.3f remaining_s=%.3f",
                    self.model,
                    attempts_executed,
                    type(e).__name__,
                    rest_elapsed,
                    max(deadline - after_rest, 0.0),
                )
            except requests.Timeout as e:
                after_rest = time.monotonic()
                last_ts = after_rest
                rest_elapsed = max(after_rest - after_sdk, 0.0)
                last_error = f"Gemini request timed out after {self.timeout_seconds}s."
                logger.warning(
                    "gemini_diag event=rest_failure model=%s attempt=%d stage=timeout error_type=%s elapsed_s=%.3f remaining_s=%.3f",
                    self.model,
                    attempts_executed,
                    type(e).__name__,
                    rest_elapsed,
                    max(deadline - after_rest, 0.0),
                )
            except Exception as e:
                after_rest = time.monotonic()
                last_ts = after_rest
                rest_elapsed = max(after_rest - after_sdk, 0.0)
                last_error = f"Gemini execution error: {self._sanitize_text(str(e))}"
                logger.warning(
                    "gemini_diag event=rest_failure model=%s attempt=%d stage=exception error_type=%s elapsed_s=%.3f remaining_s=%.3f",
                    self.model,
                    attempts_executed,
                    type(e).__name__,
                    rest_elapsed,
                    max(deadline - after_rest, 0.0),
                )

            if attempt < self.max_retries:
                now_ts = time.monotonic()
                last_ts = now_ts
                remaining = deadline - now_ts
                backoff = 1.0 * (attempt + 1)
                if remaining <= backoff:
                    last_error = last_error or f"Gemini request timed out after {self.timeout_seconds}s."
                    break
                time.sleep(backoff)

        logger.warning(
            "gemini_diag event=provider_failed model=%s attempts_executed=%d max_attempts=%d remaining_s=%.3f error=%s",
            self.model,
            attempts_executed,
            self.max_retries + 1,
            max(deadline - last_ts, 0.0),
            self._sanitize_text(last_error or ""),
        )
        return LLMResponse(
            content="",
            provider=self.name,
            model=self.model,
            success=False,
            error=last_error
        )
