"""
Service-Aware Intent Detection Service for Edison Township Engineering
Identifies the canonical municipal engineering service for citizen inquiries,
computes confidence scores, resolves ambiguity, and routes to appropriate
procedural workflows or general grounded guidance.
"""

import re
import logging
from typing import List, Dict, Optional, Tuple
from pydantic import BaseModel, Field

logger = logging.getLogger("services.service_intent")


class ServiceIntentResult(BaseModel):
    service_id: str
    service_name: str
    confidence: float
    is_ambiguous: bool = False
    clarifying_question: Optional[str] = None
    intent_type: str = "procedure_inquiry"  # "procedure_inquiry" | "form_request" | "general_info"
    has_flowchart: bool = False
    flow_id: Optional[str] = None
    official_form_id: Optional[str] = None
    official_form_file: Optional[str] = None


# Canonical service definitions with metadata
CANONICAL_SERVICES = {
    "tree_removal": {
        "name": "Tree Removal & Preservation",
        "has_flowchart": True,
        "flow_id": "tree_removal_flow",
        "form_id": "tree_removal",
        "form_file": "3.23.21 tree permit application.pdf",
        "keywords": [
            "tree", "trees", "arborist", "forester", "stump", "sapling",
            "dead tree", "dying tree", "falling tree", "remove tree", "cut tree",
            "cutting down a tree", "tree permit", "tree removal"
        ]
    },
    "soil_import": {
        "name": "Soil Importation",
        "has_flowchart": True,
        "flow_id": "soil_import_export_flow",
        "form_id": "soil_import",
        "form_file": "Forms_Soil_Importation_Appl.pdf",
        "keywords": [
            "import soil", "importing soil", "bring soil", "bringing soil",
            "deliver soil", "delivering soil", "bring dirt", "fill dirt",
            "hauling in dirt", "bring topsoil", "import fill", "fill my yard",
            "bring clean fill", "import clean fill", "receive soil", "add soil"
        ]
    },
    "soil_export": {
        "name": "Soil Exportation",
        "has_flowchart": True,
        "flow_id": "soil_import_export_flow",
        "form_id": "soil_export",
        "form_file": "Forms_Soil_Exportation_App.pdf",
        "keywords": [
            "export soil", "exporting soil", "remove soil", "removing soil",
            "take away dirt", "haul away soil", "hauling soil", "haul soil away",
            "excess soil off site", "remove dirt", "export dirt", "haul away dirt",
            "digging foundation export", "cart away soil", "cart soil"
        ]
    },
    "soil_movement": {
        "name": "Soil Movement (Ambiguous Import/Export)",
        "has_flowchart": True,
        "flow_id": "soil_import_export_flow",
        "form_id": None,
        "form_file": None,
        "keywords": [
            "soil permit", "soil regulations", "moving soil", "soil movement",
            "dirt regulations", "soil disturbance", "fill regulations", "soil rules"
        ]
    },
    "road_opening": {
        "name": "Street Opening & Road Excavation",
        "has_flowchart": True,
        "flow_id": "street_opening_flow",
        "form_id": "road_opening",
        "form_file": "RoadOpenApp.pdf",
        "keywords": [
            "road opening", "street opening", "excavat", "saw-cut", "saw cut",
            "pavement cut", "utility trench", "trench road", "curb cut",
            "driveway apron in right of way", "dig in street", "dig the street",
            "cut the sidewalk", "excavate driveway", "public right of way",
            "cut pavement", "trenching"
        ]
    },
    "site_improvement": {
        "name": "Site Improvement & Grading",
        "has_flowchart": True,
        "flow_id": "site_improvement_flow",
        "form_id": "site_improvement",
        "form_file": "SIP_Application.pdf",
        "keywords": [
            "site improvement", "site improvements", "sip application", "sip permit",
            "improve my property", "improving my property", "property improvement",
            "impervious coverage", "impervious surface", "ground disturbance",
            "disturb ground", "disturbing ground", "site disturbance", "grading plan",
            "drainage improvement", "site checklist", "stormwater runoff"
        ]
    },
    "zoning": {
        "name": "Residential Construction & Zoning",
        "has_flowchart": True,
        "flow_id": "residential_zoning_permit_flow",
        "form_id": "zoning_permit",
        "form_file": "Zoning_Permit_Application_Edison.pdf",
        "keywords": [
            "zoning permit", "zoning application", "construct an addition", "addition",
            "new house", "new home", "single family dwelling", "build a house",
            "swimming pool", "inground pool", "above ground pool", "deck permit",
            "build a deck", "open deck", "shed permit", "storage shed", "fence permit",
            "residential fence", "detached garage", "setbacks", "schedule a"
        ]
    },
    "sewer_connection": {
        "name": "Sanitary Sewer Connection",
        "has_flowchart": True,
        "flow_id": "sewer_connection_flow",
        "form_id": "sewer_connection",
        "form_file": "Sewer_Connection_Charge_Applications.pdf",
        "keywords": [
            "sewer connection", "sewer tap", "sanitary sewer", "sewer lateral",
            "fixture unit", "sewer charge", "connect to sewer", "sewer utility"
        ]
    }
}

OUT_OF_CONTEXT_PATTERNS = [
    r'\b(cat|cats|dog|dogs|pet|pets|animal|animals|adopt|adoption|kitten|kittens|puppy|puppies|shelter|rabies|spay|neuter)\b',
    r'\b(restaurant|food|kitchen|vital statistics|birth certificate|death certificate|marriage license|marriage)\b',
    r'\b(election|elections|voting|voter|ballot|council minutes|landlord|charity|bingo|tax|taxes|assessor)\b',
    r'\b(police|fire|court|ticket|parking ticket|traffic ticket|library|school|schools)\b',
    r'\b(quantum|fusion|space shuttle|orbital|rocket|astronomy)\b'
]


class ServiceIntentService:
    """
    Intelligent municipal intent detection layer.
    Classifies natural language user queries into canonical municipal services.
    """

    def detect_intent(
        self,
        query: str,
        history: Optional[List[Dict[str, str]]] = None
    ) -> ServiceIntentResult:
        q = (query or "").lower().strip()
        
        # 1. Out-of-context check
        for pat in OUT_OF_CONTEXT_PATTERNS:
            if re.search(pat, q):
                return ServiceIntentResult(
                    service_id="out_of_context",
                    service_name="Out of Engineering Context",
                    confidence=1.0,
                    is_ambiguous=False,
                    intent_type="general_info",
                    has_flowchart=False
                )

        # 2. Check for form download / application request intent
        has_form_keyword = bool(re.search(r'\b(form|application|pdf|packet|download|checklist)\b', q))
        intent_type = "form_request" if has_form_keyword else "procedure_inquiry"

        # 3. Contextual expansion from conversation history
        context_text = q
        if history:
            for msg in history[-4:]:
                context_text += " " + msg.get("content", "").lower()

        # 4. Service-specific matching with priority rules
        
        # A. Soil Importation (Explicit)
        is_soil_import_explicit = any(phrase in q for phrase in [
            "import soil", "importing soil", "bring soil", "bringing soil",
            "deliver soil", "bring dirt", "fill dirt", "hauling in dirt",
            "bring topsoil", "import fill", "fill my yard", "bring clean fill",
            "how to import soil", "want to import soil", "need to import soil"
        ])
        # Also check volume mention with soil
        is_soil_import_volume = ("soil" in q or "dirt" in q or "fill" in q) and any(w in q for w in ["bring", "import", "deliver", "into", "onto", "fill"])
        if is_soil_import_explicit or is_soil_import_volume:
            return ServiceIntentResult(
                service_id="soil_import",
                service_name="Soil Importation",
                confidence=0.95 if is_soil_import_explicit else 0.85,
                is_ambiguous=False,
                intent_type=intent_type,
                has_flowchart=True,
                flow_id="soil_import_export_flow",
                official_form_id="soil_import",
                official_form_file="Forms_Soil_Importation_Appl.pdf"
            )

        # B. Soil Exportation (Explicit)
        is_soil_export_explicit = any(phrase in q for phrase in [
            "export soil", "exporting soil", "remove soil", "removing soil",
            "take away dirt", "haul away soil", "hauling soil", "haul soil away",
            "excess soil off site", "remove dirt", "export dirt", "haul away dirt",
            "digging foundation export", "cart away soil", "how to export soil",
            "want to export soil", "need to export soil"
        ])
        is_soil_export_volume = ("soil" in q or "dirt" in q) and any(w in q for w in ["remove", "export", "haul away", "off site", "take away", "cart"])
        if is_soil_export_explicit or is_soil_export_volume:
            return ServiceIntentResult(
                service_id="soil_export",
                service_name="Soil Exportation",
                confidence=0.95 if is_soil_export_explicit else 0.85,
                is_ambiguous=False,
                intent_type=intent_type,
                has_flowchart=True,
                flow_id="soil_import_export_flow",
                official_form_id="soil_export",
                official_form_file="Forms_Soil_Exportation_App.pdf"
            )

        # C. Soil Movement Ambiguous (User mentions soil/dirt without specifying import vs export)
        is_soil_ambiguous = any(phrase in q for phrase in [
            "soil permit", "soil regulations", "moving soil", "soil movement",
            "dirt regulations", "soil rules", "how to move soil", "regulations for soil"
        ]) or (("soil" in q or "dirt" in q) and any(w in q for w in ["permit", "requirement", "rule", "procedure", "guidance"]) and not any(w in q for w in ["tree", "plant", "garden"]))
        if is_soil_ambiguous:
            return ServiceIntentResult(
                service_id="soil_movement",
                service_name="Soil Movement (Import / Export)",
                confidence=0.88,
                is_ambiguous=True,
                clarifying_question=(
                    "I can help you understand the Township of Edison's soil regulations.\n\n"
                    "First, **are you planning to bring soil onto your property (Soil Import) or remove soil from your property (Soil Export)?**"
                ),
                intent_type=intent_type,
                has_flowchart=True,
                flow_id="soil_import_export_flow"
            )

        # D. Tree Removal
        is_tree_explicit = bool(re.search(r'\b(tree|trees|arborist|forester|sapling|stump|stumps|subdivision|demolition)\b', q))
        if is_tree_explicit:
            return ServiceIntentResult(
                service_id="tree_removal",
                service_name="Tree Removal & Preservation",
                confidence=0.95,
                is_ambiguous=False,
                intent_type=intent_type,
                has_flowchart=True,
                flow_id="tree_removal_flow",
                official_form_id="tree_removal",
                official_form_file="3.23.21 tree permit application.pdf"
            )

        # E. Road Opening / Street Excavation
        is_road_explicit = any(phrase in q for phrase in [
            "road opening", "street opening", "pavement opening", "road-opening",
            "excavate driveway", "cut the sidewalk", "cut sidewalk", "curb cut",
            "utility trench", "trench road", "dig in street", "dig the street",
            "pavement cut", "saw-cut", "saw cut", "public right of way"
        ]) or (any(w in q for w in ["excavat", "trench"]) and any(w in q for w in ["road", "street", "pavement", "curb", "sidewalk", "right of way"]))
        if is_road_explicit:
            return ServiceIntentResult(
                service_id="road_opening",
                service_name="Street Opening & Road Excavation",
                confidence=0.95,
                is_ambiguous=False,
                intent_type=intent_type,
                has_flowchart=True,
                flow_id="street_opening_flow",
                official_form_id="road_opening",
                official_form_file="RoadOpenApp.pdf"
            )

        # F. Site Improvement & Grading
        is_site_explicit = any(phrase in q for phrase in [
            "site improvement", "site improvements", "sip application", "sip permit",
            "improve my property", "improving my property", "property improvement",
            "impervious coverage", "ground disturbance", "disturb ground",
            "site disturbance", "grading plan", "site checklist", "stormwater management"
        ])
        if is_site_explicit:
            return ServiceIntentResult(
                service_id="site_improvement",
                service_name="Site Improvement & Grading",
                confidence=0.92,
                is_ambiguous=False,
                intent_type=intent_type,
                has_flowchart=True,
                flow_id="site_improvement_flow",
                official_form_id="site_improvement",
                official_form_file="SIP_Application.pdf"
            )

        # G. Sanitary Sewer Connection
        is_sewer_explicit = any(phrase in q for phrase in [
            "sewer connection", "sewer tap", "sanitary sewer", "sewer lateral",
            "fixture unit", "sewer charge", "connect to sewer", "sewer utility"
        ])
        if is_sewer_explicit:
            return ServiceIntentResult(
                service_id="sewer_connection",
                service_name="Sanitary Sewer Connection",
                confidence=0.95,
                is_ambiguous=False,
                intent_type=intent_type,
                has_flowchart=True,
                flow_id="sewer_connection_flow",
                official_form_id="sewer_connection",
                official_form_file="Sewer_Connection_Charge_Applications.pdf"
            )

        # H. Residential Construction & Zoning
        is_zoning_explicit = any(phrase in q for phrase in [
            "zoning permit", "zoning application", "residential permit", "residential construction",
            "construct an addition", "build an addition", "addition to my home", "new single family",
            "new dwelling", "build a house", "swimming pool", "inground pool", "above ground pool",
            "deck permit", "build a deck", "open deck", "shed permit", "storage shed", "fence permit",
            "residential fence", "detached garage", "bulk setback", "schedule a yard", "yard requirements"
        ])
        if is_zoning_explicit:
            return ServiceIntentResult(
                service_id="zoning",
                service_name="Residential Construction & Zoning",
                confidence=0.92,
                is_ambiguous=False,
                intent_type=intent_type,
                has_flowchart=True,
                flow_id="residential_zoning_permit_flow",
                official_form_id="zoning_permit",
                official_form_file="Zoning_Permit_Application_Edison.pdf"
            )

        # I. Check History Context for Follow-ups (e.g. "I want to bring 20 cubic yards" or "Yes, 15 yards")
        if history:
            # Check if previous assistant message discussed soil
            last_bot_msg = ""
            for msg in reversed(history):
                if msg.get("role") in ["assistant", "model", "system"]:
                    last_bot_msg = msg.get("content", "").lower()
                    break

            if "soil" in last_bot_msg or "cubic yard" in last_bot_msg:
                if any(w in q for w in ["bring", "import", "in", "add"]):
                    return ServiceIntentResult(
                        service_id="soil_import",
                        service_name="Soil Importation",
                        confidence=0.90,
                        has_flowchart=True,
                        flow_id="soil_import_export_flow",
                        official_form_id="soil_import",
                        official_form_file="Forms_Soil_Importation_Appl.pdf"
                    )
                if any(w in q for w in ["remove", "export", "out", "take away"]):
                    return ServiceIntentResult(
                        service_id="soil_export",
                        service_name="Soil Exportation",
                        confidence=0.90,
                        has_flowchart=True,
                        flow_id="soil_import_export_flow",
                        official_form_id="soil_export",
                        official_form_file="Forms_Soil_Exportation_App.pdf"
                    )
                # If quantity or number mentioned in context of soil
                if any(w in q for w in ["yard", "cubic", "10", "20", "5", "more", "less", "yes", "no"]):
                    # Inherit whether import or export from history
                    if "import" in last_bot_msg:
                        return ServiceIntentResult(
                            service_id="soil_import",
                            service_name="Soil Importation",
                            confidence=0.88,
                            has_flowchart=True,
                            flow_id="soil_import_export_flow",
                            official_form_id="soil_import",
                            official_form_file="Forms_Soil_Importation_Appl.pdf"
                        )
                    if "export" in last_bot_msg:
                        return ServiceIntentResult(
                            service_id="soil_export",
                            service_name="Soil Exportation",
                            confidence=0.88,
                            has_flowchart=True,
                            flow_id="soil_import_export_flow",
                            official_form_id="soil_export",
                            official_form_file="Forms_Soil_Exportation_App.pdf"
                        )

        # J. Non-Flowchart Engineering Inquiry (General Engineering Service)
        is_general_engineering = any(w in q for w in [
            "engineering", "drainage", "flood", "floodplain", "flood zone", "elevation",
            "easement", "catch basin", "storm drain", "storm sewer", "culvert", "retaining wall",
            "driveway standard", "engineering standard", "as-built", "capital project"
        ])
        if is_general_engineering:
            return ServiceIntentResult(
                service_id="other_engineering",
                service_name="General Municipal Engineering",
                confidence=0.75,
                is_ambiguous=False,
                intent_type=intent_type,
                has_flowchart=False,
                flow_id=None
            )

        # K. Ambiguous / Underspecified Engineering Request
        if any(w in q for w in ["permit", "procedure", "application", "guidance", "how do i", "requirements"]):
            return ServiceIntentResult(
                service_id="other_engineering",
                service_name="Municipal Engineering Guidance",
                confidence=0.60,
                is_ambiguous=True,
                clarifying_question=(
                    "I would be glad to help you with Edison Township Engineering services.\n\n"
                    "To guide you with the exact municipal procedure, **what specific type of work are you planning to carry out?**\n"
                    "(For example: Tree removal, soil importation/exportation, road/curb excavation, site improvements, residential additions/zoning, or sewer connections?)"
                ),
                intent_type=intent_type,
                has_flowchart=False,
                flow_id=None
            )

        return ServiceIntentResult(
            service_id="other_engineering",
            service_name="General Engineering Inquiry",
            confidence=0.50,
            is_ambiguous=False,
            intent_type=intent_type,
            has_flowchart=False,
            flow_id=None
        )


service_intent_service = ServiceIntentService()
