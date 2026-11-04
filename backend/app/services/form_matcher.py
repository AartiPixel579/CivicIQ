import re
import logging
from typing import List, Optional, Tuple
from .form_schema_service import OFFICIAL_FORMS_REGISTRY, OFFICIAL_REFERENCE_DOCUMENTS, FormSchemaService
from ..models.form import FormMetadata, FormRecommendation

logger = logging.getLogger("services.form_matcher")

class FormMatcherService:
    """
    Intelligent Form Identification Service:
    - Distinguishes Application Forms from Info Sheets, Fee Schedules, and Flowcharts.
    - Confidence-based intent matching against official Edison Township forms.
    - Never hallucinates non-existent forms.
    - Offers conversational form-filling only for verified application forms.
    """

    def match_form(self, query: str, history: Optional[List[dict]] = None) -> Optional[FormRecommendation]:
        q = (query or "").lower().strip()
        context_text = q
        if history:
            for msg in history[-4:]:
                context_text += " " + msg.get("content", "").lower()

        # 1. Road Opening / Street Excavation
        if any(w in context_text for w in [
            "road opening", "street opening", "excavat", "saw-cut", "trench",
            "curb cut", "driveway apron", "pavement opening", "road open", "dig in street"
        ]):
            form = OFFICIAL_FORMS_REGISTRY["road_opening"]
            score = 0.95 if any(w in q for w in ["road opening", "street opening", "excavat"]) else 0.85
            return FormRecommendation(
                form=form,
                confidence_score=score,
                reason="Matches official Edison Township Road Opening & Pavement Excavation regulations.",
                is_application_form=True,
                offer_conversational_fill=True
            )

        # 2. Tree Removal Clearance / Permit
        if any(w in context_text for w in [
            "tree removal", "remove a tree", "cut tree", "cut down tree", "hazardous tree",
            "dead tree", "dying tree", "tree permit", "tree clearance", "removing tree"
        ]):
            form = OFFICIAL_FORMS_REGISTRY["tree_removal"]
            score = 0.95 if any(w in q for w in ["tree removal", "remove a tree", "tree permit"]) else 0.82
            return FormRecommendation(
                form=form,
                confidence_score=score,
                reason="Matches official Edison Township Tree Protection (Chapter 34) and Permit Flow Chart.",
                is_application_form=True,
                offer_conversational_fill=True
            )

        # 3. Sanitary Sewer Connection Charge
        if any(w in context_text for w in [
            "sewer connection", "sewer tap", "sanitary sewer", "sewer charge", "sewer application", "fixture unit"
        ]):
            form = OFFICIAL_FORMS_REGISTRY["sewer_connection"]
            score = 0.95 if any(w in q for w in ["sewer connection", "sewer tap"]) else 0.80
            return FormRecommendation(
                form=form,
                confidence_score=score,
                reason="Matches official Edison Township Sewer Utility tap-in and connection allocation.",
                is_application_form=True,
                offer_conversational_fill=True
            )

        # 4. General Residential Construction / Zoning Permit (Dwelling, Addition, Shed, Pool, Deck, Fence)
        if any(w in context_text for w in [
            "building permit", "zoning permit", "construction permit", "new home", "single family dwelling",
            "addition", "deck permit", "pool permit", "shed permit", "fence permit", "residential permit",
            "permit to build", "permit for deck", "permit for pool", "permit for addition"
        ]):
            form = OFFICIAL_FORMS_REGISTRY["zoning_permit"]
            score = 0.92 if any(w in q for w in ["zoning permit", "building permit", "construction permit"]) else 0.78
            return FormRecommendation(
                form=form,
                confidence_score=score,
                reason="Matches official Edison Township Residential Permit & Zoning Application.",
                is_application_form=True,
                offer_conversational_fill=True
            )

        # 5. Check if query is strictly asking for a reference document (e.g., fee schedule, setback sheet, flowcharts)
        # These are NOT application forms and must not offer conversational filling!
        if any(w in q for w in ["fee schedule", "how much is the fee", "zoning fees"]):
            doc = OFFICIAL_REFERENCE_DOCUMENTS["zoning_fees_schedule"]
            return FormRecommendation(
                form=doc,
                confidence_score=0.88,
                reason="Informational fee schedule under municipal Ordinance O.2158-2022.",
                is_application_form=False,
                offer_conversational_fill=False
            )

        if any(w in q for w in ["flow chart", "flowchart", "decision tree", "permit flow"]):
            doc = OFFICIAL_REFERENCE_DOCUMENTS["permit_flow_charts"]
            return FormRecommendation(
                form=doc,
                confidence_score=0.90,
                reason="Official municipal permit decision flowcharts.",
                is_application_form=False,
                offer_conversational_fill=False
            )

        if any(w in q for w in ["schedule a", "setback distance", "yard requirements", "bulk requirements"]):
            doc = OFFICIAL_REFERENCE_DOCUMENTS["schedule_a_yard"]
            return FormRecommendation(
                form=doc,
                confidence_score=0.85,
                reason="Schedule A bulk yard dimensions table.",
                is_application_form=False,
                offer_conversational_fill=False
            )

        return None

form_matcher = FormMatcherService()
