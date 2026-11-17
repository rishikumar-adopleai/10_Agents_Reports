"""Central Approval Center Service."""

from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.exceptions import (
    NotFoundError,
    PermissionDeniedError,
)
from backend.app.core.rbac import CurrentUser, RoleEnum
from backend.app.models.governance import ApprovalItem
from backend.app.repositories.governance_repo import ApprovalRepository


class ApprovalService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = ApprovalRepository(session)

    async def create_approval_request(
        self,
        organization_id: str,
        account_id: str,
        artifact_type: str,
        artifact_id: str,
        requested_action: str,
        draft_content: str,
        contact_id: Optional[str] = None,
        source_evidence: Optional[Dict[str, Any]] = None,
        risk_flags: Optional[List[str]] = None,
        due_at: Optional[str] = None,
    ) -> ApprovalItem:
        """Create a required approval item before customer-facing transmission."""
        item = ApprovalItem(
            organization_id=organization_id,
            account_id=account_id,
            contact_id=contact_id,
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            requested_action=requested_action,
            draft_content=draft_content,
            source_evidence=source_evidence or {},
            risk_flags=risk_flags or [],
            status="pending",
            due_at=due_at,
        )
        return await self.repo.create(item)

    async def list_pending_approvals(self, organization_id: str) -> List[ApprovalItem]:
        return await self.repo.list_pending(organization_id=organization_id)

    async def get_approval_by_id(self, approval_id: str) -> ApprovalItem:
        item = await self.repo.get_by_id(approval_id)
        if not item:
            raise NotFoundError(f"Approval item {approval_id} not found")
        return item

    async def process_decision(
        self,
        approval_id: str,
        decision: str,  # approved, edited_approved, rejected, revision_requested, taken_over
        current_user: CurrentUser,
        edited_content: Optional[str] = None,
        feedback: Optional[str] = None,
    ) -> ApprovalItem:
        """Process human reviewer decision with role-based checks."""
        item = await self.get_approval_by_id(approval_id)

        # Enforce specific domain authorization rules from the plan:
        # Commercial proposals require SALES_MANAGER
        if item.artifact_type == "proposal" and decision in ["approved", "edited_approved"]:
            if not current_user.has_role(RoleEnum.SALES_MANAGER):
                raise PermissionDeniedError(
                    "Commercial proposal approvals strictly require SALES_MANAGER role.",
                    details={"artifact_type": "proposal"},
                )

        # Security attestations require SECURITY_REVIEWER
        if item.artifact_type == "security_answer" and decision in ["approved", "edited_approved"]:
            if not current_user.has_role(RoleEnum.SECURITY_REVIEWER):
                raise PermissionDeniedError(
                    "Security attestations strictly require SECURITY_REVIEWER role.",
                    details={"artifact_type": "security_answer"},
                )

        item.status = decision
        item.reviewed_by_user_id = current_user.id
        item.review_feedback = feedback
        if edited_content and decision == "edited_approved":
            item.draft_content = edited_content

        await self.repo.update(
            item,
            {
                "status": item.status,
                "reviewed_by_user_id": item.reviewed_by_user_id,
                "review_feedback": item.review_feedback,
                "draft_content": item.draft_content,
            },
        )
        return item

    async def invalidate_stale_response_approval(self, contact_id: str) -> int:
        """If a lead replies with a new message, prior pending draft approvals are invalidated."""
        from sqlalchemy import update

        stmt = (
            update(ApprovalItem)
            .where(
                ApprovalItem.contact_id == contact_id,
                ApprovalItem.artifact_type == "lead_reply",
                ApprovalItem.status == "pending",
            )
            .values(
                status="expired", review_feedback="Invalidated by new incoming message from lead"
            )
        )
        result = await self.session.execute(stmt)
        return result.rowcount
