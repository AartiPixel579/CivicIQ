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

    def match_form(self, query: str, history: Optional[List[dict]] = None, include_internal: bool = False) -> Optional[FormRecommendation]:
        q = (query or "").lower().strip()
        context_text = q
        if history:
            for msg in history[-4:]:
                context_text += " " + msg.get("content", "").lower()

        # 0. Tree Removal Permit Application (Verified Official Form)
        is_tree_query = bool(re.search(r'\b(tree|trees|arborist|forester|sapling|stump|stumps|branch|branches)\b', q))
        in_tree_context = bool(re.search(r'\b(tree|trees|arborist|forester|sapling|stump|stumps|branch|branches)\b', context_text))
        is_other_explicit = any(w in q for w in ["road opening", "street opening", "saw-cut", "sewer", "soil import", "soil export", "site improvement", "zoning permit", "building permit"])
        if is_tree_query or (in_tree_context and not is_other_explicit):
            form = OFFICIAL_FORMS_REGISTRY["tree_removal"]
            score = 0.95 if is_tree_query else 0.85
            return FormRecommendation(
                form=form,
                confidence_score=score,
                reason="Matches official Edison Township Tree Permit Application (Removal / Replacement / Conservation) under Ordinance 25-3 & 25-8.",
                is_application_form=True,
                offer_conversational_fill=True
            )

        # 1. Road Opening / Street Excavation
        q_norm = q.replace("-", " ")
        ctx_norm = context_text.replace("-", " ")
        is_road_explicit = any(w in q_norm for w in [
            "road opening", "street opening", "pavement opening", "road excavation",
            "saw cut", "utility trench", "curb cut", "driveway apron",
            "pavement cut", "road open", "dig in street", "dig the street"
        ])
        if is_road_explicit or any(w in ctx_norm for w in [
            "road opening", "street opening", "pavement opening", "road excavation",
            "saw cut", "utility trench", "curb cut", "driveway apron", "road open", "dig in street"
        ]):
            form = OFFICIAL_FORMS_REGISTRY["road_opening"]
            score = 0.95 if is_road_explicit else 0.85
            return FormRecommendation(
                form=form,
                confidence_score=score,
                reason="Matches official Edison Township Road Opening & Pavement Excavation regulations.",
                is_application_form=True,
                offer_conversational_fill=True
            )

        # 2. Soil Importation Permit Application
        if any(w in context_text for w in ["soil import", "soil importation", "import soil", "importing soil", "fill dirt", "bring soil"]):
            form = OFFICIAL_FORMS_REGISTRY["soil_import"]
            score = 0.95 if any(w in q for w in ["soil import", "soil importation", "import soil"]) else 0.82
            return FormRecommendation(
                form=form,
                confidence_score=score,
                reason="Matches official Edison Township Soil Importation Permit Application.",
                is_application_form=True,
                offer_conversational_fill=True
            )

        # 3. Soil Exportation Permit Application
        if any(w in context_text for w in ["soil export", "soil exportation", "export soil", "exporting soil", "remove soil", "hauling soil"]):
            form = OFFICIAL_FORMS_REGISTRY["soil_export"]
            score = 0.95 if any(w in q for w in ["soil export", "soil exportation", "export soil"]) else 0.82
            return FormRecommendation(
                form=form,
                confidence_score=score,
                reason="Matches official Edison Township Soil Exportation Permit Application.",
                is_application_form=True,
                offer_conversational_fill=True
            )

        # 4. Site Improvement Permit Application with Checklist
        if any(w in context_text for w in ["site improvement", "site improvements", "sip application", "sip permit", "ground disturbance", "impervious surface", "site checklist"]):
            form = OFFICIAL_FORMS_REGISTRY["site_improvement"]
            score = 0.95 if any(w in q for w in ["site improvement", "sip"]) else 0.82
            return FormRecommendation(
                form=form,
                confidence_score=score,
                reason="Matches official Edison Township Site Improvement Permit Application with Checklist.",
                is_application_form=True,
                offer_conversational_fill=True
            )

        # 5. Sanitary Sewer Connection Charge
        if any(w in context_text for w in [
            "sewer connection", "sewer tap", "sanitary sewer", "sewer charge", "sewer application", "fixture unit"
        ]) and not any(w in context_text for w in ["tree", "soil", "dirt"]):
            form = OFFICIAL_FORMS_REGISTRY["sewer_connection"]
            score = 0.95 if any(w in q for w in ["sewer connection", "sewer tap"]) else 0.80
            return FormRecommendation(
                form=form,
                confidence_score=score,
                reason="Matches official Edison Township Sewer Utility tap-in and connection allocation.",
                is_application_form=True,
                offer_conversational_fill=True
            )

        # 6. General Residential Construction / Zoning Permit (Dwelling, Addition, Shed, Pool, Deck, Fence)
        if any(w in context_text for w in [
            "building permit", "zoning permit", "construction permit", "new home", "single family dwelling",
            "addition", "deck permit", "pool permit", "shed permit", "fence permit", "residential permit",
            "permit to build", "permit for deck", "permit for pool", "permit for addition"
        ]) and not any(w in context_text for w in ["tree", "soil", "dirt", "road opening", "street opening", "sewer", "site improvement"]):
            form = OFFICIAL_FORMS_REGISTRY["zoning_permit"]
            score = 0.92 if any(w in q for w in ["zoning permit", "building permit", "construction permit"]) else 0.78
            return FormRecommendation(
                form=form,
                confidence_score=score,
                reason="Matches official Edison Township Residential Permit & Zoning Application.",
                is_application_form=True,
                offer_conversational_fill=True
            )

        # 7. Check if query is strictly asking for a public reference document (e.g., fee schedule, setback sheet)
        if any(w in q for w in ["fee schedule", "how much is the fee", "zoning fees"]):
            doc = OFFICIAL_REFERENCE_DOCUMENTS["zoning_fees_schedule"]
            return FormRecommendation(
                form=doc,
                confidence_score=0.88,
                reason="Informational fee schedule under municipal Ordinance O.2158-2022.",
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

        # Internal Flowchart Reference (Restricted to internal lookups)
        if include_internal and any(w in q for w in ["flow chart", "flowchart"]):
            doc = OFFICIAL_REFERENCE_DOCUMENTS.get("permit_flow_charts")
            if doc:
                return FormRecommendation(
                    form=doc,
                    confidence_score=0.90,
                    reason="Internal municipal decision flow chart.",
                    is_application_form=False,
                    offer_conversational_fill=False
                )

        return None

form_matcher = FormMatcherService()
