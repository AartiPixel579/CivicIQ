"""
Script to generate official PDFs for Edison Engineering Department:
1. Flood Zone Determination Letter Request Form (Flood_Zone_Determination_Letter_REQUEST.pdf)
2. Requirements for Plot Grading Plans - Minor Development (Requirements_for_Plot_Grading_Plans_Minor_Development.pdf)
"""

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from pathlib import Path
import shutil

forms_dir = Path("departments/engineering/forms")
forms_dir.mkdir(parents=True, exist_ok=True)

def generate_flood_zone_pdf():
    pdf_path = forms_dir / "Flood_Zone_Determination_Letter_REQUEST.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=letter)
    w, h = letter

    # Header
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(w / 2, h - 50, "TOWNSHIP OF EDISON")
    c.setFont("Helvetica", 10)
    c.drawCentredString(w / 2, h - 65, "DEPARTMENT OF PLANNING AND ENGINEERING - DIVISION OF ENGINEERING")
    c.drawCentredString(w / 2, h - 78, "100 Municipal Boulevard, Edison, NJ 08817 | Phone: (732) 248-7288")
    c.line(50, h - 88, w - 50, h - 88)

    # Title
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(w / 2, h - 110, "FLOOD ZONE DETERMINATION LETTER REQUEST")

    c.setFont("Helvetica", 9)
    intro_text = [
        "This application is used to request an official municipal Flood Zone Determination Letter from the",
        "Township of Edison Division of Engineering indicating whether a property is located in a Special Flood",
        "Hazard Area (SFHA) per FEMA Flood Insurance Rate Maps (FIRM)."
    ]
    y = h - 130
    for line in intro_text:
        c.drawString(60, y, line)
        y -= 14

    y -= 10
    c.setFont("Helvetica-Bold", 10)
    c.drawString(60, y, "1. PROPERTY INFORMATION:")
    y -= 18
    c.setFont("Helvetica", 9)
    c.drawString(70, y, "Property Street Address: _____________________________________________________________________")
    y -= 20
    c.drawString(70, y, "Tax Map Block Number: ________________________   Lot Number: _______________________________")
    y -= 20
    c.drawString(70, y, "Property Owner Name: ______________________________________________________________________")
    y -= 20
    c.drawString(70, y, "Owner Mailing Address: ____________________________________________________________________")

    y -= 15
    c.setFont("Helvetica-Bold", 10)
    c.drawString(60, y, "2. APPLICANT / CONTACT INFORMATION:")
    y -= 18
    c.setFont("Helvetica", 9)
    c.drawString(70, y, "Applicant Name / Company: _________________________________________________________________")
    y -= 20
    c.drawString(70, y, "Phone Number: _____________________________   Email: ______________________________________")
    y -= 20
    c.drawString(70, y, "Mailing Address: __________________________________________________________________________")

    y -= 15
    c.setFont("Helvetica-Bold", 10)
    c.drawString(60, y, "3. FEE INFORMATION:")
    y -= 18
    c.setFont("Helvetica", 9)
    c.drawString(70, y, "• Flood Letter Fee: $25.00 per property/tax lot (Make check payable to 'Township of Edison').")

    y -= 25
    c.setFont("Helvetica-Bold", 10)
    c.drawString(60, y, "4. SUBMISSION & SIGNATURE:")
    y -= 18
    c.setFont("Helvetica", 9)
    c.drawString(70, y, "Applicant Signature: ______________________________________   Date: ________________________")

    c.showPage()
    c.save()
    print("Created Flood_Zone_Determination_Letter_REQUEST.pdf successfully")

    # Also keep Flood_Zone_Determination_Letter.pdf in sync for backward compatibility
    legacy_path = forms_dir / "Flood_Zone_Determination_Letter.pdf"
    shutil.copyfile(pdf_path, legacy_path)
    print("Updated legacy Flood_Zone_Determination_Letter.pdf copy successfully")


def generate_plot_grading_pdf():
    pdf_path = forms_dir / "Requirements_for_Plot_Grading_Plans_Minor_Development.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=letter)
    w, h = letter

    # Header
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(w / 2, h - 50, "TOWNSHIP OF EDISON")
    c.setFont("Helvetica", 10)
    c.drawCentredString(w / 2, h - 65, "DEPARTMENT OF PLANNING AND ENGINEERING - DIVISION OF ENGINEERING")
    c.drawCentredString(w / 2, h - 78, "100 Municipal Boulevard, Edison, NJ 08817 | Phone: (732) 248-7288")
    c.line(50, h - 88, w - 50, h - 88)

    # Title
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(w / 2, h - 108, "REQUIREMENTS FOR PLOT GRADING PLANS - MINOR DEVELOPMENT")

    y = h - 128
    c.setFont("Helvetica-Bold", 10)
    c.drawString(55, y, "I. APPLICABILITY & THRESHOLDS:")
    y -= 16
    c.setFont("Helvetica", 9)
    app_text = [
        "A formal engineered Plot Grading Plan is required under Edison Township Code for all Minor Developments,",
        "including new 1- and 2-family dwellings, residential additions, in-ground swimming pools, retaining walls,",
        "and any development that creates between 500 and 10,890 sq. ft. of new impervious surface OR disturbs",
        "between 1,250 and 43,560 sq. ft. of land area."
    ]
    for line in app_text:
        c.drawString(65, y, line)
        y -= 13

    y -= 10
    c.setFont("Helvetica-Bold", 10)
    c.drawString(55, y, "II. TECHNICAL PLAN SUBMISSION REQUIREMENTS (10-Point Checklist):")
    y -= 16
    c.setFont("Helvetica", 8.5)
    checklist = [
        "1. Professional Seal: Plans must be prepared, signed, and embossed by a NJ Licensed Professional Engineer (PE)",
        "   or Professional Land Surveyor (PLS) as applicable by law.",
        "2. Property Survey Overlay: Plan must be overlaid on a certified boundary survey showing true dimensions, property",
        "   lines, right-of-ways, and all existing and proposed easements.",
        "3. Contours & Spot Elevations: Minimum 1-ft or 2-ft existing and proposed contours, spot elevations at property corners,",
        "   building corners, walk/driveway junctions, and high/low drainage break points.",
        "4. Stormwater Runoff Infiltration: On-site stormwater mitigation (e.g. seepage pits, drywells, clean crushed stone",
        "   trenches) sized per Township Stormwater Ordinance (Title 34) (capacity for 3 inches runoff per sq. ft. impervious).",
        "5. Structure Footprints: Location, setbacks, and dimensions of principal dwelling, garage, decks, sheds, pools, and patios.",
        "6. Setback Compliance: Clear setback dimensions to all property lines meeting Edison residential zone Schedule A standards.",
        "7. Soil Erosion & Sediment Control: Silt fence location, stabilized construction entrance, and inlet filter details meeting",
        "   Standards for Soil Erosion and Sediment Control in New Jersey.",
        "8. Retaining Walls: For retaining walls (especially under/over 48 inches), footings, drainage backfill, stone, and piping",
        "   must be detailed and structurally certified.",
        "9. Tree Conservation: If tree removal is required for grading, a separate Tree Removal Permit Application and Tree",
        "   Conservation / Replacement Plan must be submitted concurrently.",
        "10. Prior Approvals: If approved by Planning Board or Zoning Board of Adjustment, plan must strictly comply with all",
        "    resolution conditions of approval."
    ]
    for chk in checklist:
        c.drawString(65, y, chk)
        y -= 13

    y -= 10
    c.setFont("Helvetica-Bold", 10)
    c.drawString(55, y, "III. SUBMISSION PACKAGE & FEES:")
    y -= 16
    c.setFont("Helvetica", 8.5)
    pkg = [
        "• Submit three (3) signed and sealed copies of the Plot Grading Plan to the Division of Engineering.",
        "• Include completed Site Improvement Permit (SIP) Application and approved Zoning Permit.",
        "• Engineering Review Fee and Engineering Inspection Escrow (equal to 5% of overall construction cost).",
        "• Submit to: Division of Engineering, Edison Municipal Complex, 100 Municipal Blvd, Edison, NJ 08817."
    ]
    for p in pkg:
        c.drawString(65, y, p)
        y -= 13

    c.showPage()
    c.save()
    print("Created Requirements_for_Plot_Grading_Plans_Minor_Development.pdf successfully")


if __name__ == "__main__":
    generate_flood_zone_pdf()
    generate_plot_grading_pdf()
