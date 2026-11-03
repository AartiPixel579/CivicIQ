"""
Grounded Municipal RAG Engine & Multi-Turn Intent Router for CivicIQ
("Your civic intelligence buddy" - Edison Township Department of Engineering)
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
            "street_opening_flow"
        ]):
            return ("engineering", "street_opening_flow")

        # 2. Tree Removal Clearance & Permit
        if any(k in text for k in [
            "start tree removal", "apply for tree removal", "tree removal flow",
            "tree_removal_flow"
        ]):
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

        # 1. Road Opening / Street Excavation
        if any(w in context_text for w in ["road", "street", "opening", "excavation", "trench", "pavement", "curb cut", "dig"]):
            return FormIssuanceDetails(
                form_code="EDISON-DPW-ROADOPEN",
                form_title="Edison Township Street Opening & Road Excavation Application",
                form_file="RoadOpenApp.pdf",
                pdf_download_url="/api/forms/engineering/RoadOpenApp.pdf",
                department_id="engineering",
                fill_in_instructions="1. Affix NJ 811 Call Before You Dig ticket number.\n2. Submit sketch of proposed pavement trench dimensions.\n3. Post $5,000 restoration guarantee bond.\n4. Submit to Department of Public Works / Engineering.",
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
                    desk="Engineering Intake Counter",
                    building_address="100 Municipal Blvd, Edison, NJ 08817",
                    hours="Monday – Friday: 8:00 AM – 4:30 PM",
                    contact_phone="(732) 248-7288",
                    contact_email="engineering@edisonnj.gov",
                    digital_upload_url="https://www.edisonnj.org/document_center/RoadOpenApp.pdf"
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
                fill_in_instructions="1. Enter parcel Block, Lot, and property owner details.\n2. Fill out plumbing fixture unit count worksheet.\n3. Attach plumbing schematic.\n4. Submit to Sewer Utility / Engineering Division.",
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
                    desk="Engineering Counter, Municipal Complex",
                    building_address="100 Municipal Blvd, Edison, NJ 08817",
                    hours="Monday – Friday: 8:00 AM – 4:30 PM",
                    contact_phone="(732) 248-7288",
                    contact_email="engineering@edisonnj.gov",
                    digital_upload_url="https://www.edisonnj.org/Sewer%20Connection%20Charge%20Applications.pdf"
                ),
                lead_time="7 to 10 Business Days"
            )

        # 3. Tree Removal
        if any(w in context_text for w in ["tree", "removal", "clearance", "dbh", "forestry"]):
            return FormIssuanceDetails(
                form_code="EDISON-ENG-TREE",
                form_title="Edison Township Tree Removal & Preservation Requirement Sheet",
                form_file="ZONING_PERMIT_REQUIREMENT_SHEET.pdf",
                pdf_download_url="/api/forms/engineering/ZONING_PERMIT_REQUIREMENT_SHEET.pdf",
                department_id="engineering",
                fill_in_instructions="1. Submit plot plan indicating DBH and species of trees to be removed.\n2. Provide replacement canopy plan.\n3. Submit to Township Engineering / Municipal Arborist.",
                required_attachments=[
                    "Site plot plan showing tree locations to be removed",
                    "Canopy replacement planting proposal or contribution waiver request",
                    "Property owner certification"
                ],
                fee_info=FeeInfo(
                    amount="$25 application review fee",
                    payment_methods="Check payable to 'Township of Edison'"
                ),
                submission_routing=SubmissionRouting(
                    department="Department of Engineering",
                    desk="Engineering Intake Counter",
                    building_address="100 Municipal Blvd, Edison, NJ 08817",
                    hours="Monday – Friday: 8:00 AM – 4:30 PM",
                    contact_phone="(732) 248-7288",
                    contact_email="engineering@edisonnj.gov",
                    digital_upload_url="https://www.edisonnj.org/document_center/ZONING%20PERMIT%20REQUIREMENT%20SHEET.pdf"
                ),
                lead_time="5 to 7 Business Days"
            )

        # 4. General Engineering / Permit Application
        if any(w in context_text for w in ["permit", "construction", "building", "dwelling", "addition", "shed", "deck", "pool", "fence", "engineering", "zoning"]):
            return FormIssuanceDetails(
                form_code="EDISON-ENG-PERMIT",
                form_title="Township of Edison Official Permit Application Form",
                form_file="Zoning_Permit_Application_Edison.pdf",
                pdf_download_url="/api/forms/engineering/Zoning_Permit_Application_Edison.pdf",
                department_id="engineering",
                fill_in_instructions="1. Download or print the official municipal application.\n2. Complete Property Owner data, Work Site Address, Block, and Lot.\n3. Attach two (2) signed and sealed surveys.\n4. Submit to Engineering Department.",
                required_attachments=[
                    "Two (2) copies of current property survey sealed by NJ Licensed Surveyor",
                    "Plot plan showing exact dimensions and setbacks",
                    "Contractor registration & insurance",
                    "Application review fee"
                ],
                fee_info=FeeInfo(
                    amount="Fee schedule per municipal ordinance",
                    payment_methods="Check payable to 'Township of Edison' or Credit Card at Counter"
                ),
                submission_routing=SubmissionRouting(
                    department="Department of Engineering",
                    desk="Engineering Intake Counter, Municipal Complex",
                    building_address="100 Municipal Blvd, Edison, NJ 08817",
                    hours="Monday – Friday: 8:00 AM – 4:30 PM",
                    contact_phone="(732) 248-7288",
                    contact_email="engineering@edisonnj.gov",
                    digital_upload_url="https://www.edisonnj.org/document_center/Zoning%20ApplicationNEW.pdf"
                ),
                lead_time="10 to 14 Business Days"
            )

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
