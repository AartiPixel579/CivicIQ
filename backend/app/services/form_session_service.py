import os
import re
import shutil
import time
import logging
import threading
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Optional, Any, Tuple, Set, Callable
from collections import OrderedDict

from ..models.form_session import (
    FormSessionState, FormQuestionResponse, FormStartSessionRequest,
    FormAnswerRequest, FormEditRequest
)
from ..models.form import FormField, FormMetadata
from ..config import GENERATED_DRAFTS_DIR
from .form_schema_service import form_schema_service
from .form_lifecycle_store import form_lifecycle_store

logger = logging.getLogger("services.form_session")


class BoundedIdTracker:
    """
    Thread-safe LRU-bounded tracker for session identifiers.
    Enforces max capacity to prevent unbounded memory growth.
    Stores no personal data (only session ID strings).
    """

    def __init__(self, max_capacity: int = 5000):
        self.max_capacity = max_capacity
        self._store: OrderedDict[str, float] = OrderedDict()
        self._lock = threading.Lock()

    def add(self, item_id: str):
        if not item_id:
            return
        with self._lock:
            now = time.monotonic()
            if item_id in self._store:
                self._store.move_to_end(item_id)
                self._store[item_id] = now
                return
            while len(self._store) >= self.max_capacity:
                self._store.popitem(last=False)
            self._store[item_id] = now

    def discard(self, item_id: str):
        if not item_id:
            return
        with self._lock:
            self._store.pop(item_id, None)

    def contains(self, item_id: str) -> bool:
        if not item_id:
            return False
        with self._lock:
            return item_id in self._store

    def clear(self):
        with self._lock:
            self._store.clear()

    def __contains__(self, item_id: str) -> bool:
        return self.contains(item_id)

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)


class FormSessionService:
    """
    Deterministic Form-Filling State Machine:
    - Guides resident one question at a time.
    - Validates mandatory fields and formats.
    - Handles cross-field validations (e.g. trees_to_remove <= trees_on_site).
    - Handles editing previous answers with continuous validation.
    - Displays a comprehensive review summary with fee calculation prior to PDF generation.
    - Enforces 1-hour session inactivity TTL, purging resident answers upon expiration.
    - Distinguishes cancelled from expired lifecycle states.
    - Completely deletes on-disk draft folders upon cancellation.
    - Enforces bounded memory for tracking expired and cancelled session IDs.
    - Cleans up expired generated drafts safely without directory traversal risks.
    - Maintains strict session isolation.
    """

    def __init__(self, ttl_seconds: int = 3600, max_tracked_sessions: int = 5000):
        self.sessions: Dict[str, FormSessionState] = {}
        self.expired_session_ids = BoundedIdTracker(max_capacity=max_tracked_sessions)
        self.cancelled_session_ids = BoundedIdTracker(max_capacity=max_tracked_sessions)
        self._generating_sessions: Set[str] = set()
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._on_session_cleared_callback: Optional[Callable[[str], None]] = None

    def begin_pdf_generation(self, session_id: str):
        """Marks session as actively generating a PDF draft to protect against cleanup race conditions."""
        with self._lock:
            self._generating_sessions.add(session_id)

    def end_pdf_generation(self, session_id: str):
        """Unmarks session from active PDF generation."""
        with self._lock:
            self._generating_sessions.discard(session_id)

    def get_protected_session_ids(self) -> Set[str]:
        """Returns session IDs that must not be deleted during draft cleanup (active + generating)."""
        with self._lock:
            active = {sid for sid, state in self.sessions.items() if not self._is_expired(state)}
            return active.union(self._generating_sessions)

    def set_session_cleared_callback(self, callback: Callable[[str], None]):
        """Registers a hook to notify chat history to purge session state."""
        self._on_session_cleared_callback = callback

    def _is_expired(self, state: FormSessionState) -> bool:
        """Determines if a session has exceeded its inactivity TTL."""
        try:
            updated_dt = datetime.fromisoformat(state.updated_at)
            if updated_dt.tzinfo is None:
                updated_dt = updated_dt.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            return (now - updated_dt).total_seconds() > self.ttl_seconds
        except Exception:
            return False

    def is_session_cancelled(self, session_id: str) -> bool:
        """Checks if session has been explicitly cancelled (in-memory tracker + persistent store)."""
        if self.cancelled_session_ids.contains(session_id):
            return True
        return form_lifecycle_store.get_session_lifecycle_status(session_id) == "cancelled"

    def is_session_expired(self, session_id: str) -> bool:
        """Checks if session is expired, purging memory if newly expired."""
        if self.expired_session_ids.contains(session_id):
            return True
        with self._lock:
            state = self.sessions.get(session_id)
            if state and self._is_expired(state):
                # Expire immediately
                self._expire_session_locked(session_id)
                return True
        return form_lifecycle_store.get_session_lifecycle_status(session_id) == "expired"

    def _safe_delete_session_drafts(self, session_id: str):
        """Safely removes generated draft directory for session_id enforcing strict containment."""
        if not session_id or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id):
            return
        root_allowed = GENERATED_DRAFTS_DIR.resolve()
        session_dir = (root_allowed / session_id).resolve()
        if session_dir.is_relative_to(root_allowed) and session_dir != root_allowed:
            if session_dir.exists() and session_dir.is_dir():
                try:
                    shutil.rmtree(session_dir, ignore_errors=True)
                    logger.info(f"Safely removed draft directory for session: {session_id}")
                except Exception as e:
                    logger.warning(f"Error removing draft directory for session {session_id}: {e}")

    def cancel_session(self, session_id: str):
        """
        Cancels a session:
        1. Purges all resident answers from memory.
        2. Revokes access via bounded cancelled tracker and persistent lifecycle store.
        3. Deletes generated draft files on disk.
        4. Invokes callback to purge chat history.
        """
        with self._lock:
            if session_id in self.sessions:
                self.sessions[session_id].answers.clear()
                del self.sessions[session_id]
            self.expired_session_ids.discard(session_id)
            self.cancelled_session_ids.add(session_id)

        form_lifecycle_store.record_session_cancelled(session_id)
        self._safe_delete_session_drafts(session_id)

        if self._on_session_cleared_callback:
            try:
                self._on_session_cleared_callback(session_id)
            except Exception:
                pass
        logger.info(f"Form session '{session_id}' cancelled, answers purged, and draft access revoked.")

    def reset_session(self, session_id: str):
        """
        Completely resets session to a blank state upon user /reset command:
        1. Purges all resident answers from memory.
        2. Discards expired and cancelled tracking.
        3. Removes lifecycle record from persistent store.
        4. Deletes generated draft files on disk.
        5. Invokes callback to purge chat history.
        """
        with self._lock:
            if session_id in self.sessions:
                self.sessions[session_id].answers.clear()
                del self.sessions[session_id]
            self.expired_session_ids.discard(session_id)
            self.cancelled_session_ids.discard(session_id)

        form_lifecycle_store.delete_session(session_id)
        self._safe_delete_session_drafts(session_id)

        if self._on_session_cleared_callback:
            try:
                self._on_session_cleared_callback(session_id)
            except Exception:
                pass
        logger.info(f"Form session '{session_id}' completely reset to clean state.")

    def _expire_session_locked(self, session_id: str):
        """Internal helper to expire a session under lock."""
        if session_id in self.sessions:
            sess = self.sessions[session_id]
            sess.answers.clear()
            del self.sessions[session_id]
        self.cancelled_session_ids.discard(session_id)
        self.expired_session_ids.add(session_id)
        form_lifecycle_store.record_session_expired(session_id)

        if self._on_session_cleared_callback:
            try:
                self._on_session_cleared_callback(session_id)
            except Exception:
                pass
        logger.info(f"Form session '{session_id}' expired and answers purged from memory.")

    def expire_session(self, session_id: str):
        """Explicitly expires a session, purging all resident answers from memory."""
        with self._lock:
            self._expire_session_locked(session_id)

    def cleanup_expired_sessions(self) -> int:
        """Purges any expired sessions from memory."""
        expired = []
        with self._lock:
            for sid, s in list(self.sessions.items()):
                if self._is_expired(s):
                    expired.append(sid)
            for sid in expired:
                self._expire_session_locked(sid)
        return len(expired)

    def get_session(self, session_id: str) -> Optional[FormSessionState]:
        """Retrieves session if active and neither cancelled nor expired."""
        if self.is_session_cancelled(session_id):
            return None
        if self.is_session_expired(session_id):
            return None
        with self._lock:
            state = self.sessions.get(session_id)
            if not state:
                return None
            if self._is_expired(state):
                self._expire_session_locked(session_id)
                return None
            return state

    def get_session_lifecycle_status(self, session_id: str) -> Optional[str]:
        """Returns authoritative session lifecycle status (in-memory + persistent)."""
        if self.is_session_cancelled(session_id):
            return "cancelled"
        if self.is_session_expired(session_id):
            return "expired"
        persistent_status = form_lifecycle_store.get_session_lifecycle_status(session_id)
        if persistent_status in ("cancelled", "expired"):
            return persistent_status
        with self._lock:
            state = self.sessions.get(session_id)
            if state:
                return state.status
        return persistent_status

    def start_session(self, session_id: str, form_id: str) -> Tuple[bool, str, Optional[FormQuestionResponse]]:
        # Unblock restarted session if previously cancelled or expired
        with self._lock:
            self.expired_session_ids.discard(session_id)
            self.cancelled_session_ids.discard(session_id)

        form_lifecycle_store.record_session_start(session_id, form_id)

        # Notify chat history to purge previous session turns
        if self._on_session_cleared_callback:
            try:
                self._on_session_cleared_callback(session_id)
            except Exception:
                pass

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
        with self._lock:
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
        is_skip = v.lower() in ["skip", "n/a", "none", "na", ""]

        if field.required and not v:
            return False, f"This field is mandatory for the official municipal record. Please provide: {field.label}."

        if not field.required and is_skip:
            return True, ""

        if not v:
            return True, ""

        if field.field_type == "email":
            if not is_skip and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
                return False, "Please enter a valid email address (e.g., name@example.com) for official municipal notifications."

        elif field.field_type == "phone":
            digits = re.sub(r"\D", "", v)
            if len(digits) < 10:
                return False, "Please enter a valid 10-digit telephone number including area code (e.g., (732) 555-0123)."

        elif field.field_type == "number":
            if not field.required and is_skip:
                return True, ""
            try:
                num = float(v)
                if num <= 0:
                    return False, "Please enter a positive numeric value."
                if field.name in ("trees_on_site", "trees_to_remove"):
                    if not num.is_integer():
                        return False, f"{field.label} must be a positive whole number (integer)."
            except ValueError:
                return False, "Please enter a valid numeric value."

        elif field.field_type == "choice" and field.options:
            clean_v = v.lower()
            matched = None
            for opt in field.options:
                if clean_v in opt.lower() or opt.lower() in clean_v:
                    matched = opt
                    break
            if not matched and len(v) < 3:
                return False, f"Please select one of the following valid options: {', '.join(field.options)}."

        return True, ""

    def answer_question(self, session_id: str, answer_text: str) -> Tuple[bool, str, Optional[FormQuestionResponse]]:
        if self.is_session_cancelled(session_id):
            return False, "Form session has been cancelled. Please start a new session.", None
        if self.is_session_expired(session_id):
            return False, "Form session has expired due to 1 hour of inactivity. Please start a new session.", None

        state = self.get_session(session_id)
        if not state:
            return False, "No active application form session found. Please request an application to start.", None

        form = form_schema_service.get_form_by_id(state.form_id)
        if not form or not form.fields:
            return False, "Invalid form definition.", None

        if state.status == "review":
            lower_ans = answer_text.strip().lower()
            if any(w in lower_ans for w in ["yes", "generate", "confirm", "ready", "proceed", "draft", "looks good", "ok"]):
                state.status = "completed"
                state.updated_at = datetime.now(timezone.utc).isoformat()
                form_lifecycle_store.record_session_status(session_id, "completed")
                return True, "Ready for PDF draft generation.", self._build_review_response(state, form, is_ready_to_generate=True)
            elif lower_ans.startswith("edit") or lower_ans.startswith("change"):
                return True, "Please specify which field you would like to edit from your summary.", self._build_review_response(state, form, is_ready_to_generate=False)

        current_idx = state.current_field_index
        if current_idx >= len(form.fields):
            state.status = "review"
            return True, "All fields collected.", self._build_review_response(state, form)

        current_field = form.fields[current_idx]

        # 1. Base validation
        valid, err_msg = self._validate_field(current_field, answer_text)
        if not valid:
            return self._build_validation_failure_response(state, form, current_field, current_idx, err_msg)

        # 2. Contextual / Cross-field validations
        v = answer_text.strip()
        is_skip = v.lower() in ["skip", "n/a", "none", "na", ""]

        # Cross-field: trees_to_remove <= trees_on_site
        if current_field.name == "trees_to_remove":
            try:
                val_remove = int(float(v))
                val_on_site_str = state.answers.get("trees_on_site")
                if val_on_site_str:
                    val_on_site = int(float(val_on_site_str))
                    if val_remove > val_on_site:
                        err_msg = f"The number of trees to be removed ({val_remove}) cannot exceed the total number of trees on-site ({val_on_site}). Please enter a valid number."
                        return self._build_validation_failure_response(state, form, current_field, current_idx, err_msg)
            except ValueError:
                pass

        # Conditional: board_resolution_number required if fee category is Board approval
        if current_field.name == "board_resolution_number":
            fee_cat = state.answers.get("fee_category", "").lower()
            if ("board" in fee_cat or "200" in fee_cat) and (not v or is_skip):
                err_msg = "A Planning/Zoning Board Resolution number is required when Board approval fee category is selected."
                return self._build_validation_failure_response(state, form, current_field, current_idx, err_msg)

        # Save validated answer
        saved_val = v
        if not current_field.required and is_skip:
            saved_val = "N/A"
        state.answers[current_field.name] = saved_val
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
            state.status = "review"
            form_lifecycle_store.record_session_status(session_id, "review")
            return True, "All questions completed. Review presented.", self._build_review_response(state, form)

    def _build_validation_failure_response(
        self,
        state: FormSessionState,
        form: FormMetadata,
        field: FormField,
        idx: int,
        err_msg: str
    ) -> Tuple[bool, str, FormQuestionResponse]:
        total_steps = len(form.fields)
        repeat_msg = (
            f"⚠️ **Validation Notice**: {err_msg}\n\n"
            f"**Question {idx + 1} of {total_steps}**: {field.label}"
        )
        if field.options:
            repeat_msg += f"\n*Options: {', '.join(field.options)}*"
        if field.help_text:
            repeat_msg += f"\n*({field.help_text})*"

        resp = FormQuestionResponse(
            session_id=state.session_id,
            form_id=state.form_id,
            form_title=form.official_title,
            status="in_progress",
            current_field=field,
            current_step=idx + 1,
            total_steps=total_steps,
            message=repeat_msg,
            collected_answers=state.answers,
            can_edit=bool(state.answers),
            is_complete=False
        )
        return True, "Validation failed; question repeated.", resp

    def edit_answer(self, session_id: str, field_name: str, new_answer: str) -> Tuple[bool, str, Optional[FormQuestionResponse]]:
        if self.is_session_cancelled(session_id):
            return False, "Form session has been cancelled.", None
        if self.is_session_expired(session_id):
            return False, "Form session has expired due to 1 hour of inactivity.", None

        state = self.get_session(session_id)
        if not state:
            return False, "Active application session not found.", None

        form = form_schema_service.get_form_by_id(state.form_id)
        if not form:
            return False, "Form definition missing.", None

        target_field = None
        for f in form.fields:
            if f.name.lower() == field_name.lower() or f.label.lower() == field_name.lower():
                target_field = f
                break

        if not target_field:
            return False, f"Field '{field_name}' not found on this application.", None

        # 1. Base validation
        valid, err_msg = self._validate_field(target_field, new_answer)
        if not valid:
            return False, err_msg, None

        # 2. Contextual cross-field check
        v = new_answer.strip()
        is_skip = v.lower() in ["skip", "n/a", "none", "na", ""]

        if target_field.name == "trees_to_remove":
            try:
                val_remove = int(float(v))
                if "trees_on_site" in state.answers:
                    val_on_site = int(float(state.answers["trees_on_site"]))
                    if val_remove > val_on_site:
                        return False, f"The number of trees to be removed ({val_remove}) cannot exceed the total number of trees on-site ({val_on_site}).", None
            except ValueError:
                pass

        if target_field.name == "trees_on_site":
            try:
                val_on_site = int(float(v))
                if "trees_to_remove" in state.answers:
                    val_remove = int(float(state.answers["trees_to_remove"]))
                    if val_on_site < val_remove:
                        return False, f"Total trees on-site ({val_on_site}) cannot be less than trees to be removed ({val_remove}).", None
            except ValueError:
                pass

        if target_field.name == "board_resolution_number":
            fee_cat = state.answers.get("fee_category", "").lower()
            if ("board" in fee_cat or "200" in fee_cat) and (not v or is_skip):
                return False, "A Planning/Zoning Board Resolution number is required when Board approval fee category is selected.", None

        saved_val = v
        if not target_field.required and is_skip:
            saved_val = "N/A"
        state.answers[target_field.name] = saved_val
        state.updated_at = datetime.now(timezone.utc).isoformat()

        return True, f"Field '{target_field.label}' successfully updated.", self._build_review_response(state, form)

    def get_applicable_fee(self, answers: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculates municipal fee and senior exemption per Edison Township Ordinance.
        Rules:
        - $25 standard residential fee categories are waived for senior citizen property owners (age 62+ with ID).
        - $200 Planning/Zoning Board approval fee is NEVER waived for senior citizens.
        """
        fee_cat = answers.get("fee_category", "")
        is_senior = answers.get("is_owner_senior_citizen", "")
        senior_eligible = "yes" in is_senior.lower() or "62" in is_senior

        if "200" in fee_cat or "board" in fee_cat.lower():
            return {
                "amount": 200.0,
                "currency": "USD",
                "category": "Planning/Zoning Board Approval",
                "is_waived": False,
                "waiver_reason": "Senior citizen fee waiver does not apply to the $200 Planning/Zoning Board fee.",
                "display_fee": "$200.00"
            }
        elif fee_cat:
            if senior_eligible:
                return {
                    "amount": 0.0,
                    "currency": "USD",
                    "category": fee_cat,
                    "is_waived": True,
                    "waiver_reason": "Fee waived for senior citizen property owner (age 62+ with valid ID).",
                    "display_fee": "$0.00 (Waived for senior citizen property owner)"
                }
            else:
                return {
                    "amount": 25.0,
                    "currency": "USD",
                    "category": fee_cat,
                    "is_waived": False,
                    "waiver_reason": None,
                    "display_fee": "$25.00"
                }
        return {
            "amount": 25.0,
            "currency": "USD",
            "category": "Standard",
            "is_waived": False,
            "waiver_reason": None,
            "display_fee": "$25.00"
        }

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

        if state.form_id == "tree_removal" and "fee_category" in state.answers:
            fee_info = self.get_applicable_fee(state.answers)
            summary_lines.append(f"\n💵 **Permit Fee Calculation**: `{fee_info['display_fee']}`")
            if fee_info.get("waiver_reason"):
                summary_lines.append(f"  *({fee_info['waiver_reason']})*")

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

    def cleanup_expired_drafts(self, max_age_seconds: int = 86400, base_dir: Optional[Path] = None) -> int:
        """
        Safely cleans up generated draft PDFs older than max_age_seconds (default 24 hours).
        Safety guarantees:
        1. Path containment: Enforces that base_dir is strictly inside or equal to GENERATED_DRAFTS_DIR.
           Rejects any base_dir attempting directory traversal (outside GENERATED_DRAFTS_DIR).
        2. Active draft preservation: Never deletes drafts belonging to active, non-expired sessions.
        3. Traversal prevention: Resolves each file and verifies it is inside GENERATED_DRAFTS_DIR.
        4. Age verification: Checks file modification time against max_age_seconds.
        Returns count of deleted files.
        """
        target_dir = (base_dir or GENERATED_DRAFTS_DIR).resolve()
        root_allowed = GENERATED_DRAFTS_DIR.resolve()

        if not target_dir.is_relative_to(root_allowed):
            raise ValueError(f"Security violation: cleanup directory '{target_dir}' is outside '{root_allowed}'")

        if not target_dir.exists():
            return 0

        now_ts = datetime.now(timezone.utc).timestamp()
        deleted_count = 0

        protected_session_ids = self.get_protected_session_ids()

        for item in list(target_dir.rglob("*")):
            try:
                resolved = item.resolve()
                if not resolved.is_relative_to(root_allowed) or resolved == root_allowed:
                    continue

                rel_parts = resolved.relative_to(root_allowed).parts
                if rel_parts and rel_parts[0] in protected_session_ids:
                    continue

                if resolved.is_file():
                    mtime = resolved.stat().st_mtime
                    if (now_ts - mtime) >= max_age_seconds:
                        resolved.unlink(missing_ok=True)
                        deleted_count += 1
                        logger.info(f"Deleted expired draft PDF: {resolved}")
            except Exception as e:
                logger.warning(f"Error checking file during draft cleanup {item}: {e}")

        # Clean up empty inactive subdirectories (with race condition protection on mtime)
        for sub_dir in list(target_dir.iterdir()):
            try:
                resolved_sub = sub_dir.resolve()
                if resolved_sub.is_dir() and resolved_sub.is_relative_to(root_allowed) and resolved_sub != root_allowed:
                    if resolved_sub.name not in protected_session_ids:
                        dir_mtime = resolved_sub.stat().st_mtime
                        if (now_ts - dir_mtime) >= max_age_seconds:
                            if not any(resolved_sub.iterdir()):
                                resolved_sub.rmdir()
                                logger.info(f"Removed empty expired draft directory: {resolved_sub}")
            except Exception:
                pass

        return deleted_count

form_session_service = FormSessionService()
