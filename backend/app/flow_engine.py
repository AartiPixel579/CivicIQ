import re
import logging
from typing import Dict, Optional, Tuple, Any
from .department_loader import registry
from .models import (
    FlowDefinition, FlowStep, FlowOption, FormIssuanceDetails, 
    SubmissionRouting, FeeInfo, ChatResponse
)

logger = logging.getLogger("flow_engine")

class FlowSession:
    def __init__(self, session_id: str, department_id: str, flow_id: str):
        self.session_id = session_id
        self.department_id = department_id
        self.flow_id = flow_id
        self.current_step_id: str = ""
        self.history = []
        self.completed: bool = False
        self.form_packet: Optional[FormIssuanceDetails] = None

    @property
    def current_step(self) -> Optional[FlowStep]:
        flow = registry.get_flow(self.department_id, self.flow_id)
        if flow and self.current_step_id:
            return flow.steps.get(self.current_step_id)
        return None

class FlowEngine:
    def __init__(self):
        self.sessions: Dict[str, FlowSession] = {}

    def get_session(self, session_id: str) -> Optional[FlowSession]:
        return self.sessions.get(session_id)

    def reset_session(self, session_id: str):
        if session_id in self.sessions:
            del self.sessions[session_id]

    def _build_form_packet(self, session: FlowSession, step: FlowStep) -> Optional[FormIssuanceDetails]:
        if step.type != "form_issuance":
            return None
        dept_config = registry.get_department(session.department_id)
        download_url = f"/api/forms/{session.department_id}/{step.form_file}"
        sub_routing = step.submission_routing
        if not sub_routing and dept_config:
            sub_routing = SubmissionRouting(
                department=dept_config.name,
                desk="Engineering Division",
                digital_upload_url="https://www.edisonnj.org/document_center/index.php"
            )

        return FormIssuanceDetails(
            form_code=step.form_code or "OFFICIAL FORM",
            form_title=step.form_title or "Standardized Municipal Application",
            form_file=step.form_file or "document.pdf",
            pdf_download_url=download_url,
            department_id=session.department_id,
            fill_in_instructions=step.fill_in_instructions or "Complete all marked fields and sign in ink.",
            required_attachments=step.required_attachments or [],
            fee_info=step.fee_info,
            submission_routing=sub_routing,
            lead_time=step.lead_time or "5 to 10 business days",
            visibility="public",
            document_type="permit_application",
            service=session.flow_id.replace("_flow", "")
        )

    def start_flow(
        self,
        session_id: str,
        department_id: str,
        flow_id: str,
        initial_user_text: str = ""
    ) -> Tuple[bool, str, Optional[FlowStep], Optional[FormIssuanceDetails]]:
        flow = registry.get_flow(department_id, flow_id)
        if not flow:
            found = registry.find_flow_by_id(flow_id)
            if found:
                department_id, flow = found
            else:
                return False, f"Procedure flow '{flow_id}' not found.", None, None

        session = FlowSession(session_id, department_id, flow_id)
        session.current_step_id = flow.initial_step
        self.sessions[session_id] = session

        current_step = flow.steps.get(flow.initial_step)
        if not current_step:
            return False, f"Initial step '{flow.initial_step}' not found in flow {flow_id}.", None, None

        # Check if user's initial query already answers procedural steps (e.g. for tree removal)
        if flow_id == "tree_removal_flow" and initial_user_text:
            t = initial_user_text.lower().strip()
            # 1. Dead, falling, hazard, or emergency mentioned upfront
            if any(w in t for w in ["dead", "dying", "danger", "hazardous", "hazard", "falling", "imminent", "emergency", "urgent", "crack", "cracked", "split", "leaning", "lean"]):
                dest_step = flow.steps.get("step_emergency_protocol_result")
                if dest_step:
                    session.current_step_id = "step_emergency_protocol_result"
                    session.completed = True
                    pkt = self._build_form_packet(session, dest_step)
                    session.form_packet = pkt
                    return True, "Emergency protocol delivered.", dest_step, pkt

            # 2. Healthy / planned removal mentioned upfront
            if any(w in t for w in ["healthy", "planned", "routine", "landscape"]) and not any(w in t for w in ["dead", "dying", "hazard"]):
                dest_step = flow.steps.get("step_planned_permit_required_result")
                if dest_step:
                    session.current_step_id = "step_planned_permit_required_result"
                    session.completed = True
                    pkt = self._build_form_packet(session, dest_step)
                    session.form_packet = pkt
                    return True, "Permit requirement confirmed.", dest_step, pkt

            # 3. Not removing trees mentioned upfront
            if any(w in t for w in ["not removing", "no tree", "no trees", "none", "don't want to remove", "dont want to remove", "not planning to remove"]):
                dest_step = flow.steps.get("step_subdivision_demolition_check")
                if dest_step:
                    session.current_step_id = "step_subdivision_demolition_check"
                    return True, "Subdivision check required.", dest_step, None

            # 4. Subdivision or demolition mentioned upfront
            if any(w in t for w in ["subdivision", "demolition", "demo"]) and not any(w in t for w in ["not part", "neither"]):
                dest_step = flow.steps.get("step_subdivision_permit_required_result")
                if dest_step:
                    session.current_step_id = "step_subdivision_permit_required_result"
                    session.completed = True
                    pkt = self._build_form_packet(session, dest_step)
                    session.form_packet = pkt
                    return True, "Subdivision permit required.", dest_step, pkt

        # Check if user's initial query answers soil import/export steps
        if flow_id == "soil_import_export_flow" and initial_user_text:
            t = initial_user_text.lower().strip()
            is_import = any(w in t for w in ["import", "bring", "deliver", "fill dirt", "topsoil", "fill my yard", "into", "onto", "add soil"])
            is_export = any(w in t for w in ["export", "remove", "take away", "haul away", "off site", "excess soil"])
            has_10_or_more = any(w in t for w in ["10", "20", "15", "25", "30", "40", "50", "more", "over", "large"]) and not any(w in t for w in ["less", "under"])
            has_under_10 = any(w in t for w in ["less than 10", "under 10", "less than ten", "under ten", "5 cubic", "3 cubic", "2 cubic", "1 cubic", "few yards", "small amount"])

            if is_import and not is_export:
                if has_10_or_more:
                    dest_step = flow.steps.get("step_soil_import_permit_required_result")
                    if dest_step:
                        session.current_step_id = "step_soil_import_permit_required_result"
                        session.completed = True
                        pkt = self._build_form_packet(session, dest_step)
                        session.form_packet = pkt
                        return True, "Soil import permit required.", dest_step, pkt
                elif has_under_10:
                    dest_step = flow.steps.get("step_soil_permit_not_required_result")
                    if dest_step:
                        session.current_step_id = "step_soil_permit_not_required_result"
                        session.completed = True
                        return True, "Soil permit not required.", dest_step, None
                else:
                    dest_step = flow.steps.get("step_soil_import_volume_check")
                    if dest_step:
                        session.current_step_id = "step_soil_import_volume_check"
                        return True, "Volume check required.", dest_step, None

            elif is_export and not is_import:
                if has_10_or_more:
                    dest_step = flow.steps.get("step_soil_export_permit_required_result")
                    if dest_step:
                        session.current_step_id = "step_soil_export_permit_required_result"
                        session.completed = True
                        pkt = self._build_form_packet(session, dest_step)
                        session.form_packet = pkt
                        return True, "Soil export permit required.", dest_step, pkt
                elif has_under_10:
                    dest_step = flow.steps.get("step_soil_permit_not_required_result")
                    if dest_step:
                        session.current_step_id = "step_soil_permit_not_required_result"
                        session.completed = True
                        return True, "Soil permit not required.", dest_step, None
                else:
                    dest_step = flow.steps.get("step_soil_export_volume_check")
                    if dest_step:
                        session.current_step_id = "step_soil_export_volume_check"
                        return True, "Volume check required.", dest_step, None

        # Check if user's initial query answers site improvement
        if flow_id == "site_improvement_flow" and initial_user_text:
            t = initial_user_text.lower().strip()
            if any(w in t for w in ["more than 500", "over 500", "more than 1250", "over 1250", "major disturbance", "commercial", "subdivision"]):
                dest_step = flow.steps.get("step_site_permit_required_result")
                if dest_step:
                    session.current_step_id = "step_site_permit_required_result"
                    session.completed = True
                    pkt = self._build_form_packet(session, dest_step)
                    session.form_packet = pkt
                    return True, "Site improvement permit required.", dest_step, pkt

        return True, "Procedure initiated.", current_step, None

    def advance_step(
        self,
        session_id: str,
        option_id: Optional[str] = None,
        user_text: Optional[str] = None
    ) -> Tuple[bool, str, Optional[FlowStep], Optional[FormIssuanceDetails]]:
        session = self.get_session(session_id)
        if not session:
            return False, "No active procedure found. Please select a procedure to start.", None, None

        flow = registry.get_flow(session.department_id, session.flow_id)
        if not flow:
            return False, "Flow definition not found.", None, None

        current_step = flow.steps.get(session.current_step_id)
        if not current_step:
            return False, "Current step is invalid.", None, None

        # Resolve option_id from natural language user_text if option_id was not explicitly sent
        if not option_id and user_text:
            t = user_text.lower().strip()
            if session.flow_id == "tree_removal_flow":
                if session.current_step_id == "step_removing_trees_check":
                    if re.search(r'\b(no|nope|not|none|negative)\b', t):
                        option_id = "opt_removing_trees_no"
                    elif re.search(r'\b(yes|yeah|yep|sure|removing|remove|one|1|tree|trees)\b', t):
                        option_id = "opt_removing_trees_yes"
                elif session.current_step_id == "step_emergency_check":
                    if any(w in t for w in ["yes", "dead", "dying", "danger", "urgent", "emergency", "hazard", "falling", "cracked", "split", "leaning", "lean", "risk"]):
                        option_id = "opt_emergency_yes"
                    elif any(w in t for w in ["no", "healthy", "not urgent", "not emergency", "planned", "routine", "fine"]):
                        option_id = "opt_emergency_no"
                elif session.current_step_id == "step_subdivision_demolition_check":
                    if any(w in t for w in ["yes", "subdivision", "demolition", "demo"]) and not ("no" in t or "not" in t):
                        option_id = "opt_subdivision_demo_yes"
                    elif any(w in t for w in ["no", "neither", "not part", "nope"]):
                        option_id = "opt_subdivision_demo_no"
            elif session.flow_id == "soil_import_export_flow":
                if session.current_step_id == "step_soil_direction_check":
                    if any(w in t for w in ["import", "bring", "deliver", "onto", "in", "add", "topsoil", "fill my yard", "bring soil"]):
                        option_id = "opt_soil_import"
                    elif any(w in t for w in ["export", "remove", "take away", "haul away", "out", "off", "remove soil"]):
                        option_id = "opt_soil_export"
                elif session.current_step_id == "step_soil_import_volume_check":
                    if any(w in t for w in ["10", "20", "15", "25", "30", "more", "over", "yes", "exceed", "large"]) and not any(w in t for w in ["less", "under"]):
                        option_id = "opt_import_volume_10_or_more"
                    elif any(w in t for w in ["less", "under", "no", "small", "5", "3", "2", "few", "minor"]):
                        option_id = "opt_import_volume_under_10"
                elif session.current_step_id == "step_soil_export_volume_check":
                    if any(w in t for w in ["10", "20", "15", "25", "30", "more", "over", "yes", "exceed", "large"]) and not any(w in t for w in ["less", "under"]):
                        option_id = "opt_export_volume_10_or_more"
                    elif any(w in t for w in ["less", "under", "no", "small", "5", "3", "2", "few", "minor"]):
                        option_id = "opt_export_volume_under_10"
            elif session.flow_id == "site_improvement_flow":
                if session.current_step_id == "step_site_disturbance_check":
                    if any(w in t for w in ["yes", "more", "over", "500", "1250", "exceed", "large", "improve"]):
                        option_id = "opt_disturbance_yes"
                    elif any(w in t for w in ["no", "less", "under", "small", "minor"]):
                        option_id = "opt_disturbance_no"
                elif session.current_step_id == "step_site_drainage_check":
                    if any(w in t for w in ["yes", "drainage", "grading", "runoff", "slope"]):
                        option_id = "opt_drainage_yes"
                    elif any(w in t for w in ["no", "neither", "none", "no drainage"]):
                        option_id = "opt_drainage_no"
            else:
                # General option text matching for other flows
                if current_step.options:
                    for opt in current_step.options:
                        if opt.id.lower() in t or opt.label.lower() in t:
                            option_id = opt.id
                            break

        # Find matching option
        matched_option = None
        if current_step.options and option_id:
            for opt in current_step.options:
                if opt.id == option_id:
                    matched_option = opt
                    break

        if not matched_option:
            return False, f"Invalid choice '{option_id or user_text}' for current step '{current_step.title}'.", current_step, None

        # Record history
        session.history.append({
            "step_id": session.current_step_id,
            "option_id": option_id,
            "option_label": matched_option.label
        })

        next_step_id = matched_option.next_step

        # If resident's message already answered upcoming question, advance directly
        if session.flow_id == "tree_removal_flow" and user_text:
            t = user_text.lower().strip()
            if session.current_step_id == "step_removing_trees_check" and option_id == "opt_removing_trees_yes":
                if any(w in t for w in ["dead", "dying", "danger", "urgent", "emergency", "hazard", "falling", "cracked", "split", "leaning", "lean", "risk"]):
                    next_step_id = "step_emergency_protocol_result"
                elif any(w in t for w in ["healthy", "planned", "routine"]) and not any(w in t for w in ["dead", "dying", "hazard"]):
                    next_step_id = "step_planned_permit_required_result"
            elif session.current_step_id == "step_removing_trees_check" and option_id == "opt_removing_trees_no":
                if any(w in t for w in ["subdivision", "demolition", "demo"]) and not ("not" in t or "neither" in t):
                    next_step_id = "step_subdivision_permit_required_result"
                elif any(w in t for w in ["neither", "not part", "no subdivision", "not subdivision"]):
                    next_step_id = "step_permit_not_required_result"
        next_step = flow.steps.get(next_step_id)

        if not next_step:
            return False, f"Destination step '{next_step_id}' does not exist.", None, None

        session.current_step_id = next_step_id

        # Check if destination step completes the flow
        if next_step.type in ["procedure_result", "disqualification"] or not next_step.options:
            session.completed = True

        # Check if destination step is form issuance
        if next_step.type == "form_issuance":
            session.completed = True
            form_packet = self._build_form_packet(session, next_step)
            session.form_packet = form_packet
            return True, "Form issued successfully.", next_step, form_packet

        return True, "Step advanced.", next_step, None

flow_engine = FlowEngine()
