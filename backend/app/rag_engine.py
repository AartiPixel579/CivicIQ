import re
import logging
from typing import List, Optional, Tuple
from .vector_store import vector_store
from .department_loader import registry
from .models import RagCitation, RagResult

logger = logging.getLogger("rag_engine")

class GroundedRagEngine:
    def __init__(self):
        pass

    def answer_query(self, query: str, department_id: Optional[str] = None) -> RagResult:
        """
        Executes grounded retrieval from indexed client links.
        Ensures strict anti-hallucination compliance by refusing queries that do not match verified link content.
        """
        citations: List[RagCitation] = vector_store.search(
            query=query,
            department_id=department_id,
            top_k=3,
            threshold=0.10
        )

        dept_config = registry.get_department(department_id) if department_id else None
        dept_name = dept_config.name if dept_config else "the City Municipal Service Desk"
        desk_counter = dept_config.location.counter if dept_config else "the Public Service Counter"
        desk_phone = dept_config.contact.phone if dept_config else "(555) 019-4820"

        if not citations:
            fallback_answer = (
                f"Under strict municipal protocol, I only provide information directly verified in official "
                f"documentation links. I was unable to retrieve a verified citation for **\"{query}\"** in our "
                f"current {dept_name} knowledge base.\n\n"
                f"**Next Steps:**\n"
                f"• Please contact {dept_name} directly at **{desk_phone}**.\n"
                f"• Or visit **{desk_counter}** during regular municipal business hours.\n"
                f"• If you wish to apply for an official permit or license, you can initiate a structured application flow."
            )
            return RagResult(
                answer=fallback_answer,
                citations=[],
                grounded=False,
                query=query
            )

        # Synthesize grounded answer from top matching excerpts
        primary = citations[0]
        excerpts_text = "\n\n".join([f"• [{c.title}]: {c.excerpt}" for c in citations])

        # Generate a structured, professional, grounded response
        answer_parts = [
            f"According to official **{primary.department_id.capitalize()} Department** documentation retrieved from [{primary.title}]({primary.url}):",
            "",
            f"> \"{primary.excerpt}\"",
            ""
        ]

        if len(citations) > 1:
            answer_parts.append("**Additional Corroborating Municipal References:**")
            for c in citations[1:]:
                answer_parts.append(f"• **[{c.title}]({c.url})** ({c.category}): {c.excerpt}")
            answer_parts.append("")

        answer_parts.append(
            f"*Citation Source: Verified official municipal document from {primary.url} (Match relevance: {int(primary.relevance_score * 100)}%).*"
        )

        full_answer = "\n".join(answer_parts)

        return RagResult(
            answer=full_answer,
            citations=citations,
            grounded=True,
            query=query
        )

    def detect_flow_intent(self, user_text: str, department_id: Optional[str] = None) -> Optional[Tuple[str, str]]:
        """
        Detects if user intent is procedural (starting a workflow or applying for a permit/license).
        Returns (department_id, flow_id) if matched, else None.
        Disambiguates from informational inquiries ("what is", "how much", "setback", etc.).
        """
        text = user_text.lower().strip()
        
        # If question starts with or strongly indicates informational query, let RAG handle it
        info_starters = ["what is", "what are", "how much", "how do i know", "tell me about", "regulations for", "guidelines for", "explain", "distance", "feet", "fee schedule"]
        if any(text.startswith(s) or s in text for s in info_starters) and not any(a in text for a in ["apply", "start", "begin", "initiate", "fill out", "issue form"]):
            return None

        # Action intent check for Engineering: residential building permit
        if any(k in text for k in [
            "apply for building permit", "apply for residential permit", "need building permit", 
            "start building permit", "get building permit", "apply for permit", "build a house permit",
            "addition permit application", "eng-204 application", "apply for addition"
        ]) or (text in ["residential permit", "building permit", "flow-eng-01", "eng-204"]):
            return ("engineering", "residential_building_permit")

        # Action intent check for Engineering: excavation / road opening
        if any(k in text for k in [
            "apply for excavation", "need excavation permit", "street opening permit", 
            "road cut permit", "dig permit application", "trenching permit", "eng-102 application",
            "apply for right of way", "curb cut application"
        ]) or (text in ["excavation permit", "road permit", "flow-eng-02", "eng-102"]):
            return ("engineering", "road_excavation_permit")

        # Action intent check for Healthcare: food establishment license
        if any(k in text for k in [
            "apply for food license", "need restaurant permit", "open restaurant license", 
            "commercial kitchen permit application", "apply for café license", "hlt-101 application",
            "food safety license application", "get food license"
        ]) or (text in ["food license", "restaurant license", "flow-hlt-01", "hlt-101"]):
            return ("healthcare", "food_establishment_license")

        # Action intent check for Healthcare: mobile food truck
        if any(k in text for k in [
            "apply for food truck permit", "need food truck license", "mobile cart permit application",
            "pushcart license", "hlt-202 application", "food truck license application"
        ]) or (text in ["food truck permit", "mobile food permit", "flow-hlt-02", "hlt-202"]):
            return ("healthcare", "mobile_food_vendor_sanitation_permit")

        return None

rag_engine = GroundedRagEngine()
