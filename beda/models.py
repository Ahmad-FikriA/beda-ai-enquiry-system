from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CRMRecord(BaseModel):
    id: str
    company: str
    contact: str
    email: str = ""
    phone: str = ""
    location: str = ""
    type: str = ""
    interest: str = ""
    status: str = ""


class Proposal(BaseModel):
    category: str
    confidence: str = "HIGH"  # HIGH, MEDIUM, LOW
    extracted_fields: Dict[str, Any] = Field(default_factory=dict)
    missing_fields: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    recommended_owner: Optional[str] = None
    recommended_action: Optional[str] = None
    rationale: Optional[str] = None


class MatchCandidate(BaseModel):
    crm_id: str
    company: str = ""
    contact: str = ""
    email: Optional[str] = None
    phone: Optional[str] = None
    score: float = 0.0
    match_reasons: List[str] = Field(default_factory=list)
    ambiguous: bool = False


class Recommendation(BaseModel):
    action: str
    owner: str
    confidence: str = "HIGH"
    requires_approval: bool = True
    explanation: str = ""
    target_crm_id: Optional[str] = None


class Action(BaseModel):
    id: str
    enquiry_id: str
    action_type: str
    idempotency_key: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    status: str = "PENDING_APPROVAL"  # PENDING_APPROVAL, PENDING, RUNNING, SUCCEEDED, FAILED_RETRYABLE, FAILED_FINAL
    attempt_count: int = 0
    max_attempts: int = 3
    last_error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class AuditEvent(BaseModel):
    id: Optional[int] = None
    enquiry_id: str
    event_type: str
    actor: str
    details: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now_iso)


class Enquiry(BaseModel):
    id: str
    source_message_id: str
    sender: Optional[str] = None
    sender_email: Optional[str] = None
    sender_name: Optional[str] = None
    subject: str = ""
    body: str = ""
    attachment_filename: Optional[str] = None
    attachment_content: Optional[str] = None
    received_at: str = Field(default_factory=utc_now_iso)
    status: str = "RECEIVED"
    related_enquiry_id: Optional[str] = None
    proposal: Optional[Proposal] = None
    match_candidates: List[MatchCandidate] = Field(default_factory=list)
    recommendation: Optional[Recommendation] = None
    draft_response: Optional[str] = None
    raw_payload: Optional[Dict[str, Any]] = None
