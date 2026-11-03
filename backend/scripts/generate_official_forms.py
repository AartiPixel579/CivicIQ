"""
Official Municipal PDF Form Generator for City of Pixelvyne
Creates authentic, high-fidelity standardized government PDF documents
stored in /departments/<dept>/forms/ for deterministic citizen delivery.
"""

import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.graphics.shapes import Drawing, Rect, Circle, String

def create_seal_banner(canvas, doc):
    """Draws an official municipal header banner on the PDF canvas."""
    canvas.saveState()
    # Header bar
    canvas.setFillColor(colors.HexColor("#1e3a8a")) # Deep municipal navy
    canvas.rect(0, 10.5 * 72, 8.5 * 72, 0.5 * 72, fill=True, stroke=False)
    
    # Official Seal / Text
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawString(36, 10.65 * 72, "MUNICIPALITY OF PIXELVYNE  •  OFFICIAL GOVERNMENT RECORD")
    canvas.drawRightString(8.5 * 72 - 36, 10.65 * 72, "VERIFIED DOCUMENT PORTAL")
    
    # Footer bar
    canvas.setFillColor(colors.HexColor("#f1f5f9"))
    canvas.rect(0, 0, 8.5 * 72, 36, fill=True, stroke=False)
    canvas.setFillColor(colors.HexColor("#475569"))
    canvas.setFont("Helvetica", 8)
    canvas.drawString(36, 14, "City of Pixelvyne • Office of Municipal Records • 100 Civic Center Blvd • portal.pixelvyne.gov")
    canvas.drawRightString(8.5 * 72 - 36, 14, f"Page {doc.page} of Standard Document")
    canvas.restoreState()

def build_pdf_form(filepath, doc_code, title, dept_name, revision, sections, checklist_items, submission_info):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    doc = SimpleDocTemplate(
        filepath,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=54,
        bottomMargin=48
    )

    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=15,
        leading=18,
        textColor=colors.HexColor('#0f172a'),
        alignment=1, # Center
        spaceAfter=4
    )
    
    dept_style = ParagraphStyle(
        'DocDept',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=13,
        textColor=colors.HexColor('#1e40af'),
        alignment=1,
        spaceAfter=2
    )

    code_style = ParagraphStyle(
        'DocCode',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=11,
        textColor=colors.HexColor('#64748b'),
        alignment=1,
        spaceAfter=12
    )

    section_heading = ParagraphStyle(
        'SecHeading',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=13,
        textColor=colors.HexColor('#1e3a8a'),
        spaceBefore=8,
        spaceAfter=4
    )

    body_style = ParagraphStyle(
        'BodyDark',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#334155')
    )

    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=10,
        textColor=colors.HexColor('#1e293b')
    )

    story = []

    # Title block
    story.append(Paragraph(f"<b>{title.upper()}</b>", title_style))
    story.append(Paragraph(f"DEPARTMENT OF {dept_name.upper()}", dept_style))
    story.append(Paragraph(f"DOCUMENT IDENTIFIER: <b>{doc_code}</b> | {revision}", code_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#cbd5e1'), spaceBefore=2, spaceAfter=8))

    # Official Notice Box
    notice_text = (
        f"<b>OFFICIAL NOTICE:</b> This is an official standardized municipal application issued by the City of Pixelvyne. "
        f"All information provided is subject to verification under Municipal Code Chapter 4. "
        f"Incomplete applications or omitted attachments will result in immediate rejection at counter intake."
    )
    notice_data = [[Paragraph(notice_text, body_style)]]
    notice_table = Table(notice_data, colWidths=[7.5 * inch])
    notice_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#eff6ff')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#93c5fd')),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(notice_table)
    story.append(Spacer(1, 8))

    # Render structured sections
    for sec in sections:
        story.append(Paragraph(f"<b>{sec['title']}</b>", section_heading))
        table_rows = []
        for row in sec['rows']:
            formatted_row = [
                Paragraph(f"<b>{cell['label']}:</b><br/>{cell.get('value', '____________________')}", body_style)
                for cell in row
            ]
            table_rows.append(formatted_row)
        
        # Calculate col widths evenly
        num_cols = len(sec['rows'][0]) if sec['rows'] else 1
        col_w = (7.5 * inch) / num_cols
        sec_table = Table(table_rows, colWidths=[col_w] * num_cols)
        sec_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
            ('BOX', (0,0), (-1,-1), 0.75, colors.HexColor('#cbd5e1')),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ('LEFTPADDING', (0,0), (-1,-1), 6),
            ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(sec_table)
        story.append(Spacer(1, 6))

    # Mandatory Attachments Checklist Section
    story.append(Paragraph("<b>SECTION: MANDATORY ATTACHMENTS CHECKLIST (SUBMIT WITH FORM)</b>", section_heading))
    checklist_rows = [
        [
            Paragraph("<b>CHECK</b>", table_header_style),
            Paragraph("<b>REQUIRED ATTACHMENT / DOCUMENT</b>", table_header_style),
            Paragraph("<b>MUNICIPAL COMPLIANCE STANDARD</b>", table_header_style)
        ]
    ]
    for item in checklist_items:
        checklist_rows.append([
            Paragraph("[  ]", body_style),
            Paragraph(f"<b>{item['name']}</b>", body_style),
            Paragraph(item['standard'], body_style)
        ])
    
    chk_table = Table(checklist_rows, colWidths=[0.6 * inch, 3.8 * inch, 3.1 * inch])
    chk_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#e2e8f0')),
        ('BOX', (0,0), (-1,-1), 0.75, colors.HexColor('#94a3b8')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 5),
        ('RIGHTPADDING', (0,0), (-1,-1), 5),
        ('ALIGN', (0,0), (0,-1), 'CENTER'),
    ]))
    story.append(chk_table)
    story.append(Spacer(1, 8))

    # Submission & Routing Panel
    story.append(Paragraph("<b>DEPARTMENTAL SUBMISSION & INTAKE ROUTING INSTRUCTIONS</b>", section_heading))
    sub_text = (
        f"<b>TARGET INTAKE COUNTER:</b> {submission_info['desk']}<br/>"
        f"<b>PHYSICAL ADDRESS:</b> {submission_info['address']}<br/>"
        f"<b>OFFICIAL INTAKE HOURS:</b> {submission_info['hours']}<br/>"
        f"<b>TELEPHONE CONTACT:</b> {submission_info['phone']} | <b>EMAIL:</b> {submission_info['email']}<br/>"
        f"<b>PROCESSING TIMEFRAME:</b> {submission_info['turnaround']} (Expedited processing requires Division Chief sign-off)"
    )
    sub_table = Table([[Paragraph(sub_text, body_style)]], colWidths=[7.5 * inch])
    sub_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f0fdf4')), # Subtle official green
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#86efac')),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(sub_table)
    story.append(Spacer(1, 8))

    # Legal Oath / Signature Block
    sig_text = (
        "I hereby certify under penalty of perjury that all statements made in this application are true and correct "
        "to the best of my knowledge, and that I have verified compliance with all applicable municipal zoning and building codes."
    )
    story.append(Paragraph(sig_text, ParagraphStyle('SigNotice', parent=body_style, fontSize=7.5, leading=10, textColor=colors.HexColor('#64748b'))))
    story.append(Spacer(1, 6))

    sig_data = [
        [
            Paragraph("<b>Applicant / Owner Signature:</b><br/><br/>________________________________________", body_style),
            Paragraph("<b>Date of Execution:</b><br/><br/>______ / ______ / 2026", body_style),
            Paragraph("<b>Official Intake Stamp (Municipal Use Only):</b><br/>[ RECEIVED STAMP HERE ]", body_style)
        ]
    ]
    sig_table = Table(sig_data, colWidths=[3.2 * inch, 1.8 * inch, 2.5 * inch])
    sig_table.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(sig_table)

    # Build document with page template header & footer
    doc.build(story, onFirstPage=create_seal_banner, onLaterPages=create_seal_banner)
    print(f"Generated official PDF: {filepath}")

def generate_all_forms():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "departments"))

    # 1. Engineering: Form ENG-204
    eng_forms_dir = os.path.join(base_dir, "engineering", "forms")
    build_pdf_form(
        filepath=os.path.join(eng_forms_dir, "ENG-204_Residential_Permit_Application.pdf"),
        doc_code="FORM ENG-204",
        title="Municipal Residential Building & Excavation Permit Application",
        dept_name="Engineering & Public Works",
        revision="Revision 2026.1 (Effective Jan 1, 2026)",
        sections=[
            {
                "title": "SECTION A: APPLICANT & TITLEHOLDER IDENTIFICATION",
                "rows": [
                    [{"label": "Full Legal Name of Property Owner", "value": "John / Jane Citizen"}, {"label": "Daytime Contact Phone", "value": "(555) 012-3456"}],
                    [{"label": "Owner Mailing Address", "value": "123 Elmwood Street, Pixelvyne, PV 94016"}, {"label": "Contact Email", "value": "citizen@pixelvyne-email.org"}],
                ]
            },
            {
                "title": "SECTION B: SUBJECT PROPERTY & PARCEL DETAILS",
                "rows": [
                    [{"label": "Construction Site Street Address", "value": "452 Maple Ridge Road"}, {"label": "Parcel Tax Assessor ID (PIN)", "value": "PV-08-449-0129"}],
                    [{"label": "Zoning Classification", "value": "Residential R-1 (Low-Density)"}, {"label": "Lot Dimensions & Total Area", "value": "75 ft x 140 ft (10,500 sq.ft.)"}],
                    [{"label": "Existing Setbacks (Front / Rear / Side)", "value": "Front: 28 ft | Rear: 22 ft | Sides: 8 ft / 9 ft"}, {"label": "Easement Disclosures", "value": "Standard 5ft municipal drainage rear easement"}]
                ]
            },
            {
                "title": "SECTION C: CONTRACTOR / ARCHITECT CREDENTIALS",
                "rows": [
                    [{"label": "General Contractor Business Name", "value": "Apex Municipal Construction LLC"}, {"label": "State GC License Number", "value": "PV-GC-99210-A"}],
                    [{"label": "Architect / Civil PE License Number", "value": "PE-55019"}, {"label": "Liability Insurance Carrier & Policy #", "value": "Hartford Underwriters #POL-88402"}],
                ]
            },
            {
                "title": "SECTION D: SCOPE OF CONSTRUCTION WORK & VALUATION",
                "rows": [
                    [{"label": "Description of Work", "value": "Ground-floor master suite addition (450 sq.ft.) and foundation underpinning"}, {"label": "Estimated Valuation of Work", "value": "$85,000.00"}],
                    [{"label": "Proposed Impervious Area Addition", "value": "450 sq.ft. (Retention dry well specified)"}, {"label": "Anticipated Start / Finish Date", "value": "April 1, 2026 – August 15, 2026"}]
                ]
            }
        ],
        checklist_items=[
            {"name": "Dimensioned Site Boundary Plan (2 Sets)", "standard": "Drawn to 1/4\"=1' scale by registered surveyor or architect showing setbacks"},
            {"name": "Proof of Legal Title Ownership", "standard": "Recorded Deed copy or current County Real Property Tax Receipt"},
            {"name": "Contractor License & Insurance Certificate", "standard": "Minimum $1,000,000 general liability with City named as certificate holder"},
            {"name": "Workers' Compensation Exemption/Policy", "standard": "Form C-105.2 or State Exemption Certificate"},
            {"name": "Base Intake Fee Payment Receipt", "standard": "$250.00 non-refundable check or cashier counter receipt"}
        ],
        submission_info={
            "desk": "Counter 3, Engineering & Public Works Annex Intake",
            "address": "100 Civic Center Blvd, Ground Floor, Pixelvyne, PV 94016",
            "hours": "Monday – Friday: 8:30 AM – 4:30 PM (Drop-off closes at 4:00 PM)",
            "phone": "(555) 019-4820",
            "email": "engineering-permits@pixelvyne.gov",
            "turnaround": "5 to 10 Business Days"
        }
    )

    # 2. Engineering: Form ENG-102
    build_pdf_form(
        filepath=os.path.join(eng_forms_dir, "ENG-102_Excavation_Right_of_Way_Permit.pdf"),
        doc_code="FORM ENG-102",
        title="Municipal Right-of-Way & Street Opening Excavation Permit",
        dept_name="Engineering & Public Works",
        revision="Revision 2026.1",
        sections=[
            {
                "title": "SECTION 1: APPLICANT & UTILITY DIG INFORMATION",
                "rows": [
                    [{"label": "Contractor / Utility Entity", "value": "Highland Trenching & Utilities Inc."}, {"label": "811 Dig Ticket Confirmation #", "value": "TICKET-2026-88192-PV"}],
                    [{"label": "Excavation Location (Street & Cross)", "value": "Intersection of 4th Ave and Pine Lane"}, {"label": "Emergency 24/7 Field Phone", "value": "(555) 019-9944"}]
                ]
            },
            {
                "title": "SECTION 2: CUT SPECIFICATIONS & TRAFFIC IMPACT",
                "rows": [
                    [{"label": "Trench Dimensions (L x W x D)", "value": "35 ft Length x 3 ft Width x 6 ft Depth"}, {"label": "Pavement Cut Type", "value": "Asphalt Saw-Cut with 12\" step-back"}],
                    [{"label": "Traffic Impairment Status", "value": "Single lane detour with two certified flaggers"}, {"label": "Work Duration (Hours / Days)", "value": "48 Hours (Night work prohibited 10PM-6AM)"}]
                ]
            }
        ],
        checklist_items=[
            {"name": "Verified 811 Locate Ticket Confirmation", "standard": "Must be valid within 14 calendar days of planned excavation"},
            {"name": "Surety Restoration Deposit Bond", "standard": "$5,000.00 cashier's check or licensed surety bond"},
            {"name": "MUTCD Compliant Traffic Control Plan", "standard": "Mandatory if obstructing any lane, bike path, or pedestrian sidewalk"},
            {"name": "Commercial General Liability Insurance", "standard": "$2,000,000 aggregate policy naming City as Additional Insured"}
        ],
        submission_info={
            "desk": "Counter 4, Right-of-Way & Utilities Desk, Annex",
            "address": "100 Civic Center Blvd, Ground Floor, Pixelvyne, PV 94016",
            "hours": "Monday – Friday: 8:30 AM – 4:30 PM",
            "phone": "(555) 019-4820",
            "email": "engineering-permits@pixelvyne.gov",
            "turnaround": "3 to 5 Business Days"
        }
    )

    # 3. Healthcare: Form HLT-101
    hlt_forms_dir = os.path.join(base_dir, "healthcare", "forms")
    build_pdf_form(
        filepath=os.path.join(hlt_forms_dir, "HLT-101_Food_Establishment_License.pdf"),
        doc_code="FORM HLT-101",
        title="Commercial Food Establishment Operating License Application",
        dept_name="Healthcare, Food Safety & Sanitation",
        revision="Revision 2026 (Annual)",
        sections=[
            {
                "title": "SECTION 1: BUSINESS & ESTABLISHMENT DETAILS",
                "rows": [
                    [{"label": "Legal Entity Name", "value": "Pixelvyne Artisan Bakery LLC"}, {"label": "DBA Establishment Name", "value": "The Golden Crust Café"}],
                    [{"label": "Physical Location", "value": "512 Main Street, Suite A, Pixelvyne, PV 94022"}, {"label": "Seating Capacity", "value": "42 Seats (Category Tier 1)"}]
                ]
            },
            {
                "title": "SECTION 2: FOOD SAFETY MANAGER & SANITARY SPECS",
                "rows": [
                    [{"label": "Certified Food Protection Manager", "value": "Chef Maria Santos"}, {"label": "CFPM Certificate # & Expiration", "value": "SERV-883910 (Expires: 11/2028)"}],
                    [{"label": "Grease Interceptor Capacity & Make", "value": "Zurn 50 GPM Hydro-Mechanical Trap"}, {"label": "Dishwashing System", "value": "3-Compartment Sink + High-Temp Sanitizer Unit"}]
                ]
            }
        ],
        checklist_items=[
            {"name": "Certified Food Protection Manager Certificate", "standard": "ANSI-accredited certificate copy valid for current year"},
            {"name": "Commercial Kitchen Floor Plan Schematic", "standard": "Scale layout showing handwash sinks, 3-bay sink, prep tables, mop sink"},
            {"name": "Grease Interceptor Maintenance Agreement", "standard": "Contract with licensed waste grease hauler for quarterly pumping"},
            {"name": "Potable Water Test / Municipal Account", "standard": "Proof of municipal water or certified coliform/nitrate water lab test"},
            {"name": "Plan Review & Licensing Intake Fee", "standard": "$470.00 total cashier counter receipt"}
        ],
        submission_info={
            "desk": "Counter 7, Food & Facility Licensing Desk, Civic Health Pavilion",
            "address": "240 Wellness Parkway, 2nd Floor, Suite 210, Pixelvyne, PV 94022",
            "hours": "Monday – Thursday: 8:00 AM – 4:00 PM; Friday: 8:00 AM – 1:00 PM",
            "phone": "(555) 019-7241",
            "email": "health-licensing@pixelvyne.gov",
            "turnaround": "3 to 7 Business Days prior to pre-opening audit"
        }
    )

    # 4. Healthcare: Form HLT-202
    build_pdf_form(
        filepath=os.path.join(hlt_forms_dir, "HLT-202_Mobile_Food_Sanitation_Clearance.pdf"),
        doc_code="FORM HLT-202",
        title="Mobile Food Truck & Cart Sanitation Clearance Application",
        dept_name="Healthcare, Food Safety & Sanitation",
        revision="Revision 2026",
        sections=[
            {
                "title": "SECTION 1: MOBILE UNIT & OPERATOR DATA",
                "rows": [
                    [{"label": "Operating Business Name", "value": "Baja Taco Cruiser LLC"}, {"label": "Vehicle License Plate & VIN", "value": "PV-MBL-782 / VIN: 1FTFW1ED4KF12903"}],
                    [{"label": "Registered Commissary Depot", "value": "Pixelvyne Central Commissary, 90 Industrial Way"}, {"label": "Commissary Depot Account #", "value": "COMM-2026-041"}]
                ]
            },
            {
                "title": "SECTION 2: ON-BOARD PLUMBING & SAFETY",
                "rows": [
                    [{"label": "Potable Water Tank Capacity", "value": "35 Gallons (Minimum 30 gal required)"}, {"label": "Wastewater Tank Capacity", "value": "42 Gallons (120% of fresh water)"}],
                    [{"label": "Handwashing Sink Specs", "value": "Dedicated stainless sink with 110°F instant water heater"}, {"label": "Fire Suppression System Tag", "value": "NFPA-96 Tagged Jan 2026"}]
                ]
            }
        ],
        checklist_items=[
            {"name": "Signed Commissary Depot Agreement", "standard": "Notarized contract guaranteeing daily depot servicing and disposal"},
            {"name": "Vehicle Plumbing & Water Flow Diagram", "standard": "Showing freshwater fill, backflow prevention, and greywater drain"},
            {"name": "State Vehicle Registration & Commercial Auto", "standard": "Active registration and $1M commercial liability insurance"},
            {"name": "Fire Marshal Suppression Tag", "standard": "Current Type K fire extinguisher and hood suppression certification"}
        ],
        submission_info={
            "desk": "Counter 7, Mobile Licensing Intake, Civic Health Pavilion",
            "address": "240 Wellness Parkway, 2nd Floor, Pixelvyne, PV 94022",
            "hours": "Monday – Thursday: 8:00 AM – 4:00 PM; Friday: 8:00 AM – 1:00 PM",
            "phone": "(555) 019-7241",
            "email": "health-licensing@pixelvyne.gov",
            "turnaround": "3 to 5 Business Days"
        }
    )

if __name__ == "__main__":
    generate_all_forms()
