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
from .models import RagCitation, RagResult, FormIssuanceDetails, SubmissionRouting, FeeInfo
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
        """
        text = user_text.lower().strip()

        # If question is informational (asking about documents, fees, setbacks, or requesting a form download), don't hijack into a flow
        if any(phrase in text for phrase in [
            "can i download", "where can i download", "give me the form", "download the form", "download the application",
            "what documents", "what document", "what do i need to attach", "documents do i need", "what attachments",
            "how much is the fee", "fee schedule", "what is the fee", "what are the fees", "setback", "setbacks"
        ]):
            return None

        from .services.service_intent_service import service_intent_service
        intent = service_intent_service.detect_intent(user_text, history=history)

        if intent.has_flowchart and intent.flow_id:
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
        """
        t = text.lower()

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
            "permit application", "application", "how do i apply", "how to apply"
        ])

        if not force and not is_form_request:
            return None

        # Gather conversational context from current query and recent history
        context_text = t
        if history:
            for msg in history[-4:]:
                context_text += " " + msg.get("content", "").lower()

        # 0. Tree Removal Permit Application (Verified Official Form)
        is_tree_query = bool(re.search(r'\b(tree|trees|arborist|forester|sapling|stump|stumps|branch|branches)\b', t))
        if is_tree_query or any(w in context_text for w in ["tree removal", "tree permit", "remove tree", "cut tree"]):
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

        # 1. Soil Importation Permit Application
        if any(w in context_text for w in ["soil import", "soil importation", "import soil", "fill dirt", "bring soil"]):
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

        # 2. Soil Exportation Permit Application
        if any(w in context_text for w in ["soil export", "soil exportation", "export soil", "remove soil", "hauling soil"]):
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

        # 3. Site Improvement Permit Application with Checklist
        if any(w in context_text for w in ["site improvement", "site improvements", "sip application", "sip permit", "ground disturbance", "impervious surface", "site checklist"]):
            return FormIssuanceDetails(
                form_code="EDISON-ENG-SIP",
                form_title="Township of Edison Site Improvement Permit Application with Checklist",
                form_file="SIP_Application.pdf",
                pdf_download_url="/api/forms/engineering/SIP_Application.pdf",
                department_id="engineering",
                fill_in_instructions="1. Complete owner, contractor, and design engineer information.\n2. Complete Site Improvement Checklist (Items 1-25).\n3. Attach 2 signed/sealed engineering site plans.\n4. Submit to Division of Engineering.",
                required_attachments=[
                    "Two (2) signed and sealed copies of Site Improvement Engineering Plan",
                    "Completed Site Improvement Checklist",
                    "Stormwater management and runoff calculation report",
                    "Engineering review fee and inspection escrow deposit"
                ],
                fee_info=FeeInfo(
                    amount="Engineering review fee per municipal rate schedule",
                    payment_methods="Check payable to 'Township of Edison'"
                ),
                submission_routing=SubmissionRouting(
                    department="Department of Engineering",
                    desk="Engineering Division",
                    digital_upload_url="https://www.edisonnj.org/document_center/index.php"
                ),
                lead_time="10 to 14 Business Days"
            )

        # 4. Road Opening / Street Excavation
        normalized_t = t.replace("-", " ")
        is_road_explicit = any(w in normalized_t for w in ["road opening", "street opening", "pavement opening", "road excavation", "saw cut", "trench", "curb cut", "driveway apron", "pavement cut"])
        if is_road_explicit or any(w in context_text.replace("-", " ") for w in ["road opening", "street opening", "road excavation", "saw cut", "pavement opening", "public right of way"]):
            return FormIssuanceDetails(
                form_code="EDISON-DPW-ROADOPEN",
                form_title="Edison Township Street Opening & Road Excavation Application",
                form_file="RoadOpenApp.pdf",
                pdf_download_url="/api/forms/engineering/RoadOpenApp.pdf",
                department_id="engineering",
                fill_in_instructions="1. Affix NJ 811 Call Before You Dig ticket number.\n2. Submit sketch of proposed pavement trench dimensions.\n3. Post $5,000 restoration guarantee bond.\n4. Submit online via the official municipal portal at https://www.edisonnj.org/document_center/index.php.",
                required_attachments=[
                    "NJ 811 One-Call Utility Mark-Out confirmation ticket",
                    "$5,000 Refundable Restoration Guarantee Deposit / Surety Bond",
                    "Traffic Control Detour Plan (if blocking public lanes)",
                    "Certificate of Commercial Liability Insurance naming Township of Edison"
                ],
                fee_info=FeeInfo(
                    amount="$150 Filing Fee + $5,000 Restoration Guarantee Bond",
                    payment_methods="Certified Bank Check or Bond"
                ),
                submission_routing=SubmissionRouting(
                    department="Department of Engineering",
                    desk="Engineering Division",
                    digital_upload_url="https://www.edisonnj.org/document_center/index.php"
                ),
                lead_time="5 to 7 Business Days"
            )

        # 2. Sewer Connection
        if any(w in context_text for w in ["sewer", "tap", "connection", "lateral", "sanitary"]) and not any(w in context_text for w in ["tree", "soil", "dirt"]):
            return FormIssuanceDetails(
                form_code="EDISON-ENG-SEWER",
                form_title="Township of Edison Sewer Connection Charge Application",
                form_file="Sewer_Connection_Charge_Applications.pdf",
                pdf_download_url="/api/forms/engineering/Sewer_Connection_Charge_Applications.pdf",
                department_id="engineering",
                fill_in_instructions="1. Enter parcel Block, Lot, and property owner details.\n2. Fill out plumbing fixture unit count worksheet.\n3. Attach plumbing schematic.\n4. Submit online via the official municipal portal at https://www.edisonnj.org/document_center/index.php.",
                required_attachments=[
                    "Plumbing Fixture Unit Calculation Schedule",
                    "Civil engineering utility connection schematic",
                    "Copy of approved building or engineering permit",
                    "Sewer connection review fee payment"
                ],
                fee_info=FeeInfo(
                    amount="Calculated per fixture unit according to municipal rate code",
                    payment_methods="Check payable to 'Township of Edison Sewer Utility'"
                ),
                submission_routing=SubmissionRouting(
                    department="Department of Engineering",
                    desk="Sewer Utility Division",
                    digital_upload_url="https://www.edisonnj.org/document_center/index.php"
                ),
                lead_time="7 to 10 Business Days"
            )

        # 5. Residential Zoning Permit (Dwelling, Addition, Shed, Pool, Deck, Fence)
        if any(w in context_text for w in [
            "zoning permit", "zoning application", "new dwelling", "addition", "shed permit",
            "deck permit", "pool permit", "fence permit", "residential construction"
        ]) and not any(w in context_text for w in ["tree", "soil", "dirt", "road opening", "street opening", "sewer", "site improvement"]):
            return FormIssuanceDetails(
                form_code="EDISON-ENG-ZONING",
                form_title="Township of Edison Official Zoning Permit Application Form",
                form_file="Zoning_Permit_Application_Edison.pdf",
                pdf_download_url="/api/forms/engineering/Zoning_Permit_Application_Edison.pdf",
                department_id="engineering",
                fill_in_instructions="1. Complete Property Owner data, Work Site Address, Block, and Lot.\n2. Attach two (2) signed and sealed surveys.\n3. Submit to Division of Zoning, 100 Municipal Blvd.",
                required_attachments=[
                    "Two (2) copies of current property survey sealed by NJ Licensed Surveyor",
                    "Plot plan showing exact dimensions and setbacks",
                    "Application review fee"
                ],
                fee_info=FeeInfo(
                    amount="Fee schedule per municipal ordinance ($50 - $200)",
                    payment_methods="Check payable to 'Township of Edison' or Credit Card"
                ),
                submission_routing=SubmissionRouting(
                    department="Department of Planning and Engineering",
                    desk="Division of Zoning, Edison Municipal Complex",
                    building_address="100 Municipal Boulevard, Edison, NJ 08817",
                    digital_upload_url="https://www.edisonnj.org/document_center/index.php"
                ),
                lead_time="10 to 14 Business Days"
            )

        return None

    def handle_tree_removal_flow(
        self,
        query: str,
        history: Optional[List[Dict[str, str]]] = None
    ) -> Optional[Tuple[str, Optional[FormIssuanceDetails]]]:
        """
        Interactive conversational guidance for tree removal under official
        Edison Township Permit Flow Charts (Permit Flow Charts.pdf - Page 3: Tree Removal Permit).
        
        Handles:
        - Resident asks to be guided with tree removal -> asks 'Do you currently have an approved permit?'
        - Resident replies 'No' -> asks if urgent/emergency
        - Resident says 'it's urgent' / 'no time to ask for permit' -> asks for reason
        - Resident explains reason -> if valid hazard, explains immediate removal is allowed
          concurrent to permit application, and delivers official form packet.
        - If non-emergency, checks if part of subdivision / demolition.
        """
        q = query.lower().strip()
        hist = history or []

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
                    "### 1. Applicable Procedure\n"
                    "For planned or non-emergency tree removal in Edison Township, municipal regulations require that you obtain an approved **Tree Removal Permit** from the Division of Engineering prior to cutting down or removing any regulated trees on your property.\n\n"
                    "### 2. Important Requirements & Supporting Documents\n"
                    "• **Completed Municipal Application**: Official Township of Edison Tree Permit (Removal/Replacement/Conservation) Application.\n"
                    "• **Property Sketch or Survey**: A plot plan or survey showing property boundaries and indicating the exact location, diameter, and species of the trees proposed for removal.\n"
                    "• **Contractor Information**: Details of the NJ licensed tree care operator performing the removal.\n"
                    "• **Standard Application Fee**: $25.00 for residential removal of 1 to 3 trees (review fee is waived for senior citizens aged 62+).\n\n"
                    "### 3. Next Steps for Resident\n"
                    "1. Download and complete the official municipal application form provided below.\n"
                    "2. Attach a property sketch showing tree locations and diameter measurements.\n"
                    "3. Submit the completed application and $25 review fee to the Division of Engineering.\n"
                    "4. Await engineering review and permit issuance before commencing any tree cutting.\n\n"
                    "### Relevant Official Documents & Forms\n"
                    "- [Township of Edison Official Tree Removal Application Form (PDF)](/api/forms/engineering/3.23.21%20tree%20permit%20application.pdf)"
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
                    "### 1. Applicable Procedure\n"
                    "Under official Edison Township tree preservation guidelines, an emergency removal is permitted when a tree is dead, dying, or presents an imminent hazard to life, structures, or public safety. You are authorized to proceed with immediate removal to eliminate danger, provided that you submit your official municipal permit application concurrently with documentation of the emergency.\n\n"
                    "### 2. Important Requirements & Supporting Documents\n"
                    "• **Hazard Documentation**: Clear photographic evidence showing the dead, dying, or structurally dangerous condition of the tree, OR a certified letter from a licensed tree expert/arborist confirming imminent danger.\n"
                    "• **Completed Municipal Application**: Official Township of Edison Tree Permit (Removal/Replacement/Conservation) Application.\n"
                    "• **Standard Application Fee**: $25.00 filing fee (fee waived for senior citizens aged 62+).\n"
                    "• **Property Details**: Block, Lot, property address, and property owner authorization.\n\n"
                    "### 3. Next Steps for Resident\n"
                    "1. Document the hazard immediately by taking clear photos or obtaining an arborist letter.\n"
                    "2. Proceed with safe emergency removal of the hazardous tree to eliminate imminent risk.\n"
                    "3. Complete the official municipal application form below.\n"
                    "4. Submit the completed application and hazard evidence concurrently to the Edison Township Division of Engineering.\n\n"
                    "### Relevant Official Documents & Forms\n"
                    "- [Township of Edison Official Tree Removal Application Form (PDF)](/api/forms/engineering/3.23.21%20tree%20permit%20application.pdf)"
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
                    "### 1. Applicable Procedure\n"
                    "Under official Edison Township municipal guidelines, because your project does not involve removing trees and is NOT "
                    "part of a subdivision or demolition permit from Code Enforcement, **a Tree Removal Permit is NOT required**.\n\n"
                    "### 2. Important Requirements & Supporting Documents\n"
                    "• No municipal tree permit application or fee is required for this scope of work.\n"
                    "• If your project scope changes to include tree cutting or land clearing, an engineering permit review will be required.\n\n"
                    "### 3. Next Steps for Resident\n"
                    "You may proceed with your project without filing a tree removal application. For general municipal inquiries, visit https://www.edisonnj.org/document_center/index.php."
                )
                return (msg, None)
            else:
                msg = (
                    "### 1. Applicable Procedure\n"
                    "Under official Edison Township guidelines, because your project is part of a subdivision "
                    "or involves a demolition permit from Code Enforcement, **a Tree Removal Permit is required** before removing any trees or clearing land.\n\n"
                    "### 2. Important Requirements & Supporting Documents\n"
                    "• **Completed Municipal Application**: Official Township of Edison Tree Permit (Removal/Replacement/Conservation) Application.\n"
                    "• **Site / Demolition Plan**: Sealed site survey showing tree locations, limits of disturbance, and tree protection measures.\n"
                    "• **Tree Replacement Plan**: Mitigation plan or fund contribution conforming to Township Code Chapter 25.\n\n"
                    "### 3. Next Steps for Resident\n"
                    "1. Download and complete the official Tree Removal Application Form below.\n"
                    "2. Coordinate with your engineer to submit the tree application alongside your Planning Board or Code Enforcement package.\n"
                    "3. Submit all materials to the Division of Engineering.\n\n"
                    "### Relevant Official Documents & Forms\n"
                    "- [Township of Edison Official Tree Removal Application Form (PDF)](/api/forms/engineering/3.23.21%20tree%20permit%20application.pdf)"
                )
                return (msg, self.match_official_form_packet("tree removal", force=True))

        return None

    def _build_soil_import_required_msg(self) -> str:
        return (
            "### 1. Applicable Procedure\n"
            "Because you are importing 10 cubic yards or more of soil onto your property in Edison Township, a **Soil Importation Permit** is required under municipal regulations (Chapter 31) prior to bringing any fill onto the site.\n\n"
            "### 2. Important Requirements & Supporting Documents\n"
            "• **Certified Clean Fill Lab Analysis**: Laboratory chemical analysis certifying that fill material is uncontaminated and free of foreign debris.\n"
            "• **Property Survey & Grading Plan**: Certified property survey showing proposed fill placement, existing grades, and proposed finished grading contours.\n"
            "• **Designated Haul Route**: Approved truck haul route through Edison Township roadways.\n"
            "• **Filing Fee & Engineering Escrow**: Standard municipal review fee and engineering escrow deposit.\n\n"
            "### 3. Next Steps for Resident\n"
            "1. Download and complete the official **Township of Edison Soil Importation Permit Application** below.\n"
            "2. Obtain clean fill certification documentation from your supplier or source site.\n"
            "3. Prepare a grading sketch or survey showing where soil will be placed.\n"
            "4. Submit the completed application and attachments to the Division of Engineering.\n"
            "5. Await engineering review and permit issuance before transporting soil.\n\n"
            "### Relevant Official Documents & Forms\n"
            "- [Township of Edison Soil Importation Permit Application (PDF)](/api/forms/engineering/Forms_Soil_Importation_Appl.pdf)"
        )

    def _build_soil_export_required_msg(self) -> str:
        return (
            "### 1. Applicable Procedure\n"
            "Because you are exporting 10 cubic yards or more of soil from your property in Edison Township, a **Soil Exportation Permit** is required under municipal regulations (Chapter 31) prior to removing soil from the site.\n\n"
            "### 2. Important Requirements & Supporting Documents\n"
            "• **Topographical Survey with Cut/Fill Calculations**: Prepared and certified by a NJ licensed professional engineer or surveyor.\n"
            "• **Soil Erosion & Sediment Control Certification**: Measures to prevent runoff and dust during excavation.\n"
            "• **Designated Truck Haul Route**: Approved municipal travel route through Edison.\n"
            "• **Filing Fee & Performance Guarantee**: Standard municipal fee and restoration guarantee bond.\n\n"
            "### 3. Next Steps for Resident\n"
            "1. Download and complete the official **Township of Edison Soil Exportation Permit Application** below.\n"
            "2. Coordinate with your engineer/contractor to prepare cut/fill calculations and haul route.\n"
            "3. Submit the completed application and attachments to the Division of Engineering.\n"
            "4. Await engineering review and permit issuance before hauling soil off-site.\n\n"
            "### Relevant Official Documents & Forms\n"
            "- [Township of Edison Soil Exportation Permit Application (PDF)](/api/forms/engineering/Forms_Soil_Exportation_App.pdf)"
        )

    def _build_soil_not_required_msg(self) -> str:
        return (
            "### 1. Applicable Procedure\n"
            "Under official Township of Edison engineering guidelines, because your project involves **less than 10 cubic yards of soil**, a municipal Soil Import / Export Permit is **NOT required**.\n\n"
            "### 2. Important Requirements & Environmental Best Practices\n"
            "• **No Permit or Fee**: No municipal soil permit application, review fee, or escrow deposit is required for quantities under 10 cubic yards.\n"
            "• **Drainage Protection**: When placing soil, ensure that grading does not alter natural drainage patterns or direct stormwater runoff onto neighboring properties.\n"
            "• **Ground Disturbance Check**: If your project also involves major site grading (disturbing 1,250 sq.ft. or more) or new impervious coverage (500 sq.ft. or more), an engineering Site Improvement review may be required.\n\n"
            "### 3. Next Steps for Resident\n"
            "You may proceed with your project without filing a soil permit application. If you have additional engineering or zoning questions, visit https://www.edisonnj.org/document_center/index.php."
        )

    def _build_site_improvement_required_msg(self) -> str:
        return (
            "### 1. Applicable Procedure\n"
            "Under official Edison Township engineering regulations, your project requires an approved **Site Improvement Permit (SIP)** with Checklist prior to commencing site work, grading, or ground disturbance.\n\n"
            "### 2. Important Requirements & Supporting Documents\n"
            "• **Site Improvement Plan**: Two (2) signed and sealed copies of engineering site plans prepared by a NJ licensed professional engineer.\n"
            "• **Completed 25-Point Checklist**: Official municipal Site Improvement Checklist completed by applicant or engineer.\n"
            "• **Stormwater Management Report**: Runoff calculations and drainage design.\n"
            "• **Review & Inspection Escrow**: Engineering review fee and inspection escrow deposit.\n\n"
            "### 3. Next Steps for Resident\n"
            "1. Download and complete the official **Township of Edison Site Improvement Permit Application with Checklist** below.\n"
            "2. Work with your licensed civil engineer to prepare sealed site improvement plans.\n"
            "3. Submit the completed application, checklist, plans, and review fees to the Division of Engineering.\n"
            "4. Await engineering review and permit issuance before commencing any excavation or grading.\n\n"
            "### Relevant Official Documents & Forms\n"
            "- [Township of Edison Site Improvement Permit Application with Checklist (PDF)](/api/forms/engineering/SIP_Application.pdf)"
        )

    def _build_site_improvement_not_required_msg(self) -> str:
        return (
            "### 1. Applicable Procedure\n"
            "Under official Township of Edison guidelines, a **Site Improvement Permit may not be required** for your project because your work does not exceed 500 sq.ft. of impervious coverage, does not exceed 1,250 sq.ft. of disturbance, and does not alter drainage or grading.\n\n"
            "### 2. Important Requirements & Next Steps\n"
            "• **Final Determination**: A final determination will be confirmed when your standard Zoning Permit or Building Permit application is reviewed by the township.\n"
            "• If your project scope expands to exceed coverage thresholds or includes site grading, a Site Improvement review will then be required.\n\n"
            "### 3. Next Steps for Resident\n"
            "You may proceed with submitting your standard zoning/building permit application. For municipal document references, visit https://www.edisonnj.org/document_center/index.php."
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

        in_soil_flow = (
            "soil regulations" in last_bot_msg or
            "soil import requirements" in last_bot_msg or
            "soil export requirements" in last_bot_msg or
            "planning to bring soil onto your property" in last_bot_msg or
            "10 cubic yards or more" in last_bot_msg
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

        # Turn 3: Assistant previously asked: 'Is it 10 cubic yards or more?'
        if "10 cubic yards or more" in last_bot_msg:
            # Determine if this was an import or export flow from history
            is_export = any("export" in m.get("content", "").lower() or "remove" in m.get("content", "").lower() for m in hist)
            is_import = not is_export

            is_over_10 = any(w in q for w in ["yes", "10", "20", "15", "25", "30", "40", "50", "more", "over", "large", "exceed", "a lot"]) and not any(w in q for w in ["less", "under", "no"])
            is_under_10 = any(w in q for w in ["no", "less", "under", "small", "5", "3", "2", "1", "few", "tiny", "minor"])

            if is_over_10:
                if is_import:
                    return (self._build_soil_import_required_msg(), self.match_official_form_packet("give me the soil importation permit application"))
                else:
                    return (self._build_soil_export_required_msg(), self.match_official_form_packet("give me the soil exportation permit application"))
            elif is_under_10:
                return (self._build_soil_not_required_msg(), None)
            else:
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

        # 2. Check for multi-turn tree removal procedural guidance
        tree_flow_res = self.handle_tree_removal_flow(query, history=history)
        if tree_flow_res:
            msg, packet = tree_flow_res
            citations = []
            if packet:
                citations.append(
                    RagCitation(
                        url=packet.pdf_download_url,
                        title=packet.form_title,
                        category="Application Form",
                        department_id="engineering",
                        relevance_score=1.0,
                        excerpt=f"Official Township of Edison Tree Permit (Removal/Replacement/Conservation) Application. Code: {packet.form_code}. Download: {packet.pdf_download_url}",
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
                form_packet=packet
            )

        # 3. Check for multi-turn soil import/export procedural guidance
        soil_flow_res = self.handle_soil_flow(query, history=history)
        if soil_flow_res:
            msg, packet = soil_flow_res
            citations = []
            if packet:
                citations.append(
                    RagCitation(
                        url=packet.pdf_download_url,
                        title=packet.form_title,
                        category="Application Form",
                        department_id="engineering",
                        relevance_score=1.0,
                        excerpt=f"Official Township of Edison {packet.form_title}. Code: {packet.form_code}. Download: {packet.pdf_download_url}",
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
                form_packet=packet
            )

        # 4. Check for multi-turn site improvement procedural guidance
        site_flow_res = self.handle_site_improvement_flow(query, history=history)
        if site_flow_res:
            msg, packet = site_flow_res
            citations = []
            if packet:
                citations.append(
                    RagCitation(
                        url=packet.pdf_download_url,
                        title=packet.form_title,
                        category="Application Form",
                        department_id="engineering",
                        relevance_score=1.0,
                        excerpt=f"Official Township of Edison {packet.form_title}. Code: {packet.form_code}. Download: {packet.pdf_download_url}",
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
                form_packet=packet
            )

        # 5. Service-aware intent and ambiguity check
        from .services.service_intent_service import service_intent_service
        intent_res = service_intent_service.detect_intent(query, history=history)
        if intent_res.is_ambiguous and intent_res.clarifying_question:
            return RagResult(
                answer=intent_res.clarifying_question,
                citations=[],
                grounded=True,
                query=query,
                form_packet=None
            )
        if intent_res.service_id == "out_of_context":
            return RagResult(
                answer=OUT_OF_CONTEXT_MESSAGE,
                citations=[],
                grounded=False,
                query=query
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
        seen_urls = set()
        citations = []
        for c in raw_citations:
            if getattr(c, "visibility", "public") == "internal":
                continue
            if "permit flow chart" in c.title.lower() or "flowchart" in getattr(c, "category", "").lower() or "permit_flow_charts" in c.url.lower():
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
            # If the inquiry is genuinely an engineering inquiry, provide helpful grounded guidance
            if intent_res.service_id in ["other_engineering", "road_opening", "sewer_connection", "zoning", "soil_import", "soil_export", "site_improvement"]:
                guidance_msg = (
                    f"### Edison Township Department of Engineering\n\n"
                    f"Regarding your inquiry concerning **{query.strip()}**:\n\n"
                    f"Edison Township municipal engineering guidelines require that all civil work, curb modifications, driveway connections, or drainage alterations comply with current township engineering standards.\n\n"
                    f"### Next Steps for Resident\n"
                    f"1. To review technical engineering specifications, standard construction details, or submit engineering plan packages, please visit the official municipal document center at https://www.edisonnj.org/document_center/index.php.\n"
                    f"2. For specific driveway, curb-cut, or drainage reviews, prepare a property survey showing the proposed work dimensions for engineering intake."
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
