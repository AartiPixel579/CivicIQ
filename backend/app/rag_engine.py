"""
Grounded Municipal RAG Engine & Multi-Turn Intent Router for CivicIQ
("Mushkil Your Edison Township Buddy" - Edison Township Department of Engineering)
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

    def detect_flow_intent(self, user_text: str, department_id: Optional[str] = None) -> Optional[Tuple[str, str]]:
        """
        Detects if user intent is procedural (starting a multi-step engineering flow).
        """
        text = user_text.lower().strip()

        # If question is informational or requesting a download, don't hijack into a flow
        if any(text.startswith(s) for s in ["what", "how much", "where", "can i download", "give me"]):
            return None

        # 1. Street Opening & Road Excavation Permit
        if any(k in text for k in [
            "apply for street opening", "start street opening", "apply for excavation",
            "start excavation", "need excavation permit", "street opening permit",
            "road opening", "road-opening", "street opening", "pavement excavation",
            "excavation permit", "street_opening_flow"
        ]):
            return ("engineering", "street_opening_flow")

        # 2. Tree Removal Clearance & Permit Decision Flow (Page 3 of Permit Flow Charts)
        if bool(re.search(r'\b(tree|trees|arborist|forester|sapling|stump|stumps|branch|branches)\b', text)) or "subdivision" in text:
            return ("engineering", "tree_removal_flow")

        # 3. Sewer Connection Charge Application
        if any(k in text for k in [
            "start sewer connection", "apply for sewer connection", "sewer connection flow",
            "sewer_connection_flow"
        ]):
            return ("engineering", "sewer_connection_flow")

        # 4. Residential Construction / Engineering Permit
        if any(k in text for k in [
            "start residential permit", "apply for residential permit",
            "residential_zoning_permit_flow"
        ]):
            return ("engineering", "residential_zoning_permit_flow")

        return None

    def match_official_form_packet(
        self,
        text: str,
        department_id: str = "engineering",
        history: Optional[List[Dict[str, str]]] = None
    ) -> Optional[FormIssuanceDetails]:
        """
        Delivers an official form packet ONLY when the resident explicitly asks for a form/download.
        Uses conversation history to accurately identify WHICH form is needed.
        """
        t = text.lower()

        # Check for explicit form/download requests
        is_form_request = any(phrase in t for phrase in [
            "download form", "download the form", "give me the form", "provide the form",
            "get the form", "send the form", "application form", "official form",
            "download application", "where can i download", "pdf form", "need the form",
            "need the application", "give me that form", "send me the form",
            "send me the application", "access the form", "where is the form",
            "download the application form", "download official form",
            "give me the road opening application", "official application form"
        ])

        if not is_form_request:
            return None

        # Gather conversational context from current query and recent history
        context_text = t
        if history:
            for msg in history[-4:]:
                context_text += " " + msg.get("content", "").lower()

        # Check if query is about trees first to prevent history bleed and avoid hallucinating unverified forms
        is_tree_query = bool(re.search(r'\b(tree|trees|arborist|forester|sapling|stump|stumps|branch|branches)\b', t))
        if is_tree_query:
            # Standalone Tree Removal application form is NOT verified on the official Document Center.
            # Do NOT return a form packet or substitute an unrelated application.
            return None

        # 1. Road Opening / Street Excavation
        is_road_explicit = any(w in t for w in ["road", "street", "opening", "excavat", "trench", "pavement", "curb cut", "dig"])
        if is_road_explicit or any(w in context_text for w in ["road opening", "street opening", "excavat", "saw-cut", "pavement opening"]):
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
        if any(w in context_text for w in ["sewer", "tap", "connection", "lateral", "sanitary"]):
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

        # 3. General Engineering / Permit Application
        if any(w in context_text for w in ["permit", "construction", "building", "dwelling", "addition", "shed", "deck", "pool", "fence", "engineering", "zoning"]):
            return FormIssuanceDetails(
                form_code="EDISON-ENG-PERMIT",
                form_title="Township of Edison Official Permit Application Form",
                form_file="Zoning_Permit_Application_Edison.pdf",
                pdf_download_url="/api/forms/engineering/Zoning_Permit_Application_Edison.pdf",
                department_id="engineering",
                fill_in_instructions="1. Download or print the official municipal application.\n2. Complete Property Owner data, Work Site Address, Block, and Lot.\n3. Attach two (2) signed and sealed surveys.\n4. Submit online via the official municipal portal at https://www.edisonnj.org/document_center/index.php.",
                required_attachments=[
                    "Two (2) copies of current property survey sealed by NJ Licensed Surveyor",
                    "Plot plan showing exact dimensions and setbacks",
                    "Contractor registration & insurance",
                    "Application review fee"
                ],
                fee_info=FeeInfo(
                    amount="Fee schedule per municipal ordinance",
                    payment_methods="Check payable to 'Township of Edison' or Credit Card"
                ),
                submission_routing=SubmissionRouting(
                    department="Department of Engineering",
                    desk="Engineering Division",
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
                    "Under the official **Edison Township Permit Flow Chart** for planned tree removals:\n\n"
                    "**Is this tree removal part of a subdivision or does it require a demolition permit from Code Enforcement?**\n"
                    "• If **Yes**: A permit is required before removing the tree.\n"
                    "• If **No**: A permit is not required under the flowchart."
                )
                return (msg, None)
            else:
                msg = (
                    "Understood. If this is an urgent situation, please explain the reason: **What is the emergency condition of the tree?**\n\n"
                    "(For example, is the tree dead or dying, cracked, leaning dangerously over your home, power lines, or driveway, or presenting an eminent danger to safety?)"
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
                    "Thank you for providing the details. Because this situation involves an imminent danger (a dead, dying, or structurally hazardous tree):\n\n"
                    "According to the official **Edison Township Permit Flow Charts** (Page 3):\n"
                    "1. **Document Immediate Evidence**: Take photographic proof showing the tree's hazardous condition, or obtain a certified letter from a licensed arborist/forester confirming the tree is dead/dying and presents an imminent danger.\n"
                    "2. **Immediate Removal Authorized**: You may proceed with removing the tree immediately to safeguard life and property.\n"
                    "3. **Concurrent Permit Filing**: You must submit your official permit application concurrent to (or immediately following) the tree removal along with your proof.\n\n"
                    "*(Note: An official standalone Tree Removal application form has not yet been verified on the official Edison Township Document Center. Please visit https://www.edisonnj.org/document_center/index.php for official updates.)*"
                )
                return (msg, None)
            else:
                msg = (
                    "Based on your description, this situation does not appear to involve an imminent safety hazard or dead/dying tree.\n\n"
                    "Under the official **Edison Township Tree Removal Flow Chart**:\n"
                    "**Is this tree removal part of a subdivision or does it require a demolition permit from Code Enforcement?**\n"
                    "• If **Yes**: A permit is required prior to tree removal.\n"
                    "• If **No**: A permit is NOT required under the flowchart."
                )
                return (msg, None)

        # Turn 4: Assistant previously asked: 'Is this tree removal part of a subdivision...'
        if "part of a subdivision" in last_bot_msg:
            if re.search(r'\b(no|nope|not|negative|never)\b', q):
                msg = (
                    "Under the official **Edison Township Permit Flow Charts** (Page 3), because you are not removing trees and your project is NOT "
                    "part of a subdivision or demolition permit from Code, **a Tree Removal Permit is NOT required**.\n\n"
                    "For more municipal guidance or document references, please visit https://www.edisonnj.org/document_center/index.php."
                )
                return (msg, None)
            else:
                msg = (
                    "Under the official **Edison Township Permit Flow Charts** (Page 3), because your project is part of a subdivision "
                    "or involves a demolition permit from Code Enforcement, **a Tree Removal Permit is required** before removing any trees.\n\n"
                    "*(Note: An official standalone Tree Removal application form has not yet been verified on the official Edison Township Document Center. Please visit https://www.edisonnj.org/document_center/index.php for official updates.)*"
                )
                return (msg, None)

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
            return RagResult(
                answer=msg,
                citations=[
                    RagCitation(
                        url="https://cms2.revize.com/revize/edisonnj/document_center/Permit%20Flow%20Charts.pdf",
                        title="Township of Edison Official Permit Flow Charts",
                        category="Permit Flow Charts",
                        department_id="engineering",
                        relevance_score=1.0,
                        excerpt="Official Edison Township Tree Removal Flow Chart: Take photographic proof or get a certified letter from a licensed arborist/forester stating the tree is dead/dying and is an eminent danger. Remove the tree and submit for permit concurrent to tree removal."
                    )
                ],
                grounded=True,
                query=query,
                form_packet=packet
            )

        # 2. Search vector store
        dept = department_id if department_id else "engineering"
        citations: List[RagCitation] = vector_store.search(
            query=query,
            department_id=dept,
            top_k=4,
            threshold=SIMILARITY_THRESHOLD
        )

        dept_config = registry.get_department(dept)
        dept_name = dept_config.name if dept_config else "Department of Engineering"

        # If no citations found above threshold -> out of context
        if not citations:
            return RagResult(
                answer=OUT_OF_CONTEXT_MESSAGE,
                citations=[],
                grounded=False,
                query=query
            )

        # 3. Generate grounded answer via LLMClient (Gemini / Groq / Fallback) with history
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
