from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class Severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class Signal(BaseModel):
    """A raw telemetry/log event that may indicate an incident."""

    service: str
    metric: str
    value: float
    threshold: float
    message: str
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Detection(BaseModel):
    is_anomaly: bool
    affected_service: str
    severity: Severity
    summary: str
    confidence: float = Field(ge=0, le=1)


class Diagnosis(BaseModel):
    root_cause: str
    evidence: list[str]
    confidence: float = Field(ge=0, le=1)
    recommended_action_type: str


class Verification(BaseModel):
    resolved: bool
    summary: str
    notes: str | None = None


class ProposedFix(BaseModel):
    """A code change the agent proposes to fix a CI failure. The LLM fills this
    in; opening it as a PR is a gated side effect (see RemediationActionType.
    OPEN_PR), so the human reviews this before it ever touches the repo."""

    file_path: str
    new_content: str
    pr_title: str
    pr_body: str
    rationale: str
