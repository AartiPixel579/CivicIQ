from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field

class FormField(BaseModel):
    name: str = Field(..., description="Unique machine identifier for this field")
    label: str = Field(..., description="Citizen-facing question or field label")
    field_type: str = Field(default="text", description="text | address | phone | email | number | choice | date")
    required: bool = Field(default=True, description="Whether the field is mandatory")
    options: Optional[List[str]] = Field(default=None, description="Available choices if choice type")
    help_text: Optional[str] = Field(default=None, description="Helpful guidance for the citizen")
    validation_regex: Optional[str] = Field(default=None, description="Optional regex for validation")
    conditional_on: Optional[Dict[str, Any]] = Field(default=None, description="Conditional visibility rule")
    placeholder: Optional[str] = None

class FormMetadata(BaseModel):
    form_id: str
    official_title: str
    form_code: str
    department: str = "engineering"
    application_type: str = Field(..., description="Application form | Permit application | Information sheet | Fee schedule | Flowchart")
    description: str
    official_source_url: str
    local_filename: Optional[str] = None
    fields: List[FormField] = Field(default_factory=list)
    signature_required: bool = True
    signature_instructions: str = "Must be physically signed in ink by property owner or authorized agent after printing."
    supporting_documents: List[str] = Field(default_factory=list)
    submission_method: str = "Submit via official municipal portal or physical counter with required attachments."
    fee_info: Optional[str] = None
    is_verified: bool = True
    last_verified_date: str = "2026-11-04"

class FormRecommendation(BaseModel):
    form: FormMetadata
    confidence_score: float
    reason: str
    is_application_form: bool
    offer_conversational_fill: bool = True
