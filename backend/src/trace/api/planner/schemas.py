"""Pydantic v2 schemas for F07 Upgrade Planner API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class LLMConfigSchema(BaseModel):
    """Optional LLM configuration parameters."""

    enabled: bool = False
    api_key: str | None = None
    model: str | None = "mistralai/mistral-7b-instruct:free"


class GenerateUpgradePlanRequest(BaseModel):
    """Request payload to generate an upgrade plan."""

    repository_id: uuid.UUID
    impact_analysis_id: uuid.UUID | None = None
    base_ref: str = Field(default="HEAD~1", description="Base commit / branch / tag")
    target_ref: str = Field(default="HEAD", description="Target commit / branch / tag")
    title: str | None = Field(
        default=None, description="Optional custom title for the upgrade plan"
    )
    llm_config: LLMConfigSchema | None = None


class TaskEvidenceSchema(BaseModel):
    """Evidence details supporting task generation."""

    diff_snippet: str = ""
    lines_affected: list[int] = Field(default_factory=list)
    call_chain: list[str] = Field(default_factory=list)
    file_path: str = ""
    target_symbol: str = ""


class UpgradeTaskResponse(BaseModel):
    """Complete representation of an individual upgrade task."""

    id: uuid.UUID
    plan_id: uuid.UUID
    step_number: int
    component: str
    component_type: str
    category: str
    reason: str
    dependencies: list[str] = Field(default_factory=list)
    expected_changes: str = ""
    required_tests: list[str] = Field(default_factory=list)
    risk_level: str = "LOW"
    status: str = "PENDING"
    is_circular: bool = False
    parallel_group_id: int = 1
    notes: str | None = None
    evidence: TaskEvidenceSchema | None = None
    actionability: str = "UPGRADE"
    action_type: str = "REQUIRED_CHANGE"
    tier_name: str = ""
    tier_meaning: str = ""
    change_significance: str | None = None
    ai_confidence: str | None = None
    ai_review: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class InformationalChangeSchema(BaseModel):
    """Representation of non-behavioral documentation/comment/config changes."""

    component: str
    file_path: str
    category: str
    reason: str
    diff_snippet: str = ""
    actionability: str = "INFORMATIONAL"


class AIPlanReviewSchema(BaseModel):
    """Comprehensive whole-plan AI architectural peer review."""

    sequence_valid: bool = True
    confidence: float | str = 1.0
    warnings: list[str] = Field(default_factory=list)
    unnecessary_tasks: list[dict[str, Any]] = Field(default_factory=list)
    missing_task_suggestions: list[dict[str, Any]] = Field(default_factory=list)
    test_recommendations: list[dict[str, Any]] = Field(default_factory=list)
    actionability_reviews: list[dict[str, Any]] = Field(default_factory=list)


class SummaryMetricsSchema(BaseModel):
    """Progress metrics for an upgrade plan."""

    total_tasks: int = 0
    completed_tasks: int = 0
    in_progress_tasks: int = 0
    pending_tasks: int = 0
    blocked_tasks: int = 0
    skipped_tasks: int = 0
    progress_percentage: float = 0.0


class UpgradePlanResponse(BaseModel):
    """Complete upgrade plan response payload including task DAG and progress metrics."""

    id: uuid.UUID
    repository_id: uuid.UUID
    impact_analysis_id: uuid.UUID
    title: str
    base_commit: str
    target_commit: str
    risk_level: str
    status: str
    reasoning_mode: str
    change_significance: str = "MODERATE_CHANGE"
    significance_reasoning: str = ""
    recommended_action: str = ""
    order_rationale: str = ""
    optional_suggestions: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    summary_metrics: SummaryMetricsSchema
    informational_changes: list[InformationalChangeSchema] = Field(default_factory=list)
    ai_plan_review: AIPlanReviewSchema | dict[str, Any] | None = None
    tasks: list[UpgradeTaskResponse] = Field(default_factory=list)


class UpdateTaskStatusRequest(BaseModel):
    """Request payload to update task lifecycle status and notes."""

    status: str = Field(
        ..., description="Target status: PENDING, IN_PROGRESS, COMPLETED, BLOCKED, SKIPPED"
    )
    notes: str | None = None


class UpgradeTaskListResponse(BaseModel):
    """Paginated list of upgrade tasks."""

    plan_id: uuid.UUID
    total: int
    limit: int
    offset: int
    items: list[UpgradeTaskResponse]


class UpgradePlanSummaryItem(BaseModel):
    """Summary item for listing historical plans."""

    id: uuid.UUID
    title: str
    base_commit: str
    target_commit: str
    risk_level: str
    status: str
    total_tasks: int
    completed_tasks: int
    progress_percentage: float
    created_at: datetime


class UpgradePlanListResponse(BaseModel):
    """List of upgrade plans for a repository."""

    repository_id: uuid.UUID
    total: int
    items: list[UpgradePlanSummaryItem]
