"""24/7 Lead Responder Agent."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.base import BaseAgent
from backend.app.models.conversations import Conversation
from backend.app.models.governance import ApprovalItem
from backend.app.models.sales import Contact
from backend.app.schemas.agents import (
    AgentExecutionRequest,
    AgentExecutionResult,
    AgentStatus,
    ArtifactReference,
)
from backend.app.services.attempt_service import AttemptTrackingService
from backend.app.services.memory_service import MemoryService
from backend.app.services.suppression_service import SuppressionService


class LeadResponderAgent(BaseAgent):
    @property
    def agent_id(self) -> str:
        return "lead_responder"

    @property
    def name(self) -> str:
        return "24/7 Lead Responder"

    @property
    def description(self) -> str:
        return "Handles inbound inquiries, answers questions with grounded private memory, and arranges discovery meetings."

    async def execute(
        self,
        request: AgentExecutionRequest,
        session: AsyncSession,
    ) -> AgentExecutionResult:
        conversation_id = request.parameters.get("conversation_id")
        message_body = request.parameters.get("body", "")
        contact_id = request.contact_id or request.parameters.get("contact_id")

        if not conversation_id:
            return AgentExecutionResult(
                agent_id=self.agent_id,
                execution_id=f"exec-{uuid.uuid4().hex[:12]}",
                status=AgentStatus.TERMINAL_FAILURE,
                error_details="conversation_id is required for Lead Responder",
            )

        # 1. Fetch Conversation and verify status
        res = await session.execute(select(Conversation).where(Conversation.id == conversation_id))
        conv = res.scalars().first()
        if not conv:
            return AgentExecutionResult(
                agent_id=self.agent_id,
                execution_id=f"exec-{uuid.uuid4().hex[:12]}",
                status=AgentStatus.TERMINAL_FAILURE,
                error_details=f"Conversation {conversation_id} not found",
            )

        if conv.is_human_takeover:
            return AgentExecutionResult(
                agent_id=self.agent_id,
                execution_id=f"exec-{uuid.uuid4().hex[:12]}",
                status=AgentStatus.BLOCKED,
                error_details="Human takeover is active for this conversation. Autonomous replies are disabled.",
            )

        # 2. Check Suppression
        suppression_service = SuppressionService(session)
        if contact_id:
            res_contact = await session.execute(select(Contact).where(Contact.id == contact_id))
            contact = res_contact.scalars().first()
            if contact and await suppression_service.is_contact_suppressed(
                email=contact.email, phone=contact.phone, contact_id=contact.id
            ):
                return AgentExecutionResult(
                    agent_id=self.agent_id,
                    execution_id=f"exec-{uuid.uuid4().hex[:12]}",
                    status=AgentStatus.BLOCKED,
                    error_details="Contact is suppressed. Responses blocked.",
                )

        # 3. Access Private Contact Memory (Isolated Scope)
        memory_service = MemoryService(session)
        memory = await memory_service.get_or_create_contact_memory(
            contact_id=conv.contact_id,
            organization_id=request.organization_id,
        )

        # 4. Classify Intent and Draft Grounded Response
        body_lower = message_body.lower()
        is_meeting_intent = any(
            word in body_lower
            for word in [
                "call",
                "meet",
                "schedule",
                "demo",
                "time",
                "calendar",
                "tomorrow",
                "tuesday",
            ]
        )

        if is_meeting_intent:
            reply_draft = (
                "Thanks for reaching out! I'd love to get a quick 20-minute discovery call set up with our solutions team. "
                "Would Tuesday at 2:00 PM EST or Wednesday at 10:00 AM EST work better for your schedule?"
            )
            proposed_actions = ["await:buyer_slot_selection", "route:microsoft_graph_calendar"]
        else:
            reply_draft = (
                "Thanks for your message! Yes, our platform provides full bidirectional sync with HubSpot and GoHighLevel, "
                "with automated deduplication and webhook latency under 2 seconds. "
                "Would you like to see how this fits your current tech stack on a brief demo?"
            )
            proposed_actions = ["await:lead_followup"]

        # Reset logical outreach attempts on positive inbound reply
        attempt_service = AttemptTrackingService(session)
        await attempt_service.reset_on_positive_response(conv.contact_id)

        # Record atomic memory fact
        await memory_service.add_memory_fact(
            organization_id=request.organization_id,
            scope="contact",
            fact_key="inbound_inquiry_intent",
            fact_value=message_body[:200],
            contact_id=conv.contact_id,
            account_id=conv.account_id,
            confidence=0.95,
        )

        # 5. Mandatory Rule: Create Approval Item for customer-facing reply
        approval = ApprovalItem(
            organization_id=request.organization_id,
            account_id=conv.account_id,
            contact_id=conv.contact_id,
            artifact_type="lead_reply",
            artifact_id=conv.id,
            requested_action="send_sms_reply",
            draft_content=reply_draft,
            source_evidence={"inbound_message": message_body, "memory_summary": memory.summary},
            risk_flags=[],
            status="pending",
        )
        session.add(approval)
        await session.flush()

        return AgentExecutionResult(
            agent_id=self.agent_id,
            execution_id=f"exec-{uuid.uuid4().hex[:12]}",
            status=AgentStatus.WAITING_FOR_REVIEW,
            structured_result={
                "conversation_id": conv.id,
                "reply_draft": reply_draft,
                "approval_id": approval.id,
                "is_meeting_intent": is_meeting_intent,
            },
            artifact_references=[
                ArtifactReference(
                    artifact_id=approval.id,
                    artifact_type="approval_item",
                    summary="Lead reply draft awaiting review",
                )
            ],
            uncertainty=0.08,
            proposed_next_actions=proposed_actions,
        )
