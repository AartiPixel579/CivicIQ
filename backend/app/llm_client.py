"""
LLM Client for CivicIQ (Township of Edison, New Jersey)
Supports OpenAI, Google Gemini, and transparent grounded retrieval-only fallback.
Enforces strict municipal anti-hallucination guardrails and source citation.
"""

import os
import logging
from typing import List, Optional
from .config import (
    LLM_PROVIDER, OPENAI_API_KEY, OPENAI_MODEL,
    GEMINI_API_KEY, GEMINI_MODEL, MUNICIPALITY_NAME,
    MUNICIPAL_ADDRESS, ENGINEERING_PHONE, ENGINEERING_EMAIL
)
from .models import RagCitation

logger = logging.getLogger("llm_client")

MUNICIPAL_SYSTEM_PROMPT = f"""You are CivicIQ, the official AI resident services assistant for the {MUNICIPALITY_NAME}.
You help residents navigate actual municipal services, permits, and official procedures under municipal protocols.

STRICT OPERATIONAL RULES:
1. Ground your answers strictly in the retrieved official municipal context provided.
2. DO NOT hallucinate, fabricate, or assume fees, requirements, or department procedures.
3. Always cite the official document title and source link (e.g. https://www.edisonnj.org/...).
4. Direct residents to the verified submission desk: Edison Municipal Complex, {MUNICIPAL_ADDRESS}, or contact {ENGINEERING_EMAIL} / {ENGINEERING_PHONE}.
5. If the exact answer is not present in the provided municipal documents, state that clearly and provide the official contact desk.
6. Maintain a helpful, respectful, and authoritative tone suitable for government resident services.
"""

class LLMClient:
    def __init__(self):
        self.provider = LLM_PROVIDER
        self.openai_key = OPENAI_API_KEY or os.getenv("OPENAI_API_KEY", "")
        self.gemini_key = GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "")

    def _has_openai(self) -> bool:
        return bool(self.openai_key and len(self.openai_key) > 5)

    def _has_gemini(self) -> bool:
        return bool(self.gemini_key and len(self.gemini_key) > 5)

    def generate_answer(
        self,
        query: str,
        citations: List[RagCitation],
        department_name: str = "Engineering & Zoning"
    ) -> str:
        """
        Generates a grounded response using OpenAI, Gemini, or grounded retrieval synthesis.
        """
        if not citations:
            return (
                f"Under official municipal protocols for the **{MUNICIPALITY_NAME}**, "
                f"I only provide answers directly grounded in verified Township documentation.\n\n"
                f"I could not locate an official citation for **\"{query}\"** in our active {department_name} records.\n\n"
                f"**Official Inquiries & Assistance:**\n"
                f"• **Counter:** Division of Zoning & Engineering, Municipal Complex, {MUNICIPAL_ADDRESS}\n"
                f"• **Phone:** {ENGINEERING_PHONE}\n"
                f"• **Email:** {ENGINEERING_EMAIL}\n"
                f"• **Document Center:** [edisonnj.org/document_center](https://www.edisonnj.org/document_center/index.php)"
            )

        # Build context from top citations
        context_blocks = []
        for idx, c in enumerate(citations[:3]):
            context_blocks.append(
                f"[Source {idx+1}]: {c.title}\nURL: {c.url}\nCategory: {c.category}\nExcerpt: {c.excerpt}"
            )
        context_str = "\n\n".join(context_blocks)

        # 1. Try OpenAI if enabled
        if (self.provider in ["auto", "openai"]) and self._has_openai():
            try:
                import openai
                client = openai.OpenAI(api_key=self.openai_key)
                response = client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": MUNICIPAL_SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": f"Citizen Question: {query}\n\nOfficial Municipal Context:\n{context_str}\n\nProvide a concise, grounded answer citing the source URLs."
                        }
                    ],
                    temperature=0.1
                )
                answer = response.choices[0].message.content
                if answer and len(answer.strip()) > 20:
                    return answer.strip()
            except Exception as e:
                logger.warning(f"OpenAI completion failed ({e}); falling back.")

        # 2. Try Gemini if enabled
        if (self.provider in ["auto", "gemini"]) and self._has_gemini():
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.gemini_key)
                model = genai.GenerativeModel(GEMINI_MODEL, system_instruction=MUNICIPAL_SYSTEM_PROMPT)
                prompt = f"Citizen Question: {query}\n\nOfficial Municipal Context:\n{context_str}\n\nProvide a concise, grounded answer citing the source URLs."
                res = model.generate_content(prompt)
                if res and res.text:
                    return res.text.strip()
            except Exception as e:
                logger.warning(f"Gemini completion failed ({e}); falling back.")

        # 3. Transparent, high-fidelity grounded retrieval synthesis (Deterministic Fallback)
        primary = citations[0]
        paragraphs = [
            f"According to official **{MUNICIPALITY_NAME}** records for the {department_name} ({primary.title}):",
            "",
            f"> \"{primary.excerpt}\"",
            ""
        ]

        if len(citations) > 1:
            paragraphs.append("**Relevant Official Provisions & Guidelines:**")
            for c in citations[1:3]:
                paragraphs.append(f"• **[{c.title}]({c.url})** ({c.category}): {c.excerpt}")
            paragraphs.append("")

        paragraphs.append(
            f"**Official Source:** Verified from [{primary.title}]({primary.url}) "
            f"(Match relevance: {int(primary.relevance_score * 100)}%)."
        )

        return "\n".join(paragraphs)

llm_client = LLMClient()
