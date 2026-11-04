import time
import logging
import requests
from typing import List, Dict, Optional, Any
from .base import BaseLLMProvider, LLMResponse

logger = logging.getLogger("llm_provider.gemini")

class GeminiProvider(BaseLLMProvider):
    """Primary Google Gemini API Provider (Free-tier supported models)."""

    def __init__(
        self,
        api_key: str = "",
        model: str = "gemini-1.5-flash",
        timeout_seconds: int = 30,
        max_retries: int = 2
    ):
        super().__init__(
            name="gemini",
            model=model or "gemini-1.5-flash",
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries
        )

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
                error="Gemini API key is not configured or invalid."
            )

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                # 1. Try with google.generativeai SDK if available
                try:
                    import google.generativeai as genai
                    genai.configure(api_key=self.api_key)
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

                    res = model_inst.generate_content(contents)
                    if res and res.text:
                        return LLMResponse(
                            content=res.text.strip(),
                            provider=self.name,
                            model=self.model,
                            success=True
                        )
                except Exception as sdk_err:
                    logger.debug(f"Gemini SDK attempt failed ({sdk_err}); trying official REST endpoint.")

                # 2. Resilient REST API fallback directly to Google's v1beta endpoint
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
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

                resp = requests.post(url, json=payload, timeout=self.timeout_seconds)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            text = parts[0].get("text", "").strip()
                            if text:
                                return LLMResponse(
                                    content=text,
                                    provider=self.name,
                                    model=self.model,
                                    success=True
                                )
                elif resp.status_code == 429:
                    last_error = f"Gemini Rate Limit (429): {resp.text[:120]}"
                else:
                    last_error = f"Gemini API returned status {resp.status_code}: {resp.text[:120]}"

            except requests.Timeout:
                last_error = f"Gemini request timed out after {self.timeout_seconds}s."
            except Exception as e:
                last_error = f"Gemini execution error: {str(e)}"

            if attempt < self.max_retries:
                time.sleep(1.0 * (attempt + 1))

        logger.warning(f"Gemini provider failed after {self.max_retries + 1} attempts: {last_error}")
        return LLMResponse(
            content="",
            provider=self.name,
            model=self.model,
            success=False,
            error=last_error
        )
