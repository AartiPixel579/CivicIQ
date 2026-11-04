"""
Service-Aware Intent Detection Service for Edison Township Engineering
Identifies the canonical municipal engineering service for citizen inquiries,
computes confidence scores, resolves ambiguity, and routes to appropriate
procedural workflows, specific detail inquiries, or general grounded guidance.
"""

import re
import logging
from typing import List, Dict, Optional, Tuple
from pydantic import BaseModel, Field
from ..models.core import FlowOption

logger = logging.getLogger("services.service_intent")


class ServiceIntentResult(BaseModel):
    service_id: str
    service_name: str
    confidence: float
    is_supported: bool = True
    is_ambiguous: bool = False
    ambiguity_type: Optional[str] = None
    clarifying_question: Optional[str] = None
    options: Optional[List[FlowOption]] = None
    intent_type: str = "procedure_inquiry"  # "procedure_inquiry" | "form_request" | "general_info"
    detail_type: str = "procedure"  # "procedure" | "fee" | "documents" | "submission" | "turnaround" | "form_fields" | "complete_process" | "emergency"
    has_flowchart: bool = False
    flow_id: Optional[str] = None
    official_form_id: Optional[str] = None
    official_form_file: Optional[str] = None


# Canonical service definitions with metadata
CANONICAL_SERVICES = {
    "tree_removal": {
        "name": "Tree Removal & Preservation",
        "is_supported": True,
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
        "is_supported": True,
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
        "is_supported": True,
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
        "is_supported": True,
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
        "is_supported": False,
        "has_flowchart": False,
        "flow_id": None,
        "form_id": None,
        "form_file": None,
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
        "is_supported": False,
        "has_flowchart": False,
        "flow_id": None,
        "form_id": None,
        "form_file": None,
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
        "is_supported": False,
        "has_flowchart": False,
        "flow_id": None,
        "form_id": None,
        "form_file": None,
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
        "is_supported": False,
        "has_flowchart": False,
        "flow_id": None,
        "form_id": None,
        "form_file": None,
        "keywords": [
            "sewer connection", "sewer tap", "sanitary sewer", "sewer lateral",
            "fixture unit", "sewer charge", "connect to sewer", "sewer utility"
        ]
    }
}

SERVICE_SPECIFIC_DETAILS: Dict[str, Dict[str, str]] = {
    "tree_removal": {
        "fee": (
            "The standard filing fee is $25 for a single residential lot. "
            "The fee waiver is available to eligible senior citizens aged 62 or older, "
            "subject to the proof-of-age requirement stated in the application. "
            "For removals associated with Planning/Zoning Board approval or a subdivision, the fee is $200.\n\n"
            "• **Senior Citizen Waiver:** Waived for residents aged 62 or older with valid proof of age.\n"
            "• **Board Approval / Subdivision:** $200 filing fee for board-approved removals.\n\n"
            "Source: [Township of Edison Tree Permit Application](/api/forms/engineering/3.23.21%20tree%20permit%20application.pdf)\n\n"
            "Would you like help with the application?"
        ),
        "documents": (
            "To apply for a Tree Removal Permit, you must provide:\n\n"
            "• **Survey or Tax Map sketch:** Property boundaries showing existing trees with diameter and removal trees marked with an X.\n"
            "• **Written statement:** Brief explanation detailing the reason for removal (Ordinance 25-8.1a6).\n"
            "• **Site marking / Hazard proof:** Trees marked on site with red ribbon or paint (or photos/certified arborist letter if dead/hazardous).\n"
            "• **Completed Application Form:** Signed by the property owner.\n\n"
            "Source: [Township of Edison Tree Permit Application](/api/forms/engineering/3.23.21%20tree%20permit%20application.pdf)\n\n"
            "Would you like help with the application?"
        ),
        "submission": (
            "Submit your completed Tree Removal application and materials to the Division of Engineering:\n\n"
            "• **In Person:** Division of Engineering, Edison Municipal Complex, 100 Municipal Boulevard, Edison, NJ 08817 (Monday – Friday, 8:00 AM – 4:30 PM).\n"
            "• **Online:** Accessible via the [Edison Township Document Center](https://www.edisonnj.org/document_center/index.php).\n\n"
            "Source: [Township of Edison Tree Permit Application](/api/forms/engineering/3.23.21%20tree%20permit%20application.pdf)"
        ),
        "turnaround": (
            "The standard processing turnaround for a Tree Removal Permit is **5 to 10 business days** for the municipal inspector field visit and sign-off.\n\n"
            "• **Field Inspection:** 5–10 business days from application receipt.\n"
            "• **Emergency Removal:** In an emergency involving a dead, dying, or hazardous tree posing imminent danger, you may remove the tree immediately and file concurrently.\n\n"
            "Source: [Township of Edison Tree Permit Application](/api/forms/engineering/3.23.21%20tree%20permit%20application.pdf)"
        ),
        "form_fields": (
            "Key instructions for completing the Tree Removal Permit Application:\n\n"
            "• **Property Details:** Fill in Property Owner information, property address, and Block and Lot numbers.\n"
            "• **Tree Count:** Indicate total number of trees on site and number of trees to be removed.\n"
            "• **Fee Category:** Select the applicable fee category ($25 residential or Senior 62+ waiver).\n"
            "• **Submission:** Attach the property sketch and submit to the Division of Engineering.\n\n"
            "Source: [Township of Edison Tree Permit Application](/api/forms/engineering/3.23.21%20tree%20permit%20application.pdf)\n\n"
            "Would you like help with the application?"
        ),
        "complete_process": (
            "Here is the complete tree-removal process for Edison Township:\n\n"
            "• **1. Application Submission:** Download and complete the official Tree Removal Permit Application, attaching a survey sketch marking the trees and a written reason for removal.\n"
            "• **2. Tree Marking:** Mark all trees to be removed on site with red ribbon or paint for township identification.\n"
            "• **3. Engineering Inspection:** A township arborist or engineering inspector visits the property within 5–10 business days to inspect the marked trees.\n"
            "• **4. Permit Decision:** Once approved (with payment of the $25 fee, waived for seniors 62+), the permit is issued.\n"
            "• **5. Tree Removal:** You may proceed with removal according to any permit conditions (such as tree replacement requirements if removing more than 25% of site trees).\n\n"
            "Source: [Township of Edison Tree Permit Application](/api/forms/engineering/3.23.21%20tree%20permit%20application.pdf)\n\n"
            "Would you like help with the application?"
        ),
        "emergency": (
            "Under Edison Township guidelines, emergency removal is permitted. If it's an emergency, take photos of the hazardous tree or obtain a certified letter from a licensed arborist/forester confirming that it is dead, dying or an imminent danger. You can then safely remove the tree immediately and submit the Tree Removal Permit Application concurrently with removal via the Edison Document Center.\n\n"
            "• **Immediate Action:** Safely remove the hazardous tree without waiting for standard review.\n"
            "• **Documentation:** Retain clear photographic evidence or an arborist certification.\n"
            "• **Concurrent Filing:** Submit the Tree Removal Permit Application concurrently with removal.\n\n"
            "Source: [Township of Edison Tree Permit Application](/api/forms/engineering/3.23.21%20tree%20permit%20application.pdf)\n\n"
            "Would you like help with the application?"
        ),
        "permit_required": (
            "Yes, an approved Tree Removal Permit is required before removing mature trees in Edison Township (Chapter 25-8).\n\n"
            "• **Standard Removals:** A permit must be approved by the Division of Engineering prior to cutting.\n"
            "• **Emergency Exception:** Immediate removal is authorized for dead, dying, or hazardous trees posing imminent danger, with concurrent application filing.\n\n"
            "Source: [Township of Edison Tree Permit Application](/api/forms/engineering/3.23.21%20tree%20permit%20application.pdf)\n\n"
            "Would you like help with the application?"
        )
    },
    "soil_import": {
        "fee": (
            "The municipal fee for a Soil Importation Permit in Edison Township includes a **$50.00 application fee** "
            "plus standard engineering review escrow for quantities of 10 cubic yards or more.\n\n"
            "• **Application Fee:** $50.00 standard filing fee.\n"
            "• **Review Escrow:** Required for volumes of 10 cubic yards or greater.\n\n"
            "Source: [Township of Edison Soil Importation Permit Application](/api/forms/engineering/Forms_Soil_Importation_Appl.pdf)\n\n"
            "Would you like help with the application?"
        ),
        "documents": (
            "For an Edison Township Soil Importation Permit, you must provide:\n\n"
            "• **Completed Application:** Official Soil Importation Permit Application.\n"
            "• **Certified Clean Fill Analysis:** Laboratory test results confirming the soil is clean and free of contaminants.\n"
            "• **Property Survey & Grading Plan:** Showing proposed fill location, depth, and finished contours.\n"
            "• **Designated Truck Haul Route:** Planned travel route through Edison Township roadways.\n\n"
            "Source: [Township of Edison Soil Importation Permit Application](/api/forms/engineering/Forms_Soil_Importation_Appl.pdf)\n\n"
            "Would you like help with the application?"
        ),
        "submission": (
            "Submit your Soil Importation Application and documents to the **Division of Engineering**:\n\n"
            "• **Address:** Edison Municipal Complex, 100 Municipal Boulevard, Edison, NJ 08817 (Monday – Friday, 8:00 AM – 4:30 PM).\n"
            "• **Online:** Accessible via the [Edison Township Document Center](https://www.edisonnj.org/document_center/index.php).\n\n"
            "Source: [Township of Edison Soil Importation Permit Application](/api/forms/engineering/Forms_Soil_Importation_Appl.pdf)\n\n"
            "Would you like help with the application?"
        ),
        "turnaround": (
            "Standard processing turnaround for a Soil Importation review is **7 to 10 business days** upon receipt of complete lab certifications and grading plans.\n\n"
            "• **Review Period:** 7–10 business days.\n"
            "• **Permit Issuance:** Soil delivery may proceed once formal engineering approval is issued.\n\n"
            "Source: [Township of Edison Soil Importation Permit Application](/api/forms/engineering/Forms_Soil_Importation_Appl.pdf)"
        ),
        "complete_process": (
            "Here is the complete soil importation process in Edison Township (for 10+ cubic yards):\n\n"
            "• **1. Clean Fill Verification:** Obtain laboratory chemical test certification verifying fill is uncontaminated.\n"
            "• **2. Application Submission:** Submit the Soil Importation Application, clean fill analysis, grading sketch, and haul route to the Division of Engineering.\n"
            "• **3. Engineering Review:** Township engineers review the grading and environmental data (typically 7–10 business days).\n"
            "• **4. Permit Issuance:** Once approved and fee/escrow paid, the permit is issued.\n"
            "• **5. Delivery:** Soil may then be transported to the property following the approved haul route.\n\n"
            "Source: [Township of Edison Soil Importation Permit Application](/api/forms/engineering/Forms_Soil_Importation_Appl.pdf)\n\n"
            "Would you like help with the application?"
        ),
        "permit_required": (
            "A Soil Importation Permit is required in Edison Township for quantities of 10 cubic yards or more (Chapter 31).\n\n"
            "• **10+ Cubic Yards:** Approved permit and clean fill certification required prior to delivery.\n"
            "• **Under 10 Cubic Yards:** A municipal permit is not required.\n\n"
            "Source: [Township of Edison Soil Importation Permit Application](/api/forms/engineering/Forms_Soil_Importation_Appl.pdf)\n\n"
            "Would you like help with the application?"
        )
    },
    "soil_export": {
        "fee": (
            "The municipal fee for a Soil Exportation Permit in Edison Township includes a **$50.00 application fee** "
            "plus a refundable performance/restoration bond if required for large volume hauling.\n\n"
            "• **Application Fee:** $50.00 standard filing fee.\n"
            "• **Performance Bond:** Held during excavation and released upon final inspection.\n\n"
            "Source: [Township of Edison Soil Exportation Permit Application](/api/forms/engineering/Forms_Soil_Exportation_App.pdf)\n\n"
            "Would you like help with the application?"
        ),
        "documents": (
            "For an Edison Township Soil Exportation Permit, you must provide:\n\n"
            "• **Completed Application:** Official Soil Exportation Permit Application.\n"
            "• **Topographical Survey:** Showing existing and proposed grades with cut/fill volume calculations by a licensed engineer.\n"
            "• **Soil Erosion & Sediment Control Plan:** Measures to protect adjacent properties from runoff.\n"
            "• **Designated Haul Route:** Planned trucking route through Edison Township.\n\n"
            "Source: [Township of Edison Soil Exportation Permit Application](/api/forms/engineering/Forms_Soil_Exportation_App.pdf)\n\n"
            "Would you like help with the application?"
        ),
        "submission": (
            "Submit your Soil Exportation Application to the **Division of Engineering**:\n\n"
            "• **Address:** Edison Municipal Complex, 100 Municipal Boulevard, Edison, NJ 08817 (Monday – Friday, 8:00 AM – 4:30 PM).\n"
            "• **Online:** [Edison Township Document Center](https://www.edisonnj.org/document_center/index.php).\n\n"
            "Source: [Township of Edison Soil Exportation Permit Application](/api/forms/engineering/Forms_Soil_Exportation_App.pdf)\n\n"
            "Would you like help with the application?"
        ),
        "turnaround": (
            "Standard processing turnaround for a Soil Exportation review is **7 to 10 business days**.\n\n"
            "• **Review Period:** 7–10 business days.\n"
            "• **Hauling Authorization:** Soil hauling may proceed once permit is issued and bond is posted.\n\n"
            "Source: [Township of Edison Soil Exportation Permit Application](/api/forms/engineering/Forms_Soil_Exportation_App.pdf)"
        ),
        "complete_process": (
            "Here is the complete soil exportation process in Edison Township (for 10+ cubic yards):\n\n"
            "• **1. Volume & Grading Assessment:** Have a licensed NJ surveyor or engineer prepare topographical cut calculations.\n"
            "• **2. Application Filing:** Submit the Soil Exportation Application, survey, soil erosion control plan, and haul route to Engineering.\n"
            "• **3. Engineering Review:** Division of Engineering reviews excavation impact and haul route (7–10 business days).\n"
            "• **4. Permit & Bond:** Furnish required restoration bond and receive permit approval.\n"
            "• **5. Hauling:** Excavate and transport soil off-site in accordance with approved permit conditions.\n\n"
            "Source: [Township of Edison Soil Exportation Permit Application](/api/forms/engineering/Forms_Soil_Exportation_App.pdf)\n\n"
            "Would you like help with the application?"
        ),
        "permit_required": (
            "A Soil Exportation Permit is required in Edison Township for quantities of 10 cubic yards or more (Chapter 31).\n\n"
            "• **10+ Cubic Yards:** Approved permit, topographical survey with cut calculations, and haul route required prior to hauling.\n"
            "• **Under 10 Cubic Yards:** A municipal permit is not required.\n\n"
            "Source: [Township of Edison Soil Exportation Permit Application](/api/forms/engineering/Forms_Soil_Exportation_App.pdf)\n\n"
            "Would you like help with the application?"
        )
    },
    "road_opening": {
        "fee": (
            "For a Street Opening Permit in Edison Township, the fees are:\n"
            "- **Application Filing Fee:** $150.00 (non-refundable).\n"
            "- **Restoration Guarantee Bond:** Refundable $5,000.00 certified check or surety bond held during the 12-month post-restoration settlement period."
        ),
        "documents": (
            "For an Edison Township Street Opening Permit, you must submit:\n"
            "1. **Completed Application:** Official Street Opening Application Form.\n"
            "2. **811 Dig Ticket:** Active confirmation ticket number from New Jersey One Call (811).\n"
            "3. **Trench Sketch:** Plan showing pavement saw-cut dimensions (length, width, depth).\n"
            "4. **Certificate of Insurance:** Minimum $1,000,000 general liability naming Township of Edison as additional insured.\n"
            "5. **Restoration Bond:** $5,000.00 guarantee deposit."
        ),
        "submission": (
            "Submit Street Opening Applications to the **Department of Public Works / Engineering Desk**:\n"
            "- **Address:** Edison Municipal Complex, 100 Municipal Boulevard, Edison, NJ 08817 (Monday – Friday, 8:00 AM – 4:30 PM).\n"
            "- **Online:** [Edison Township Document Center](https://www.edisonnj.org/document_center/index.php)."
        ),
        "turnaround": (
            "Standard processing turnaround is **5 to 7 business days** from receipt of complete application, insurance certificate, and bond."
        ),
        "complete_process": (
            "Here is the complete street opening and road excavation process in Edison Township:\n"
            "1. **Call 811:** Contact NJ One Call (811) at least 3 business days prior to mark underground utilities.\n"
            "2. **Application Submission:** Submit the application, trench dimension sketch, certificate of insurance, $150 fee, and $5,000 bond.\n"
            "3. **Traffic Division Review:** If obstructing traffic or sidewalks, coordinate safety detour plan with Edison Police Traffic Division.\n"
            "4. **Permit Issuance:** Engineering and DPW issue the excavation permit.\n"
            "5. **Excavation & Restoration:** Perform work and restore pavement per Township trench restoration standards.\n"
            "6. **Bond Release:** After 12 months with no settlement, request final inspection for bond release."
        )
    },
    "site_improvement": {
        "fee": (
            "Site Improvement Permit fees in Edison Township include an **application review fee ($100.00)** "
            "plus engineering inspection escrow based on the scope of site grading and drainage improvements."
        ),
        "documents": (
            "For an Edison Township Site Improvement Permit, you must submit:\n"
            "1. **Completed SIP Application:** Signed by the property owner.\n"
            "2. **Completed 25-Point Checklist:** All checklist items addressed.\n"
            "3. **Signed & Sealed Engineering Plans:** Two (2) sets of grading, drainage, and utility plans prepared by a NJ licensed professional engineer.\n"
            "4. **Stormwater Management Report:** If creating 500+ sq. ft. of new impervious surface or disturbing 1,250+ sq. ft."
        ),
        "submission": (
            "Submit Site Improvement packets to the **Division of Engineering**:\n"
            "- **Address:** Edison Municipal Complex, 100 Municipal Boulevard, Edison, NJ 08817 (Monday – Friday, 8:00 AM – 4:30 PM).\n"
            "- **Online:** [Edison Township Document Center](https://www.edisonnj.org/document_center/index.php)."
        ),
        "turnaround": (
            "Standard engineering review turnaround is **10 to 15 business days**."
        ),
        "complete_process": (
            "Here is the complete Site Improvement (SIP) process in Edison Township:\n"
            "1. **Engineering Preparation:** Retain a NJ licensed civil engineer to prepare grading, drainage, and coverage plans.\n"
            "2. **Application Submission:** Submit the SIP Application, 25-Point Checklist, sealed plans, and review escrow.\n"
            "3. **Technical Review:** Township engineers review grading, stormwater impact, and zoning compliance.\n"
            "4. **Permit Approval:** Once approved, engineering signs off for building permit issuance or site construction.\n"
            "5. **As-Built Inspection:** Upon completion of site work, submit as-built survey for final engineering release."
        )
    },
    "zoning": {
        "fee": (
            "Edison Township Zoning Permit fees by project scope:\n"
            "- New Single-Family Dwelling: **$200.00**\n"
            "- Residential Addition / Alteration: **$100.00**\n"
            "- Swimming Pool (In-ground: $150.00 / Above-ground: $75.00)\n"
            "- Deck / Porch / Patio: **$75.00**\n"
            "- Storage Shed / Fence / Driveway: **$50.00**"
        ),
        "documents": (
            "For an Edison Township Zoning Permit application, you must provide:\n"
            "1. **Completed Zoning Permit Application:** Signed by the property owner.\n"
            "2. **Three (3) copies of Property Survey:** Prepared by a NJ licensed surveyor (to scale 1\"=20' or 1\"=30') showing existing structures and proposed construction with setback dimensions.\n"
            "3. **Construction / Architectural Drawings:** Dimensioned plans showing heights and layout.\n"
            "4. **Application Fee:** Payable to Township of Edison."
        ),
        "submission": (
            "Submit Zoning Permit applications to the **Division of Zoning**:\n"
            "- **Address:** Edison Municipal Complex, 100 Municipal Boulevard, Edison, NJ 08817 (Monday – Friday, 8:00 AM – 4:30 PM).\n"
            "- **Online:** [Edison Township Document Center](https://www.edisonnj.org/document_center/index.php)."
        ),
        "turnaround": (
            "Zoning review turnaround is typically **10 business days** under NJ municipal land use law."
        ),
        "complete_process": (
            "Here is the complete residential zoning permit process in Edison Township:\n"
            "1. **Survey Preparation:** Obtain 3 copies of your scaled property survey and draw proposed additions/structures with setback distances to property lines.\n"
            "2. **Application Submission:** Submit the Zoning Application, surveys, construction sketches, and fee to the Division of Zoning.\n"
            "3. **Zoning Officer Review:** The Zoning Officer verifies compliance with Chapter 39 bulk setback and coverage standards.\n"
            "4. **Zoning Approval:** Once approved, the zoning permit certificate is issued.\n"
            "5. **Building Permits:** Present the approved zoning certificate to the Code Enforcement department to obtain construction/building permits."
        )
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
    Classifies natural language user queries into canonical municipal services,
    detects specific detail inquiries (fee, documents, submission, turnaround, complete process),
    and resolves progressive disclosure context across multi-turn sessions.
    """

    def detect_detail_type(self, query: str) -> str:
        """
        Classifies whether the user is asking for a specific detail:
        'procedure', 'fee', 'documents', 'submission', 'turnaround',
        'form_fields', 'complete_process', or 'emergency'.
        """
        q = (query or "").lower().strip()

        # 1. Complete process / How to apply
        if any(phrase in q for phrase in [
            "complete process", "full process", "all steps", "entire process",
            "explain the complete", "explain the entire", "overview of process",
            "explain the whole process", "start to finish", "step by step process",
            "complete tree-removal process", "complete tree removal process",
            "how do i apply", "how to apply", "application process", "how can i apply",
            "applying for", "how do we apply"
        ]):
            return "complete_process"

        # 1.5 Permit requirement inquiries
        if any(phrase in q for phrase in [
            "is it required", "is a permit required", "do i need a permit",
            "is permit required", "do we need a permit", "is it mandatory",
            "do i have to get a permit", "is it necessary", "required for this",
            "is it needed", "need a permit for this", "permit needed", "permit required"
        ]):
            return "permit_required"

        # 2. Fee / Cost inquiries
        if any(w in q for w in ["fee", "cost", "how much", "price", "charge", "senior waiver", "waiver"]) or any(phrase in q for phrase in [
            "is there any cost", "is there any fee", "how much does", "what is the cost", "tree removal cost",
            "soil import cost", "road opening cost", "what does it cost", "cost for this", "fee for this"
        ]):
            return "fee"

        # 3. Documents / Attachments / Checklist
        if any(phrase in q for phrase in [
            "what documents", "what document", "what do i need", "documents do i need",
            "what about documents", "attachment", "attachments", "checklist", "paperwork",
            "papers do i need", "what to attach", "required documents", "what is required to attach",
            "required attachments", "which documents"
        ]):
            return "documents"

        # 4. Submission / Where to submit / Address / Office / Where to apply
        if any(phrase in q for phrase in [
            "where do i submit", "where to submit", "where can i submit",
            "how do i submit", "where do i submit it", "submission", "submit the application",
            "where do i send", "where to bring", "where do i file",
            "where to file", "office address", "drop off", "where to drop",
            "where do i apply", "where to apply", "where can i apply", "where do we apply"
        ]):
            return "submission"

        # 5. Turnaround / Lead time / Timeline
        if any(phrase in q for phrase in [
            "how long", "turnaround", "timeline", "lead time", "processing time",
            "how many days", "when will it be approved", "review time"
        ]):
            return "turnaround"

        # 6. Form fields / How to fill out
        if any(phrase in q for phrase in [
            "how to fill", "filling out", "fill out the form", "how do i fill", "form instructions"
        ]):
            return "form_fields"

        # 7. Emergency condition inquiry (e.g. "The tree is dangerous. Can I remove it?")
        has_hazard_word = any(w in q for w in ["dangerous", "hazard", "dead", "dying", "falling", "fallen", "cracked", "storm damage", "imminent danger", "emergency"])
        has_action_word = any(w in q for w in ["can i remove", "remove it", "emergency", "danger", "cut it", "cut down", "urgent removal", "it is an emergency"])
        if has_hazard_word and has_action_word:
            return "emergency"

        return "procedure"

    def get_detail_response(self, service_id: str, detail_type: str) -> Optional[str]:
        """Returns direct, concise municipal detail text if configured."""
        if service_id in SERVICE_SPECIFIC_DETAILS:
            return SERVICE_SPECIFIC_DETAILS[service_id].get(detail_type)
        return None

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
                    detail_type="procedure",
                    has_flowchart=False
                )

        # 2. Check for form download / application request intent
        has_form_keyword = bool(re.search(r'\b(form|application|pdf|packet|download|checklist)\b', q))
        intent_type = "form_request" if has_form_keyword else "procedure_inquiry"

        # 3. Detect detail query type
        detail_type = self.detect_detail_type(q)

        # 4. Contextual expansion from conversation history
        context_text = q
        last_bot_msg = ""
        if history:
            for msg in history[-4:]:
                context_text += " " + msg.get("content", "").lower()
            for msg in reversed(history):
                if msg.get("role") in ["assistant", "model", "system"]:
                    last_bot_msg = msg.get("content", "").lower()
                    break

        # 4.1 Multi-turn Follow-up Resolution for Clarification Questions
        if "what would you like to remove" in last_bot_msg:
            if any(w in q for w in ["tree", "trees", "a tree", "opt_remove_tree"]):
                return ServiceIntentResult(
                    service_id="tree_removal",
                    service_name="Tree Removal & Preservation",
                    confidence=0.95,
                    is_ambiguous=False,
                    intent_type="procedure_inquiry",
                    detail_type="procedure",
                    has_flowchart=True,
                    flow_id="tree_removal_flow",
                    official_form_id="tree_removal",
                    official_form_file="3.23.21 tree permit application.pdf"
                )
            if any(w in q for w in ["soil", "dirt", "topsoil", "fill", "opt_remove_soil"]):
                # Removing soil = Soil Export!
                return ServiceIntentResult(
                    service_id="soil_export",
                    service_name="Soil Exportation",
                    confidence=0.95,
                    is_ambiguous=False,
                    intent_type="procedure_inquiry",
                    detail_type="procedure",
                    has_flowchart=True,
                    flow_id="soil_import_export_flow",
                    official_form_id="soil_export",
                    official_form_file="Forms_Soil_Exportation_App.pdf"
                )
            if any(w in q for w in ["something else", "other", "neither", "opt_remove_other"]):
                return ServiceIntentResult(
                    service_id="other_engineering",
                    service_name="Municipal Engineering Guidance",
                    confidence=0.80,
                    is_ambiguous=True,
                    ambiguity_type="other_service",
                    clarifying_question=(
                        "What type of municipal service or work are you planning in Edison Township?\n\n"
                        "I can assist with configured Engineering services like Tree Removal and Soil Movement. "
                        "Other municipal services can be found at the [Edison Document Center](https://www.edisonnj.org/document_center/index.php)."
                    ),
                    options=[
                        FlowOption(id="opt_permit_tree", label="Tree Removal", next_step="tree_removal"),
                        FlowOption(id="opt_permit_soil", label="Soil Movement", next_step="soil_movement"),
                    ]
                )

        if "excavate and remove soil from your property" in last_bot_msg:
            if any(w in q for w in ["remove soil", "soil export", "export", "soil", "property", "opt_excavate_soil"]):
                return ServiceIntentResult(
                    service_id="soil_export",
                    service_name="Soil Exportation",
                    confidence=0.95,
                    is_ambiguous=False,
                    intent_type="procedure_inquiry",
                    detail_type="procedure",
                    has_flowchart=True,
                    flow_id="soil_import_export_flow",
                    official_form_id="soil_export",
                    official_form_file="Forms_Soil_Exportation_App.pdf"
                )
            if any(w in q for w in ["street", "pavement", "public", "road", "opt_excavate_street"]):
                return ServiceIntentResult(
                    service_id="unconfigured_service",
                    service_name="Street Opening & Road Excavation",
                    confidence=0.95,
                    is_supported=False,
                    is_ambiguous=False,
                    intent_type="procedure_inquiry",
                    detail_type="procedure",
                    has_flowchart=False
                )

        if "which official application form do you need" in last_bot_msg:
            if any(w in q for w in ["tree", "trees", "opt_app_tree"]):
                return ServiceIntentResult(
                    service_id="tree_removal",
                    service_name="Tree Removal & Preservation",
                    confidence=0.95,
                    is_ambiguous=False,
                    intent_type="form_request",
                    detail_type="procedure",
                    has_flowchart=True,
                    flow_id="tree_removal_flow",
                    official_form_id="tree_removal",
                    official_form_file="3.23.21 tree permit application.pdf"
                )
            if any(w in q for w in ["import", "soil import", "opt_app_soil_imp"]):
                return ServiceIntentResult(
                    service_id="soil_import",
                    service_name="Soil Importation",
                    confidence=0.95,
                    is_ambiguous=False,
                    intent_type="form_request",
                    detail_type="procedure",
                    has_flowchart=True,
                    flow_id="soil_import_export_flow",
                    official_form_id="soil_import",
                    official_form_file="Forms_Soil_Importation_Appl.pdf"
                )
            if any(w in q for w in ["export", "soil export", "opt_app_soil_exp"]):
                return ServiceIntentResult(
                    service_id="soil_export",
                    service_name="Soil Exportation",
                    confidence=0.95,
                    is_ambiguous=False,
                    intent_type="form_request",
                    detail_type="procedure",
                    has_flowchart=True,
                    flow_id="soil_import_export_flow",
                    official_form_id="soil_export",
                    official_form_file="Forms_Soil_Exportation_App.pdf"
                )

        if "which engineering permit are you looking for" in last_bot_msg:
            if any(w in q for w in ["tree", "trees", "opt_permit_tree"]):
                return ServiceIntentResult(
                    service_id="tree_removal",
                    service_name="Tree Removal & Preservation",
                    confidence=0.95,
                    is_ambiguous=False,
                    intent_type="procedure_inquiry",
                    detail_type="procedure",
                    has_flowchart=True,
                    flow_id="tree_removal_flow",
                    official_form_id="tree_removal",
                    official_form_file="3.23.21 tree permit application.pdf"
                )
            if any(w in q for w in ["soil", "dirt", "movement", "opt_permit_soil"]):
                return ServiceIntentResult(
                    service_id="soil_movement",
                    service_name="Soil Movement (Import / Export)",
                    confidence=0.90,
                    is_ambiguous=True,
                    ambiguity_type="soil",
                    clarifying_question="Are you planning to bring soil onto your property (Soil Import) or remove soil from your property (Soil Export)?",
                    options=[
                        FlowOption(id="opt_soil_import", label="Bring soil (Import)", next_step="soil_import"),
                        FlowOption(id="opt_soil_export", label="Remove soil (Export)", next_step="soil_export")
                    ]
                )

        # 4.2 Ambiguity Detection for Short / Underspecified Inquiries
        
        # 1. Removal: "removal", "i want to remove something", "i need a removal permit", "removal permit", "remove something"
        is_removal_ambiguous = (
            q in [
                "removal", "remove", "removals", "i want to remove something",
                "i need a removal permit", "remove something", "removal permit",
                "need a removal permit", "want to remove something", "removal procedure",
                "removal process", "opt_remove_tree", "opt_remove_soil", "opt_remove_other"
            ] or (
                bool(re.search(r'\b(removal|removals)\b', q)) and
                not any(w in q for w in ["tree", "soil", "dirt", "stump", "branch", "fill", "street", "pavement", "sewer", "fence", "tank", "asbestos", "sidewalk", "curb"])
            )
        ) and not any(w in context_text for w in ["tree", "soil", "dirt"])

        if is_removal_ambiguous:
            return ServiceIntentResult(
                service_id="soil_movement",
                service_name="Permit Removal Inquiry",
                confidence=0.90,
                is_ambiguous=True,
                ambiguity_type="removal",
                clarifying_question="What would you like to remove — a tree or soil?",
                options=[
                    FlowOption(id="opt_remove_tree", label="Tree", next_step="tree_removal"),
                    FlowOption(id="opt_remove_soil", label="Soil", next_step="soil_export"),
                    FlowOption(id="opt_remove_other", label="Something else", next_step="something_else")
                ]
            )

        # 2. Permit: "permit", "permits", "i need a permit", "permit please"
        is_permit_ambiguous = (
            q in [
                "permit", "permits", "a permit", "i need a permit", "need a permit",
                "permit please", "apply for a permit", "engineering permit", "permits please"
            ] or (
                bool(re.search(r'\b(permit|permits)\b', q)) and
                len(q.split()) <= 4 and
                not any(w in q for w in ["tree", "soil", "dirt", "road", "street", "sewer", "site", "zoning", "cost", "fee", "how much", "how do i", "turnaround"])
            )
        ) and not any(w in context_text for w in ["tree", "soil", "dirt", "road", "street", "sewer", "site", "zoning"])

        if is_permit_ambiguous:
            return ServiceIntentResult(
                service_id="other_engineering",
                service_name="Permit Inquiry",
                confidence=0.85,
                is_ambiguous=True,
                ambiguity_type="permit",
                clarifying_question="Which Engineering permit are you looking for in Edison Township?",
                options=[
                    FlowOption(id="opt_permit_tree", label="Tree Removal Permit", next_step="tree_removal"),
                    FlowOption(id="opt_permit_soil", label="Soil Import / Export Permit", next_step="soil_movement"),
                    FlowOption(id="opt_permit_other", label="Other municipal service", next_step="other")
                ]
            )

        # 3. Application: "application", "form", "forms", "i need an application"
        is_app_ambiguous = (
            q in [
                "application", "applications", "form", "forms", "i need an application",
                "need an application", "where is the application", "where is the form",
                "application form", "official application", "give me the application",
                "give me the form", "engineering form", "engineering application"
            ] or (
                bool(re.search(r'\b(application|form|forms|packet)\b', q)) and
                len(q.split()) <= 4 and
                not any(w in q for w in ["tree", "soil", "dirt", "road", "street", "sewer", "site", "zoning", "cost", "fee"])
            )
        ) and not any(w in context_text for w in ["tree", "soil", "dirt", "road", "street", "sewer", "site", "zoning"])

        if is_app_ambiguous:
            return ServiceIntentResult(
                service_id="other_engineering",
                service_name="Application Inquiry",
                confidence=0.85,
                is_ambiguous=True,
                ambiguity_type="application",
                clarifying_question="Which official application form do you need?",
                options=[
                    FlowOption(id="opt_app_tree", label="Tree Removal Application", next_step="tree_removal"),
                    FlowOption(id="opt_app_soil_imp", label="Soil Import Application", next_step="soil_import"),
                    FlowOption(id="opt_app_soil_exp", label="Soil Export Application", next_step="soil_export")
                ]
            )

        # 4. Excavation: "excavation", "excavate", "excavating", "digging"
        is_excavation_ambiguous = (
            q in [
                "excavation", "excavate", "excavating", "digging", "excavation permit",
                "excavations", "dig"
            ] or (
                bool(re.search(r'\b(excavat|excavation|digging)\b', q)) and
                len(q.split()) <= 3 and
                not any(w in q for w in ["soil", "dirt", "tree", "street", "road", "curb", "sidewalk", "pavement"])
            )
        ) and not any(w in context_text for w in ["soil", "dirt", "tree", "street", "road"])

        if is_excavation_ambiguous:
            return ServiceIntentResult(
                service_id="soil_movement",
                service_name="Excavation Inquiry",
                confidence=0.85,
                is_ambiguous=True,
                ambiguity_type="excavation",
                clarifying_question="Are you planning to excavate and remove soil from your property (Soil Export), or excavate the street or public pavement?",
                options=[
                    FlowOption(id="opt_excavate_soil", label="Remove soil from property (Soil Export)", next_step="soil_export"),
                    FlowOption(id="opt_excavate_street", label="Street / pavement excavation", next_step="road_opening")
                ]
            )

        # 5. Tree: Single word "tree" or "trees" without specific action
        is_tree_standalone = (
            q in ["tree", "trees", "a tree", "about trees", "tree please"]
        ) and not any(w in context_text for w in ["remove", "removal", "cut", "cost", "fee", "document", "arborist", "hazard", "emergency"])

        if is_tree_standalone:
            return ServiceIntentResult(
                service_id="tree_removal",
                service_name="Tree Removal & Preservation",
                confidence=0.90,
                is_ambiguous=True,
                ambiguity_type="tree",
                clarifying_question="I can help with Edison Township tree regulations. Are you planning to remove a tree, or do you have a question about tree permits and fees?",
                options=[
                    FlowOption(id="opt_tree_remove", label="Remove a tree", next_step="tree_removal"),
                    FlowOption(id="opt_tree_fee", label="Tree permit fees", next_step="tree_fee"),
                    FlowOption(id="opt_tree_docs", label="Required documents", next_step="tree_docs")
                ]
            )

        # 6. Soil / Dirt: Standalone or ambiguous direction
        is_soil_standalone = (
            q in [
                "soil", "dirt", "soil permit", "dirt permit", "soil regulations", "moving soil", "soil movement",
                "dirt regulations", "soil rules", "how to move soil", "regulations for soil"
            ] or (
                ("soil" in q or "dirt" in q) and
                len(q.split()) <= 4 and
                not any(w in q for w in ["import", "bring", "deliver", "into", "onto", "fill", "export", "remove", "take away", "haul", "cart", "yard", "cost", "fee", "document", "10", "less", "more"])
            )
        ) and not any(w in context_text for w in ["import", "export", "bring", "remove"])

        if is_soil_standalone:
            return ServiceIntentResult(
                service_id="soil_movement",
                service_name="Soil Movement (Import / Export)",
                confidence=0.88,
                is_ambiguous=True,
                ambiguity_type="soil",
                clarifying_question="Are you planning to bring soil onto your property (Soil Import) or remove soil from your property (Soil Export)?",
                options=[
                    FlowOption(id="opt_soil_import", label="Bring soil (Import)", next_step="soil_import"),
                    FlowOption(id="opt_soil_export", label="Remove soil (Export)", next_step="soil_export")
                ],
                intent_type=intent_type,
                detail_type=detail_type,
                has_flowchart=True,
                flow_id="soil_import_export_flow"
            )

        # 5. Service-specific matching with priority rules
        
        # A. Soil Importation (Explicit or in context)
        is_soil_import_explicit = any(phrase in q for phrase in [
            "import soil", "importing soil", "bring soil", "bringing soil",
            "deliver soil", "delivering soil", "bring dirt", "fill dirt", "hauling in dirt",
            "bring topsoil", "import fill", "fill my yard", "bring clean fill",
            "how to import soil", "want to import soil", "need to import soil"
        ])
        is_soil_import_volume = ("soil" in q or "dirt" in q or "fill" in q) and any(w in q for w in ["bring", "import", "deliver", "into", "onto", "fill"])
        is_soil_import_context = ("import" in context_text and "soil" in context_text and detail_type != "procedure" and not any(w in q for w in ["tree", "road", "street", "sewer", "zoning"]))

        if is_soil_import_explicit or is_soil_import_volume or is_soil_import_context:
            return ServiceIntentResult(
                service_id="soil_import",
                service_name="Soil Importation",
                confidence=0.95 if is_soil_import_explicit else 0.85,
                is_ambiguous=False,
                intent_type=intent_type,
                detail_type=detail_type,
                has_flowchart=True,
                flow_id="soil_import_export_flow",
                official_form_id="soil_import",
                official_form_file="Forms_Soil_Importation_Appl.pdf"
            )

        # B. Soil Exportation (Explicit or in context)
        is_soil_export_explicit = any(phrase in q for phrase in [
            "export soil", "exporting soil", "remove soil", "removing soil",
            "take away dirt", "haul away soil", "hauling soil", "haul soil away",
            "excess soil off site", "remove dirt", "export dirt", "haul away dirt",
            "digging foundation export", "cart away soil", "how to export soil",
            "want to export soil", "need to export soil"
        ])
        is_soil_export_volume = ("soil" in q or "dirt" in q) and any(w in q for w in ["remove", "export", "haul away", "off site", "take away", "cart"])
        is_soil_export_context = ("export" in context_text and "soil" in context_text and detail_type != "procedure" and not any(w in q for w in ["tree", "road", "street", "sewer", "zoning"]))

        if is_soil_export_explicit or is_soil_export_volume or is_soil_export_context:
            return ServiceIntentResult(
                service_id="soil_export",
                service_name="Soil Exportation",
                confidence=0.95 if is_soil_export_explicit else 0.85,
                is_ambiguous=False,
                intent_type=intent_type,
                detail_type=detail_type,
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
                detail_type=detail_type,
                has_flowchart=True,
                flow_id="soil_import_export_flow"
            )

        # D. Tree Removal (Explicit or contextual follow-up)
        is_tree_explicit = bool(re.search(r'\b(tree|trees|arborist|forester|sapling|stump|stumps|subdivision|demolition)\b', q))
        is_tree_context = ("tree" in context_text or "arborist" in context_text) and (
            detail_type != "procedure" or 
            any(w in q for w in ["emergency", "dead", "dying", "urgent", "hazard", "fall", "danger"]) or
            q in ["yes", "no", "yes, it is an emergency", "yes it is an emergency"]
        )

        if is_tree_explicit or is_tree_context:
            return ServiceIntentResult(
                service_id="tree_removal",
                service_name="Tree Removal & Preservation",
                confidence=0.95 if is_tree_explicit else 0.88,
                is_ambiguous=False,
                intent_type=intent_type,
                detail_type=detail_type,
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
        is_road_context = ("road opening" in context_text or "street opening" in context_text) and (detail_type != "procedure")

        if is_road_explicit or is_road_context:
            return ServiceIntentResult(
                service_id="unconfigured_service",
                service_name="Street Opening & Road Excavation",
                confidence=0.95 if is_road_explicit else 0.88,
                is_supported=False,
                is_ambiguous=False,
                intent_type=intent_type,
                detail_type=detail_type,
                has_flowchart=False,
                flow_id=None,
                official_form_id=None,
                official_form_file=None
            )

        # F. Site Improvement & Grading
        is_site_explicit = any(phrase in q for phrase in [
            "site improvement", "site improvements", "sip application", "sip permit",
            "improve my property", "improving my property", "property improvement",
            "impervious coverage", "ground disturbance", "disturb ground",
            "site disturbance", "grading plan", "site checklist", "stormwater management"
        ])
        is_site_context = ("site improvement" in context_text or "sip" in context_text) and (detail_type != "procedure")

        if is_site_explicit or is_site_context:
            return ServiceIntentResult(
                service_id="unconfigured_service",
                service_name="Site Improvement & Grading",
                confidence=0.92 if is_site_explicit else 0.85,
                is_supported=False,
                is_ambiguous=False,
                intent_type=intent_type,
                detail_type=detail_type,
                has_flowchart=False,
                flow_id=None,
                official_form_id=None,
                official_form_file=None
            )

        # G. Sanitary Sewer Connection
        is_sewer_explicit = any(phrase in q for phrase in [
            "sewer connection", "sewer tap", "sanitary sewer", "sewer lateral",
            "fixture unit", "sewer charge", "connect to sewer", "sewer utility"
        ]) or bool(re.search(r'\bsewer\b', q))
        is_sewer_context = "sewer" in context_text and (detail_type != "procedure")

        if is_sewer_explicit or is_sewer_context:
            return ServiceIntentResult(
                service_id="unconfigured_service",
                service_name="Sanitary Sewer Connection",
                confidence=0.95 if is_sewer_explicit else 0.88,
                is_supported=False,
                is_ambiguous=False,
                intent_type=intent_type,
                detail_type=detail_type,
                has_flowchart=False,
                flow_id=None,
                official_form_id=None,
                official_form_file=None
            )

        # H. Residential Construction & Zoning
        is_zoning_explicit = any(phrase in q for phrase in [
            "zoning permit", "zoning application", "residential permit", "residential construction",
            "construct a house", "construct a new house", "construct a home", "construct an addition",
            "build an addition", "addition to my home", "new single family", "new house", "new home",
            "new dwelling", "build a house", "swimming pool", "inground pool", "above ground pool",
            "deck permit", "build a deck", "open deck", "shed permit", "storage shed", "fence permit",
            "residential fence", "detached garage", "bulk setback", "schedule a yard", "yard requirements"
        ]) or bool(re.search(r'\b(zoning|construction)\b', q))
        is_zoning_context = "zoning" in context_text and (detail_type != "procedure")

        if is_zoning_explicit or is_zoning_context:
            return ServiceIntentResult(
                service_id="unconfigured_service",
                service_name="Residential Construction & Zoning",
                confidence=0.92 if is_zoning_explicit else 0.85,
                is_supported=False,
                is_ambiguous=False,
                intent_type=intent_type,
                detail_type=detail_type,
                has_flowchart=False,
                flow_id=None,
                official_form_id=None,
                official_form_file=None
            )

        # I. Check History Context for Follow-ups with volume/quantities
        if history and ("soil" in last_bot_msg or "cubic yard" in last_bot_msg):
            if any(w in q for w in ["bring", "import", "in", "add"]):
                return ServiceIntentResult(
                    service_id="soil_import",
                    service_name="Soil Importation",
                    confidence=0.90,
                    intent_type=intent_type,
                    detail_type=detail_type,
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
                    intent_type=intent_type,
                    detail_type=detail_type,
                    has_flowchart=True,
                    flow_id="soil_import_export_flow",
                    official_form_id="soil_export",
                    official_form_file="Forms_Soil_Exportation_App.pdf"
                )
            if any(w in q for w in ["yard", "cubic", "10", "20", "5", "more", "less", "yes", "no"]):
                if "import" in last_bot_msg:
                    return ServiceIntentResult(
                        service_id="soil_import",
                        service_name="Soil Importation",
                        confidence=0.88,
                        intent_type=intent_type,
                        detail_type=detail_type,
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
                        intent_type=intent_type,
                        detail_type=detail_type,
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
                detail_type=detail_type,
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
                    "(For example: Tree removal, or soil importation/exportation?)"
                ),
                intent_type=intent_type,
                detail_type=detail_type,
                has_flowchart=False,
                flow_id=None
            )

        return ServiceIntentResult(
            service_id="other_engineering",
            service_name="General Engineering Inquiry",
            confidence=0.50,
            is_ambiguous=False,
            intent_type=intent_type,
            detail_type=detail_type,
            has_flowchart=False,
            flow_id=None
        )


service_intent_service = ServiceIntentService()
