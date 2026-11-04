"""
LLM Client for CivicIQ ("Mushkil Your Edison Township Buddy")
Municipality: Township of Edison, New Jersey (Engineering Department)
Uses free-first provider architecture: Gemini (Primary) -> Groq (First Backup) -> OpenRouter (Free Only)
Provides transparent grounded retrieval fallback when offline.
"""

import os
import re
import logging
from typing import List, Optional, Dict
from .config import (
    MUNICIPALITY_NAME, OUT_OF_CONTEXT_MESSAGE, APP_NAME, APP_TAGLINE
)
from .models import RagCitation
from .llm_provider.manager import llm_manager

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

MUNICIPAL_SYSTEM_PROMPT = f"""You are {APP_NAME}, {APP_TAGLINE} for the {MUNICIPALITY_NAME} Department of Engineering.
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
6. Always maintain a friendly, helpful, and professional tone as Mushkil Your Edison Township Buddy.
"""

class LLMClient:
    def __init__(self):
        self.manager = llm_manager

    def generate_answer(
        self,
        query: str,
        citations: List[RagCitation],
        history: Optional[List[Dict[str, str]]] = None,
        department_name: str = "Department of Engineering"
    ) -> str:
        """
        Generates a grounded response using LLMProviderManager (Gemini -> Groq -> OpenRouter)
        with transparent grounded retrieval synthesis fallback when providers are offline/unconfigured.
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

        prompt = (
            f"Official Municipal Context:\n{context_str}\n\n"
            f"Citizen Question: {query}\n\n"
            f"Answer accurately using the context above. Do NOT include any phone numbers, physical street addresses, or staff emails; direct users only to the official website: https://www.edisonnj.org/document_center/index.php. If outside Engineering context, strictly output: {OUT_OF_CONTEXT_MESSAGE}"
        )

        # 1. Attempt LLM generation through free-first Provider Manager
        resp = self.manager.generate(
            prompt=prompt,
            system_prompt=MUNICIPAL_SYSTEM_PROMPT,
            history=history,
            temperature=0.1,
            max_tokens=1000
        )

        if resp.success and resp.content and len(resp.content.strip()) > 10:
            return sanitize_contact_info(resp.content.strip())

        # 2. Transparent grounded retrieval synthesis (Offline / Local Deterministic Fallback)
        logger.info("Using transparent grounded retrieval synthesis fallback.")
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
