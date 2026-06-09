from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field

from app.schemas.incident import Detection, Diagnosis, Signal, Verification
from app.tools.schemas import ApprovalDecision, RemediationPlan, RemediationResult


class IncidentStatus(str, Enum):
    DETECTED = "detected"
    DIAGNOSING = "diagnosing"
    PLANNED = "planned"
    AWAITING_APPROVAL = "awaiting_approval"
    REJECTED = "rejected"
    REMEDIATING = "remediating"
    VERIFYING = "verifying"
    RESOLVED = "resolved"
    FAILED = "failed"


class AuditEvent(BaseModel):
    at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    actor: str
    event: str
    detail: str | None = None


class IncidentState(BaseModel):
    """The single source of truth that flows through the agent graph.

    Externalised (Redis/Postgres in prod) so agent workers stay stateless and
    horizontally scalable."""

    id: str = Field(default_factory=lambda: f"inc-{uuid4().hex[:8]}")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: IncidentStatus = IncidentStatus.DETECTED

    signal: Signal
    detection: Detection | None = None
    diagnosis: Diagnosis | None = None
    plan: RemediationPlan | None = None
    approval: ApprovalDecision | None = None
    remediation_results: list[RemediationResult] = Field(default_factory=list)
    verification: Verification | None = None

    audit: list[AuditEvent] = Field(default_factory=list)

    def log(self, actor: str, event: str, detail: str | None = None) -> None:
        self.audit.append(AuditEvent(actor=actor, event=event, detail=detail))
