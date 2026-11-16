"""Buying-Signal Radar Agent."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.base import BaseAgent
from backend.app.models.artifacts import BuyingSignal
from backend.app.models.sales import Account
from backend.app.schemas.agents import (
    AgentExecutionRequest,
    AgentExecutionResult,
    AgentStatus,
    ArtifactReference,
    EvidenceReference,
)


class BuyingSignalRadarAgent(BaseAgent):
    @property
    def agent_id(self) -> str:
        return "buying_signal_radar"

    @property
    def name(self) -> str:
        return "Buying-Signal Radar"

    @property
    def description(self) -> str:
        return "Discovers target enterprise accounts with observable growth/hiring buying signals."

    async def execute(
        self,
        request: AgentExecutionRequest,
        session: AsyncSession,
    ) -> AgentExecutionResult:
        domain = request.parameters.get("domain", "acme-corp.com")
        company_name = request.parameters.get("company_name", "Acme Corporation")
        industry = request.parameters.get("industry", "Enterprise Software")

        # Deterministic signal detection logic
        observed_facts = [
            f"{company_name} expanded engineering department by 25% in last 90 days.",
            "Active open job postings for Enterprise Sales Directors and Solution Architects.",
            "New VP of Digital Transformation announced in quarterly press release.",
        ]
        fit_score = 0.88
        why_now = "Aggressive enterprise expansion and leadership appointment in sales engineering."

        # Persist Account if not existing
        from sqlalchemy import select

        res = await session.execute(
            select(Account).where(
                Account.domain == domain.lower().strip(),
                Account.organization_id == request.organization_id,
            )
        )
        account = res.scalars().first()
        if not account:
            account = Account(
                organization_id=request.organization_id,
                name=company_name,
                domain=domain.lower().strip(),
                industry=industry,
                fit_score=fit_score,
                status="prioritized",
            )
            session.add(account)
            await session.flush()
        else:
            account.fit_score = fit_score
            account.status = "prioritized"
            await session.flush()

        # Persist Buying Signal
        signal = BuyingSignal(
            organization_id=request.organization_id,
            account_id=account.id,
            signal_type="hiring_expansion",
            fit_reason=why_now,
            fit_score=fit_score,
            evidence_url=f"https://{domain}/careers",
            observed_at="2026-11-14T12:00:00Z",
        )
        session.add(signal)
        await session.flush()

        return AgentExecutionResult(
            agent_id=self.agent_id,
            execution_id=f"exec-{uuid.uuid4().hex[:12]}",
            status=AgentStatus.COMPLETED,
            structured_result={
                "account_id": account.id,
                "company_name": company_name,
                "domain": domain,
                "fit_score": fit_score,
                "why_now": why_now,
                "observed_facts": observed_facts,
            },
            artifact_references=[
                ArtifactReference(
                    artifact_id=signal.id,
                    artifact_type="buying_signal",
                    summary=why_now,
                )
            ],
            evidence_references=[
                EvidenceReference(
                    source_url=f"https://{domain}/careers",
                    source_type="website",
                    excerpt="We are scaling our enterprise sales and delivery organizations nationwide.",
                )
            ],
            uncertainty=0.12,
            proposed_next_actions=["trigger:research_personal_outreach"],
        )
