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

class FlowEngine:
    def __init__(self):
        self.sessions: Dict[str, FlowSession] = {}

    def get_session(self, session_id: str) -> Optional[FlowSession]:
        return self.sessions.get(session_id)

    def reset_session(self, session_id: str):
        if session_id in self.sessions:
            del self.sessions[session_id]

    def start_flow(self, session_id: str, department_id: str, flow_id: str) -> Tuple[bool, str, Optional[FlowStep], Optional[FormIssuanceDetails]]:
        flow = registry.get_flow(department_id, flow_id)
        if not flow:
            # Try searching across all departments
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

        return True, "Procedure initiated.", current_step, None

    def advance_step(self, session_id: str, option_id: str) -> Tuple[bool, str, Optional[FlowStep], Optional[FormIssuanceDetails]]:
        session = self.get_session(session_id)
        if not session:
            return False, "No active procedure found. Please select a procedure to start.", None, None

        flow = registry.get_flow(session.department_id, session.flow_id)
        if not flow:
            return False, "Flow definition not found.", None, None

        current_step = flow.steps.get(session.current_step_id)
        if not current_step:
            return False, "Current step is invalid.", None, None

        # Find matching option
        matched_option = None
        if current_step.options:
            for opt in current_step.options:
                if opt.id == option_id:
                    matched_option = opt
                    break

        if not matched_option:
            return False, f"Invalid choice '{option_id}' for current step '{current_step.title}'.", current_step, None

        # Record history
        session.history.append({
            "step_id": session.current_step_id,
            "option_id": option_id,
            "option_label": matched_option.label
        })

        next_step_id = matched_option.next_step
        next_step = flow.steps.get(next_step_id)

        if not next_step:
            return False, f"Destination step '{next_step_id}' does not exist.", None, None

        session.current_step_id = next_step_id

        # Check if destination step is form issuance
        if next_step.type == "form_issuance":
            session.completed = True
            dept_config = registry.get_department(session.department_id)

            # Build FormIssuanceDetails
            download_url = f"/api/forms/{session.department_id}/{next_step.form_file}"
            
            sub_routing = next_step.submission_routing
            if not sub_routing and dept_config:
                sub_routing = SubmissionRouting(
                    department=dept_config.name,
                    desk="Engineering Division",
                    digital_upload_url="https://www.edisonnj.org/document_center/index.php"
                )

            form_packet = FormIssuanceDetails(
                form_code=next_step.form_code or "OFFICIAL FORM",
                form_title=next_step.form_title or "Standardized Municipal Application",
                form_file=next_step.form_file or "document.pdf",
                pdf_download_url=download_url,
                department_id=session.department_id,
                fill_in_instructions=next_step.fill_in_instructions or "Complete all marked fields and sign in ink.",
                required_attachments=next_step.required_attachments or [],
                fee_info=next_step.fee_info,
                submission_routing=sub_routing,
                lead_time=next_step.lead_time or "5 to 10 business days"
            )
            session.form_packet = form_packet
            return True, "Form issued successfully.", next_step, form_packet

        return True, "Step advanced.", next_step, None

flow_engine = FlowEngine()
