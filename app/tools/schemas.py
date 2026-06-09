from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class RemediationActionType(str, Enum):
    RESTART_SERVICE = "restart_service"
    SCALE_UP = "scale_up"
    ROLLBACK = "rollback"
    CLEAR_CACHE = "clear_cache"
    NONE = "none"


class RemediationAction(BaseModel):
    action: RemediationActionType
    target: str
    params: dict = Field(default_factory=dict)
    rationale: str
    risk: str  # low | medium | high


class RemediationPlan(BaseModel):
    summary: str
    requires_approval: bool = True
    actions: list[RemediationAction]


class ApprovalDecision(BaseModel):
    approved: bool
    approver: str
    reason: str | None = None


class RemediationResult(BaseModel):
    action: RemediationAction
    success: bool
    output: str
