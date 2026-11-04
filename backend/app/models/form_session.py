from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field
from .form import FormField, FormMetadata

class FormSessionState(BaseModel):
    session_id: str
    form_id: str
    status: str = Field(default="in_progress", description="in_progress | review | completed | cancelled")
    current_field_index: int = 0
    answers: Dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str
    generated_pdf_filename: Optional[str] = None
    generated_pdf_url: Optional[str] = None

class FormStartSessionRequest(BaseModel):
    session_id: str
    form_id: str

class FormAnswerRequest(BaseModel):
    session_id: str
    answer: str
    field_name: Optional[str] = None

class FormEditRequest(BaseModel):
    session_id: str
    field_name: str
    new_answer: str

class FormQuestionResponse(BaseModel):
    session_id: str
    form_id: str
    form_title: str
    status: str # in_progress | review | completed
    current_field: Optional[FormField] = None
    current_step: int
    total_steps: int
    message: str
    collected_answers: Dict[str, Any] = Field(default_factory=dict)
    can_edit: bool = True
    is_complete: bool = False
    generated_pdf_url: Optional[str] = None
    submission_guidance: Optional[Dict[str, Any]] = None
