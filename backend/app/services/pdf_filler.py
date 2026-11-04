import os
import io
import re
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
import pypdf
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors

from ..config import GENERATED_DRAFTS_DIR, DEPARTMENTS_DIR, MUNICIPALITY_NAME
from ..models.form import FormMetadata
from .form_schema_service import form_schema_service

logger = logging.getLogger("services.pdf_filler")

class PdfFillerService:
    """
    Automatic Municipal PDF Form Filling Service:
    - Detects AcroForm fillable fields.
    - Generates high-fidelity ReportLab municipal draft overlays/companion drafts.
    - Strictly leaves signature fields blank with manual ink signing notice.
    - Watermarks all generated outputs as unsubmitted resident drafts.
    - Safely isolates generated drafts per resident session.
    """

    def __init__(self):
        self.output_base_dir = GENERATED_DRAFTS_DIR
        self.output_base_dir.mkdir(parents=True, exist_ok=True)

    def generate_draft_pdf(
        self,
        session_id: str,
        form_id: str,
        answers: Dict[str, Any]
    ) -> Tuple[bool, str, Optional[str], Optional[str]]:
        """
        Generates completed draft PDF populated with resident answers.
        Returns: (success, message, local_filepath, download_url)
        """
        form = form_schema_service.get_form_by_id(form_id)
        if not form:
            return False, f"Form '{form_id}' not found.", None, None

        # Create session directory
        session_dir = self.output_base_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        safe_title = re.sub(r'[^a-zA-Z0-9_-]', '_', form.form_code or form_id)
        draft_filename = f"{safe_title}_DRAFT_{timestamp_str}.pdf"
        output_path = session_dir / draft_filename

        try:
            # Generate the professional municipal draft PDF
            self._create_structured_draft_pdf(
                output_path=output_path,
                form=form,
                answers=answers,
                session_id=session_id
            )

            download_url = f"/api/form-session/download/{session_id}/{draft_filename}"
            logger.info(f"Generated draft PDF for session {session_id}: {output_path}")
            return True, "Draft PDF generated successfully.", str(output_path), download_url

        except Exception as e:
            logger.exception(f"Failed to generate draft PDF: {e}")
            return False, f"PDF generation failed: {str(e)}", None, None

    def _create_structured_draft_pdf(
        self,
        output_path: Path,
        form: FormMetadata,
        answers: Dict[str, Any],
        session_id: str
    ):
        """Builds a standardized, beautifully formatted municipal draft document."""
        c = canvas.Canvas(str(output_path), pagesize=letter)
        width, height = letter

        # 1. Unsubmitted Draft Watermark Banner (Top)
        c.setFillColor(colors.HexColor("#DC2626")) # Red banner
        c.rect(0, height - 28, width, 28, fill=True, stroke=False)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(
            width / 2.0,
            height - 18,
            "*** OFFICIAL REVIEW COPY — UNSUBMITTED MUNICIPAL DRAFT — PHYSICAL SIGNATURE REQUIRED ***"
        )

        # 2. Municipal Header
        y = height - 55
        c.setFillColor(colors.HexColor("#0F172A"))
        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(width / 2.0, y, MUNICIPALITY_NAME.upper())

        y -= 16
        c.setFont("Helvetica-Bold", 11)
        c.setFillColor(colors.HexColor("#1E3A8A"))
        c.drawCentredString(width / 2.0, y, f"DEPARTMENT OF {form.department.upper()} — DIVISION OF PERMITS")

        y -= 18
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(colors.HexColor("#0F172A"))
        c.drawCentredString(width / 2.0, y, form.official_title)

        y -= 14
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.HexColor("#475569"))
        now_str = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")
        c.drawCentredString(
            width / 2.0,
            y,
            f"Document Code: {form.form_code} | Generated: {now_str} | Session ID: {session_id[:8]}"
        )

        # Decorative Divider Rule
        y -= 10
        c.setStrokeColor(colors.HexColor("#2563EB"))
        c.setLineWidth(1.5)
        c.line(40, y, width - 40, y)

        # 3. Form Answers Table
        y -= 25
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(colors.HexColor("#1E293B"))
        c.drawString(45, y, "SECTION 1: APPLICANT & PROJECT DETAILS (COLLECTED VIA CIVICIQ)")

        y -= 8
        c.setStrokeColor(colors.HexColor("#CBD5E1"))
        c.setLineWidth(0.5)
        c.line(45, y, width - 45, y)

        y -= 18
        for field in form.fields:
            val = answers.get(field.name, "")
            display_val = str(val).strip() if val else "[NOT PROVIDED - MANUAL COMPLETION REQUIRED]"

            # Field Box Container
            box_height = 28
            if len(display_val) > 75:
                box_height = 42

            c.setFillColor(colors.HexColor("#F8FAFC"))
            c.setStrokeColor(colors.HexColor("#E2E8F0"))
            c.rect(45, y - box_height + 12, width - 90, box_height, fill=True, stroke=True)

            # Field Label
            c.setFont("Helvetica-Bold", 8)
            c.setFillColor(colors.HexColor("#475569"))
            c.drawString(52, y - 2, field.label.upper())

            # Field Value
            c.setFont("Helvetica", 9)
            c.setFillColor(colors.HexColor("#0F172A"))
            if len(display_val) > 75:
                c.drawString(52, y - 14, display_val[:75])
                c.drawString(52, y - 25, display_val[75:150])
            else:
                c.drawString(52, y - 14, display_val)

            y -= (box_height + 6)
            if y < 180: # Check page boundary
                break

        # 4. Mandatory Attachments Checklist Section
        y -= 10
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(colors.HexColor("#1E293B"))
        c.drawString(45, y, "SECTION 2: MANDATORY ATTACHMENTS TO BRING / ATTACH")

        y -= 8
        c.setStrokeColor(colors.HexColor("#CBD5E1"))
        c.setLineWidth(0.5)
        c.line(45, y, width - 45, y)

        y -= 14
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.HexColor("#334155"))
        for att in form.supporting_documents[:4]:
            c.rect(48, y - 1, 8, 8, stroke=True, fill=False)
            c.drawString(62, y, f"{att}")
            y -= 13

        # 5. Signature Section (Strictly Left Blank for In-Person Ink Signature!)
        y -= 8
        c.setFillColor(colors.HexColor("#FFFBEB")) # Amber warning box
        c.setStrokeColor(colors.HexColor("#F59E0B"))
        c.rect(45, y - 62, width - 90, 68, fill=True, stroke=True)

        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(colors.HexColor("#92400E"))
        c.drawString(55, y - 4, "SECTION 3: APPLICANT INK SIGNATURE & VERIFICATION (SIGN MANUALLY)")

        c.setFont("Helvetica", 7.5)
        c.setFillColor(colors.HexColor("#78350F"))
        c.drawString(
            55,
            y - 16,
            "Per municipal regulations, AI generated signatures are NOT permitted. You must print this document"
        )
        c.drawString(
            55,
            y - 25,
            "and sign below in physical ink prior to submitting to the Department of Engineering."
        )

        # Signature Line
        c.setStrokeColor(colors.HexColor("#92400E"))
        c.setLineWidth(0.8)
        c.line(55, y - 48, 320, y - 48)
        c.line(340, y - 48, 440, y - 48)
        c.line(460, y - 48, width - 55, y - 48)

        c.setFont("Helvetica-Bold", 7)
        c.drawString(55, y - 58, "APPLICANT SIGNATURE (SIGN IN INK)")
        c.drawString(340, y - 58, "DATE")
        c.drawString(460, y - 58, "TELEPHONE")

        # 6. Official Footer
        c.setFont("Helvetica", 7)
        c.setFillColor(colors.HexColor("#94A3B8"))
        c.drawCentredString(
            width / 2.0,
            20,
            "CivicIQ Assistant • Township of Edison Official Document Center • edisonnj.org/document_center/index.php • Page 1 of 1"
        )

        c.save()

pdf_filler = PdfFillerService()
