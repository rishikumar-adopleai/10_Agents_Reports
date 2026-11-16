"""Event Contracts and Event Dispatcher."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class EventContract(BaseModel):
    """Standard Event Envelope conforming to Section 5 of the Implementation Plan."""

    event_id: str
    schema_version: str = "1.0"
    event_type: str
    organization_id: str
    account_id: Optional[str] = None
    contact_id: Optional[str] = None
    workflow_id: Optional[str] = None
    task_id: Optional[str] = None
    occurred_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    correlation_id: str
    payload: Dict[str, Any] = Field(default_factory=dict)


# Standard Domain Event Names
ACCOUNT_PRIORITIZED = "account.prioritized"
RESEARCH_COMPLETED = "research.completed"
DEMO_READY = "demo.ready"
OUTREACH_APPROVED = "outreach.approved"
MESSAGE_RECEIVED = "message.received"
MEETING_CONFIRMED = "meeting.confirmed"
DISCOVERY_COMPLETED = "discovery.completed"
SECURITY_REVIEW_REQUESTED = "security_review.requested"
DELIVERY_MILESTONE_VERIFIED = "delivery_milestone.verified"
PROOF_APPROVED = "proof.approved"
REVIVAL_REVIEW_REQUESTED = "revival.review_requested"
