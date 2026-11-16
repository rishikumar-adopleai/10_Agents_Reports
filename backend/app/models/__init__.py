"""SQLAlchemy Models Registry."""

from backend.app.db.base import Base, BaseModel
from backend.app.models.artifacts import (
    BuyingSignal,
    DemoArtifact,
    EvidenceRef,
    ProofAsset,
    ProposalArtifact,
    ResearchBrief,
    SecurityQuestionnaire,
)
from backend.app.models.conversations import (
    Conversation,
    Message,
    OutreachAttempt,
    SuppressionEntry,
)
from backend.app.models.execution import (
    AgentTask,
    DomainEvent,
    IntegrationAttempt,
    OutboxEvent,
    WorkflowRun,
)
from backend.app.models.governance import (
    ApprovalItem,
    AuditEvent,
    ClientPermission,
    PolicyVersion,
    RetentionAction,
)
from backend.app.models.identity import (
    Membership,
    Organization,
    RecordGrant,
    RefreshTokenRevocation,
    Role,
    User,
    user_roles,
)
from backend.app.models.intelligence import (
    ContactMemory,
    EvaluationRun,
    KnowledgeVersion,
    LearningCandidate,
    LearningRelease,
    MemoryFact,
    ResponseFeedback,
)
from backend.app.models.sales import (
    Account,
    Campaign,
    Contact,
    Opportunity,
    Partner,
    Referral,
)

__all__ = [
    "Base",
    "BaseModel",
    "Organization",
    "Role",
    "User",
    "Membership",
    "RecordGrant",
    "RefreshTokenRevocation",
    "user_roles",
    "Account",
    "Contact",
    "Campaign",
    "Opportunity",
    "Partner",
    "Referral",
    "Conversation",
    "Message",
    "OutreachAttempt",
    "SuppressionEntry",
    "AgentTask",
    "WorkflowRun",
    "DomainEvent",
    "OutboxEvent",
    "IntegrationAttempt",
    "ResearchBrief",
    "BuyingSignal",
    "DemoArtifact",
    "ProposalArtifact",
    "SecurityQuestionnaire",
    "ProofAsset",
    "EvidenceRef",
    "MemoryFact",
    "ContactMemory",
    "KnowledgeVersion",
    "ResponseFeedback",
    "LearningCandidate",
    "EvaluationRun",
    "LearningRelease",
    "ApprovalItem",
    "ClientPermission",
    "PolicyVersion",
    "AuditEvent",
    "RetentionAction",
]
