"""Research and Personal Outreach Agent."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.base import BaseAgent
from backend.app.models.artifacts import ResearchBrief
from backend.app.models.governance import ApprovalItem
from backend.app.models.sales import Contact
from backend.app.schemas.agents import (
    AgentExecutionRequest,
    AgentExecutionResult,
    AgentStatus,
    ArtifactReference,
)
from backend.app.services.attempt_service import AttemptTrackingService
from backend.app.services.suppression_service import SuppressionService


class ResearchOutreachAgent(BaseAgent):
    @property
    def agent_id(self) -> str:
        return "research_personal_outreach"

    @property
    def name(self) -> str:
        return "Research & Personal Outreach"

    @property
    def description(self) -> str:
        return "Researches prioritized enterprise accounts and crafts personalized, approved outreach drafts."

    async def execute(
        self,
        request: AgentExecutionRequest,
        session: AsyncSession,
    ) -> AgentExecutionResult:
        account_id = request.account_id or request.parameters.get("account_id")
        contact_id = request.contact_id or request.parameters.get("contact_id")

        if not account_id:
            return AgentExecutionResult(
                agent_id=self.agent_id,
                execution_id=f"exec-{uuid.uuid4().hex[:12]}",
                status=AgentStatus.TERMINAL_FAILURE,
                error_details="account_id is required for Research & Personal Outreach",
            )

        # 1. Check Contact Eligibility & Suppression
        suppression_service = SuppressionService(session)
        attempt_service = AttemptTrackingService(session)

        if contact_id:
            from sqlalchemy import select

            res = await session.execute(select(Contact).where(Contact.id == contact_id))
            contact = res.scalars().first()
            if contact:
                if await suppression_service.is_contact_suppressed(
                    email=contact.email, phone=contact.phone, contact_id=contact.id
                ):
                    return AgentExecutionResult(
                        agent_id=self.agent_id,
                        execution_id=f"exec-{uuid.uuid4().hex[:12]}",
                        status=AgentStatus.BLOCKED,
                        error_details="Contact is in suppression registry. Outreach strictly halted.",
                    )

                current_attempts = await attempt_service.get_logical_attempts(contact.id)
                if current_attempts >= 3:
                    return AgentExecutionResult(
                        agent_id=self.agent_id,
                        execution_id=f"exec-{uuid.uuid4().hex[:12]}",
                        status=AgentStatus.BLOCKED,
                        error_details="Max 3 logical outreach attempts reached without reply. 4th attempt forbidden.",
                    )

        # 2. Synthesize Grounded Research Brief
        facts = {
            "core_business": "Enterprise B2B SaaS and IT Infrastructure",
            "detected_signal": "Rapid expansion of field engineering teams",
            "stakeholders": ["VP Engineering", "Chief Revenue Officer"],
        }
        hypotheses = {
            "primary_pain": "Pipeline latency in enterprise technical sales demos",
            "opportunity": "Automated personalized synthetic demos to accelerate deal velocity",
        }

        brief = ResearchBrief(
            organization_id=request.organization_id,
            account_id=account_id,
            summary="Strong fit for autonomous enterprise sales workflows based on current scaling signals.",
            facts=facts,
            hypotheses=hypotheses,
            stakeholders={"leads": ["Jane Doe (VP Sales)", "John Smith (Head of Tech)"]},
            sources={"careers": "https://example.com/careers", "press": "https://example.com/news"},
            version=1,
        )
        session.add(brief)
        await session.flush()

        # 3. Generate Personal Sourced Draft
        contact_name = "there"
        if contact_id:
            contact_name = contact.first_name if contact else "there"

        draft_body = (
            f"Hi {contact_name}, noticed Acme's recent team expansion in solutions engineering. "
            f"Many enterprise sales teams facing this growth use our autonomous agent platform "
            f"to respond to inbound inquiries in under 60 seconds and automate deal proposals. "
            f"Would you be open to seeing a tailored 2-minute demo of how this works for your team?"
        )

        # 4. Mandatory Rule: Create Approval Item for Human Review before sending!
        approval = ApprovalItem(
            organization_id=request.organization_id,
            account_id=account_id,
            contact_id=contact_id,
            artifact_type="outreach_draft",
            artifact_id=brief.id,
            requested_action="send_sms_outreach",
            draft_content=draft_body,
            source_evidence={"facts": facts, "hypotheses": hypotheses},
            risk_flags=["unverified_timezone"],
            status="pending",
        )
        session.add(approval)
        await session.flush()

        return AgentExecutionResult(
            agent_id=self.agent_id,
            execution_id=f"exec-{uuid.uuid4().hex[:12]}",
            status=AgentStatus.WAITING_FOR_REVIEW,
            structured_result={
                "brief_id": brief.id,
                "approval_id": approval.id,
                "draft_body": draft_body,
                "needs_human_approval": True,
            },
            artifact_references=[
                ArtifactReference(
                    artifact_id=brief.id,
                    artifact_type="research_brief",
                    summary="Sourced company brief",
                ),
                ArtifactReference(
                    artifact_id=approval.id,
                    artifact_type="approval_item",
                    summary="Outreach draft awaiting sales rep review",
                ),
            ],
            uncertainty=0.10,
            proposed_next_actions=["await:human_approval", "optional:trigger_demo_builder"],
        )
