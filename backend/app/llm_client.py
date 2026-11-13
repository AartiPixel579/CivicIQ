"""
LLM Client for CivicIQ ("Your Edison Township Buddy")
Municipality: Township of Edison, New Jersey (Engineering Department)
Uses free-first provider architecture: Gemini (Primary) -> Groq (Fallback)
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


_RAW_METADATA_KEY_RE = re.compile(
    r'(?:^|\n|\s{2,})(?:DOCUMENT|MUNICIPALITY|DEPARTMENT|DOCUMENT TYPE|SERVICE|OFFICIAL URL|SUBMISSION INTAKE|FEE STRUCTURE|OFFICIAL SUMMARY|PDF PAGE)\s*:[^\n]*(?=\s{2,}(?:DOCUMENT|MUNICIPALITY|DEPARTMENT|DOCUMENT TYPE|SERVICE|OFFICIAL URL|SUBMISSION INTAKE|FEE STRUCTURE|OFFICIAL SUMMARY|PDF PAGE)\s*:|$|\n)',
    flags=re.IGNORECASE,
)


def strip_raw_metadata(text: str, title: str = "") -> str:
    """
    Removes internal ingestion metadata headers (DOCUMENT:, MUNICIPALITY:, FEE STRUCTURE:, etc.)
    so raw chunk metadata is never exposed to residents or treated as verified rule text.
    """
    if not text:
        return ""
    cleaned = _RAW_METADATA_KEY_RE.sub(" ", text)
    cleaned = re.sub(r'\s*\[Page\s+\d+\]\s*', ' ', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    if not cleaned or len(cleaned) < 15:
        label = title or "this official document"
        return (
            f"The official {label} is available for download, but machine-readable text could not be "
            f"extracted from this scanned PDF to verify specific fees or requirements."
        )
    return cleaned

MUNICIPAL_SYSTEM_PROMPT = f"""You are {APP_NAME}, {APP_TAGLINE} for the {MUNICIPALITY_NAME} Department of Engineering.
You assist residents with municipal engineering inquiries: road opening permits, street excavations, tree removal clearances, soil importation/exportation, site improvements, and official permit procedures from edisonnj.org.

RULES:
1. Ground your answers STRICTLY in the official municipal context and retrieved source documents provided.
2. ANTI-HALLUCINATION RULE: Never invent or guess filing fees, processing times, permit requirements, eligibility conditions, legal rules, ordinances, or emergency procedures. Only state specific municipal facts that appear in the provided official sources. If the provided documents do not contain a requested fact, explicitly state that the detail could not be verified from the available official documents.
3. DISTINGUISH OFFICIAL FACTS FROM GENERAL EXPLANATIONS: Clearly label official municipal requirements with their source citation (document title, URL, and PDF page number when available), separate from any brief general explanation.
4. CONCISENESS & PROGRESSIVE DISCLOSURE:
   - Answer ONLY what the resident asked. Be brief, specific, and actionable.
   - For procedural answers: Provide 2–4 concise sentences or numbered steps. Do NOT dump unrequested fee schedules, checklists, survey maps, submission addresses, or turnaround times.
   - For specific inquiries (fees, checklist, turnaround, submission): Answer only that detail directly.
5. If the user asks about topics outside Edison Engineering (such as animal shelter, health, clerk, elections, marriage, taxes, or general non-engineering questions), respond strictly with:
"{OUT_OF_CONTEXT_MESSAGE}"
6. Maintain conversation context from previous messages. If the user refers to "this", "it", or previous answers, take reference of the prior context to continue the procedure seamlessly.
7. STRICT PRIVACY & CONTACT RULE: Do NOT provide any physical street addresses, building counters, phone numbers, or staff emails to the user unless specifically asked for submission location, and always direct users to the official municipal website: https://www.edisonnj.org/document_center/index.php.
8. Always maintain a friendly, helpful, and professional tone as Your Edison Township Buddy.
9. INTERNAL KNOWLEDGE RULE: Do not cite, link, or mention internal flowcharts or internal decision tree documents to the resident. Always provide public application forms and guidelines. Never repeat raw metadata labels such as DOCUMENT:, MUNICIPALITY:, DEPARTMENT:, FEE STRUCTURE:, or SUBMISSION INTAKE: in your response.
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
        Generates a grounded response using LLMProviderManager (Gemini -> Groq)
        with transparent grounded retrieval synthesis fallback when providers are offline/unconfigured.
        """
        if not citations:
            return OUT_OF_CONTEXT_MESSAGE

        # Build context from top citations with provenance (never expose raw metadata headers)
        context_blocks = []
        for idx, c in enumerate(citations[:4]):
            page_info = f"\nPDF Page: {c.pdf_page_number}" if getattr(c, "pdf_page_number", None) else ""
            clean_excerpt = strip_raw_metadata(c.excerpt, title=c.title)
            context_blocks.append(
                f"[Source {idx+1}]: {c.title}\nURL: {c.url}{page_info}\nExcerpt: {clean_excerpt}"
            )
        context_str = "\n\n".join(context_blocks)

        prompt = (
            f"Official Municipal Context:\n{context_str}\n\n"
            f"Citizen Question: {query}\n\n"
            f"Answer accurately using ONLY the verified official sources above. "
            f"Cite the source document title and URL (and PDF page number if provided) for official facts, "
            f"and clearly separate verified official facts from any general explanation. "
            f"If the provided documents do not verify a requested fee, timeline, or rule, explicitly state that it could not be verified from the available official documents. "
            f"Do NOT include any phone numbers, physical street addresses, or staff emails; direct users only to the official website: https://www.edisonnj.org/document_center/index.php. "
            f"If outside Engineering context, strictly output: {OUT_OF_CONTEXT_MESSAGE}"
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
        cleaned_primary = sanitize_contact_info(strip_raw_metadata(primary.excerpt, title=primary.title)).strip()

        # 1. Direct answer in the first sentence
        parts = re.split(r'(?<=[.!?])\s+', cleaned_primary)
        first_sentence = parts[0].strip() if parts else cleaned_primary
        if not first_sentence.endswith((".", "!", "?")):
            first_sentence += "."

        paragraphs = [first_sentence]

        # 2. Short scannable bullet points for subsequent provisions or other citations
        bullets = []
        if len(parts) > 1:
            for p in parts[1:3]:
                clean_p = p.strip()
                if len(clean_p) > 10:
                    bullets.append(f"• {clean_p}")

        if len(citations) > 1:
            for c in citations[1:3]:
                c_clean = sanitize_contact_info(strip_raw_metadata(c.excerpt, title=c.title)).strip()
                c_parts = re.split(r'(?<=[.!?])\s+', c_clean)
                c_first = c_parts[0].strip() if c_parts else c_clean
                if c_first and len(c_first) > 10:
                    bullets.append(f"• **{c.title}**: {c_first}")

        if bullets:
            paragraphs.append("")
            paragraphs.extend(bullets[:4])

        # 3. Compact, clickable source reference linked to official document
        paragraphs.append("")
        paragraphs.append(f"Source: [{primary.title}]({primary.url})")

        return "\n".join(paragraphs)

llm_client = LLMClient()
