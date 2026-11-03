"""
LLM Client for CivicIQ ("Your civic intelligence buddy")
Municipality: Township of Edison, New Jersey (Engineering Department)
Prioritizes Google Gemini, supports Groq / OpenAI-compatible fallback,
and provides transparent grounded retrieval fallback when offline.
"""

import os
import logging
from typing import List, Optional, Dict
from .config import (
    LLM_PROVIDER, GEMINI_API_KEY, GEMINI_MODEL,
    GROQ_API_KEY, GROQ_BASE_URL, GROQ_MODEL,
    OPENAI_API_KEY, OPENAI_MODEL, MUNICIPALITY_NAME,
    MUNICIPAL_ADDRESS, ENGINEERING_PHONE, ENGINEERING_EMAIL,
    OUT_OF_CONTEXT_MESSAGE
)
from .models import RagCitation

logger = logging.getLogger("llm_client")

MUNICIPAL_SYSTEM_PROMPT = f"""You are CivicIQ, your civic intelligence buddy for the {MUNICIPALITY_NAME} Department of Engineering.
You assist residents with municipal engineering inquiries: road opening permits, street excavations, tree removal clearances, sewer connections, and engineering documents from edisonnj.org.

RULES:
1. Ground your answers strictly in the official municipal context provided.
2. If the user asks about topics outside Edison Engineering (or other departments like animal shelter, health, clerk, marriage, taxes, or general non-engineering questions), respond with:
"{OUT_OF_CONTEXT_MESSAGE}"
3. Maintain conversation context from previous messages. If the user refers to "this", "it", or "the permit" discussed earlier, use the conversation history to understand what they are referring to.
4. Always maintain a friendly, helpful, and concise tone as a civic intelligence buddy.
5. Do not invent fees or requirements. Cite official source URLs from edisonnj.org.
"""

class LLMClient:
    def __init__(self):
        self.provider = LLM_PROVIDER
        self.gemini_key = GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "")
        self.groq_key = GROQ_API_KEY or os.getenv("GROQ_API_KEY", os.getenv("OPENAI_API_KEY", ""))
        self.openai_key = OPENAI_API_KEY or os.getenv("OPENAI_API_KEY", "")

    def _has_gemini(self) -> bool:
        return bool(self.gemini_key and len(self.gemini_key) > 5)

    def _has_groq(self) -> bool:
        return bool(self.groq_key and len(self.groq_key) > 5)

    def _has_openai(self) -> bool:
        return bool(self.openai_key and len(self.openai_key) > 5)

    def generate_answer(
        self,
        query: str,
        citations: List[RagCitation],
        history: Optional[List[Dict[str, str]]] = None,
        department_name: str = "Department of Engineering"
    ) -> str:
        """
        Generates a grounded response using Gemini (preferred), Groq (alternate),
        OpenAI, or transparent grounded retrieval synthesis.
        """
        if not citations:
            return OUT_OF_CONTEXT_MESSAGE

        # Build context from top citations
        context_blocks = []
        for idx, c in enumerate(citations[:3]):
            context_blocks.append(
                f"[Source {idx+1}]: {c.title}\nURL: {c.url}\nExcerpt: {c.excerpt}"
            )
        context_str = "\n\n".join(context_blocks)

        # 1. Preferred: Google Gemini API (Fast & High-fidelity)
        if (self.provider in ["auto", "gemini"]) and self._has_gemini():
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.gemini_key)
                model = genai.GenerativeModel(GEMINI_MODEL, system_instruction=MUNICIPAL_SYSTEM_PROMPT)

                # Format conversation history for Gemini
                contents = []
                if history:
                    for h in history[-6:]: # Last 3 turns
                        role = "user" if h.get("role") == "user" else "model"
                        contents.append({"role": role, "parts": [h.get("content", "")]})

                current_prompt = (
                    f"Official Municipal Context:\n{context_str}\n\n"
                    f"Citizen Question: {query}\n\n"
                    f"Answer accurately using the context above. If outside Engineering context, output: {OUT_OF_CONTEXT_MESSAGE}"
                )
                contents.append({"role": "user", "parts": [current_prompt]})

                res = model.generate_content(contents)
                if res and res.text:
                    return res.text.strip()
            except Exception as e:
                logger.warning(f"Gemini API call failed ({e}); checking fallback.")

        # 2. Alternate: Groq API (Ultra-fast OpenAI-compatible endpoint)
        if (self.provider in ["auto", "groq", "openai"]) and self._has_groq():
            try:
                import openai
                client = openai.OpenAI(
                    api_key=self.groq_key,
                    base_url=GROQ_BASE_URL if "groq" in self.groq_key.lower() or "gsk_" in self.groq_key else None
                )
                model_name = GROQ_MODEL if "groq" in self.groq_key.lower() or "gsk_" in self.groq_key else OPENAI_MODEL

                messages = [{"role": "system", "content": MUNICIPAL_SYSTEM_PROMPT}]
                if history:
                    for h in history[-6:]:
                        messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})

                messages.append({
                    "role": "user",
                    "content": (
                        f"Official Municipal Context:\n{context_str}\n\n"
                        f"Citizen Question: {query}\n\n"
                        f"Provide a clear, grounded answer. If outside Engineering, output: {OUT_OF_CONTEXT_MESSAGE}"
                    )
                })

                response = client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=0.1
                )
                answer = response.choices[0].message.content
                if answer and len(answer.strip()) > 10:
                    return answer.strip()
            except Exception as e:
                logger.warning(f"Groq/OpenAI completion failed ({e}); falling back.")

        # 3. Transparent grounded retrieval synthesis (Offline / Local Deterministic Fallback)
        primary = citations[0]
        paragraphs = [
            f"According to official **{MUNICIPALITY_NAME}** records for the {department_name} ({primary.title}):",
            "",
            f"> \"{primary.excerpt}\"",
            ""
        ]

        if len(citations) > 1:
            paragraphs.append("**Relevant Official Provisions:**")
            for c in citations[1:3]:
                paragraphs.append(f"• **[{c.title}]({c.url})**: {c.excerpt}")
            paragraphs.append("")

        paragraphs.append(
            f"**Official Source:** Verified from [{primary.title}]({primary.url}) "
            f"(Match relevance: {int(primary.relevance_score * 100)}%)."
        )

        return "\n".join(paragraphs)

llm_client = LLMClient()
