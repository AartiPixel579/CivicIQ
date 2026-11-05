import re
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, Any, Tuple
from ..models.form_session import (
    FormSessionState, FormQuestionResponse, FormStartSessionRequest,
    FormAnswerRequest, FormEditRequest
)
from ..models.form import FormField, FormMetadata
from .form_schema_service import form_schema_service

logger = logging.getLogger("services.form_session")

class FormSessionService:
    """
    Deterministic Form-Filling State Machine:
    - Guides resident one question at a time.
    - Validates mandatory fields and formats.
    - Handles editing previous answers.
    - Displays a comprehensive review summary prior to PDF generation.
    - Maintains strict session isolation.
    """

    def __init__(self):
        # In-memory session store (can be persisted to Redis or PostgreSQL in production)
        self.sessions: Dict[str, FormSessionState] = {}

    def get_session(self, session_id: str) -> Optional[FormSessionState]:
        return self.sessions.get(session_id)

    def cancel_session(self, session_id: str):
        if session_id in self.sessions:
            del self.sessions[session_id]

    def start_session(self, session_id: str, form_id: str) -> Tuple[bool, str, Optional[FormQuestionResponse]]:
        if form_id == "tree_removal":
            return False, "Interactive form filling for Tree Removal is currently unavailable. Please download the official blank application.", None

        form = form_schema_service.get_form_by_id(form_id)
        if not form:
            return False, f"Official form '{form_id}' not found in registry.", None

        if form.application_type not in ["Application form", "Permit application"]:
            return False, f"Document '{form.official_title}' is an {form.application_type.lower()}, not an application form.", None

        now = datetime.now(timezone.utc).isoformat()
        state = FormSessionState(
            session_id=session_id,
            form_id=form_id,
            status="in_progress",
            current_field_index=0,
            answers={},
            created_at=now,
            updated_at=now
        )
        self.sessions[session_id] = state

        first_field = form.fields[0] if form.fields else None
        total_steps = len(form.fields)

        welcome_msg = (
            f"I can help you fill out your official **{form.official_title}** step-by-step.\n\n"
            f"I will ask one question at a time. You can edit any answer before generating your official draft.\n\n"
            f"**Question 1 of {total_steps}**: {first_field.label}"
        )
        if first_field and first_field.help_text:
            welcome_msg += f"\n*({first_field.help_text})*"

        resp = FormQuestionResponse(
            session_id=session_id,
            form_id=form_id,
            form_title=form.official_title,
            status="in_progress",
            current_field=first_field,
            current_step=1,
            total_steps=total_steps,
            message=welcome_msg,
            collected_answers={},
            can_edit=False,
            is_complete=False
        )
        return True, "Form session started.", resp

    def _validate_field(self, field: FormField, val: str) -> Tuple[bool, str]:
        v = (val or "").strip()
        if field.required and not v:
            return False, f"This field is mandatory for the official municipal record. Please provide: {field.label}."

        if not v:
            return True, ""

        if field.field_type == "email":
            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
                return False, "Please enter a valid email address (e.g., name@example.com) for official municipal notifications."

        elif field.field_type == "phone":
            digits = re.sub(r"\D", "", v)
            if len(digits) < 10:
                return False, "Please enter a valid 10-digit telephone number including area code (e.g., (732) 555-0123)."

        elif field.field_type == "number":
            try:
                num = float(v)
                if num <= 0:
                    return False, "Please enter a positive numeric value."
            except ValueError:
                return False, "Please enter a valid numeric value."

        elif field.field_type == "choice" and field.options:
            # Flexible matching of choice
            clean_v = v.lower()
            matched = None
            for opt in field.options:
                if clean_v in opt.lower() or opt.lower() in clean_v:
                    matched = opt
                    break
            # If user provided something meaningful, accept it or return choice
            if not matched and len(v) < 3:
                return False, f"Please select one of the following valid options: {', '.join(field.options)}."

        return True, ""

    def answer_question(self, session_id: str, answer_text: str) -> Tuple[bool, str, Optional[FormQuestionResponse]]:
        state = self.get_session(session_id)
        if not state:
            return False, "No active application form session found. Please request an application to start.", None

        form = form_schema_service.get_form_by_id(state.form_id)
        if not form or not form.fields:
            return False, "Invalid form definition.", None

        if state.status == "review":
            # Citizen is reviewing answers or confirmed generation
            lower_ans = answer_text.strip().lower()
            if any(w in lower_ans for w in ["yes", "generate", "confirm", "ready", "proceed", "draft", "looks good", "ok"]):
                state.status = "completed"
                state.updated_at = datetime.now(timezone.utc).isoformat()
                return True, "Ready for PDF draft generation.", self._build_review_response(state, form, is_ready_to_generate=True)
            elif lower_ans.startswith("edit") or lower_ans.startswith("change"):
                # Handle edit intent in text
                return True, "Please specify which field you would like to edit from your summary.", self._build_review_response(state, form, is_ready_to_generate=False)

        current_idx = state.current_field_index
        if current_idx >= len(form.fields):
            # Already answered all fields, show review
            state.status = "review"
            return True, "All fields collected.", self._build_review_response(state, form)

        current_field = form.fields[current_idx]

        # Validate answer
        valid, err_msg = self._validate_field(current_field, answer_text)
        if not valid:
            total_steps = len(form.fields)
            repeat_msg = (
                f"⚠️ **Validation Notice**: {err_msg}\n\n"
                f"**Question {current_idx + 1} of {total_steps}**: {current_field.label}"
            )
            if current_field.help_text:
                repeat_msg += f"\n*({current_field.help_text})*"

            resp = FormQuestionResponse(
                session_id=session_id,
                form_id=state.form_id,
                form_title=form.official_title,
                status="in_progress",
                current_field=current_field,
                current_step=current_idx + 1,
                total_steps=total_steps,
                message=repeat_msg,
                collected_answers=state.answers,
                can_edit=bool(state.answers),
                is_complete=False
            )
            return True, "Validation failed; question repeated.", resp

        # Save validated answer
        state.answers[current_field.name] = answer_text.strip()
        state.current_field_index += 1
        state.updated_at = datetime.now(timezone.utc).isoformat()

        # Check if more fields remain
        next_idx = state.current_field_index
        total_steps = len(form.fields)

        if next_idx < total_steps:
            next_field = form.fields[next_idx]
            msg = (
                f"Thank you.\n\n"
                f"**Question {next_idx + 1} of {total_steps}**: {next_field.label}"
            )
            if next_field.options:
                msg += f"\n*Options: {', '.join(next_field.options)}*"
            if next_field.help_text:
                msg += f"\n*({next_field.help_text})*"

            resp = FormQuestionResponse(
                session_id=session_id,
                form_id=state.form_id,
                form_title=form.official_title,
                status="in_progress",
                current_field=next_field,
                current_step=next_idx + 1,
                total_steps=total_steps,
                message=msg,
                collected_answers=state.answers,
                can_edit=True,
                is_complete=False
            )
            return True, "Answer recorded; next question delivered.", resp
        else:
            # All questions complete! Switch to review state
            state.status = "review"
            return True, "All questions completed. Review presented.", self._build_review_response(state, form)

    def edit_answer(self, session_id: str, field_name: str, new_answer: str) -> Tuple[bool, str, Optional[FormQuestionResponse]]:
        state = self.get_session(session_id)
        if not state:
            return False, "Active application session not found.", None

        form = form_schema_service.get_form_by_id(state.form_id)
        if not form:
            return False, "Form definition missing.", None

        # Find matching field
        target_field = None
        for f in form.fields:
            if f.name.lower() == field_name.lower() or f.label.lower() == field_name.lower():
                target_field = f
                break

        if not target_field:
            return False, f"Field '{field_name}' not found on this application.", None

        valid, err_msg = self._validate_field(target_field, new_answer)
        if not valid:
            return False, err_msg, None

        state.answers[target_field.name] = new_answer.strip()
        state.updated_at = datetime.now(timezone.utc).isoformat()

        return True, f"Field '{target_field.label}' successfully updated.", self._build_review_response(state, form)

    def _build_review_response(
        self,
        state: FormSessionState,
        form: FormMetadata,
        is_ready_to_generate: bool = False
    ) -> FormQuestionResponse:
        total_steps = len(form.fields)

        summary_lines = [
            f"📋 **Application Review Summary: {form.official_title}**\n",
            "Please review your information carefully before we generate your official municipal PDF draft:\n"
        ]

        for idx, field in enumerate(form.fields):
            val = state.answers.get(field.name, "*(Not provided)*")
            summary_lines.append(f"• **{field.label}**: `{val}`")

        if is_ready_to_generate:
            summary_lines.append(
                f"\n✅ All information confirmed! Generating your official **{form.official_title}** draft now..."
            )
        else:
            summary_lines.append(
                "\nWould you like me to generate your official draft PDF, or would you like to edit any of your answers?"
            )

        return FormQuestionResponse(
            session_id=state.session_id,
            form_id=state.form_id,
            form_title=form.official_title,
            status=state.status,
            current_field=None,
            current_step=total_steps,
            total_steps=total_steps,
            message="\n".join(summary_lines),
            collected_answers=state.answers,
            can_edit=True,
            is_complete=(state.status == "completed"),
            generated_pdf_url=state.generated_pdf_url
        )

form_session_service = FormSessionService()
