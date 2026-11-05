"""
Grounded Municipal RAG Engine & Multi-Turn Intent Router for CivicIQ
("Your Edison Township Buddy" - Edison Township Department of Engineering)
"""

import re
import logging
from typing import List, Optional, Tuple, Dict, Any
from .vector_store import vector_store
from .department_loader import registry
from .llm_client import llm_client
from .models import RagCitation, RagResult, FormIssuanceDetails, SubmissionRouting, FeeInfo, FlowOption
from .config import (
    MUNICIPALITY_NAME, MUNICIPAL_ADDRESS,
    ENGINEERING_PHONE, ENGINEERING_EMAIL,
    OUT_OF_CONTEXT_MESSAGE, SIMILARITY_THRESHOLD
)

logger = logging.getLogger("rag_engine")

class GroundedRagEngine:
    def __init__(self):
        pass

    def check_unsupported_department_inquiry(self, text: str) -> Optional[str]:
        """
        Detects if citizen inquiry is asking about a municipal topic outside Engineering.
        Returns the exact out-of-context message if detected.
        """
        t = text.lower()
        out_of_context_patterns = [
            r'\b(cat|cats|dog|dogs|pet|pets|animal|animals|adopt|adoption|kitten|kittens|puppy|puppies|shelter|rabies|spay|neuter)\b',
            r'\b(restaurant|food|kitchen|vital statistics|birth certificate|death certificate|marriage license|marriage)\b',
            r'\b(election|elections|voting|voter|ballot|council minutes|landlord|charity|bingo|tax|taxes|assessor)\b',
            r'\b(police|fire|court|ticket|parking ticket|traffic ticket|library|school|schools)\b',
            r'\b(quantum|fusion|space shuttle|orbital|rocket|astronomy)\b'
        ]
        for pattern in out_of_context_patterns:
            if re.search(pattern, t):
                return OUT_OF_CONTEXT_MESSAGE
        return None

    def detect_flow_intent(
        self,
        user_text: str,
        department_id: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None
    ) -> Optional[Tuple[str, str]]:
        """
        Detects if user intent is procedural (starting a multi-step engineering flow).
        Uses ServiceIntentService to accurately classify services.
        Separates specific detail inquiries (fees, documents, submission) from workflow initiation.
        """
        from .services.service_intent_service import service_intent_service
        intent = service_intent_service.detect_intent(user_text, history=history)

        # Never hijack detail inquiries (fee, documents, submission, turnaround, complete process) into a workflow
        if intent.detail_type not in ["procedure", "emergency"]:
            return None

        # Never hijack form requests into a procedural workflow
        if intent.intent_type in ["form_request", "fee_inquiry", "document_inquiry", "submission_inquiry"]:
            return None

        # For soil services, conversational handling in handle_soil_flow handles import/export branching dynamically
        if intent.service_id in ["soil_import", "soil_export", "soil_movement"]:
            return None

        text = user_text.lower().strip()
        # Only start a flow when the resident actively wants procedural guidance or workflow initiation
        is_workflow_initiation = any(phrase in text for phrase in [
            "want to", "planning to", "need to", "help me with", "guide me", "procedure",
            "workflow", "how to remove", "how to import", "how to export", "how to cut",
            "steps for", "start"
        ]) or (
            intent.confidence >= 0.90 and 
            intent.has_flowchart and
            not any(w in text for w in ["cost", "fee", "price", "pay", "charge", "document", "attachment", "form", "download", "where", "how much"])
        )

        if is_workflow_initiation and intent.is_supported and intent.has_flowchart and intent.flow_id:
            return ("engineering", intent.flow_id)

        return None

    def match_official_form_packet(
        self,
        text: str,
        department_id: str = "engineering",
        history: Optional[List[Dict[str, str]]] = None,
        force: bool = False
    ) -> Optional[FormIssuanceDetails]:
        """
        Delivers an official form packet when the resident explicitly asks for a form/application
        or when invoked by a concluding procedural flow (force=True).
        Uses conversation history to accurately identify WHICH form is needed.
        Explicit service/document names in current message take absolute priority over history.
        """
        t = text.lower().strip()

        # Check for explicit form/download/application requests
        has_form_keyword = bool(re.search(r'\b(form|application|pdf|packet|checklist)\b', t))
        has_intent_keyword = any(w in t for w in [
            "give", "get", "need", "send", "where", "download", "access",
            "can i", "can you", "provide", "obtain", "attach", "show", "official"
        ])
        is_form_request = (has_form_keyword and has_intent_keyword) or any(phrase in t for phrase in [
            "download form", "download the form", "give me the form", "provide the form",
            "get the form", "send the form", "application form", "official form",
            "download application", "where can i download", "pdf form", "need the form",
            "need the application", "give me that form", "send me the form",
            "send me the application", "access the form", "where is the form",
            "download the application form", "download official form",
            "give me the road opening application", "official application form",
            "permit application", "application", "how do i apply", "how to apply",
            "pdf to download"
        ])

        if not force and not is_form_request:
            return None

        def _tree_packet():
            return FormIssuanceDetails(
                form_code="EDISON-ENG-TRP",
                form_title="Township of Edison Tree Permit Application (Removal / Replacement / Conservation)",
                form_file="3.23.21 tree permit application.pdf",
                pdf_download_url="/api/forms/engineering/3.23.21%20tree%20permit%20application.pdf",
                department_id="engineering",
                fill_in_instructions="1. Complete Property Owner data, Subject Permit Site Address, Block, and Lot.\n2. Note Number of Trees On-Site and Number of Trees to be Removed.\n3. Check appropriate fee category ($25 for single residential lot; waived for senior citizens age 62+ with ID).\n4. Attach colored photos of dead/dying tree OR arborist certification, and Survey/Tax Map sketch.\n5. Visibly mark trees on site with ribbon or paint for inspection.\n6. Submit to the Division of Engineering.",
                required_attachments=[
                    "Survey or Tax Map sketch showing property lines, existing trees with diameter, and removal trees marked with an X",
                    "Colored photographs of dead/dying/hazard tree condition OR certified statement from licensed arborist/forester",
                    "Written statement detailing the reason for removal (Township Ordinance 25-8.1a6)",
                    "Payment of $25 fee (payable to 'Township of Edison') or Senior ID (age 62+)"
                ],
                fee_info=FeeInfo(
                    amount="$25.00 for single residential lot (Waived for Senior Citizens age 62+ with ID; $200 with Board approval / subdivision)",
                    payment_methods="Check or Credit Card payable to 'Township of Edison'"
                ),
                submission_routing=SubmissionRouting(
                    department="Township of Edison Department of Planning and Engineering",
                    desk="Division of Engineering, Edison Municipal Complex",
                    building_address="100 Municipal Boulevard, Edison, NJ 08817",
                    digital_upload_url="https://www.edisonnj.org/document_center/index.php"
                ),
                lead_time="5 to 10 business days for field inspection sign-off"
            )

        def _soil_import_packet():
            return FormIssuanceDetails(
                form_code="EDISON-ENG-SOIL-IMP",
                form_title="Township of Edison Soil Importation Permit Application",
                form_file="Forms_Soil_Importation_Appl.pdf",
                pdf_download_url="/api/forms/engineering/Forms_Soil_Importation_Appl.pdf",
                department_id="engineering",
                fill_in_instructions="1. Enter applicant, property owner, and contractor details.\n2. Detail source of fill and attach clean fill lab certification.\n3. Attach property survey showing proposed grading.\n4. Submit to Division of Engineering.",
                required_attachments=[
                    "Certified laboratory clean fill analysis",
                    "Property survey showing proposed fill placement and grading contours",
                    "Designated truck haul route plan",
                    "Soil importation review fee and engineering escrow deposit"
                ],
                fee_info=FeeInfo(
                    amount="Standard municipal soil review fee and engineering escrow deposit",
                    payment_methods="Check payable to 'Township of Edison'"
                ),
                submission_routing=SubmissionRouting(
                    department="Department of Engineering",
                    desk="Engineering Division",
                    digital_upload_url="https://www.edisonnj.org/document_center/index.php"
                ),
                lead_time="7 to 10 Business Days"
            )

        def _soil_export_packet():
            return FormIssuanceDetails(
                form_code="EDISON-ENG-SOIL-EXP",
                form_title="Township of Edison Soil Exportation Permit Application",
                form_file="Forms_Soil_Exportation_App.pdf",
                pdf_download_url="/api/forms/engineering/Forms_Soil_Exportation_App.pdf",
                department_id="engineering",
                fill_in_instructions="1. Enter parcel details and volume of soil to be removed in cubic yards.\n2. Attach topographical survey and cut/fill cross-sections.\n3. Detail truck route through Edison.\n4. Submit to Division of Engineering.",
                required_attachments=[
                    "Topographical survey with cut/fill calculations by NJ licensed engineer/surveyor",
                    "Soil erosion and sediment control certification",
                    "Truck haul route plan",
                    "Filing fee and restoration bond"
                ],
                fee_info=FeeInfo(
                    amount="Standard municipal soil exportation fee schedule",
                    payment_methods="Check payable to 'Township of Edison'"
                ),
                submission_routing=SubmissionRouting(
                    department="Department of Engineering",
                    desk="Engineering Division",
                    digital_upload_url="https://www.edisonnj.org/document_center/index.php"
                ),
                lead_time="7 to 10 Business Days"
            )

        def _road_opening_packet():
            return FormIssuanceDetails(
                form_code="EDISON-DPW-ROADOPEN",
                form_title="Township of Edison Street Opening Application",
                form_file="RoadOpenApp.pdf",
                pdf_download_url="/api/forms/engineering/RoadOpenApp.pdf",
                department_id="public_works",
                fill_in_instructions="Download the official blank application to complete and submit directly to the Department of Public Works.",
                required_attachments=[
                    "NJ One Call (811) ticket confirmation",
                    "Trench excavation dimensions sketch",
                    "Certificate of Insurance ($1,000,000 liability naming Township of Edison)",
                    "Application fee ($150) and restoration guarantee bond ($5,000)"
                ],
                fee_info=FeeInfo(
                    amount="$150.00 application fee; $5,000.00 restoration guarantee bond",
                    payment_methods="Check payable to 'Township of Edison'"
                ),
                submission_routing=SubmissionRouting(
                    department="Department of Public Works",
                    desk="Department of Public Works, 100 Municipal Blvd, Edison, NJ 08817 (dpw@edisonnj.gov)",
                    digital_upload_url="https://www.edisonnj.org/document_center/RoadOpenApp.pdf?t=202409111411520"
                ),
                lead_time="5 to 7 business days"
            )

        def _flood_zone_packet():
            return FormIssuanceDetails(
                form_code="EDISON-ENG-FLOOD",
                form_title="Township of Edison Flood Zone Determination Letter Request",
                form_file="Flood_Zone_Determination_Letter_REQUEST.pdf",
                pdf_download_url="/api/forms/engineering/Flood_Zone_Determination_Letter_REQUEST.pdf",
                department_id="engineering",
                fill_in_instructions="1. Enter Property Street Address, Tax Map Block, and Lot number(s).\n2. Provide applicant contact details.\n3. Include the $25.00 Flood Letter Fee.\n4. Submit to Division of Engineering.",
                required_attachments=[
                    "Property Address, Block, and Lot number(s)",
                    "Applicant contact details",
                    "$25.00 Flood Letter Fee"
                ],
                fee_info=FeeInfo(
                    amount="$25.00 Flood Letter Fee",
                    payment_methods="Check payable to 'Township of Edison'"
                ),
                submission_routing=SubmissionRouting(
                    department="Division of Engineering",
                    desk="Division of Engineering, Edison Municipal Complex",
                    building_address="100 Municipal Boulevard, Edison, NJ 08817",
                    digital_upload_url="https://www.edisonnj.org/document_center/Flood_Zone_Determination_Letter_REQUEST.pdf?t=202409111411240"
                ),
                lead_time="Standard municipal review turnaround"
            )

        def _permit_flowchart_packet():
            return FormIssuanceDetails(
                form_code="EDISON-ENG-FLOWCHART",
                form_title="Township of Edison Permit Flow Charts",
                form_file="Permit_Flow_Charts.pdf",
                pdf_download_url="/api/forms/engineering/Permit_Flow_Charts.pdf",
                department_id="engineering",
                fill_in_instructions="Official Township of Edison guidance document outlining municipal permit requirements across Road Opening, Tree Removal, Soil Import/Export, and Site Improvements.",
                required_attachments=[],
                fee_info=FeeInfo(
                    amount="No fee (Guidance Document)",
                    payment_methods="N/A"
                ),
                submission_routing=SubmissionRouting(
                    department="Division of Engineering",
                    desk="Engineering Division",
                    building_address="100 Municipal Boulevard, Edison, NJ 08817",
                    digital_upload_url="https://www.edisonnj.org/document_center/index.php"
                ),
                lead_time="Immediate reference"
            )

        def _plot_grading_packet():
            return FormIssuanceDetails(
                form_code="EDISON-ENG-PLOT-GRADING",
                form_title="Requirements for Plot Grading Plans – Minor Development",
                form_file="Requirements_for_Plot_Grading_Plans_Minor_Development.pdf",
                pdf_download_url="/api/forms/engineering/Requirements_for_Plot_Grading_Plans_Minor_Development.pdf",
                department_id="engineering",
                fill_in_instructions="Review official engineering submission requirements. Retain a NJ licensed PE or PLS to prepare, sign, and seal 3 copies of plot grading and drainage plans.",
                required_attachments=[
                    "Three (3) sealed plan sets by NJ licensed PE or PLS",
                    "Certified boundary survey overlay with existing/proposed contours and spot elevations",
                    "Title 34 stormwater seepage pit infiltration calculations",
                    "Site Improvement Permit (SIP) application and approved Zoning Permit"
                ],
                fee_info=FeeInfo(
                    amount="Review fee plus 5% construction cost inspection escrow",
                    payment_methods="Check payable to 'Township of Edison'"
                ),
                submission_routing=SubmissionRouting(
                    department="Division of Engineering",
                    desk="Engineering Division",
                    building_address="100 Municipal Boulevard, Edison, NJ 08817",
                    digital_upload_url="https://www.edisonnj.org/document_center/index.php"
                ),
                lead_time="Standard engineering review turnaround"
            )

        def _sewer_connection_packet():
            return FormIssuanceDetails(
                form_code="EDISON-ENG-SEWER",
                form_title="Township of Edison Sewer Connection Charge Application",
                form_file="Sewer_Connection_Charge_Applications.pdf",
                pdf_download_url="/api/forms/engineering/Sewer_Connection_Charge_Applications.pdf",
                department_id="engineering",
                fill_in_instructions="1. Fill in property owner and location details.\n2. Detail fixture units breakdown.\n3. Attach engineering utility lateral plan.\n4. Submit to Sewer Utility / Engineering Division.",
                required_attachments=[
                    "Completed Sewer Connection Charge Application",
                    "Fixture unit calculation schedule",
                    "Civil engineering utility lateral connection plan"
                ],
                fee_info=FeeInfo(
                    amount="Calculated by total fixture units per municipal rate schedule",
                    payment_methods="Check payable to 'Township of Edison'"
                ),
                submission_routing=SubmissionRouting(
                    department="Edison Sewer Utility / Division of Engineering",
                    desk="Sewer Utility Desk",
                    building_address="100 Municipal Boulevard, Edison, NJ 08817",
                    digital_upload_url="https://www.edisonnj.org/document_center/index.php"
                ),
                lead_time="Standard municipal review turnaround"
            )

        def _site_improvement_packet():
            return FormIssuanceDetails(
                form_code="EDISON-ENG-SIP",
                form_title="Township of Edison Site Improvement Permit Application with Checklist",
                form_file="SIP_Application.pdf",
                pdf_download_url="/api/forms/engineering/SIP_Application.pdf",
                department_id="engineering",
                fill_in_instructions="1. Complete Site Improvement Permit application and 25-point checklist.\n2. Attach approved Zoning Permit.\n3. Attach two (2) signed and sealed sets of engineering grading and drainage plans.\n4. Submit to Division of Engineering with 5% inspection escrow.",
                required_attachments=[
                    "Completed 25-point engineering checklist signed by applicant",
                    "Copy of approved Zoning Permit and stamped plans",
                    "Two (2) signed and sealed engineering site/grading plans",
                    "Stormwater infiltration design and soil erosion sediment control measures",
                    "5% construction cost engineering inspection escrow deposit"
                ],
                fee_info=FeeInfo(
                    amount="Application review fee plus 5% construction cost inspection escrow",
                    payment_methods="Check payable to 'Township of Edison'"
                ),
                submission_routing=SubmissionRouting(
                    department="Division of Engineering",
                    desk="Engineering Division",
                    building_address="100 Municipal Boulevard, Edison, NJ 08817",
                    digital_upload_url="https://www.edisonnj.org/document_center/index.php"
                ),
                lead_time="10 to 15 business days"
            )

        # 1. Check if CURRENT QUERY explicitly specifies the service (Priority 1)
        if any(w in t for w in ["flood zone", "floodzone", "floodplain", "flood plain", "flood determination", "flood letter", "flood insurance"]):
            return _flood_zone_packet()

        if any(w in t for w in ["which permit do i need", "what permit do i need", "permit flow chart", "permit flowchart", "flow chart to help determine"]):
            return _permit_flowchart_packet()

        if any(w in t for w in ["plot grading", "plot grading plan", "minor development grading", "grading plan requirements", "requirements for plot grading"]):
            return _plot_grading_packet()

        if any(w in t for w in ["sewer connection", "sewer connection charge", "sewer charge", "sewer tap", "sanitary sewer", "fixture unit", "sewer application"]):
            return _sewer_connection_packet()

        if any(w in t for w in ["site improvement", "site improvements", "sip application", "sip permit", "site checklist", "impervious coverage"]):
            return _site_improvement_packet()

        if any(w in t for w in ["road opening", "street opening", "pavement opening", "road-opening", "street opening permit", "road opening permit"]):
            return _road_opening_packet()

        is_explicit_soil_import = any(w in t for w in ["soil import", "soil importation", "import soil", "import fill", "fill dirt", "bring soil", "topsoil import"])
        is_explicit_soil_export = any(w in t for w in ["soil export", "soil exportation", "export soil", "remove soil", "hauling soil", "haul soil"])
        is_explicit_tree = bool(re.search(r'\b(tree|trees|arborist|forester|sapling|stump|stumps|branch|branches)\b', t))

        if is_explicit_soil_import and not is_explicit_tree:
            return _soil_import_packet()
        if is_explicit_soil_export and not is_explicit_tree:
            return _soil_export_packet()
        if is_explicit_tree:
            return _tree_packet()

        # 2. If current query does not explicitly specify a service (ambiguous query),
        # inspect conversation history in REVERSE so the MOST RECENT service wins
        if history:
            for msg in reversed(history):
                c = msg.get("content", "").lower()
                if any(w in c for w in ["flood zone", "floodplain", "flood_zone_determination"]):
                    return _flood_zone_packet()
                if any(w in c for w in ["permit flow chart", "permit_flow_charts"]):
                    return _permit_flowchart_packet()
                if any(w in c for w in ["plot grading", "requirements_for_plot_grading"]):
                    return _plot_grading_packet()
                if any(w in c for w in ["sewer", "sewer_connection"]):
                    return _sewer_connection_packet()
                if any(w in c for w in ["site improvement", "sip_application"]):
                    return _site_improvement_packet()
                if any(w in c for w in ["road opening", "street opening", "roadopenapp"]):
                    return _road_opening_packet()
                if any(w in c for w in ["soil import", "soil importation", "import soil", "forms_soil_importation_appl.pdf"]):
                    return _soil_import_packet()
                if any(w in c for w in ["soil export", "soil exportation", "export soil", "forms_soil_exportation_app.pdf"]):
                    return _soil_export_packet()
                if any(w in c for w in ["tree removal", "tree permit", "3.23.21 tree permit application.pdf", "emergency condition of the tree"]):
                    return _tree_packet()

        return None

    def handle_tree_removal_flow(
        self,
        query: str,
        history: Optional[List[Dict[str, str]]] = None
    ) -> Optional[Tuple[str, Optional[FormIssuanceDetails]]]:
        """
        Interactive conversational guidance for tree removal under official
        Edison Township Permit Flow Charts (Permit Flow Charts.pdf - Page 3: Tree Removal Permit).
        """
        q = query.lower().strip()
        hist = history or []

        # If resident is explicitly asking for the application / form / PDF download
        has_form_ask = any(w in q for w in ["form", "application", "pdf", "packet", "download"])
        if has_form_ask:
            msg = (
                "You can download the official blank [Township of Edison Tree Removal Permit Application (PDF)](/api/forms/engineering/3.23.21%20tree%20permit%20application.pdf) "
                "to complete and submit to the Division of Engineering.\n\n"
                "• **Filing Fee:** $25 standard residential fee (waived for senior citizens aged 62+ with valid proof of age; $200 with Board approval or subdivision).\n"
                "• **Required Attachments:** Property survey or Tax Map sketch showing existing trees and trees marked for removal, written statement detailing the reason for removal, and site marking with ribbon or paint."
            )
            return (msg, self.match_official_form_packet("tree removal", force=True))

        # If user is asking for specific details (fee, documents, submission, etc.), do not intercept with flow steps
        from .services.service_intent_service import service_intent_service
        intent_check = service_intent_service.detect_intent(query, history=history)
        if intent_check.detail_type in ["fee", "documents", "submission", "turnaround", "complete_process"]:
            return None

        # Find the last assistant message in history to identify conversational turn
        last_bot_msg = ""
        for msg in reversed(hist):
            if msg.get("role") in ["assistant", "model", "system"]:
                last_bot_msg = msg.get("content", "").lower()
                break

        in_tree_flow = (
            "tree removal" in last_bot_msg or
            "permit for the tree removal" in last_bot_msg or
            "emergency condition of the tree" in last_bot_msg or
            "eminent danger" in last_bot_msg or
            "urgent situation or emergency" in last_bot_msg or
            "part of a subdivision" in last_bot_msg
        )

        is_tree_start = any(k in q for k in [
            "guide me with tree removal", "guide me on tree removal", "help me with tree removal",
            "guide me tree removal", "guide tree removal", "procedure for tree removal",
            "process for tree removal", "want to remove a tree", "removing a tree",
            "remove a tree", "cut down a tree", "tree removal guidance"
        ])

        # Turn 1: User initiates tree removal guidance
        if is_tree_start and not in_tree_flow:
            if any(w in q for w in ["urgent", "emergency", "no time"]):
                msg = (
                    "I would be glad to guide you through the official Edison Township tree removal process.\n\n"
                    "Since this is an urgent situation where there is no time to wait for a standard permit, "
                    "please explain the reason: **What is the emergency condition of the tree?**\n\n"
                    "(For example, is the tree dead or dying, cracked, storm-damaged, leaning dangerously over your home, power lines, or driveway, or presenting an eminent danger to safety?)"
                )
                return (msg, None)

            msg = (
                "I would be glad to guide you through the official Edison Township tree removal process under our municipal permit guidelines.\n\n"
                "To get started: **Do you currently have an approved permit for the tree removal?**"
            )
            return (msg, None)

        if not in_tree_flow:
            return None

        # Turn 2: Assistant previously asked: 'Do you currently have an approved permit for the tree removal?'
        if "permit for the tree removal" in last_bot_msg:
            # Check for negative response first (no / don't / do not / not yet / without)
            is_negative = bool(re.search(r'\b(no|nope|don\'t|dont|not|negative|do not|without)\b', q))

            if is_negative:
                # Did user also mention urgency / emergency / no time?
                if any(w in q for w in ["urgent", "emergency", "no time", "immediate", "hazard", "dangerous", "asap", "hurry"]):
                    msg = (
                        "Understood. If this is an urgent situation where there is no time to wait for a standard permit, "
                        "please explain the reason: **What is the emergency condition of the tree?**\n\n"
                        "(For example, is the tree dead or dying, cracked, storm-damaged, leaning dangerously over your home, power lines, or driveway, or presenting an eminent danger to safety?)"
                    )
                    return (msg, None)
                else:
                    msg = (
                        "Under official Edison Township regulations, permit procedures depend on whether the removal is an emergency:\n\n"
                        "**Is this an urgent situation or emergency** (such as a dead, dying, or storm-damaged tree posing an eminent danger to safety or property), "
                        "or is it a planned, non-emergency tree removal?"
                    )
                    return (msg, None)

            # User replies with urgency even without saying no
            if any(w in q for w in ["urgent", "emergency", "no time", "immediate", "hazard", "dangerous", "asap", "hurry"]):
                msg = (
                    "Understood. If this is an urgent situation where there is no time to wait for a standard permit, "
                    "please explain the reason: **What is the emergency condition of the tree?**\n\n"
                    "(For example, is the tree dead or dying, cracked, leaning dangerously over your home, power lines, or driveway, or presenting an eminent danger to safety?)"
                )
                return (msg, None)

            # User replies YES
            if re.search(r'\b(yes|yeah|already have|i do|i have|already got)\b', q):
                msg = (
                    "Great! Since you already hold an approved Edison Township tree removal permit, "
                    "you are authorized to proceed with the tree removal according to the conditions "
                    "and timeframe specified on your permit.\n\n"
                    "For additional guidelines or municipal document references, visit https://www.edisonnj.org/document_center/index.php."
                )
                return (msg, None)

        # Turn 3A: Assistant previously asked: 'Is this an urgent situation or emergency... or planned?'
        if "urgent situation or emergency" in last_bot_msg:
            is_non_emergency = any(w in q for w in ["not an emergency", "non-emergency", "non emergency", "planned", "routine", "not urgent", "no"])
            if is_non_emergency and not any(w in q for w in ["yes, it is urgent", "yes it is emergency", "it is urgent", "is emergency"]):
                msg = (
                    "Under Township of Edison Tree Protection regulations (Chapter 25-8), a **Tree Removal Permit is required** before removing mature trees on your property.\n\n"
                    "1. **Submit application:** Complete and submit the official Tree Removal Permit Application.\n"
                    "2. **Mark trees on site:** Mark trees proposed for removal with red ribbon or paint for township inspection.\n"
                    "3. **Await inspection:** An engineering inspector will visit the site within 5–10 business days before removal can proceed."
                )
                return (msg, self.match_official_form_packet("tree removal", force=True))
            else:
                msg = (
                    "Understood. If this is an urgent situation, please explain the reason: **What is the emergency condition of the tree?**\n\n"
                    "(For example, is the tree dead or dying, cracked, leaning dangerously over your home, power lines, or driveway, or presenting an imminent danger to safety?)"
                )
                return (msg, None)

        # Turn 3B: Assistant previously asked: 'What is the emergency condition of the tree?'
        if "emergency condition of the tree" in last_bot_msg:
            # Check if reason indicates a valid hazard/emergency
            is_valid_hazard = any(w in q for w in [
                "dead", "dying", "hazard", "danger", "crack", "cracked", "fall", "falling", "split",
                "storm", "struck", "lightning", "lean", "leaning", "roof", "wire", "power line",
                "driveway", "house", "collapse", "risk", "damage", "eminent", "imminent", "urgent",
                "bad", "heavy", "broken", "wind"
            ])

            if is_valid_hazard:
                msg = (
                    "Under Edison Township guidelines, emergency removal is permitted. If it's an emergency, take photos of the hazardous tree or obtain a certified letter from a licensed arborist/forester confirming that it is dead, dying or an imminent danger. You can then safely remove the tree immediately and submit the Tree Removal Permit Application concurrently with removal via the Edison Document Center."
                )
                return (msg, self.match_official_form_packet("tree removal", force=True))
            else:
                msg = (
                    "Based on your description, this situation does not appear to involve an imminent safety hazard or dead/dying tree.\n\n"
                    "Under official Edison Township tree preservation guidelines:\n"
                    "**Is this tree removal part of a subdivision or does it require a demolition permit from Code Enforcement?**\n"
                    "• If **Yes**: A permit is required prior to tree removal.\n"
                    "• If **No**: A permit is NOT required under township guidelines."
                )
                return (msg, None)

        # Turn 4: Assistant previously asked: 'Is this tree removal part of a subdivision...'
        if "part of a subdivision" in last_bot_msg:
            if re.search(r'\b(no|nope|not|negative|never)\b', q):
                msg = (
                    "Under Township of Edison guidelines, because your project does not involve removing trees and is not part of a subdivision or demolition, a **Tree Removal Permit is NOT required**.\n\n"
                    "You may proceed with your project without filing a tree removal application."
                )
                return (msg, None)
            else:
                msg = (
                    "Under Township of Edison Code (Chapter 25-8), a **Tree Removal Permit is required** prior to clearing trees for a subdivision or demolition project.\n\n"
                    "1. **Submit permit application:** Submit the completed Tree Removal Permit Application along with your approved Planning/Zoning Board resolution or demolition permit.\n"
                    "2. **Include tree conservation plan:** Provide the required site plan showing tree protection and replacement schedule.\n"
                    "3. **Await engineering clearance:** Await engineering division approval before clearing or tree work begins."
                )
                return (msg, self.match_official_form_packet("tree removal", force=True))

        return None

    def _build_soil_import_required_msg(self) -> str:
        return (
            "Under Township of Edison municipal regulations (Chapter 31), importing 10 cubic yards or more of soil requires an approved **Soil Importation Permit** prior to delivery.\n\n"
            "• 1. **Submit application:** Complete and submit the official Soil Importation Permit Application.\n"
            "• 2. **Provide documentation:** Attach a certified laboratory clean fill analysis and a property survey with grading plan showing proposed fill placement.\n"
            "• 3. **Await engineering approval:** Obtain permit approval from the Division of Engineering before transporting soil onto your property.\n\n"
            "Source: [Township of Edison Soil Importation Permit Application](/api/forms/engineering/Forms_Soil_Importation_Appl.pdf)"
        )

    def _build_soil_export_required_msg(self) -> str:
        return (
            "Under Township of Edison municipal regulations (Chapter 31), exporting 10 cubic yards or more of soil requires an approved **Soil Exportation Permit** prior to hauling.\n\n"
            "• 1. **Submit application:** Complete and submit the official Soil Exportation Permit Application.\n"
            "• 2. **Provide documentation:** Attach a topographical survey with cut/fill calculations and your designated truck haul route.\n"
            "• 3. **Await engineering approval:** Obtain permit approval from the Division of Engineering before moving soil off-site.\n\n"
            "Source: [Township of Edison Soil Exportation Permit Application](/api/forms/engineering/Forms_Soil_Exportation_App.pdf)"
        )

    def _build_soil_not_required_msg(self) -> str:
        return (
            "Under official Township of Edison engineering guidelines, because your project involves **less than 10 cubic yards of soil**, a municipal Soil Import/Export Permit is **NOT required**.\n\n"
            "Ensure that soil placement does not alter natural drainage patterns or direct runoff onto neighboring properties."
        )

    def _build_site_improvement_required_msg(self) -> str:
        return (
            "Under Township of Edison engineering regulations, your project requires an approved **Site Improvement Permit (SIP)** with Checklist prior to commencing ground disturbance.\n\n"
            "1. **Submit application & checklist:** Complete the official Site Improvement Application and 25-point checklist.\n"
            "2. **Provide sealed plans:** Attach signed and sealed site grading and drainage plans prepared by a NJ licensed engineer.\n"
            "3. **Await engineering approval:** Obtain permit issuance before any excavation or site disturbance begins."
        )

    def _build_site_improvement_not_required_msg(self) -> str:
        return (
            "Under Township of Edison engineering guidelines, a **Site Improvement Permit is not required** because your project does not exceed 500 sq. ft. of impervious coverage and does not alter site drainage or grading."
        )

    def handle_soil_flow(
        self,
        query: str,
        history: Optional[List[Dict[str, str]]] = None
    ) -> Optional[Tuple[str, Optional[FormIssuanceDetails]]]:
        """
        Interactive conversational guidance for soil importation and exportation
        under official Edison Township regulations (Chapter 31 and Page 4 of Permit Flow Charts).
        Decision rule:
        - Are you importing or exporting 10 cubic yards or more of soil to/from your site?
        - If >= 10 cu.yds (Import) -> Soil Import Permit Required (Forms_Soil_Importation_Appl.pdf)
        - If >= 10 cu.yds (Export) -> Soil Export Permit Required (Forms_Soil_Exportation_App.pdf)
        - If < 10 cu.yds -> Soil Permit NOT required.
        """
        q = query.lower().strip()
        hist = history or []

        last_bot_msg = ""
        for msg in reversed(hist):
            if msg.get("role") in ["assistant", "model", "system"]:
                last_bot_msg = msg.get("content", "").lower()
                break

        # Check if resident is responding to the ambiguous removal question with 'soil' (removing soil = export)
        if "what would you like to remove" in last_bot_msg and any(w in q for w in ["soil", "dirt", "export", "opt_remove_soil"]):
            msg = (
                "I can help you understand the Township of Edison's soil export requirements under municipal regulations (Chapter 31).\n\n"
                "Approximately how much soil are you planning to export or remove? **Is it 10 cubic yards or more?**\n\n"
                "*(Note: Typical excavation for home additions, pools, or foundation work often exceeds 10 cubic yards.)*"
            )
            return (msg, None)

        # Check if resident is explicitly requesting the form / PDF / application
        has_form_ask = any(w in q for w in ["form", "application", "pdf", "packet", "download"])
        if has_form_ask:
            if any(w in q for w in ["export", "remove", "haul away", "take away"]):
                return (self._build_soil_export_required_msg(), self.match_official_form_packet("soil exportation permit application", force=True))
            elif any(w in q for w in ["import", "bring", "deliver", "into", "onto", "fill"]):
                return (self._build_soil_import_required_msg(), self.match_official_form_packet("soil importation permit application", force=True))

        in_soil_flow = (
            "soil regulations" in last_bot_msg or
            "soil import requirements" in last_bot_msg or
            "soil export requirements" in last_bot_msg or
            "planning to bring soil onto your property" in last_bot_msg or
            "10 cubic yards or more" in last_bot_msg or
            "less than 10 cubic yards" in last_bot_msg or
            "soil importation permit" in last_bot_msg or
            "soil exportation permit" in last_bot_msg or
            any("soil" in m.get("content", "").lower() for m in hist[-3:])
        )

        is_soil_query = any(phrase in q for phrase in [
            "import soil", "export soil", "soil import", "soil export",
            "bring soil", "remove soil", "soil permit", "dirt permit",
            "how to import soil", "how to export soil", "moving soil", "haul soil"
        ]) or (("soil" in q or "dirt" in q) and any(w in q for w in ["bring", "remove", "import", "export", "deliver", "haul", "fill", "permit", "rule", "guidance"]))

        if not in_soil_flow and not is_soil_query:
            return None

        # Turn 1: Check for upfront specific answers
        if not in_soil_flow:
            is_import = any(w in q for w in ["import", "bring", "deliver", "into", "onto", "fill dirt", "fill my yard", "topsoil", "add soil"])
            is_export = any(w in q for w in ["export", "remove", "take away", "haul away", "off site", "excess soil", "haul soil"])
            has_10_or_more = any(w in q for w in ["10", "20", "15", "25", "30", "40", "50", "more", "over", "large"]) and not any(w in q for w in ["less", "under"])
            has_under_10 = any(w in q for w in ["less than 10", "under 10", "less than ten", "under ten", "5 cubic", "3 cubic", "2 cubic", "1 cubic", "few yards", "small amount", "minor"])

            # 1A. Upfront Import >= 10 cu.yds
            if is_import and has_10_or_more:
                return (self._build_soil_import_required_msg(), self.match_official_form_packet("soil importation permit application"))

            # 1B. Upfront Export >= 10 cu.yds
            if is_export and has_10_or_more:
                return (self._build_soil_export_required_msg(), self.match_official_form_packet("soil exportation permit application"))

            # 1C. Upfront Under 10 cu.yds
            if (is_import or is_export) and has_under_10:
                return (self._build_soil_not_required_msg(), None)

            # 1D. User specifically asks about soil import (e.g. "How to import soil?")
            if is_import and not is_export:
                msg = (
                    "I can help you understand the Township of Edison's soil import requirements under municipal regulations (Chapter 31).\n\n"
                    "Approximately how much soil are you planning to import? **Is it 10 cubic yards or more?**\n\n"
                    "*(Note: One standard single-axle dump truck typically holds about 10 cubic yards of fill material.)*"
                )
                return (msg, None)

            # 1E. User specifically asks about soil export (e.g. "How to export soil?")
            if is_export and not is_import:
                msg = (
                    "I can help you understand the Township of Edison's soil export requirements under municipal regulations (Chapter 31).\n\n"
                    "Approximately how much soil are you planning to export or remove? **Is it 10 cubic yards or more?**\n\n"
                    "*(Note: Typical excavation for home additions, pools, or foundation work often exceeds 10 cubic yards.)*"
                )
                return (msg, None)

            # 1F. Ambiguous soil movement (direction not specified)
            msg = (
                "I can help you understand the Township of Edison's soil regulations.\n\n"
                "First, **are you planning to bring soil onto your property (Soil Import) or remove soil from your property (Soil Export)?**"
            )
            return (msg, None)

        # Turn 2: Assistant previously asked: 'bring soil onto your property... or remove soil'
        if "bring soil onto your property" in last_bot_msg:
            is_import = any(w in q for w in ["bring", "import", "in", "onto", "deliver", "fill", "add", "yes, bring", "yes bring"])
            is_export = any(w in q for w in ["remove", "export", "out", "take away", "haul away", "off", "yes, remove", "yes remove"])

            if is_import:
                msg = (
                    "Understood. For importing soil onto your property:\n\n"
                    "Approximately how much soil are you planning to import? **Is it 10 cubic yards or more?**\n\n"
                    "*(Note: A standard single-axle dump truck typically holds about 10 cubic yards of fill.)*"
                )
                return (msg, None)
            elif is_export:
                msg = (
                    "Understood. For exporting or removing soil from your property:\n\n"
                    "Approximately how much soil are you planning to export? **Is it 10 cubic yards or more?**\n\n"
                    "*(Note: Excavation for foundations or pools typically exceeds 10 cubic yards.)*"
                )
                return (msg, None)
            else:
                msg = (
                    "To guide you with the correct requirements, please confirm: **Are you bringing soil onto your property (import) or removing soil from your property (export)?**"
                )
                return (msg, None)

        # Turn 3 / Volume Answers & Corrections (e.g. "Actually, it is 10 cubic yards or more.", "10 cubic yards or more", "less than 10 cubic yards", "5 cubic yards")
        is_volume_or_correction = (
            "10 cubic yards or more" in last_bot_msg or
            "less than 10 cubic yards" in last_bot_msg or
            "soil importation permit" in last_bot_msg or
            "soil exportation permit" in last_bot_msg or
            any(w in q for w in ["actually", "wait", "change", "correct", "cubic"])
        )

        if is_volume_or_correction:
            # Determine if this was an import or export flow from history and query (ignoring generic 'import/export' text)
            has_import_intent = False
            has_export_intent = False
            for m in hist:
                if m.get("role") == "user":
                    c = m.get("content", "").lower()
                    if any(w in c for w in ["import", "bring", "deliver", "into", "onto", "fill dirt", "topsoil"]):
                        has_import_intent = True
                    if any(w in c for w in ["export", "remove", "haul away", "take away", "off site"]):
                        has_export_intent = True

            if any(w in q for w in ["export", "remove", "haul"]):
                is_export = True
            elif any(w in q for w in ["import", "bring", "deliver"]):
                is_export = False
            elif has_export_intent and not has_import_intent:
                is_export = True
            else:
                is_export = False
            is_import = not is_export

            is_over_10 = (
                any(w in q for w in ["yes", "10", "20", "15", "25", "30", "40", "50", "more", "over", "large", "exceed", "a lot", "opt_soil_10_plus"]) and
                not any(w in q for w in ["less", "under"])
            ) or (
                any(w in q for w in ["actually", "wait", "change", "correction"]) and any(w in q for w in ["10", "more", "over"])
            )
            is_under_10 = (
                any(w in q for w in ["less than 10", "under 10", "less than ten", "under ten", "5 cubic", "3 cubic", "2 cubic", "1 cubic", "few yards", "small amount", "minor", "opt_soil_under_10"]) or
                (any(w in q for w in ["no", "less", "under", "small", "tiny"]) and not is_over_10) or
                (any(w in q for w in ["actually", "wait", "change", "correction"]) and any(w in q for w in ["less", "under", "5", "small"]))
            )

            if is_over_10:
                if is_import:
                    return (self._build_soil_import_required_msg(), self.match_official_form_packet("soil importation permit application", force=True))
                else:
                    return (self._build_soil_export_required_msg(), self.match_official_form_packet("soil exportation permit application", force=True))
            elif is_under_10:
                return (self._build_soil_not_required_msg(), None)
            elif "10 cubic yards or more" in last_bot_msg:
                msg = (
                    "Under official Edison Township regulations, permit requirements depend on volume:\n\n"
                    "**Will the total volume be 10 cubic yards or more**, or is it less than 10 cubic yards?"
                )
                return (msg, None)

        return None

    def handle_site_improvement_flow(
        self,
        query: str,
        history: Optional[List[Dict[str, str]]] = None
    ) -> Optional[Tuple[str, Optional[FormIssuanceDetails]]]:
        """
        Interactive conversational guidance for Site Improvement Permits (SIP)
        under Page 5 of official Edison Township Permit Flow Charts.
        Decision rules:
        - Does work include > 500 s.f. new impervious coverage OR > 1,250 s.f. disturbance?
          - Yes -> Site Improvement Permit Required
          - No -> Does project include drainage improvements or grading?
            - Yes -> Site Improvement Permit Required
            - No -> Permit may not be required upon zoning review.
        """
        q = query.lower().strip()
        hist = history or []

        last_bot_msg = ""
        for msg in reversed(hist):
            if msg.get("role") in ["assistant", "model", "system"]:
                last_bot_msg = msg.get("content", "").lower()
                break

        in_site_flow = (
            "site improvement permit" in last_bot_msg or
            "impervious coverage" in last_bot_msg or
            "ground disturbance" in last_bot_msg or
            "drainage improvements, significant grading changes" in last_bot_msg
        )

        is_site_query = any(phrase in q for phrase in [
            "improve my property", "improving my property", "property improvement",
            "site improvement", "site improvements", "sip application", "sip permit",
            "ground disturbance", "impervious surface", "grading plan"
        ])

        if not in_site_flow and not is_site_query:
            return None

        # Turn 1: Initial inquiry
        if not in_site_flow:
            # Check upfront threshold
            if any(w in q for w in ["over 500", "over 1250", "more than 500", "more than 1250", "large disturbance", "commercial"]):
                return (self._build_site_improvement_required_msg(), self.match_official_form_packet("site improvement permit application"))

            msg = (
                "I can help you determine if your project requires an Edison Township **Site Improvement Permit (SIP)**.\n\n"
                "**Does your proposed work include more than 500 sq.ft. of new impervious coverage, OR 1,250 sq.ft. of ground disturbance?**\n\n"
                "*(Impervious coverage includes buildings, driveways, patios, and paved walkways.)*"
            )
            return (msg, None)

        # Turn 2: Assistant previously asked about 500 s.f. coverage / 1,250 s.f. disturbance
        if "500 sq.ft. of new impervious coverage" in last_bot_msg:
            is_yes = any(w in q for w in ["yes", "more", "over", "500", "1250", "exceed", "large"]) and not any(w in q for w in ["no", "less", "under"])
            is_no = any(w in q for w in ["no", "less", "under", "small", "neither", "under 500"])

            if is_yes:
                return (self._build_site_improvement_required_msg(), self.match_official_form_packet("site improvement permit application"))
            elif is_no:
                msg = (
                    "Although your project is under the primary disturbance threshold:\n\n"
                    "**Does your project include any drainage improvements, significant grading changes, or stormwater runoff alterations?**"
                )
                return (msg, None)
            else:
                msg = (
                    "Please confirm: **Does the proposed work exceed 500 sq.ft. of new impervious coverage OR 1,250 sq.ft. of ground disturbance?**"
                )
                return (msg, None)

        # Turn 3: Assistant previously asked about drainage improvements or grading
        if "drainage improvements, significant grading changes" in last_bot_msg:
            is_yes = any(w in q for w in ["yes", "drainage", "grading", "runoff", "slope", "direct"]) and not any(w in q for w in ["no", "neither", "none"])
            if is_yes:
                return (self._build_site_improvement_required_msg(), self.match_official_form_packet("site improvement permit application"))
            else:
                return (self._build_site_improvement_not_required_msg(), None)

        return None

    def _determine_step_options(self, msg: str, packet: Optional[FormIssuanceDetails]) -> Optional[List[FlowOption]]:
        """Determines interactive action or decision buttons based on message context."""
        m = msg.lower()
        if "approved permit for the tree removal" in m:
            return [
                FlowOption(id="opt_tree_has_permit", label="Yes, I have an approved permit", next_step="has_permit"),
                FlowOption(id="opt_tree_no_permit", label="No, I do not have a permit", next_step="no_permit"),
                FlowOption(id="opt_tree_urgent", label="It is an emergency / hazardous", next_step="urgent")
            ]
        if "urgent situation or emergency" in m:
            return [
                FlowOption(id="opt_tree_is_emergency", label="Yes, it is an emergency (dead, dying, or hazardous)", next_step="emergency"),
                FlowOption(id="opt_tree_planned", label="Planned, non-emergency removal", next_step="planned")
            ]
        if "10 cubic yards or more" in m:
            return [
                FlowOption(id="opt_soil_10_plus", label="10 cubic yards or more", next_step="soil_over_10"),
                FlowOption(id="opt_soil_under_10", label="Less than 10 cubic yards", next_step="soil_under_10")
            ]
        if "bring soil onto your property" in m:
            return [
                FlowOption(id="opt_soil_import", label="Bring soil (Import)", next_step="soil_import"),
                FlowOption(id="opt_soil_export", label="Remove soil (Export)", next_step="soil_export")
            ]
        if "part of a subdivision" in m:
            return [
                FlowOption(id="opt_tree_subdiv_yes", label="Yes, part of subdivision or demolition", next_step="subdiv_yes"),
                FlowOption(id="opt_tree_subdiv_no", label="No, standard residential project", next_step="subdiv_no")
            ]
        return None

    def answer_query(
        self,
        query: str,
        department_id: Optional[str] = "engineering",
        history: Optional[List[Dict[str, str]]] = None
    ) -> RagResult:
        """
        Executes grounded retrieval and synthesis for resident queries.
        Returns OUT_OF_CONTEXT_MESSAGE if the inquiry is out of engineering context.
        """
        # 1. Check if explicitly out of engineering context
        unsupported = self.check_unsupported_department_inquiry(query)
        if unsupported:
            return RagResult(
                answer=unsupported,
                citations=[],
                grounded=False,
                query=query
            )

        # 2. Service-aware intent detection & unconfigured service isolation
        from .services.service_intent_service import service_intent_service
        intent_res = service_intent_service.detect_intent(query, history=history)

        if intent_res.service_id == "greeting":
            return RagResult(
                answer="Hello! Welcome to CivicIQ. How can I help you with an Edison Township municipal service today?",
                citations=[],
                grounded=True,
                query=query
            )

        if intent_res.service_id == "out_of_context":
            return RagResult(
                answer=OUT_OF_CONTEXT_MESSAGE,
                citations=[],
                grounded=False,
                query=query
            )

        # Check ambiguous queries first (e.g. short street query, permit, removal)
        if intent_res.is_ambiguous and intent_res.clarifying_question:
            return RagResult(
                answer=intent_res.clarifying_question,
                citations=[],
                grounded=True,
                query=query,
                form_packet=None,
                options=intent_res.options
            )

        # Check if Road Opening / Street Excavation (Department of Public Works)
        is_road_or_street = (
            intent_res.service_id == "road_opening" or
            (intent_res.service_id == "unconfigured_service" and any(w in query.lower() for w in ["road open", "street open", "road excavation", "street excavation", "pavement cut", "road-opening", "street opening permit", "road opening permit", "excavation permit", "excavate driveway", "dig in the street", "open the road", "street removal"]))
        )
        if is_road_or_street:
            msg = (
                "Street Opening and Road Excavation applications in Edison Township are handled under the **Department of Public Works** (not Engineering).\n\n"
                "An interactive workflow is not currently configured for Street Opening & Road Excavation in CivicIQ. "
                "This service hasn't been configured yet for interactive processing. "
                "However, you can download the official blank [Township of Edison Street Opening Application (PDF)](/api/forms/engineering/RoadOpenApp.pdf) "
                "to complete and submit directly to the Department of Public Works."
            )
            return RagResult(
                answer=msg,
                citations=[],
                grounded=True,
                query=query,
                form_packet=None,
                options=[]
            )

        # Category 2: Grounded guidance & official document for services without interactive workflow
        # (Flood Zone, Permit Flow Chart, Plot Grading, Sewer Connection, Site Improvement)
        if intent_res.service_id in ["flood_zone", "permit_flowchart", "plot_grading", "sewer_connection", "site_improvement"]:
            detail_msg = service_intent_service.get_detail_response(intent_res.service_id, intent_res.detail_type, history=history)
            if not detail_msg:
                detail_msg = service_intent_service.get_detail_response(intent_res.service_id, "procedure", history=history)
            packet = self.match_official_form_packet(query, history=history, force=True)
            citations = []
            if packet:
                citation_url = (
                    packet.submission_routing.digital_upload_url 
                    if (packet.submission_routing and packet.submission_routing.digital_upload_url and packet.submission_routing.digital_upload_url.startswith("http"))
                    else packet.pdf_download_url
                )
                citations.append(
                    RagCitation(
                        url=citation_url,
                        title=packet.form_title,
                        category="Application Form",
                        department_id="engineering",
                        relevance_score=1.0,
                        excerpt=f"Official Township Application Form: {packet.form_title}. Form Code: {packet.form_code}. Download: {packet.pdf_download_url}",
                        visibility="public",
                        document_type="application_form",
                        service=packet.form_code,
                        verification_status="verified"
                    )
                )
            return RagResult(
                answer=detail_msg,
                citations=citations,
                grounded=True,
                query=query,
                form_packet=packet,
                options=[]
            )

        # Truly unconfigured or unsupported services (e.g. Zoning, Building, Animal Control)
        if intent_res.service_id in ["unconfigured_service", "zoning"] or not intent_res.is_supported:
            from .config import UNCONFIGURED_SERVICE_MESSAGE
            return RagResult(
                answer=UNCONFIGURED_SERVICE_MESSAGE,
                citations=[],
                grounded=True,
                query=query
            )

        # 2.5 Intent-Based Detail Retrieval (Progressive Disclosure)
        # Directly answer specific detail inquiries (fee, documents, submission, turnaround, complete process, age follow-up)
        if intent_res.detail_type not in ["procedure", "emergency"]:
            detail_msg = service_intent_service.get_detail_response(intent_res.service_id, intent_res.detail_type, history=history)
            if detail_msg:
                citations = []
                packet = self.match_official_form_packet(query, history=history, force=False)
                if packet:
                    citations.append(
                        RagCitation(
                            url=packet.pdf_download_url,
                            title=packet.form_title,
                            category="Application Form",
                            department_id="engineering",
                            relevance_score=1.0,
                            excerpt=f"Official Township Application Form: {packet.form_title}. Form Code: {packet.form_code}. Download: {packet.pdf_download_url}",
                            visibility="public",
                            document_type="application_form",
                            service=packet.form_code,
                            verification_status="verified"
                        )
                    )
                return RagResult(
                    answer=detail_msg,
                    citations=citations,
                    grounded=True,
                    query=query,
                    form_packet=packet,
                    options=self._determine_step_options(detail_msg, packet)
                )

        # 3. Check for multi-turn tree removal procedural guidance (Verified Service)
        if intent_res.service_id == "tree_removal":
            tree_flow_res = self.handle_tree_removal_flow(query, history=history)
            if tree_flow_res:
                msg, packet = tree_flow_res
                if packet is None and (intent_res.intent_type == "form_request" or any(w in query.lower() for w in ["application", "form", "pdf", "packet", "download"])):
                    packet = self.match_official_form_packet(query, history=history, force=True)
                citations = []
                if packet:
                    citations.append(
                        RagCitation(
                            url=packet.pdf_download_url,
                            title=packet.form_title,
                            category="Application Form",
                            department_id="engineering",
                            relevance_score=1.0,
                            excerpt=f"Official Township of Edison Tree Permit Application. Download: {packet.pdf_download_url}",
                            visibility="public",
                            document_type="application_form",
                            service="tree_removal",
                            verification_status="verified"
                        )
                    )
                return RagResult(
                    answer=msg,
                    citations=citations,
                    grounded=True,
                    query=query,
                    form_packet=packet,
                    options=self._determine_step_options(msg, packet)
                )

        # 4. Check for multi-turn soil import/export procedural guidance (Verified Service)
        if intent_res.service_id in ["soil_import", "soil_export", "soil_movement"]:
            soil_flow_res = self.handle_soil_flow(query, history=history)
            if soil_flow_res:
                msg, packet = soil_flow_res
                if packet is None and (intent_res.intent_type == "form_request" or any(w in query.lower() for w in ["application", "form", "pdf", "packet", "download"])):
                    packet = self.match_official_form_packet(query, history=history, force=True)
                citations = []
                if packet:
                    citations.append(
                        RagCitation(
                            url=packet.pdf_download_url,
                            title=packet.form_title,
                            category="Application Form",
                            department_id="engineering",
                            relevance_score=1.0,
                            excerpt=f"Official Township of Edison {packet.form_title}. Download: {packet.pdf_download_url}",
                            visibility="public",
                            document_type="application_form",
                            service=packet.form_code,
                            verification_status="verified"
                        )
                    )
                return RagResult(
                    answer=msg,
                    citations=citations,
                    grounded=True,
                    query=query,
                    form_packet=packet,
                    options=self._determine_step_options(msg, packet)
                )

        # 5. Emergency inquiry detail fallback
        if intent_res.detail_type == "emergency":
            detail_msg = service_intent_service.get_detail_response(intent_res.service_id, intent_res.detail_type)
            if detail_msg:
                packet = self.match_official_form_packet(query, history=history, force=True)
                citations = []
                if packet:
                    citations.append(
                        RagCitation(
                            url=packet.pdf_download_url,
                            title=packet.form_title,
                            category="Application Form",
                            department_id="engineering",
                            relevance_score=1.0,
                            excerpt=f"Official Township Application Form: {packet.form_title}. Form Code: {packet.form_code}. Download: {packet.pdf_download_url}",
                            visibility="public",
                            document_type="application_form",
                            service=packet.form_code,
                            verification_status="verified"
                        )
                    )
                return RagResult(
                    answer=detail_msg,
                    citations=citations,
                    grounded=True,
                    query=query,
                    form_packet=packet,
                    options=self._determine_step_options(detail_msg, packet)
                )

        # 6. Search vector store
        dept = department_id if department_id else "engineering"
        raw_citations: List[RagCitation] = vector_store.search(
            query=query,
            department_id=dept,
            top_k=6,
            threshold=SIMILARITY_THRESHOLD
        )

        # Filter out internal documents from resident citations and deduplicate by URL
        # Prompt Section 4: Correct source matching: Grounded citations must match the specific service requested
        seen_urls = set()
        citations = []
        for c in raw_citations:
            if getattr(c, "visibility", "public") == "internal":
                continue
            if "permit flow chart" in c.title.lower() or "flowchart" in getattr(c, "category", "").lower() or "permit_flow_charts" in c.url.lower():
                continue
            
            c_doc_name = (c.title + " " + getattr(c, "service", "")).lower()
            if intent_res.service_id == "tree_removal":
                if any(w in c_doc_name for w in ["zoning", "road open", "excavat", "sewer", "soil"]):
                    continue
            elif intent_res.service_id in ["soil_import", "soil_export", "soil_movement"]:
                if any(w in c_doc_name for w in ["zoning", "road open", "excavat", "sewer", "tree"]):
                    continue
            
            base_url = c.url.split("#")[0].split("?")[0]
            if base_url in seen_urls:
                continue
            seen_urls.add(base_url)
            citations.append(c)

        dept_config = registry.get_department(dept)
        dept_name = dept_config.name if dept_config else "Department of Engineering"

        # If no citations found above threshold
        if not citations:
            if intent_res.service_id == "tree_removal":
                packet = self.match_official_form_packet("tree removal", force=True)
                return RagResult(
                    answer=(
                        "Under Township of Edison Tree Protection regulations (Chapter 25-8), an approved **Tree Removal Permit** is required before removing mature trees on your property.\n\n"
                        "• **Filing Fee:** $25 standard residential fee (waived for seniors aged 62+ with valid proof of age; $200 with Board approval / subdivision).\n"
                        "• **Required Attachments:** Property survey or Tax Map sketch showing trees marked for removal, written statement of removal reasons, and site marking with ribbon or paint."
                    ),
                    citations=[],
                    grounded=True,
                    query=query,
                    form_packet=packet,
                    options=[]
                )
            if intent_res.service_id == "soil_import":
                packet = self.match_official_form_packet("soil import", force=True)
                return RagResult(
                    answer=self._build_soil_import_required_msg(),
                    citations=[],
                    grounded=True,
                    query=query,
                    form_packet=packet,
                    options=[]
                )
            if intent_res.service_id == "soil_export":
                packet = self.match_official_form_packet("soil export", force=True)
                return RagResult(
                    answer=self._build_soil_export_required_msg(),
                    citations=[],
                    grounded=True,
                    query=query,
                    form_packet=packet,
                    options=[]
                )
            # If the inquiry is genuinely an engineering inquiry, provide helpful grounded guidance
            if intent_res.service_id in ["other_engineering"]:
                guidance_msg = (
                    "I can help you with Edison Township municipal services such as Tree Removal, Soil Movement (Import / Export), Flood Zone Determination, Plot Grading Plans, Sewer Connections, Site Improvements, and Street Opening.\n\n"
                    "Please let me know which municipal service or project you would like assistance with, or explore official forms and documents at the [Township of Edison Document Center](https://www.edisonnj.org/document_center/index.php)."
                )
                return RagResult(
                    answer=guidance_msg,
                    citations=[],
                    grounded=True,
                    query=query
                )

            return RagResult(
                answer=OUT_OF_CONTEXT_MESSAGE,
                citations=[],
                grounded=False,
                query=query
            )

        # 7. Generate grounded answer via LLMClient (Gemini / Groq / Fallback) with history
        answer = llm_client.generate_answer(
            query=query,
            citations=citations,
            history=history,
            department_name=dept_name
        )

        return RagResult(
            answer=answer,
            citations=citations,
            grounded=True,
            query=query
        )

rag_engine = GroundedRagEngine()
