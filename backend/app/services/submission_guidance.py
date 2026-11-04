import logging
from typing import Dict, Any, Optional
from ..models.form import FormMetadata
from .form_schema_service import form_schema_service

logger = logging.getLogger("services.submission_guidance")

class SubmissionGuidanceService:
    """
    Signature and Submission Guidance Service:
    - Provides verified municipal instructions after generating a draft PDF.
    - Explicitly emphasizes manual ink signature requirements.
    - Provides checklists of required supporting attachments.
    - Directs submission to the official municipal portal (edisonnj.org).
    - Clearly clarifies that CivicIQ is an application preparation assistant, not an official intake desk.
    """

    def get_guidance(self, form_id: str, answers: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        form = form_schema_service.get_form_by_id(form_id)
        if not form:
            return {
                "title": "Submission Guidance",
                "instructions": "Please submit your completed application to the Department of Engineering.",
                "portal_url": "https://www.edisonnj.org/document_center/index.php"
            }

        unanswered_fields = []
        if answers and form.fields:
            for field in form.fields:
                if not answers.get(field.name):
                    unanswered_fields.append(field.label)

        guidance_text = [
            f"Your official **{form.official_title}** draft is ready for review!\n",
            "### ✍️ Next Steps & Signature Requirement",
            "1. **Download & Review**: Click the download button below to inspect your generated municipal draft.",
            "2. **Physical Ink Signature**: Per Township of Edison regulations, this application **must be signed manually in ink** by the property owner or licensed contractor after printing. Digital/AI signatures are not recognized for municipal filings.",
            "3. **Mandatory Attachments**: Gather all required documents before submitting:\n" + "\n".join([f"   • {doc}" for doc in form.supporting_documents]),
            "\n### 🏛️ Official Submission Details",
            "• **Department**: Township of Edison Department of Engineering",
            "• **Official Document Portal**: [edisonnj.org/document_center](https://www.edisonnj.org/document_center/index.php)",
            f"• **Filing Fee / Escrow**: {form.fee_info or 'Per municipal fee schedule'}",
            "\n> ℹ️ *Disclaimer: CivicIQ helps residents navigate procedures and prepare application drafts. This draft does not constitute an official municipal filing until signed, accompanied by mandatory fees and attachments, and accepted by the Department of Engineering.*"
        ]

        if unanswered_fields:
            guidance_text.insert(
                3,
                f"⚠️ **Fields Requiring Manual Completion**: The following fields were not provided and must be filled by hand: {', '.join(unanswered_fields)}."
            )

        return {
            "form_id": form_id,
            "form_title": form.official_title,
            "signature_required": form.signature_required,
            "signature_instructions": form.signature_instructions,
            "supporting_documents": form.supporting_documents,
            "unanswered_fields": unanswered_fields,
            "portal_url": "https://www.edisonnj.org/document_center/index.php",
            "fee_info": form.fee_info,
            "markdown_guidance": "\n".join(guidance_text)
        }

submission_guidance_service = SubmissionGuidanceService()
