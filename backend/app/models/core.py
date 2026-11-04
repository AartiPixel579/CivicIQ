from typing import List, Dict, Optional, Any, Union
from pydantic import BaseModel, Field

# --- Department Models ---
class DepartmentLocation(BaseModel):
    building: str
    floor: str
    counter: str
    address: str

class DepartmentOperatingHours(BaseModel):
    weekdays: str
    intake_cutoff: Optional[str] = None
    weekends: Optional[str] = None

class DepartmentContact(BaseModel):
    email: str
    phone: str
    hotline: Optional[str] = None

class SubmissionChannel(BaseModel):
    type: str
    name: str
    details: str

class DepartmentConfig(BaseModel):
    id: str
    name: str
    short_name: str
    badge: str
    icon: Optional[str] = "Building"
    description: str
    location: DepartmentLocation
    operating_hours: DepartmentOperatingHours
    contact: DepartmentContact
    submission_channels: List[SubmissionChannel] = []
    standard_processing_time: str
    status: Optional[str] = "active"
    active: Optional[bool] = True

# --- Knowledge Link Models ---
class KnowledgeLink(BaseModel):
    url: str
    title: str
    category: Optional[str] = "General"
    summary: Optional[str] = ""
    content: Optional[str] = ""

# --- Flowchart Engine Models ---
class FlowOption(BaseModel):
    id: str
    label: str
    description: Optional[str] = None
    next_step: str

class FeeInfo(BaseModel):
    amount: str
    payment_methods: str

class SubmissionRouting(BaseModel):
    department: str
    desk: str
    building_address: Optional[str] = None
    hours: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    digital_upload_url: Optional[str] = "https://www.edisonnj.org/document_center/index.php"

class FormIssuanceDetails(BaseModel):
    form_code: str
    form_title: str
    form_file: str
    pdf_download_url: str
    department_id: str
    fill_in_instructions: str
    required_attachments: List[str]
    fee_info: Optional[FeeInfo] = None
    submission_routing: SubmissionRouting
    lead_time: str
    visibility: str = "public"
    document_type: str = "application_form"
    service: Optional[str] = None
    verification_status: str = "verified"

class FlowStep(BaseModel):
    id: str
    type: str # 'question' | 'prerequisite_check' | 'form_issuance' | 'disqualification'
    title: str
    message: str
    help_text: Optional[str] = None
    is_mandatory_prerequisite: Optional[bool] = False
    options: Optional[List[FlowOption]] = None
    alternative_action: Optional[str] = None
    # If form_issuance:
    form_code: Optional[str] = None
    form_title: Optional[str] = None
    form_file: Optional[str] = None
    department_id: Optional[str] = None
    fill_in_instructions: Optional[str] = None
    required_attachments: Optional[List[str]] = None
    fee_info: Optional[FeeInfo] = None
    submission_routing: Optional[SubmissionRouting] = None
    lead_time: Optional[str] = None
    official_source_url: Optional[str] = None

class FlowDefinition(BaseModel):
    id: str
    title: str
    code: str
    category: str
    description: str
    initial_step: str
    steps: Dict[str, FlowStep]

# --- RAG Models ---
class RagCitation(BaseModel):
    url: str
    title: str
    category: str
    department_id: str
    relevance_score: float
    excerpt: str
    visibility: str = "public"
    document_type: Optional[str] = "guideline"
    service: Optional[str] = None
    verification_status: str = "verified"

class RagResult(BaseModel):
    answer: str
    citations: List[RagCitation]
    grounded: bool
    query: str
    form_packet: Optional[FormIssuanceDetails] = None

# --- Chat & Session Models ---
class ChatMessage(BaseModel):
    sender: str # 'user' | 'assistant' | 'system'
    text: str
    timestamp: Optional[str] = None
    options: Optional[List[FlowOption]] = None
    form_packet: Optional[FormIssuanceDetails] = None
    citations: Optional[List[RagCitation]] = None
    flow_step_info: Optional[Dict[str, Any]] = None

class ChatRequest(BaseModel):
    session_id: str
    message: str
    department_id: Optional[str] = None
    selected_option_id: Optional[str] = None

class FlowStartRequest(BaseModel):
    session_id: str
    department_id: str
    flow_id: str

class FlowStepRequest(BaseModel):
    session_id: str
    option_id: str

class ChatResponse(BaseModel):
    session_id: str
    message: str
    mode: str # 'flow' | 'rag' | 'general' | 'form_fill'
    options: Optional[List[FlowOption]] = None
    form_packet: Optional[FormIssuanceDetails] = None
    citations: Optional[List[RagCitation]] = None
    current_step: Optional[FlowStep] = None
    active_flow_id: Optional[str] = None
    department_id: Optional[str] = None
    completed: Optional[bool] = False
    pdf_download_url: Optional[str] = None
    submission_guidance: Optional[Dict[str, Any]] = None
    form_recommendation: Optional[Dict[str, Any]] = None
    form_session_info: Optional[Dict[str, Any]] = None
