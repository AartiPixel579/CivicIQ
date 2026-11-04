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

    # 3. Sewer Connection Charge Application
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
    ),

    # 4. Tree Removal Permit Application (Verified Official Form)
    "tree_removal": FormMetadata(
        form_id="tree_removal",
        official_title="Township of Edison Tree Permit Application (Removal / Replacement / Conservation)",
        form_code="EDISON-ENG-TRP",
        department="engineering",
        service="tree_removal",
        document_type="permit_application",
        application_type="Application form",
        visibility="public",
        verification_status="verified",
        description="Official municipal application under Edison Township Ordinance 25-3 & 25-8 for tree removal, replacement, and conservation permits.",
        official_source_url="https://www.edisonnj.org/document_center/3.23.21%20tree%20permit%20application.pdf?t=202409111411050",
        local_filename="3.23.21 tree permit application.pdf",
        signature_required=True,
        signature_instructions="Applicant and property owner must certify that all information is true and accurate and sign in ink.",
        supporting_documents=[
            "Survey or Tax Map showing house location, existing trees marked as circles with diameter (DBH), and trees to be removed marked with an X",
            "Written statement detailing the reason for tree removal (per Township Ordinance 25-8.1a6)",
            "If dead/dying/diseased/hazard: Statement from licensed arborist/certified tree professional OR colored photographs of tree condition",
            "Tree Replacement Plan (required if removing more than 25% of trees on property; Ordinance 25-8.2a)",
            "Trees to be removed must be visibly marked on site with ribbon or paint for municipal inspection",
            "Filing fee of $25 (check/card payable to 'Township of Edison') or Senior ID (age 62+ for fee waiver)"
        ],
        submission_method="Submit completed application with survey sketch, fee, and photo/arborist proof to the Division of Engineering counter (100 Municipal Blvd) or online portal.",
        fee_info="$25.00 for single residential lot ($200.00 with Board approval / subdivision; waived for senior citizens age 62+ with ID)",
        is_verified=True,
        last_verified_date="2026-11-04",
        fields=[
            FormField(
                name="property_owner_name",
                label="Property Owner Full Name",
                field_type="text",
                required=True,
                help_text="Full legal name of Edison property owner."
            ),
            FormField(
                name="property_owner_address",
                label="Property Owner Street Address",
                field_type="address",
                required=True,
                help_text="Mailing address of property owner."
            ),
            FormField(
                name="applicant_name",
                label="Applicant Name (Owner / Agent / Contractor)",
                field_type="text",
                required=True,
                help_text="Name of person or company filing application."
            ),
            FormField(
                name="permit_address",
                label="Tree Removal Site Address",
                field_type="address",
                required=True,
                help_text="Street address where tree(s) are located in Edison."
            ),
            FormField(
                name="block_lot",
                label="Block and Lot Numbers",
                field_type="text",
                required=True,
                help_text="Municipal tax parcel Block and Lot."
            ),
            FormField(
                name="trees_on_site",
                label="Total Number of Trees On-Site",
                field_type="number",
                required=True,
                help_text="Count of all mature trees (>= 4 inches DBH) currently on property."
            ),
            FormField(
                name="trees_to_remove",
                label="Number of Trees to be Removed",
                field_type="number",
                required=True,
                help_text="Total number of trees proposed for removal."
            ),
            FormField(
                name="is_emergency_hazard",
                label="Is this an emergency situation where tree is dead, dying, or poses imminent danger?",
                field_type="choice",
                required=True,
                options=["Yes, Emergency Dead/Dying/Imminent Hazard", "No, Planned Healthy Tree Removal"],
                help_text="Emergency removals require photographic proof or arborist letter."
            ),
            FormField(
                name="removal_reason",
                label="Detailed Reason for Tree Removal",
                field_type="text",
                required=True,
                help_text="Explain reason for removal (per Township Ordinance 25-8.1a6)."
            ),
            FormField(
                name="applicant_phone",
                label="Applicant Contact Phone Number",
                field_type="phone",
                required=True,
                help_text="Daytime phone number."
            )
        ]
    ),

    # 5. Soil Importation Permit Application (Verified Official Form)
    "soil_import": FormMetadata(
        form_id="soil_import",
        official_title="Township of Edison Soil Importation Permit Application",
        form_code="EDISON-ENG-SOIL-IMP",
        department="engineering",
        service="soil_import",
        document_type="permit_application",
        application_type="Application form",
        visibility="public",
        verification_status="verified",
        description="Official municipal permit application to import 10 cubic yards or more of soil to a site in Edison Township.",
        official_source_url="https://www.edisonnj.org/document_center/Forms_Soil_Importation_Appl.pdf?t=202409111411240",
        local_filename="Forms_Soil_Importation_Appl.pdf",
        signature_required=True,
        signature_instructions="Applicant and licensed contractor must sign and certify fill origin and clean fill standards.",
        supporting_documents=[
            "Certified laboratory soil analysis / clean fill certification",
            "Property survey showing proposed fill placement and grading contours",
            "Designated truck haul route plan through Edison municipal roadways",
            "Soil importation review fee and engineering escrow deposit"
        ],
        submission_method="Submit completed application with certified test reports to the Division of Engineering counter, 100 Municipal Blvd, Edison, NJ 08817.",
        fee_info="Standard municipal soil review fee and engineering escrow deposit",
        is_verified=True,
        last_verified_date="2026-11-04",
        fields=[]
    ),

    # 6. Soil Exportation Permit Application (Verified Official Form)
    "soil_export": FormMetadata(
        form_id="soil_export",
        official_title="Township of Edison Soil Exportation Permit Application",
        form_code="EDISON-ENG-SOIL-EXP",
        department="engineering",
        service="soil_export",
        document_type="permit_application",
        application_type="Application form",
        visibility="public",
        verification_status="verified",
        description="Official municipal permit application to export 10 cubic yards or more of soil from a site in Edison Township.",
        official_source_url="https://www.edisonnj.org/document_center/Forms_Soil_Exportation_App.pdf?t=202409111411240",
        local_filename="Forms_Soil_Exportation_App.pdf",
        signature_required=True,
        signature_instructions="Applicant and property owner must certify earth disturbance calculations and sign.",
        supporting_documents=[
            "Topographical survey with cut/fill calculations by NJ licensed engineer/surveyor",
            "Soil erosion and sediment control plan certification (Freehold Soil Conservation District)",
            "Truck haul route and road maintenance protection plan",
            "Soil exportation filing fee and restoration bond"
        ],
        submission_method="Submit to the Division of Engineering counter, 100 Municipal Blvd, Edison, NJ 08817.",
        fee_info="Standard municipal soil exportation fee schedule",
        is_verified=True,
        last_verified_date="2026-11-04",
        fields=[]
    ),

    # 7. Site Improvement Permit Application with Checklist (Verified Official Form)
    "site_improvement": FormMetadata(
        form_id="site_improvement",
        official_title="Township of Edison Site Improvement Permit Application with Checklist",
        form_code="EDISON-ENG-SIP",
        department="engineering",
        service="site_improvements",
        document_type="permit_application",
        application_type="Application form",
        visibility="public",
        verification_status="verified",
        description="Official municipal permit application and engineering checklist for residential and commercial site improvements exceeding 500 sq.ft. impervious surface, 1,250 sq.ft. disturbance, or grading changes.",
        official_source_url="https://www.edisonnj.org/document_center/SIP%20Applicationa.pdf?t=202410111550460",
        local_filename="SIP_Application.pdf",
        signature_required=True,
        signature_instructions="Property owner and design engineer must sign the application and engineering certification.",
        supporting_documents=[
            "Two (2) signed and sealed copies of Site Improvement Engineering Plan",
            "Completed Site Improvement Checklist (Items 1-25)",
            "Stormwater management and runoff calculation report",
            "Soil erosion and sediment control certification",
            "Engineering review fee and inspection escrow deposit"
        ],
        submission_method="Submit completed SIP application packet with sealed engineering drawings to the Division of Engineering, 100 Municipal Blvd, Edison, NJ 08817.",
        fee_info="Engineering review fee per municipal rate schedule",
        is_verified=True,
        last_verified_date="2026-11-04",
        fields=[]
    )
}

# Distinct registry of reference documents (information sheets, guidelines, internal flowcharts, fee schedules)
# Internal documents (visibility="internal") are NEVER displayed to residents as citations or download links!
OFFICIAL_REFERENCE_DOCUMENTS: Dict[str, FormMetadata] = {
    "permit_flow_charts": FormMetadata(
        form_id="permit_flow_charts",
        official_title="Township of Edison Official Permit Flow Charts",
        form_code="EDISON-ENG-FLOW",
        department="engineering",
        service="decision_tree",
        document_type="internal_flowchart",
        application_type="Flowchart",
        visibility="internal",
        verification_status="verified",
        description="Internal decision tree flowcharts for determining whether Road Opening, Tree Removal, Soil Import/Export, or Site Improvement permits are required. (Internal Reference Only - Not public facing).",
        official_source_url="https://cms2.revize.com/revize/edisonnj/document_center/Permit%20Flow%20Charts.pdf",
        local_filename="Permit_Flow_Charts.pdf",
        signature_required=False,
        supporting_documents=[],
        submission_method="Internal reference flowchart.",
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
    def get_public_application_forms() -> List[FormMetadata]:
        return [f for f in OFFICIAL_FORMS_REGISTRY.values() if getattr(f, 'visibility', 'public') == "public"]

    @staticmethod
    def get_all_reference_documents() -> List[FormMetadata]:
        return list(OFFICIAL_REFERENCE_DOCUMENTS.values())

    @staticmethod
    def get_public_reference_documents() -> List[FormMetadata]:
        return [d for d in OFFICIAL_REFERENCE_DOCUMENTS.values() if getattr(d, 'visibility', 'public') == "public"]

form_schema_service = FormSchemaService()
