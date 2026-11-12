"""
Official Edison Township Document Ingestion Pipeline & Inventory Generator
Source: https://www.edisonnj.org/document_center/index.php

Discovers, downloads, extracts, classifies, and indexes official municipal documents
for Edison Township, New Jersey (focusing on Engineering, Zoning, DPW, and related services).
Outputs departments/engineering/document_inventory.json and populates the vector store.
"""

import os
import sys
import json
import hashlib
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple

# Add backend to sys.path
current_file = Path(__file__).resolve()
backend_root = current_file.parent.parent
sys.path.insert(0, str(backend_root))

try:
    from backend.app.config import (
        DEPARTMENTS_DIR, CHUNK_SIZE_WORDS, CHUNK_OVERLAP_WORDS,
        MUNICIPALITY_NAME, OFFICIAL_DOCUMENT_CENTER_URL, TRUSTED_ROOT_URL
    )
    from backend.app.vector_store import UnifiedVectorStore, vector_store as shared_vector_store
    from backend.app.crawler import (
        extract_pdf_pages, trusted_source_registry, canonicalize_url_for_dedup
    )
except ImportError:
    from app.config import (
        DEPARTMENTS_DIR, CHUNK_SIZE_WORDS, CHUNK_OVERLAP_WORDS,
        MUNICIPALITY_NAME, OFFICIAL_DOCUMENT_CENTER_URL, TRUSTED_ROOT_URL
    )
    from app.vector_store import UnifiedVectorStore, vector_store as shared_vector_store
    from app.crawler import (
        extract_pdf_pages, trusted_source_registry, canonicalize_url_for_dedup
    )
import pypdf

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("edison_ingest")

# Authoritative catalog of official Edison Township documents from Document Center
# The Township's Engineering category lists eight canonical documents:
# 1. Flood Zone Determination Letter
# 2. Permit Flow Chart to Help Determine What Permit is Needed
# 3. Requirements for Plot Grading Plans – Minor Development
# 4. Requirements for Plot Grading Plans – Minor Development / Soil Exportation Permit Application
# 5. Sewer Connection Charge Application
# 6. Site Improvement Permit with Checklist
# 7. Soil Importation Permit Application
# 8. Tree Removal Permit Application

EDISON_OFFICIAL_CATALOG = [
    # --- CANONICAL ENGINEERING DEPARTMENT DOCUMENTS (8 DOCUMENTS) ---
    {
        "id": "edison_flood_zone",
        "title": "Flood Zone Determination Letter",
        "department": "engineering",
        "document_type": "Application form",
        "service_or_permit_name": "Flood Zone Determination",
        "service": "flood_zone",
        "visibility": "public",
        "verification_status": "verified",
        "original_url": "https://www.edisonnj.org/document_center/Flood_Zone_Determination_Letter_REQUEST.pdf?t=202409111411240",
        "local_filename": "Flood_Zone_Determination_Letter_REQUEST.pdf",
        "workflow_id": None,
        "official_summary": "Official Township of Edison Flood Zone Determination Letter Request Form. Used by property owners, buyers, and lenders to obtain formal written determination from the Division of Engineering regarding whether a property is located in a FEMA Special Flood Hazard Area (SFHA) per current Flood Insurance Rate Maps (FIRM). Requires Block, Lot, property address, contact details, and $25 Flood Letter Fee.",
        "fee_info": "$25.00 Flood Letter Fee",
        "target_desk": "Division of Engineering, Municipal Complex, 100 Municipal Blvd, Edison, NJ 08817 (732-248-7288)"
    },
    {
        "id": "edison_permit_flowchart",
        "title": "Permit Flow Chart to Help Determine What Permit is Needed",
        "department": "engineering",
        "document_type": "Guidance flowchart",
        "service_or_permit_name": "Municipal Engineering Guidance",
        "service": "permit_flowchart",
        "visibility": "public",
        "verification_status": "verified",
        "original_url": "https://www.edisonnj.org/document_center/Permit%20Flow%20Charts.pdf",
        "local_filename": "Permit_Flow_Charts.pdf",
        "workflow_id": None,
        "official_summary": "Official Township of Edison Permit Flow Charts to help determine what municipal permit is needed for property projects. Outlines decision trees for Road Opening (Public Works), Tree Removal (Engineering), Soil Importation and Exportation (Engineering), and Site Improvement Permits (Engineering).",
        "fee_info": "No fee (Official guidance reference)",
        "target_desk": "Division of Engineering / Municipal Complex, 100 Municipal Blvd, Edison, NJ 08817"
    },
    {
        "id": "edison_plot_grading_req",
        "title": "Requirements for Plot Grading Plans – Minor Development",
        "department": "engineering",
        "document_type": "Procedure/guideline",
        "service_or_permit_name": "Plot Grading Plans & Minor Development",
        "service": "plot_grading",
        "visibility": "public",
        "verification_status": "verified",
        "original_url": "https://www.edisonnj.org/document_center/Requirments_for_plot_grading_plans.pdf?t=202409111411520",
        "local_filename": "Requirements_for_Plot_Grading_Plans_Minor_Development.pdf",
        "workflow_id": None,
        "official_summary": "Official Edison Township Requirements for Plot Grading Plans on Minor Developments. Mandatory for new dwellings, additions, in-ground pools, retaining walls, or projects disturbing 1,250+ sq.ft. or adding 500+ sq.ft. impervious coverage. Must be prepared, signed, and sealed by a NJ licensed PE or PLS, overlaid on certified boundary survey, with contours, spot elevations, on-site stormwater infiltration (seepage pits per Title 34), and soil erosion sediment control measures.",
        "fee_info": "Engineering review fee plus 5% construction cost inspection escrow",
        "target_desk": "Division of Engineering, Municipal Complex, 100 Municipal Blvd, Edison, NJ 08817"
    },
    {
        "id": "edison_soil_export_app",
        "title": "Requirements for Plot Grading Plans – Minor Development / Soil Exportation Permit Application",
        "department": "engineering",
        "document_type": "Application form",
        "service_or_permit_name": "Soil Exportation Permit",
        "service": "soil_export",
        "visibility": "public",
        "verification_status": "verified",
        "original_url": "https://www.edisonnj.org/document_center/Forms_Soil_Exportation_App.pdf",
        "local_filename": "Forms_Soil_Exportation_App.pdf",
        "workflow_id": "soil_import_export_flow",
        "official_summary": "Official Edison Township municipal application and guidelines for how to export soil, removing excess excavated soil, dirt, or fill from properties in Edison Township. Under Chapter 31, exporting 10 cubic yards or more requires a Soil Exportation Permit from the Division of Engineering. Removing less than 10 cubic yards does not require a soil permit. Requires topographical survey with cut/fill calculations by NJ licensed surveyor/engineer, soil erosion certification, designated truck haul routes, and filing fees/restoration bonds.",
        "fee_info": "Standard municipal soil exportation fee schedule",
        "target_desk": "Division of Engineering, Municipal Complex, 100 Municipal Blvd, Edison, NJ 08817"
    },
    {
        "id": "edison_sewer_connection",
        "title": "Sewer Connection Charge Application",
        "department": "engineering",
        "document_type": "Application form",
        "service_or_permit_name": "Sewer Connection Allocation & Lateral Tap Permit",
        "service": "sewer_connection",
        "visibility": "public",
        "verification_status": "verified",
        "original_url": "https://www.edisonnj.org/Sewer%20Connection%20Charge%20Applications.pdf",
        "local_filename": "Sewer_Connection_Charge_Applications.pdf",
        "workflow_id": "sewer_connection_flow",
        "official_summary": "Application for municipal sanitary sewer main tap-in, fixture unit allocation, and connection charge calculations for new dwellings or commercial developments. Requires civil engineering utility connection plan.",
        "fee_info": "Calculated by total fixture units per municipal rate schedule",
        "target_desk": "Edison Sewer Utility Division / Division of Engineering, Municipal Complex, 100 Municipal Blvd, Edison, NJ 08817 (sewer@edisonnj.gov)"
    },
    {
        "id": "edison_site_improvement_app",
        "title": "Site Improvement Permit with Checklist",
        "department": "engineering",
        "document_type": "Application form",
        "service_or_permit_name": "Site Improvement Permit / Waiver",
        "service": "site_improvement",
        "visibility": "public",
        "verification_status": "verified",
        "original_url": "https://www.edisonnj.org/document_center/SIP%20Applicationa.pdf",
        "local_filename": "SIP_Application.pdf",
        "workflow_id": "site_improvement_flow",
        "official_summary": "Official Edison Township Site Improvement Permit Application and 25-point engineering checklist for site improvements, property improvements, ground disturbance exceeding 1,250 sq.ft., or new impervious coverage exceeding 500 sq.ft. Requires two (2) signed and sealed engineering site plans, stormwater runoff management, and review fees.",
        "fee_info": "Engineering review fee plus 5% construction cost inspection escrow",
        "target_desk": "Division of Engineering, Municipal Complex, 100 Municipal Blvd, Edison, NJ 08817"
    },
    {
        "id": "edison_soil_import_app",
        "title": "Soil Importation Permit Application",
        "department": "engineering",
        "document_type": "Application form",
        "service_or_permit_name": "Soil Importation Permit",
        "service": "soil_import",
        "visibility": "public",
        "verification_status": "verified",
        "original_url": "https://www.edisonnj.org/document_center/Forms_Soil_Importation_Appl.pdf",
        "local_filename": "Forms_Soil_Importation_Appl.pdf",
        "workflow_id": "soil_import_export_flow",
        "official_summary": "Official Edison Township municipal application and guidelines for how to import soil, bringing soil, topsoil, or clean fill onto residential or commercial properties in Edison Township. Under Chapter 31, importing 10 cubic yards or more requires a Soil Importation Permit from the Division of Engineering. Importing less than 10 cubic yards does not require a soil permit. Requires certified clean fill lab analysis, property survey with proposed grading, and designated truck haul route.",
        "fee_info": "$50.00 application fee plus engineering escrow for 10+ cu. yds",
        "target_desk": "Division of Engineering, Municipal Complex, 100 Municipal Blvd, Edison, NJ 08817"
    },
    {
        "id": "edison_tree_removal_app",
        "title": "Tree Removal Permit Application",
        "department": "engineering",
        "document_type": "Application form",
        "service_or_permit_name": "Tree Removal Permit Procedure",
        "service": "tree_removal",
        "visibility": "public",
        "verification_status": "verified",
        "original_url": "https://www.edisonnj.org/document_center/3.23.21%20tree%20permit%20application.pdf?t=202409111411050",
        "local_filename": "3.23.21 tree permit application.pdf",
        "workflow_id": "tree_removal_flow",
        "official_summary": "Official Township of Edison municipal application for tree removal, replacement, and conservation permits under Chapter 25 of the Edison Township Code. Requires property sketch showing tree location and diameter, contractor details, and $25 review fee ($200 with board approval, waived for senior citizens aged 62+). Emergency removals permitted with photo proof or certified arborist letter submitted concurrently.",
        "fee_info": "$25 standard residential review fee (waived for senior citizens aged 62+); $200 with board approval",
        "target_desk": "Division of Engineering, Municipal Complex, 100 Municipal Blvd, Edison, NJ 08817"
    },

    # --- OTHER MUNICIPAL TOWNSHIP DEPARTMENTS (DPW, ZONING, PLANNING) ---
    {
        "id": "edison_road_opening",
        "title": "Township of Edison Street Opening Application",
        "department": "public_works",
        "document_type": "Permit form",
        "service_or_permit_name": "Street Opening Application",
        "service": "road_opening",
        "visibility": "public",
        "verification_status": "verified",
        "original_url": "https://www.edisonnj.org/document_center/RoadOpenApp.pdf?t=202409111411520",
        "local_filename": "RoadOpenApp.pdf",
        "workflow_id": "street_opening_flow",
        "official_summary": "Official Township of Edison Street Opening Application from the Department of Public Works. Permit application for pavement saw-cutting, utility trenching, sidewalk/curb excavation in public right-of-way. Requires NJ 811 One-Call ticket, $5,000 restoration guarantee bond, and traffic safety detour plan if blocking lanes. Submit to Department of Public Works, 100 Municipal Blvd.",
        "fee_info": "$150.00 filing fee + $5,000.00 refundable restoration guarantee bond",
        "target_desk": "Department of Public Works, 100 Municipal Blvd, Edison, NJ 08817 (dpw@edisonnj.gov)"
    },
    {
        "id": "edison_zoning_permit_req",
        "title": "Edison Township Zoning Permit Requirement Sheet",
        "department": "zoning",
        "document_type": "Procedure/guideline",
        "service_or_permit_name": "Residential Construction & Zoning Permit",
        "service": "zoning",
        "visibility": "public",
        "verification_status": "verified",
        "original_url": "https://www.edisonnj.org/document_center/ZONING%20PERMIT%20REQUIREMENT%20SHEET.pdf",
        "local_filename": "ZONING_PERMIT_REQUIREMENT_SHEET.pdf",
        "workflow_id": "residential_zoning_permit_flow",
        "official_summary": "Mandatory survey, plot plan scale (1\"=20' or 1\"=30'), and setback requirements for residential additions, new dwellings, detached garages, sheds over 100 sq.ft., swimming pools, and decks. Submit to Division of Zoning, 100 Municipal Blvd, Edison, NJ 08817.",
        "fee_info": "$50 - $200 review fee",
        "target_desk": "Division of Zoning, Municipal Complex, 100 Municipal Blvd, Edison, NJ 08817 (zoning@edisonnj.gov)"
    },
    {
        "id": "edison_zoning_app",
        "title": "Township of Edison Official Zoning Permit Application Form",
        "department": "zoning",
        "document_type": "Application form",
        "service_or_permit_name": "Residential Construction & Zoning Permit",
        "service": "zoning",
        "visibility": "public",
        "verification_status": "verified",
        "original_url": "https://www.edisonnj.org/document_center/Zoning%20ApplicationNEW.pdf",
        "local_filename": "Zoning_Permit_Application_Edison.pdf",
        "workflow_id": "residential_zoning_permit_flow",
        "official_summary": "Official standardized municipal permit application for single-family residential dwellings, additions, sheds, pools, decks, fences (>6ft), and commercial site changes. Requires 2 copies of signed/sealed survey.",
        "fee_info": "$50 (fences/sheds) - $75 (decks/above-ground pools) - $100 (additions) - $200 (new dwellings)",
        "target_desk": "Division of Zoning, Municipal Complex, 100 Municipal Blvd, Edison, NJ 08817 (zoning@edisonnj.gov)"
    },
    {
        "id": "edison_zoning_fees_2022",
        "title": "Edison Township Zoning Permit Fee Schedule (Ordinance O.2158)",
        "department": "zoning",
        "document_type": "Fee schedule",
        "service_or_permit_name": "Zoning Fee Schedule & Escrow Regulations",
        "service": "zoning",
        "visibility": "public",
        "verification_status": "verified",
        "original_url": "https://www.edisonnj.org/Departments/Engineering%20Department/Zoning%20Board/Zoning%20Permit%20Fees%202022.pdf",
        "local_filename": "Zoning_Permit_Fees_2022.pdf",
        "workflow_id": "residential_zoning_permit_flow",
        "official_summary": "Municipal schedule of zoning review fees adopted under Ordinance O.2158: Fences: $50.00; Sheds (< 200 sq.ft.): $50.00; Sheds (> 200 sq.ft.): $100.00; Swimming Pools (Above-Ground): $75.00; In-Ground Pools: $150.00; Residential Addition/Alteration: $100.00; New Single-Family Dwelling: $200.00; Open Deck: $75.00; Commercial Site Plan Review: $500.00 base.",
        "fee_info": "Standard municipal fee schedule",
        "target_desk": "Division of Zoning / Engineering Intake Counter, 100 Municipal Blvd, Edison, NJ 08817"
    },
    {
        "id": "edison_pool_setbacks",
        "title": "Edison Township Swimming Pool Setback & Enclosure Regulations",
        "department": "zoning",
        "document_type": "Procedure/guideline",
        "service_or_permit_name": "Residential Construction & Zoning Permit",
        "service": "zoning",
        "visibility": "public",
        "verification_status": "verified",
        "original_url": "https://www.edisonnj.org/document_center/Pool%20Setbacks.pdf",
        "local_filename": "Pool_Setbacks.pdf",
        "workflow_id": "residential_zoning_permit_flow",
        "official_summary": "Zoning rules for private swimming pools: Minimum rear and side setbacks buffer from property lines, mandatory 4-foot minimum barrier enclosure fence with self-closing and self-latching gate, and electrical safety clearance.",
        "fee_info": "$75 above-ground / $150 in-ground",
        "target_desk": "Division of Zoning, 100 Municipal Blvd, Edison, NJ 08817"
    },
    {
        "id": "edison_deck_coverage",
        "title": "Edison Township Deck Coverage & Rear Yard Setback Regulation Sheet",
        "department": "zoning",
        "document_type": "Procedure/guideline",
        "service_or_permit_name": "Residential Construction & Zoning Permit",
        "service": "zoning",
        "visibility": "public",
        "verification_status": "verified",
        "original_url": "https://www.edisonnj.org/document_center/DECK%20COVERAGE%20(2021).pdf",
        "local_filename": "Deck_Coverage.pdf",
        "workflow_id": "residential_zoning_permit_flow",
        "official_summary": "Open, unenclosed residential decks may project into required rear yards provided a minimum 15-foot rear yard setback is maintained in R-A, R-B, and R-C zones. Deck area counts toward total parcel maximum impervious lot coverage limits.",
        "fee_info": "$75.00 residential review fee",
        "target_desk": "Division of Zoning, 100 Municipal Blvd, Edison, NJ 08817"
    },
    {
        "id": "edison_schedule_a_yard",
        "title": "Edison Township Schedule A: Yard & Bulk Zoning Requirements",
        "department": "zoning",
        "document_type": "Procedure/guideline",
        "service_or_permit_name": "Residential Construction & Zoning Permit",
        "service": "zoning",
        "visibility": "public",
        "verification_status": "verified",
        "original_url": "https://www.edisonnj.org/document_center/Schedule%20A%20Yard%20Requirements.pdf",
        "local_filename": "Schedule_A_Yard_Requirements.pdf",
        "workflow_id": "residential_zoning_permit_flow",
        "official_summary": "Comprehensive municipal yard and bulk dimensional table for Edison residential zones (R-A, R-B, R-C, R-D): Front setback, side yard minimum, combined side yard, rear setback, maximum lot coverage percentage, and maximum building height (35 ft / 2.5 stories).",
        "fee_info": "Reference standard",
        "target_desk": "Division of Zoning, 100 Municipal Blvd, Edison, NJ 08817"
    },
    {
        "id": "edison_minor_subdivision",
        "title": "Township of Edison Minor Subdivision Application Packet",
        "department": "planning_zoning",
        "document_type": "Application packet",
        "service_or_permit_name": "Planning & Zoning Board Land Development",
        "service": "planning_zoning",
        "visibility": "public",
        "verification_status": "verified",
        "original_url": "https://www.edisonnj.org/Departments/Engineering%20Department/Zoning%20Board/2024%20MINOR%20SUBDIVISION%20APP%20PACKET.pdf",
        "local_filename": "Minor_Subdivision_Packet_2024.pdf",
        "workflow_id": None,
        "official_summary": "Official application packet for dividing a residential property into 3 or fewer lots without new street creation. Requires boundary surveys, certified tax payment certification, 200-foot property owners notice list, and engineering escrow deposit.",
        "fee_info": "$500 base filing fee + $1,500 escrow deposit",
        "target_desk": "Planning Board / Zoning Board Secretary, 100 Municipal Blvd, Edison, NJ 08817"
    },
    {
        "id": "edison_document_center_index",
        "title": "Township of Edison Official Document Center & Forms Repository",
        "department": "engineering",
        "document_type": "Other official information",
        "service_or_permit_name": "Municipal Records & Applications Index",
        "service": "document_center",
        "visibility": "public",
        "verification_status": "verified",
        "original_url": "https://www.edisonnj.org/document_center/index.php",
        "local_filename": None,
        "workflow_id": None,
        "official_summary": "Centralized municipal public repository for Edison Township, New Jersey. Provides official forms and applications for Engineering, Zoning, Public Works, Health, Township Clerk, and Code Enforcement. Documents must be submitted as unaltered official forms to the Municipal Complex (100 Municipal Blvd, Edison, NJ 08817).",
        "fee_info": "Free public portal",
        "target_desk": "Edison Municipal Complex, 100 Municipal Blvd, Edison, NJ 08817"
    }
]

def extract_text_from_pdf(pdf_path: Path, page_number: Optional[int] = None) -> Tuple[str, int, str]:
    """
    Extracts text from PDF using pypdf.
    If page_number is specified (1-indexed), extracts only that page.
    Returns: (text, page_count, extraction_status)
    """
    try:
        reader = pypdf.PdfReader(str(pdf_path))
        num_pages = len(reader.pages)
        full_text = []
        if page_number and 1 <= page_number <= num_pages:
            p_text = reader.pages[page_number - 1].extract_text() or ""
            if p_text.strip():
                full_text.append(f"[Page {page_number}]\n{p_text.strip()}")
        else:
            for idx, page in enumerate(reader.pages):
                page_text = page.extract_text() or ""
                if page_text.strip():
                    full_text.append(f"[Page {idx+1}]\n{page_text.strip()}")
        
        extracted_content = "\n\n".join(full_text).strip()
        
        if len(extracted_content) > 30:
            return extracted_content, num_pages, "extracted"
        else:
            return "", num_pages, "scanned_pdf_needs_ocr"
    except Exception as e:
        logger.error(f"Error extracting text from {pdf_path}: {e}")
        return "", 0, "extraction_error"

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE_WORDS, overlap: int = CHUNK_OVERLAP_WORDS) -> List[str]:
    """Splits text into chunks with word overlap."""
    words = text.split()
    if not words:
        return []
    if len(words) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk_words = words[start:end]
        chunks.append(" ".join(chunk_words))
        if end >= len(words):
            break
        start += (chunk_size - overlap)

    return chunks

def run_ingestion_and_inventory(
    departments_dir: Path = DEPARTMENTS_DIR,
    crawl_live: bool = False,
) -> Dict:
    """
    Runs safe, non-destructive official document discovery, PDF extraction,
    provenance-preserving versioned indexing, and inventory generation.
    Never wipes the existing active knowledge base prior to validation.
    """
    logger.info("Starting Edison Township Official Document Ingestion Pipeline (Non-Destructive)...")
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    engineering_dir = Path(departments_dir) / "engineering"
    engineering_forms_dir = engineering_dir / "forms"

    # Load configured root URL from departments/engineering/config.json if available
    cfg_path = engineering_dir / "config.json"
    client_id = "edison_nj"
    root_url = TRUSTED_ROOT_URL
    if cfg_path.exists():
        try:
            cfg_data = json.loads(cfg_path.read_text(encoding="utf-8"))
            ts = cfg_data.get("trusted_sources", {}) or {}
            client_id = ts.get("client_id", client_id)
            root_url = ts.get("root_url", root_url)
        except Exception as exc:
            logger.warning(f"Failed to read trusted_sources from {cfg_path}: {exc}")

    trusted_source_registry.seed_from_config(
        department_id="engineering",
        root_url=root_url,
        client_id=client_id,
        seed_urls=[
            {
                "url": item["original_url"],
                "source_type": "pdf" if ".pdf" in item["original_url"].lower() else "html",
                "referring_url": root_url,
                "discovered_via": "admin_seed_catalog",
            }
            for item in EDISON_OFFICIAL_CATALOG
        ],
    )

    store = shared_vector_store
    active_versions = store.get_active_document_versions("engineering")

    inventory_items = []
    total_chunks_indexed = 0
    extracted_count = 0
    scanned_count = 0
    web_count = 0
    unchanged_count = 0

    for item in EDISON_OFFICIAL_CATALOG:
        doc_id = item["id"]
        title = item["title"]
        dept = item["department"]
        doc_type = item["document_type"]
        service_name = item["service_or_permit_name"]
        url = item["original_url"]
        local_filename = item.get("local_filename")
        official_summary = item.get("official_summary", "")
        fee_info = item.get("fee_info", "")
        target_desk = item.get("target_desk", "")

        local_path = None
        file_size_bytes = None
        page_count = 0
        extracted_text = ""
        page_entries: List[Tuple[Optional[int], str]] = []
        extraction_status = "web_scraped"
        needs_manual_verification = False
        source_type = "pdf" if ".pdf" in url.lower() or local_filename else "html"
        content_type = "application/pdf" if source_type == "pdf" else "text/html"

        if local_filename:
            file_path = engineering_forms_dir / local_filename
            if file_path.exists():
                local_path = f"departments/engineering/forms/{local_filename}"
                file_size_bytes = file_path.stat().st_size
                target_page = item.get("page_number")
                pdf_res = extract_pdf_pages(file_path, enable_ocr=True)
                page_count = pdf_res.total_pages
                extraction_status = pdf_res.extraction_status

                if target_page and 1 <= target_page <= page_count:
                    matched_pages = [(p, t) for p, t in pdf_res.pages if p == target_page]
                    page_entries = matched_pages
                    extracted_text = "\n\n".join(f"[Page {p}]\n{t}" for p, t in matched_pages).strip()
                    if len(extracted_text) > 30 and extraction_status == "scanned_pdf_needs_ocr":
                        extraction_status = "extracted"
                else:
                    page_entries = list(pdf_res.pages)
                    extracted_text = "\n\n".join(f"[Page {p}]\n{t}" for p, t in pdf_res.pages).strip()

                if extraction_status in ("extracted", "ocr_extracted"):
                    extracted_count += 1
                elif extraction_status == "scanned_pdf_needs_ocr":
                    scanned_count += 1
                    needs_manual_verification = True
                    logger.warning(f"Document '{local_filename}' is a scanned PDF image; flagged for manual verification / OCR.")
            else:
                extraction_status = "pending_download"
                needs_manual_verification = True
        else:
            web_count += 1
            extraction_status = "web_scraped"

        # Build comprehensive textual corpus for RAG indexing
        meta_header = "\n\n".join([
            f"DOCUMENT: {title}",
            f"MUNICIPALITY: {MUNICIPALITY_NAME}",
            f"DEPARTMENT: {dept.capitalize()} & Zoning",
            f"DOCUMENT TYPE: {doc_type}",
            f"SERVICE: {service_name}",
            f"OFFICIAL URL: {url}",
            f"SUBMISSION INTAKE: {target_desk}",
            f"FEE STRUCTURE: {fee_info}",
            f"OFFICIAL SUMMARY: {official_summary}"
        ])

        doc_hash_input = f"{meta_header}\n{extracted_text}".encode("utf-8")
        content_hash = hashlib.sha256(doc_hash_input).hexdigest()

        prev_info = active_versions.get(doc_id)
        if prev_info and prev_info.get("content_hash") == content_hash:
            unchanged_count += 1
            doc_version = prev_info.get("version_id", 1)
        else:
            doc_version = (prev_info.get("version_id", 0) + 1) if prev_info else 1
            url_hash = hashlib.md5(canonicalize_url_for_dedup(url).encode("utf-8")).hexdigest()[:8]
            doc_chunks: List[Dict] = []

            if page_entries:
                # Index summary header on page 1 + page-attributed PDF chunks
                intro_chunks = chunk_text(meta_header)
                chunk_idx = 0
                for c_txt in intro_chunks:
                    doc_chunks.append({
                        "id": f"{dept}_{url_hash}_v{doc_version}_{chunk_idx}",
                        "client_id": client_id,
                        "department_id": dept,
                        "document_id": doc_id,
                        "url": url,
                        "referring_url": root_url,
                        "title": title,
                        "category": doc_type,
                        "content_type": content_type,
                        "source_type": source_type,
                        "pdf_page_number": item.get("page_number") or 1,
                        "chunk_index": chunk_idx,
                        "content": c_txt,
                        "word_count": len(c_txt.split()),
                        "retrieval_date": now_iso,
                        "last_modified": None,
                        "etag": None,
                        "content_hash": content_hash,
                        "is_active": True,
                        "version_id": doc_version,
                        "visibility": item.get("visibility", "public"),
                        "document_type": doc_type,
                        "service": item.get("service", service_name),
                        "verification_status": item.get("verification_status", "verified"),
                    })
                    chunk_idx += 1

                for page_num, p_text in page_entries:
                    for c_txt in chunk_text(f"[Page {page_num}] {p_text}"):
                        doc_chunks.append({
                            "id": f"{dept}_{url_hash}_v{doc_version}_{chunk_idx}",
                            "client_id": client_id,
                            "department_id": dept,
                            "document_id": doc_id,
                            "url": url,
                            "referring_url": root_url,
                            "title": title,
                            "category": doc_type,
                            "content_type": content_type,
                            "source_type": source_type,
                            "pdf_page_number": page_num,
                            "chunk_index": chunk_idx,
                            "content": c_txt,
                            "word_count": len(c_txt.split()),
                            "retrieval_date": now_iso,
                            "last_modified": None,
                            "etag": None,
                            "content_hash": content_hash,
                            "is_active": True,
                            "version_id": doc_version,
                            "visibility": item.get("visibility", "public"),
                            "document_type": doc_type,
                            "service": item.get("service", service_name),
                            "verification_status": item.get("verification_status", "verified"),
                        })
                        chunk_idx += 1
            else:
                for idx, c_txt in enumerate(chunk_text(meta_header)):
                    doc_chunks.append({
                        "id": f"{dept}_{url_hash}_v{doc_version}_{idx}",
                        "client_id": client_id,
                        "department_id": dept,
                        "document_id": doc_id,
                        "url": url,
                        "referring_url": root_url,
                        "title": title,
                        "category": doc_type,
                        "content_type": content_type,
                        "source_type": source_type,
                        "pdf_page_number": item.get("page_number"),
                        "chunk_index": idx,
                        "content": c_txt,
                        "word_count": len(c_txt.split()),
                        "retrieval_date": now_iso,
                        "last_modified": None,
                        "etag": None,
                        "content_hash": content_hash,
                        "is_active": True,
                        "version_id": doc_version,
                        "visibility": item.get("visibility", "public"),
                        "document_type": doc_type,
                        "service": item.get("service", service_name),
                        "verification_status": item.get("verification_status", "verified"),
                    })

            if doc_chunks:
                store.stage_and_activate_document_chunks(
                    department_id=dept,
                    document_id=doc_id,
                    chunks=doc_chunks,
                    new_version_id=doc_version,
                )
                total_chunks_indexed += len(doc_chunks)
                trusted_source_registry.record_discovered_source(
                    department_id=dept,
                    url=url,
                    source_type=source_type,
                    referring_url=root_url,
                    discovered_via="admin_seed_catalog",
                    client_id=client_id,
                    content_hash=content_hash,
                    active_version_id=doc_version,
                )

        inventory_record = {
            "id": doc_id,
            "client_id": client_id,
            "title": title,
            "department": dept,
            "document_type": doc_type,
            "service_or_permit_name": service_name,
            "service": item.get("service", service_name),
            "visibility": item.get("visibility", "public"),
            "verification_status": item.get("verification_status", "verified"),
            "original_url": url,
            "referring_url": root_url,
            "source_type": source_type,
            "content_type": content_type,
            "content_hash": content_hash,
            "version_id": doc_version,
            "is_active": True,
            "local_path": local_path,
            "local_filename": local_filename,
            "workflow_id": item.get("workflow_id"),
            "extraction_status": extraction_status,
            "needs_manual_verification": needs_manual_verification,
            "last_fetched": now_iso,
            "file_size_bytes": file_size_bytes,
            "page_count": page_count,
            "extracted_characters": len(extracted_text),
            "fee_summary": fee_info,
            "submission_desk": target_desk,
            "official_summary": official_summary
        }
        inventory_items.append(inventory_record)

    # Write departments/engineering/document_inventory.json atomically
    inventory_file = engineering_dir / "document_inventory.json"
    inventory_data = {
        "municipality": MUNICIPALITY_NAME,
        "official_source": root_url,
        "generated_at": now_iso,
        "total_documents": len(inventory_items),
        "extracted_text_count": extracted_count,
        "scanned_pdf_needs_ocr_count": scanned_count,
        "web_indexed_count": web_count,
        "unchanged_documents": unchanged_count,
        "documents": inventory_items
    }
    tmp_inv = inventory_file.with_suffix(".json.tmp")
    with open(tmp_inv, "w", encoding="utf-8") as f:
        json.dump(inventory_data, f, indent=2)
    tmp_inv.replace(inventory_file)
    logger.info(f"Saved document inventory ({len(inventory_items)} records) to {inventory_file}")

    crawl_report = None
    if crawl_live:
        try:
            from backend.scripts.incremental_ingest import run_incremental_ingestion
        except ImportError:
            from scripts.incremental_ingest import run_incremental_ingestion
        crawl_report = run_incremental_ingestion(department_id="engineering", departments_dir=departments_dir, store=store)

    stats = store.get_stats()
    logger.info(
        f"Non-destructive ingestion finished: {total_chunks_indexed} new/updated chunks, "
        f"{unchanged_count} unchanged docs, total active chunks={stats.get('total_chunks', 0)}."
    )

    return {
        "status": "success",
        "inventory_file": str(inventory_file),
        "total_documents": len(inventory_items),
        "extracted_count": extracted_count,
        "scanned_count": scanned_count,
        "unchanged_count": unchanged_count,
        "chunks_indexed": total_chunks_indexed,
        "total_active_chunks": stats.get("total_chunks", 0),
        "vector_backend": stats.get("backend"),
        "crawl_report": crawl_report,
    }

if __name__ == "__main__":
    result = run_ingestion_and_inventory()
    print("\n" + "="*65)
    print("EDISON TOWNSHIP OFFICIAL DOCUMENT INGESTION COMPLETE")
    print("="*65)
    print(f"Total Official Documents Processed : {result['total_documents']}")
    print(f"Extracted Text PDFs                : {result['extracted_count']}")
    print(f"Scanned PDFs (Needs OCR Flagged)   : {result['scanned_count']}")
    print(f"Total Chunks In Vector Store       : {result['chunks_indexed']}")
    print(f"Active Vector Database Backend     : {result['vector_backend']}")
    print(f"Inventory Written To               : {result['inventory_file']}")
    print("="*65 + "\n")
