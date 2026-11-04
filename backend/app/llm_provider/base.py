from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field

class LLMResponse(BaseModel):
    content: str
    provider: str
    model: str
    success: bool
    is_fallback: bool = False
    error: Optional[str] = None
    finish_reason: Optional[str] = None

class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers in CivicIQ."""

    def __init__(self, name: str, model: str, api_key: str = "", timeout_seconds: int = 30, max_retries: int = 2):
        self.name = name
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if provider has valid credentials and is enabled."""
        pass

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        history: Optional[List[Dict[str, str]]] = None,
        temperature: float = 0.1,
        max_tokens: int = 1000
    ) -> LLMResponse:
        """Generates completion for given prompt and history."""
        pass

    def get_provider_info(self) -> Dict[str, Any]:
        """Returns safe provider metadata without exposing secrets."""
        return {
            "provider": self.name,
            "model": self.model,
            "available": self.is_available(),
            "has_key": bool(self.api_key and len(self.api_key) > 5)
        }
