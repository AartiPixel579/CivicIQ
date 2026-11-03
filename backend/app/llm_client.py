"""
LLM Client for CivicIQ ("Your civic intelligence buddy")
Municipality: Township of Edison, New Jersey (Engineering Department)
Prioritizes Google Gemini, supports Groq / OpenAI-compatible fallback,
and provides transparent grounded retrieval fallback when offline.
"""

import os
import re
import logging
from typing import List, Optional, Dict
from .config import (
    LLM_PROVIDER, GEMINI_API_KEY, GEMINI_MODEL,
    GROQ_API_KEY, GROQ_BASE_URL, GROQ_MODEL,
    OPENAI_API_KEY, OPENAI_MODEL, MUNICIPALITY_NAME,
    OUT_OF_CONTEXT_MESSAGE
)
from .models import RagCitation

logger = logging.getLogger("llm_client")

def sanitize_contact_info(text: str) -> str:
    """Removes phone numbers, physical street addresses, and staff emails from text."""
    if not text:
        return text
    text = re.sub(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', '', text)
    text = re.sub(r'\b\d+\s+[A-Za-z0-9\s,]+(?:Blvd|Boulevard|St|Street|Ave|Avenue|Rd|Road|Dr|Drive)[A-Za-z0-9\s,]*\d{5}\b', 'the official municipal portal', text, flags=re.IGNORECASE)
    text = re.sub(r'100 Municipal Blvd[,\sA-Za-z0-9]*', 'the official municipal portal', text, flags=re.IGNORECASE)
    text = re.sub(r'\b[A-Za-z0-9._%+-]+@edisonnj\.(?:gov|org)\b', 'https://www.edisonnj.org/document_center/index.php', text)
    return text.strip()

MUNICIPAL_SYSTEM_PROMPT = f"""You are CivicIQ, your civic intelligence buddy for the {MUNICIPALITY_NAME} Department of Engineering.
You assist residents with municipal engineering inquiries: road opening permits, street excavations, tree removal clearances, sewer connections, and official permit flowcharts from edisonnj.org.

RULES:
1. Ground your answers strictly in the official municipal context and flowcharts provided.
2. If the user asks about topics outside Edison Engineering (such as animal shelter, health, clerk, elections, marriage, taxes, or general non-engineering questions), respond strictly with:
"{OUT_OF_CONTEXT_MESSAGE}"
3. Maintain conversation context from previous messages. If the user refers to "this", "it", or previous answers, take reference of the prior context to continue the procedure seamlessly.
4. TREE REMOVAL GUIDANCE (Official Edison Township Permit Flow Charts):
   - When the user asks for guidance with tree removal, ask if they currently have an approved permit.
   - If they reply 'No' and it is urgent / emergency / no time to ask for a permit: ask for the reason for urgency.
   - If the user provides a valid emergency reason (tree is dead, dying, cracked, leaning dangerously, or an imminent danger to life/property): instruct them that under the Edison Tree Removal Flow Chart, they should take photographic proof or obtain a certified arborist/forester letter stating the tree is dead/dying and an eminent danger, remove the tree immediately for safety, and submit for the permit concurrent to (or immediately following) the tree removal.
   - If non-emergency, check if part of a subdivision or requiring a demolition permit from Code; if yes, permit is required; if no, permit is NOT required.
5. STRICT PRIVACY & CONTACT RULE: Do NOT provide any physical street addresses, building counters, phone numbers, or staff emails to the user. Direct the user to the official municipal website: https://www.edisonnj.org/document_center/index.php.
6. Always maintain a friendly, helpful, and concise tone as a civic intelligence buddy.
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
                    f"Answer accurately using the context above. Do NOT include any phone numbers, physical street addresses, or staff emails; direct users only to the official website: https://www.edisonnj.org/document_center/index.php. If outside Engineering context, strictly output: {OUT_OF_CONTEXT_MESSAGE}"
                )
                contents.append({"role": "user", "parts": [current_prompt]})

                res = model.generate_content(contents)
                if res and res.text:
                    return sanitize_contact_info(res.text.strip())
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
                        f"Provide a clear, grounded answer. Do NOT include any phone numbers, physical street addresses, or staff emails. If outside Engineering, output: {OUT_OF_CONTEXT_MESSAGE}"
                    )
                })

                response = client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=0.1
                )
                answer = response.choices[0].message.content
                if answer and len(answer.strip()) > 10:
                    return sanitize_contact_info(answer.strip())
            except Exception as e:
                logger.warning(f"Groq/OpenAI completion failed ({e}); falling back.")

        # 3. Transparent grounded retrieval synthesis (Offline / Local Deterministic Fallback)
        primary = citations[0]
        cleaned_primary = sanitize_contact_info(primary.excerpt)
        paragraphs = [
            f"According to official **{MUNICIPALITY_NAME}** records for the {department_name} ({primary.title}):",
            "",
            f"> \"{cleaned_primary}\"",
            ""
        ]

        if len(citations) > 1:
            paragraphs.append("**Relevant Official Provisions:**")
            for c in citations[1:3]:
                cleaned_c = sanitize_contact_info(c.excerpt)
                paragraphs.append(f"• **[{c.title}]({c.url})**: {cleaned_c}")
            paragraphs.append("")

        paragraphs.append(
            f"**Official Source:** Verified from [{primary.title}]({primary.url}) "
            f"(Match relevance: {int(primary.relevance_score * 100)}%)."
        )

        return "\n".join(paragraphs)

llm_client = LLMClient()
