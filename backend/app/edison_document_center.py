"""
Township of Edison Document Center Catalog (edisonnj.org/document_center/index.php)
Provides structured metadata, departmental categorization, official PDF URLs, 
and intake routing instructions for all public forms and applications.
"""

EDISON_DOCUMENT_CATALOG = [
    # --- Engineering & Zoning Department ---
    {
        "id": "edison_zoning_permit_req",
        "title": "Zoning Permit Requirements Sheet",
        "category": "Engineering & Zoning",
        "department_id": "engineering",
        "description": "Mandatory survey, plot plan scale (1\"=20' or 1\"=30'), and setback requirements for additions, pools, decks, sheds, and fences.",
        "source_url": "https://www.edisonnj.org/document_center/ZONING%20PERMIT%20REQUIREMENT%20SHEET.pdf",
        "local_file": "ZONING_PERMIT_REQUIREMENT_SHEET.pdf",
        "flow_id": "residential_building_permit",
        "submission_desk": "Division of Zoning, Municipal Complex, 100 Municipal Blvd, Edison, NJ 08817",
        "contact_email": "zoning@edisonnj.gov",
        "fee_summary": "$50 - $200 per zoning fee schedule"
    },
    {
        "id": "edison_zoning_app",
        "title": "Official Zoning Permit Application Form",
        "category": "Engineering & Zoning",
        "department_id": "engineering",
        "description": "Application form for single-family residential dwellings, additions, sheds, pools, decks, and commercial tenancy changes.",
        "source_url": "https://www.edisonnj.org/document_center/Zoning%20ApplicationNEW.pdf",
        "local_file": "Zoning_Permit_Application_Edison.pdf",
        "flow_id": "residential_building_permit",
        "submission_desk": "Division of Zoning, Municipal Complex, 100 Municipal Blvd, Edison, NJ 08817",
        "contact_email": "zoning@edisonnj.gov",
        "fee_summary": "$50 (fences/sheds) - $150 (pools) - $200 (new dwelling)"
    },
    {
        "id": "edison_zoning_fees",
        "title": "Zoning Permit Fee Schedule (Ordinance O.2158-2022)",
        "category": "Engineering & Zoning",
        "department_id": "engineering",
        "description": "Adopted schedule of fees for residential construction, variances, escrow reviews, and site plans.",
        "source_url": "https://www.edisonnj.org/Departments/Engineering%20Department/Zoning%20Board/Zoning%20Permit%20Fees%202022.pdf",
        "local_file": None,
        "flow_id": None,
        "submission_desk": "Engineering & Zoning Counter, 100 Municipal Blvd",
        "contact_email": "engineering@edisonnj.gov",
        "fee_summary": "Ordinance fee scale"
    },
    {
        "id": "edison_zoning_map",
        "title": "Official Edison Township Zoning Map",
        "category": "Engineering & Zoning",
        "department_id": "engineering",
        "description": "Official municipal zoning boundaries (R-A, R-B, R-C residential, C-1/C-2 commercial, M-1 industrial).",
        "source_url": "https://www.edisonnj.org/Departments/Engineering%20Department/ZONING%20MAP.pdf",
        "local_file": None,
        "flow_id": None,
        "submission_desk": "Online Public Record / Engineering Counter",
        "contact_email": "engineering@edisonnj.gov",
        "fee_summary": "Free public download"
    },
    {
        "id": "edison_pool_setbacks",
        "title": "Pool Setbacks & Enclosure Guidelines",
        "category": "Engineering & Zoning",
        "department_id": "engineering",
        "description": "Setback buffers, barrier fence heights (minimum 4 ft), and safety latch requirements for inground and above-ground pools.",
        "source_url": "https://www.edisonnj.org/document_center/Pool%20Setbacks.pdf",
        "local_file": None,
        "flow_id": "residential_building_permit",
        "submission_desk": "Division of Zoning, 100 Municipal Blvd",
        "contact_email": "zoning@edisonnj.gov",
        "fee_summary": "$75 (Above-ground) / $150 (Inground)"
    },
    {
        "id": "edison_deck_coverage",
        "title": "Deck Coverage & Setback Regulation Sheet",
        "category": "Engineering & Zoning",
        "department_id": "engineering",
        "description": "Specific zoning lot coverage limitations and minimum 15ft rear yard setback standards for open and covered decks.",
        "source_url": "https://www.edisonnj.org/document_center/DECK%20COVERAGE%20(2021).pdf",
        "local_file": None,
        "flow_id": "residential_building_permit",
        "submission_desk": "Division of Zoning, 100 Municipal Blvd",
        "contact_email": "zoning@edisonnj.gov",
        "fee_summary": "$75 residential fee"
    },
    {
        "id": "edison_subdivision_minor",
        "title": "Minor Subdivision Application Packet",
        "category": "Engineering & Zoning",
        "department_id": "engineering",
        "description": "Planning Board and Zoning Board of Adjustment application for splitting residential parcels into 3 or fewer lots.",
        "source_url": "https://www.edisonnj.org/Departments/Engineering%20Department/Zoning%20Board/2024%20MINOR%20SUBDIVISION%20APP%20PACKET.pdf",
        "local_file": None,
        "flow_id": None,
        "submission_desk": "Planning Board / Zoning Board Secretary, 100 Municipal Blvd",
        "contact_email": "planning@edisonnj.gov",
        "fee_summary": "$500 base + $1,500 escrow deposit"
    },

    # --- Public Works (DPW) ---
    {
        "id": "edison_road_open",
        "title": "Street Opening & Road Trenching Application",
        "category": "Public Works (DPW)",
        "department_id": "engineering",
        "description": "Mandatory permit for pavement saw-cutting, utility connections, sidewalk excavations, and curb alterations.",
        "source_url": "https://www.edisonnj.org/document_center/RoadOpenApp.pdf",
        "local_file": "RoadOpenApp.pdf",
        "flow_id": "road_excavation_permit",
        "submission_desk": "Department of Public Works, 100 Municipal Blvd, Edison, NJ 08817",
        "contact_email": "dpw@edisonnj.gov",
        "fee_summary": "$150 filing fee + $5,000 restoration bond"
    },
    {
        "id": "edison_sewer_connection",
        "title": "Sewer Connection Charge Application",
        "category": "Public Works (DPW)",
        "department_id": "engineering",
        "description": "Municipal sanitary sewer tap-in and connection allocation review for new dwellings or commercial facilities.",
        "source_url": "https://www.edisonnj.org/Sewer%20Connection%20Charge%20Applications.pdf",
        "local_file": None,
        "flow_id": None,
        "submission_desk": "Edison Sewer Utility Division, 100 Municipal Blvd",
        "contact_email": "sewer@edisonnj.gov",
        "fee_summary": "Calculated by fixture units per municipal ordinance"
    },

    # --- Health & Human Services ---
    {
        "id": "edison_food_plan_review",
        "title": "Retail Food Establishment Plan Review Application",
        "category": "Health & Human Services",
        "department_id": "healthcare",
        "description": "Sanitary plan submission for restaurants, catering kitchens, bakeries, and grocery facilities under Chapter 24 NJ Sanitary Code.",
        "source_url": "https://www.edisonnj.org/document_center/Health%20Dept%20Plan%20Review%20Application.pdf",
        "local_file": "Health_Dept_Plan_Review_Application.pdf",
        "flow_id": "food_establishment_license",
        "submission_desk": "Edison Township Health Department, 100 Municipal Blvd, Edison, NJ 08817",
        "contact_email": "health@edisonnj.gov",
        "fee_summary": "$150 plan review + annual operating license fee"
    },
    {
        "id": "edison_farmers_market",
        "title": "Farmers Market & Temporary Food Vendor Application Packet",
        "category": "Health & Human Services",
        "department_id": "healthcare",
        "description": "Temperature integrity rules, handwashing station setup, and operational permit for open-air and seasonal food vendors.",
        "source_url": "https://www.edisonnj.org/Departments/Health%20Department/2025_Edison%20Farmers%20Market%20Application%20Packet.pdf",
        "local_file": None,
        "flow_id": "mobile_food_vendor_sanitation_permit",
        "submission_desk": "Health Department Licensing Desk, 100 Municipal Blvd",
        "contact_email": "health@edisonnj.gov",
        "fee_summary": "$50 per event / $150 full season"
    },
    {
        "id": "edison_vital_records",
        "title": "Vital Statistics - Certified Copies Application (REG-37)",
        "category": "Health & Human Services",
        "department_id": "healthcare",
        "description": "Request certified archival copies of Birth Certificates, Death Certificates, and Marriage Licenses issued in Edison.",
        "source_url": "https://www.edisonnj.org/Departments/Health%20Department/Birth,%20Death%20&%20Marriage%20Certificates%20&%20Licenses/Reg-37%20Application%20in%20English.pdf",
        "local_file": None,
        "flow_id": None,
        "submission_desk": "Office of Vital Statistics, Health Department, 100 Municipal Blvd",
        "contact_email": "vitalstats@edisonnj.gov",
        "fee_summary": "$25.00 first copy, $2.00 each additional copy"
    },

    # --- Township Clerk's Office ---
    {
        "id": "edison_opra_request",
        "title": "OPRA - Open Public Records Act Request Form",
        "category": "Township Clerk's Office",
        "department_id": "engineering",
        "description": "Official legal request for municipal government records, ordinances, council minutes, and building permit histories.",
        "source_url": "https://www.edisonnj.org/Departments/Clerk's%20Office/2024%20OPRA%20Municipal%20Writable.pdf",
        "local_file": None,
        "flow_id": None,
        "submission_desk": "Township Clerk's Office, 100 Municipal Blvd, Edison, NJ 08817",
        "contact_email": "opra@edisonnj.gov",
        "fee_summary": "Letter/Legal pages: $0.05 / $0.07 (Electronic records free)"
    },
    {
        "id": "edison_landlord_reg",
        "title": "Landlord Identity Registration Statement Form",
        "category": "Township Clerk's Office",
        "department_id": "engineering",
        "description": "Mandatory state and municipal registration for owners of rental properties under NJSA 46:8-28.",
        "source_url": "https://www.edisonnj.org/document_center/LANDLORD_reg_form.pdf",
        "local_file": None,
        "flow_id": None,
        "submission_desk": "Township Clerk's Office (Can be emailed to clerk@edisonnj.gov)",
        "contact_email": "clerk@edisonnj.gov",
        "fee_summary": "$10 filing fee"
    },
    {
        "id": "edison_bingo_raffle",
        "title": "Bingo & Raffle Charitable Gaming Application",
        "category": "Township Clerk's Office",
        "department_id": "engineering",
        "description": "Application for registered 501(c)(3) charities to hold raffles, casino nights, and bingo games.",
        "source_url": "https://www.edisonnj.org/document_center/Bingoapp.pdf",
        "local_file": None,
        "flow_id": None,
        "submission_desk": "Township Clerk's Office, 100 Municipal Blvd",
        "contact_email": "clerk@edisonnj.gov",
        "fee_summary": "$20 per $1,000 retail value"
    },

    # --- Code Enforcement ---
    {
        "id": "edison_cco_form",
        "title": "Certificate of Continued Occupancy (CCO) Application",
        "category": "Code Enforcement",
        "department_id": "engineering",
        "description": "Mandatory smoke detector, carbon monoxide, fire extinguisher, and habitability inspection prior to residential resale or tenancy.",
        "source_url": "https://www.edisonnj.org/document_center/CCO%20FORM.pdf",
        "local_file": None,
        "flow_id": None,
        "submission_desk": "Division of Code Enforcement, 100 Municipal Blvd",
        "contact_email": "codeenforcement@edisonnj.gov",
        "fee_summary": "$100 residential inspection fee"
    },
    {
        "id": "edison_contractor_license",
        "title": "Municipal Contractor License Application",
        "category": "Code Enforcement",
        "department_id": "engineering",
        "description": "Registration for general contractors, electricians, plumbers, and roofers performing work in Edison Township.",
        "source_url": "https://www.edisonnj.org/Contractor%20License%20O.2022.pdf",
        "local_file": None,
        "flow_id": None,
        "submission_desk": "Division of Code Enforcement, 100 Municipal Blvd",
        "contact_email": "codeenforcement@edisonnj.gov",
        "fee_summary": "$75 annual contractor registration"
    }
]
