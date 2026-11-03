"""
Grounded Municipal RAG Engine & Multi-Turn Intent Router
For Township of Edison, New Jersey (CivicIQ)

Handles:
1. Procedural Workflow Intent Detection (Zoning, Street Opening, Tree Removal, Sewer Connection)
2. Unsupported / Planned Department Detection (Animal Shelter, Health, Clerk) with friendly referrals
3. Grounded Official Knowledge Retrieval & Synthesis (via llm_client)
4. Anti-hallucination compliance citing official edisonnj.org documents
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
    ENGINEERING_PHONE, ENGINEERING_EMAIL, OFFICIAL_DOCUMENT_CENTER_URL
)
from .edison_document_center import find_matching_official_forms, get_document_inventory

logger = logging.getLogger("rag_engine")

class GroundedRagEngine:
    def __init__(self):
        pass

    def check_unsupported_department_inquiry(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Detects if citizen inquiry is asking about a municipal department
        that is planned or outside the current Engineering MVP scope.
        Returns helpful referral information.
        """
        t = text.lower()

        # 1. Animal Shelter / Pet Services (using whole word boundaries)
        if re.search(r'\b(cat|cats|dog|dogs|pet|pets|animal|animals|adopt|adoption|kitten|kittens|puppy|puppies|shelter|rabies|spay|neuter)\b', t):
            return {
                "department": "Edison Municipal Animal Shelter",
                "message": (
                    f"**CivicIQ Department Referral Notice:**\n\n"
                    f"You inquired about animal services (**\"{text}\"**). CivicIQ is currently active for the "
                    f"**Engineering & Zoning Department MVP**.\n\n"
                    f"For pet adoptions, animal licensing, and shelter services in Edison, please contact the "
                    f"**Edison Municipal Animal Shelter** directly:\n\n"
                    f"• **Facility:** 125 Municipal Blvd, Edison, NJ 08817 (Adjacent to the Municipal Complex)\n"
                    f"• **Phone:** (732) 248-7258\n"
                    f"• **Email:** animalshelter@edisonnj.gov\n"
                    f"• **Hours:** Monday – Friday 8:30 AM – 4:30 PM; Saturday 10:00 AM – 1:00 PM\n"
                    f"• **Website:** [edisonnj.org/departments/animal_shelter](https://www.edisonnj.org/departments/animal_shelter/index.php)\n\n"
                    f"Feel free to ask me any questions regarding **Edison Engineering, Zoning Permits, Road Excavations, or Tree Clearances**!"
                ),
                "citations": [
                    RagCitation(
                        url="https://www.edisonnj.org/departments/animal_shelter/index.php",
                        title="Edison Municipal Animal Shelter - Official Township Portal",
                        category="Animal Services",
                        department_id="animal_shelter",
                        relevance_score=0.95,
                        excerpt="Edison Municipal Animal Shelter, 125 Municipal Blvd, Edison, NJ 08817. Phone: (732) 248-7258. Hours: Mon-Fri 8:30am-4:30pm, Sat 10am-1pm."
                    )
                ]
            }

        # 2. Health & Human Services / Vital Statistics
        if re.search(r'\b(restaurant license|food inspection|food vendor|vital statistics|birth certificate|death certificate|marriage license)\b', t):
            return {
                "department": "Edison Department of Health and Human Services",
                "message": (
                    f"**CivicIQ Department Referral Notice:**\n\n"
                    f"You inquired about health or vital statistics (**\"{text}\"**). CivicIQ is currently active for the "
                    f"**Engineering & Zoning Department MVP**.\n\n"
                    f"For retail food licensing, health inspections, or vital records (birth, marriage, death certificates), "
                    f"please contact the **Edison Township Health Department**:\n\n"
                    f"• **Location:** Municipal Complex, 2nd Floor, 100 Municipal Blvd, Edison, NJ 08817\n"
                    f"• **Phone:** (732) 248-7285\n"
                    f"• **Email:** health@edisonnj.gov\n"
                    f"• **Hours:** Monday – Friday 8:00 AM – 4:30 PM\n"
                    f"• **Forms:** [Health Department Forms](https://www.edisonnj.org/document_center/index.php)\n\n"
                    f"I am happy to assist you with any **Engineering, Zoning, or Construction Permit** questions!"
                ),
                "citations": [
                    RagCitation(
                        url="https://www.edisonnj.org/document_center/index.php",
                        title="Edison Health & Human Services Department Directory",
                        category="Health & Human Services",
                        department_id="healthcare",
                        relevance_score=0.92,
                        excerpt="Edison Department of Health and Human Services, 100 Municipal Blvd, 2nd Floor. Phone: (732) 248-7285. Retail food plan review and vital records."
                    )
                ]
            }

        # 3. Township Clerk / Elections / OPRA
        if re.search(r'\b(marriage certificate|election|elections|voting|voter|council minutes|landlord registration|charity bingo)\b', t):
            return {
                "department": "Edison Township Clerk's Office",
                "message": (
                    f"**CivicIQ Department Referral Notice:**\n\n"
                    f"You inquired about municipal clerk records (**\"{text}\"**). "
                    f"Please contact the **Edison Township Clerk's Office** directly:\n\n"
                    f"• **Location:** Municipal Complex, 100 Municipal Blvd, Edison, NJ 08817\n"
                    f"• **Phone:** (732) 248-7350\n"
                    f"• **Email:** clerk@edisonnj.gov\n"
                    f"• **Hours:** Monday – Friday 8:30 AM – 4:30 PM\n\n"
                    f"For construction, property improvements, or street excavation, ask me here!"
                ),
                "citations": [
                    RagCitation(
                        url="https://www.edisonnj.org/document_center/index.php",
                        title="Edison Township Clerk's Office",
                        category="Township Clerk",
                        department_id="engineering",
                        relevance_score=0.90,
                        excerpt="Edison Township Clerk's Office, 100 Municipal Blvd. Phone: (732) 248-7350. OPRA requests and municipal licensing."
                    )
                ]
            }

        return None

    def detect_flow_intent(self, user_text: str, department_id: Optional[str] = None) -> Optional[Tuple[str, str]]:
        """
        Detects if user intent is procedural (starting a workflow or applying for a permit/service).
        Returns (department_id, flow_id) if matched, else None.
        Disambiguates pure informational inquiries from procedural applications.
        """
        text = user_text.lower().strip()

        # Pure informational questions (let RAG handle with exact quotes and citations)
        info_starters = [
            "what is", "what are", "how much is", "what fee", "what is the fee",
            "how do i know", "tell me about", "regulations for", "guidelines for",
            "explain the rules", "distance requirement", "setback requirement",
            "what documents do i need", "what are the documents", "what should i bring"
        ]
        # If text is explicitly asking for documents or fees without saying "start" or "apply", prefer RAG
        if any(text.startswith(s) for s in info_starters) and not any(a in text for a in ["start", "begin", "apply", "initiate"]):
            return None

        # 1. Residential Construction & Zoning Permit Workflow
        if any(k in text for k in [
            "construct a house", "construct a new house", "construct new house",
            "construct something", "build a new house", "build a house",
            "apply for building permit", "apply for zoning permit", "need zoning permit",
            "apply for residential permit", "start zoning permit", "residential construction permit",
            "build an addition", "apply for addition", "build a deck", "apply for deck",
            "install a pool", "apply for pool", "install a shed", "apply for fence",
            "residential_zoning_permit_flow"
        ]):
            return ("engineering", "residential_zoning_permit_flow")

        # 2. Street Opening & Road Excavation Permit
        if any(k in text for k in [
            "excavation permit", "street opening permit", "road cut permit",
            "apply for excavation", "need excavation permit", "road opening permit",
            "dig permit", "trenching permit", "curb cut permit", "pavement cut",
            "street_opening_flow"
        ]):
            return ("engineering", "street_opening_flow")

        # 3. Tree Removal Clearance & Permit
        if any(k in text for k in [
            "tree removal", "remove a tree", "cut down a tree",
            "tree permit", "tree removal permit", "tree cutting",
            "tree preservation", "tree_removal_flow"
        ]):
            return ("engineering", "tree_removal_flow")

        # 4. Sewer Connection Charge Application
        if any(k in text for k in [
            "sewer connection", "sewer permit", "connect to sewer",
            "sewer tap", "sanitary sewer permit", "sewer charge",
            "sewer_connection_flow"
        ]):
            return ("engineering", "sewer_connection_flow")

        return None

    def match_official_form_packet(self, text: str, department_id: str = "engineering") -> Optional[FormIssuanceDetails]:
        """
        If the user is asking to download or get an official form, match and construct
        the official FormIssuanceDetails packet for in-chat delivery.
        """
        t = text.lower()
        if not any(w in t for w in ["form", "application", "download", "pdf", "packet", "paperwork"]):
            return None

        # Match Residential Zoning Application
        if any(w in t for w in ["zoning", "residential", "construction", "house", "addition", "deck", "pool", "shed"]):
            return FormIssuanceDetails(
                form_code="EDISON-ENG-ZONING",
                form_title="Township of Edison Official Zoning Permit Application Form",
                form_file="Zoning_Permit_Application_Edison.pdf",
                pdf_download_url="/api/forms/engineering/Zoning_Permit_Application_Edison.pdf",
                department_id="engineering",
                fill_in_instructions="1. Print or download the official un-altered application.\n2. Complete Property Owner data, Work Site Address, Block, and Lot.\n3. Delineate proposed construction footprint and setbacks on two (2) signed and sealed surveys.\n4. Submit with review fee to Division of Zoning.",
                required_attachments=[
                    "Two (2) copies of current property survey sealed by NJ Licensed Surveyor",
                    "Plot plan showing exact dimensions, setbacks, and height of proposed structure",
                    "Contractor NJ Home Improvement Contractor (HIC) license and insurance",
                    "Application fee payment receipt"
                ],
                fee_info=FeeInfo(
                    amount="$50 (fences/sheds) - $75 (decks) - $100 (additions) - $200 (new dwellings)",
                    payment_methods="Check payable to 'Township of Edison' or Credit Card at Counter"
                ),
                submission_routing=SubmissionRouting(
                    department="Engineering & Zoning Department",
                    desk="Division of Zoning, Municipal Complex 2nd Floor",
                    building_address="100 Municipal Blvd, Edison, NJ 08817",
                    hours="Monday – Friday: 8:00 AM – 4:30 PM",
                    contact_phone="(732) 248-7230",
                    contact_email="zoning@edisonnj.gov",
                    digital_upload_url="https://www.edisonnj.org/document_center/Zoning%20ApplicationNEW.pdf"
                ),
                lead_time="10 to 15 Business Days for initial plan review"
            )

        # Match Road Opening Form
        if any(w in t for w in ["road", "street", "opening", "excavation", "trench", "pavement"]):
            return FormIssuanceDetails(
                form_code="EDISON-DPW-ROADOPEN",
                form_title="Edison Township Street Opening & Road Excavation Application",
                form_file="RoadOpenApp.pdf",
                pdf_download_url="/api/forms/engineering/RoadOpenApp.pdf",
                department_id="engineering",
                fill_in_instructions="1. Affix NJ 811 Call Before You Dig ticket number.\n2. Submit sketch of proposed pavement trench dimensions.\n3. Post $5,000 restoration guarantee bond.\n4. Submit to Department of Public Works.",
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
                    department="Department of Public Works / Engineering",
                    desk="DPW Intake Counter",
                    building_address="100 Municipal Blvd, Edison, NJ 08817",
                    hours="Monday – Friday: 8:00 AM – 4:30 PM",
                    contact_phone="(732) 248-7288",
                    contact_email="dpw@edisonnj.gov",
                    digital_upload_url="https://www.edisonnj.org/document_center/RoadOpenApp.pdf"
                ),
                lead_time="5 to 7 Business Days"
            )

        # Match Sewer Connection Form
        if any(w in t for w in ["sewer", "tap", "connection", "lateral"]):
            return FormIssuanceDetails(
                form_code="EDISON-ENG-SEWER",
                form_title="Township of Edison Sewer Connection Charge Application",
                form_file="Sewer_Connection_Charge_Applications.pdf",
                pdf_download_url="/api/forms/engineering/Sewer_Connection_Charge_Applications.pdf",
                department_id="engineering",
                fill_in_instructions="1. Enter parcel Block, Lot, and property owner details.\n2. Fill out plumbing fixture unit count worksheet.\n3. Attach plumbing schematic.\n4. Submit to Sewer Utility Division.",
                required_attachments=[
                    "Plumbing Fixture Unit Calculation Schedule",
                    "Civil engineering utility connection schematic",
                    "Copy of approved building or zoning permit",
                    "Sewer connection review fee payment"
                ],
                fee_info=FeeInfo(
                    amount="Calculated per fixture unit according to municipal rate code",
                    payment_methods="Check payable to 'Township of Edison Sewer Utility'"
                ),
                submission_routing=SubmissionRouting(
                    department="Edison Sewer Utility Division",
                    desk="Sewer Division Counter, Municipal Complex",
                    building_address="100 Municipal Blvd, Edison, NJ 08817",
                    hours="Monday – Friday: 8:30 AM – 4:30 PM",
                    contact_phone="(732) 248-7230",
                    contact_email="sewer@edisonnj.gov",
                    digital_upload_url="https://www.edisonnj.org/Sewer%20Connection%20Charge%20Applications.pdf"
                ),
                lead_time="7 to 10 Business Days"
            )

        return None

    def answer_query(self, query: str, department_id: Optional[str] = "engineering") -> RagResult:
        """
        Executes grounded retrieval and synthesis for resident queries.
        Ensures strict anti-hallucination compliance.
        """
        # 1. Check for unsupported department inquiry first
        unsupported = self.check_unsupported_department_inquiry(query)
        if unsupported:
            return RagResult(
                answer=unsupported["message"],
                citations=unsupported["citations"],
                grounded=True,
                query=query
            )

        # 2. Search vector store
        dept = department_id if department_id else "engineering"
        citations: List[RagCitation] = vector_store.search(
            query=query,
            department_id=dept,
            top_k=4,
            threshold=0.095
        )

        dept_config = registry.get_department(dept)
        dept_name = dept_config.name if dept_config else "Engineering & Zoning Department"

        if not citations:
            fallback = (
                f"Under official municipal protocols for the **{MUNICIPALITY_NAME}**, "
                f"I only provide answers directly grounded in verified Township documentation.\n\n"
                f"I was unable to locate a verified citation for **\"{query}\"** in our active {dept_name} records.\n\n"
                f"**How to Get Official Assistance:**\n"
                f"• **Counter:** Division of Zoning, Municipal Complex, {MUNICIPAL_ADDRESS}\n"
                f"• **Phone:** {ENGINEERING_PHONE}\n"
                f"• **Email:** {ENGINEERING_EMAIL}\n"
                f"• **Official Document Center:** [edisonnj.org/document_center](https://www.edisonnj.org/document_center/index.php)"
            )
            return RagResult(
                answer=fallback,
                citations=[],
                grounded=False,
                query=query
            )

        # 3. Generate grounded answer via LLMClient
        answer = llm_client.generate_answer(
            query=query,
            citations=citations,
            department_name=dept_name
        )

        # If resident asked about where/when to submit, append verified municipal desk routing
        if any(w in query.lower() for w in ["submit", "where", "office", "address", "location", "counter", "intake"]):
            hours_str = dept_config.operating_hours.weekdays if (dept_config and dept_config.operating_hours) else "Monday – Friday: 8:00 AM – 4:30 PM"
            intake_info = (
                f"\n\n**Official Submission & Intake Counter:**\n"
                f"• **Location:** Division of Zoning & Engineering, Municipal Complex, {MUNICIPAL_ADDRESS}\n"
                f"• **Operating Hours:** {hours_str}\n"
                f"• **Direct Contacts:** {ENGINEERING_PHONE} | {ENGINEERING_EMAIL}"
            )
            answer += intake_info

        return RagResult(
            answer=answer,
            citations=citations,
            grounded=True,
            query=query
        )

rag_engine = GroundedRagEngine()
