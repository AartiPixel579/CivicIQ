from typing import List, Dict, Optional
from ..models.form import FormMetadata, FormField

# Authoritative registry of official Edison Township forms and documents
OFFICIAL_FORMS_REGISTRY: Dict[str, FormMetadata] = {
    # 1. Road Opening / Street Excavation Application
    "road_opening": FormMetadata(
        form_id="road_opening",
        official_title="Edison Township Street Opening & Road Excavation Permit Application",
        form_code="EDISON-DPW-ROADOPEN",
        department="engineering",
        application_type="Application form",
        description="Official municipal application to saw-cut, trench, or excavate municipal asphalt, sidewalks, aprons, or curbs in the public right-of-way.",
        official_source_url="https://www.edisonnj.org/document_center/RoadOpenApp.pdf",
        local_filename="RoadOpenApp.pdf",
        signature_required=True,
        signature_instructions="Applicant / Contractor must physically sign and date the application in ink after printing. Unsigned submissions cannot be processed.",
        supporting_documents=[
            "NJ 811 Call Before You Dig confirmation ticket number",
            "$5,000 Refundable Restoration Guarantee Deposit / Surety Bond",
            "Traffic Safety Detour Plan (if obstructing roadway lanes)",
            "Certificate of Commercial General Liability Insurance naming Township of Edison as additional insured"
        ],
        submission_method="Submit completed signed application with required bond and attachments via the official document portal (edisonnj.org/document_center/index.php) or at the Public Works counter.",
        fee_info="$150.00 Filing Fee + $5,000.00 Refundable Restoration Guarantee Deposit",
        is_verified=True,
        last_verified_date="2026-11-04",
        fields=[
            FormField(
                name="applicant_name",
                label="Applicant / Contractor Full Name",
                field_type="text",
                required=True,
                help_text="Full legal name of person or contractor submitting the application."
            ),
            FormField(
                name="applicant_phone",
                label="Primary Contact Telephone Number",
                field_type="phone",
                required=True,
                help_text="10-digit telephone number where the applicant can be reached during municipal hours."
            ),
            FormField(
                name="applicant_email",
                label="Applicant Email Address",
                field_type="email",
                required=True,
                help_text="Official email address for departmental notifications and approval updates."
            ),
            FormField(
                name="work_location",
                label="Excavation Work Site Street Address",
                field_type="address",
                required=True,
                help_text="Street address and nearest cross street in Edison where pavement opening will take place."
            ),
            FormField(
                name="block_lot",
                label="Property Block and Lot Numbers",
                field_type="text",
                required=True,
                help_text="Official municipal tax parcel Block and Lot (found on tax bill or property deed)."
            ),
            FormField(
                name="excavation_purpose",
                label="Purpose and Scope of Road Excavation",
                field_type="choice",
                required=True,
                options=["Sewer Lateral Repair/Connection", "Water Service Line", "Gas Line Connection", "Driveway Apron / Curb Cut", "Underground Utility Trenching"],
                help_text="Select primary municipal utility purpose for pavement saw-cut."
            ),
            FormField(
                name="trench_dimensions",
                label="Estimated Pavement Trench Dimensions (Length x Width in Feet)",
                field_type="text",
                required=True,
                help_text="Example: 10 ft length x 4 ft width."
            ),
            FormField(
                name="call_before_you_dig_ticket",
                label="NJ 811 'Call Before You Dig' Locate Ticket Number",
                field_type="text",
                required=True,
                help_text="Mandatory utility mark-out confirmation number issued by NJ One Call (Call 811)."
            )
        ]
    ),

    # 2. Residential Construction / Zoning Permit Application
    "zoning_permit": FormMetadata(
        form_id="zoning_permit",
        official_title="Township of Edison Official Permit Application Form",
        form_code="EDISON-ENG-PERMIT",
        department="engineering",
        application_type="Application form",
        description="Standard municipal permit application for single-family residential dwellings, additions, open decks, swimming pools, detached garages, sheds (>100 sq.ft.), and fences (>6ft).",
        official_source_url="https://www.edisonnj.org/document_center/Zoning%20ApplicationNEW.pdf",
        local_filename="Zoning_Permit_Application_Edison.pdf",
        signature_required=True,
        signature_instructions="Property owner or authorized agent must sign in ink under the applicant certification block. Digital or typed signatures require ink verification.",
        supporting_documents=[
            "Two (2) copies of current property survey prepared and sealed by a NJ Licensed Land Surveyor (Scale: 1\"=20' or 1\"=30')",
            "Plot plan showing exact dimensions, setbacks (front, rear, side yards), and proposed structure height",
            "Building architectural plans / sketches (if addition or dwelling)",
            "Zoning review fee per municipal fee schedule"
        ],
        submission_method="Submit via the official municipal portal at https://www.edisonnj.org/document_center/index.php or at the Division of Zoning counter.",
        fee_info="$50 (fences/sheds) - $75 (decks/pools) - $100 (additions) - $200 (new dwelling)",
        is_verified=True,
        last_verified_date="2026-11-04",
        fields=[
            FormField(
                name="property_owner_name",
                label="Property Owner Full Name",
                field_type="text",
                required=True,
                help_text="Legal owner of record for the Edison parcel."
            ),
            FormField(
                name="property_address",
                label="Job Site Street Address",
                field_type="address",
                required=True,
                help_text="Exact street address where construction is proposed in Edison."
            ),
            FormField(
                name="block_lot",
                label="Block and Lot Identification",
                field_type="text",
                required=True,
                help_text="Tax parcel Block and Lot numbers."
            ),
            FormField(
                name="proposed_work",
                label="Type of Proposed Residential Improvement",
                field_type="choice",
                required=True,
                options=["New Single Family Dwelling", "Residential Addition / Alteration", "Open Deck / Patio", "Swimming Pool (In-Ground or Above-Ground)", "Detached Garage / Shed (>100 sq.ft.)", "Fence (>6 ft height)"],
                help_text="Select primary construction category."
            ),
            FormField(
                name="project_description",
                label="Detailed Description of Proposed Work & Dimensions",
                field_type="text",
                required=True,
                help_text="Example: Proposed 16'x24' rear unenclosed composite deck with 15ft rear setback."
            ),
            FormField(
                name="owner_phone",
                label="Property Owner Contact Telephone",
                field_type="phone",
                required=True,
                help_text="Best daytime contact number."
            ),
            FormField(
                name="owner_email",
                label="Property Owner Email Address",
                field_type="email",
                required=True,
                help_text="Email for zoning review status notifications."
            ),
            FormField(
                name="contractor_name",
                label="Contractor Name & NJ Home Improvement Contractor (HIC) License #",
                field_type="text",
                required=False,
                help_text="Optional if homeowner is performing work personally; otherwise provide contractor details."
            )
        ]
    ),

    # 3. Tree Removal Clearance & Permit
    "tree_removal": FormMetadata(
        form_id="tree_removal",
        official_title="Edison Township Tree Removal Clearance & Permit Application",
        form_code="EDISON-ENG-TREE",
        department="engineering",
        application_type="Application form",
        description="Official municipal application under Edison Township Tree Protection Ordinance (Chapter 34) and Permit Flow Chart for tree removal clearances and emergency hazard filings.",
        official_source_url="https://www.edisonnj.org/document_center/ZONING%20PERMIT%20REQUIREMENT%20SHEET.pdf",
        local_filename="ZONING_PERMIT_REQUIREMENT_SHEET.pdf",
        signature_required=True,
        signature_instructions="Applicant must physically sign and date after printing. If emergency hazard, attach photos or arborist certification.",
        supporting_documents=[
            "Photographic proof of hazardous / dead / dying condition (if emergency)",
            "Certified letter from NJ Licensed Tree Expert / Forester (if available)",
            "Plot sketch showing property boundary and approximate tree trunk diameter (DBH)",
            "Canopy replacement proposal or contribution waiver"
        ],
        submission_method="Submit online via https://www.edisonnj.org/document_center/index.php concurrent to removal if emergency hazard, or in advance if planned.",
        fee_info="$25 application review fee (fee waived for verified hazardous/dead trees)",
        is_verified=True,
        last_verified_date="2026-11-04",
        fields=[
            FormField(
                name="property_owner_name",
                label="Property Owner Full Name",
                field_type="text",
                required=True,
                help_text="Name of Edison property owner."
            ),
            FormField(
                name="property_address",
                label="Property Street Address",
                field_type="address",
                required=True,
                help_text="Site address where tree(s) are located."
            ),
            FormField(
                name="block_lot",
                label="Block and Lot",
                field_type="text",
                required=True,
                help_text="Municipal Block and Lot numbers."
            ),
            FormField(
                name="is_emergency_hazard",
                label="Is this removal due to an imminent hazard, dead or dying tree?",
                field_type="choice",
                required=True,
                options=["Yes, Emergency Imminent Danger / Dead or Dying Tree", "No, Planned Landscape Removal"],
                help_text="Emergency removals allow immediate action with concurrent permit filing."
            ),
            FormField(
                name="emergency_reason",
                label="Condition of Tree & Reason for Removal",
                field_type="text",
                required=True,
                help_text="Describe species, approximate trunk diameter (DBH), and specific damage/hazard (e.g., cracked trunk, leaning over roof)."
            ),
            FormField(
                name="tree_quantity",
                label="Number of Trees Proposed for Removal",
                field_type="number",
                required=True,
                help_text="Total number of trees meeting municipal size threshold (>=6 in DBH)."
            ),
            FormField(
                name="contact_phone",
                label="Contact Phone Number",
                field_type="phone",
                required=True,
                help_text="Daytime telephone number."
            )
        ]
    ),

    # 4. Sewer Connection Charge Application
    "sewer_connection": FormMetadata(
        form_id="sewer_connection",
        official_title="Township of Edison Sewer Connection Charge Application",
        form_code="EDISON-ENG-SEWER",
        department="engineering",
        application_type="Application form",
        description="Application for municipal sanitary sewer main tap-in, fixture unit allocation, and connection charge calculations for new dwellings or commercial developments.",
        official_source_url="https://www.edisonnj.org/Sewer%20Connection%20Charge%20Applications.pdf",
        local_filename="Sewer_Connection_Charge_Applications.pdf",
        signature_required=True,
        signature_instructions="Applicant and property owner must sign in ink. Certified plumbing contractor details required.",
        supporting_documents=[
            "Plumbing Fixture Unit Calculation Schedule (Form A or Form B)",
            "Civil engineering utility connection schematic",
            "Copy of approved building or zoning permit",
            "Sewer connection review fee payment"
        ],
        submission_method="Submit via official municipal portal at https://www.edisonnj.org/document_center/index.php or at the Sewer Utility Division counter.",
        fee_info="Calculated per plumbing fixture unit per municipal rate schedule",
        is_verified=True,
        last_verified_date="2026-11-04",
        fields=[
            FormField(
                name="applicant_name",
                label="Applicant / Property Owner Full Name",
                field_type="text",
                required=True,
                help_text="Full name of applicant."
            ),
            FormField(
                name="property_address",
                label="Connection Site Address",
                field_type="address",
                required=True,
                help_text="Street address where sewer connection is requested."
            ),
            FormField(
                name="block_lot",
                label="Block and Lot",
                field_type="text",
                required=True,
                help_text="Tax parcel identifier."
            ),
            FormField(
                name="application_category",
                label="Application Category",
                field_type="choice",
                required=True,
                options=["Residential Single Family", "Residential Multi-Family", "Commercial / Industrial"],
                help_text="Category of sewer service."
            ),
            FormField(
                name="plumbing_contractor",
                label="Licensed Master Plumber Name & NJ License #",
                field_type="text",
                required=True,
                help_text="Name and NJ plumbing license number of contractor executing lateral tie-in."
            ),
            FormField(
                name="contact_phone",
                label="Contact Phone Number",
                field_type="phone",
                required=True,
                help_text="Daytime telephone number."
            )
        ]
    )
}

# Distinct registry of non-application official documents (information sheets, guidelines, flowcharts, fee schedules)
# CivicIQ will NEVER label these as application forms or offer to fill them out as applications!
OFFICIAL_REFERENCE_DOCUMENTS: Dict[str, FormMetadata] = {
    "permit_flow_charts": FormMetadata(
        form_id="permit_flow_charts",
        official_title="Township of Edison Official Permit Flow Charts",
        form_code="EDISON-ENG-FLOW",
        department="engineering",
        application_type="Flowchart",
        description="Official decision tree flowcharts for determining whether Road Opening, Tree Removal, Soil Import/Export, or Site Improvement permits are required.",
        official_source_url="https://cms2.revize.com/revize/edisonnj/document_center/Permit%20Flow%20Charts.pdf",
        local_filename="Permit_Flow_Charts.pdf",
        signature_required=False,
        supporting_documents=[],
        submission_method="Informational reference flowchart.",
        fields=[]
    ),
    "zoning_fees_schedule": FormMetadata(
        form_id="zoning_fees_schedule",
        official_title="Edison Township Zoning Permit Fee Schedule (Ordinance O.2158-2022)",
        form_code="EDISON-ENG-FEE",
        department="engineering",
        application_type="Fee schedule",
        description="Official municipal fee schedule and escrow rates for residential additions, dwellings, fences, pools, and commercial reviews.",
        official_source_url="https://www.edisonnj.org/Departments/Engineering%20Department/Zoning%20Board/Zoning%20Permit%20Fees%202022.pdf",
        local_filename="Zoning_Permit_Fees_2022.pdf",
        signature_required=False,
        supporting_documents=[],
        submission_method="Informational fee schedule.",
        fields=[]
    ),
    "schedule_a_yard": FormMetadata(
        form_id="schedule_a_yard",
        official_title="Schedule A: Yard & Bulk Zoning Requirements Table",
        form_code="EDISON-ENG-SCHED-A",
        department="engineering",
        application_type="Information sheet",
        description="Official setback, yard dimensions, height limits, and maximum lot coverage percentages across R-A, R-B, R-C, and R-D zones.",
        official_source_url="https://www.edisonnj.org/document_center/Schedule%20A%20Yard%20Requirements.pdf",
        local_filename="Schedule_A_Yard_Requirements.pdf",
        signature_required=False,
        supporting_documents=[],
        submission_method="Informational bulk zoning requirement table.",
        fields=[]
    ),
    "deck_coverage": FormMetadata(
        form_id="deck_coverage",
        official_title="Deck Coverage & Rear Yard Setback Regulations Sheet",
        form_code="EDISON-ENG-DECK",
        department="engineering",
        application_type="Information sheet",
        description="Official zoning guideline regarding open unenclosed deck projections into rear yards (minimum 15-foot rear setback).",
        official_source_url="https://www.edisonnj.org/document_center/DECK%20COVERAGE%20(2021).pdf",
        local_filename="Deck_Coverage.pdf",
        signature_required=False,
        supporting_documents=[],
        submission_method="Informational guideline.",
        fields=[]
    ),
    "pool_setbacks": FormMetadata(
        form_id="pool_setbacks",
        official_title="Swimming Pool Setback & Enclosure Regulations Sheet",
        form_code="EDISON-ENG-POOL",
        department="engineering",
        application_type="Information sheet",
        description="Official zoning guideline on pool setbacks, mandatory 4-ft barrier enclosure fencing, and safety requirements.",
        official_source_url="https://www.edisonnj.org/document_center/Pool%20Setbacks.pdf",
        local_filename="Pool_Setbacks.pdf",
        signature_required=False,
        supporting_documents=[],
        submission_method="Informational guideline.",
        fields=[]
    )
}

class FormSchemaService:
    @staticmethod
    def get_form_by_id(form_id: str) -> Optional[FormMetadata]:
        return OFFICIAL_FORMS_REGISTRY.get(form_id) or OFFICIAL_REFERENCE_DOCUMENTS.get(form_id)

    @staticmethod
    def get_all_application_forms() -> List[FormMetadata]:
        return list(OFFICIAL_FORMS_REGISTRY.values())

    @staticmethod
    def get_all_reference_documents() -> List[FormMetadata]:
        return list(OFFICIAL_REFERENCE_DOCUMENTS.values())

form_schema_service = FormSchemaService()
