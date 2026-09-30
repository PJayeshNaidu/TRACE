"""Pydantic schemas for F05 Impact Analysis REST API."""

from __future__ import annotations

import uuid
from typing import Any
from pydantic import BaseModel, Field


class LLMConfigPayload(BaseModel):
    """Configuration for optional OpenRouter LLM reasoning."""

    enabled: bool = False
    api_key: str | None = None
    model: str = "anthropic/claude-3.5-sonnet"


class EvaluateImpactRequest(BaseModel):
    """Request payload to trigger impact analysis."""

    repository_id: uuid.UUID
    base_ref: str | None = Field(default=None, description="Base branch, commit SHA, or tag")
    target_ref: str | None = Field(default=None, description="Target branch, commit SHA, or tag")
    llm_config: LLMConfigPayload | None = None


class CallerAtRiskSchema(BaseModel):
    """Upstream caller reached via transposed graph traversal."""

    qualified_name: str
    file_path: str
    distance: int
    call_chain: list[str] = Field(default_factory=list)


class DetailedImpactSchema(BaseModel):
    """Detailed per-entity impact record."""

    file: str
    entity: str
    entity_type: str
    lines_affected: list[int]
    diff_snippet: str
    change_summary: str
    remediation_guidance: str
    justification: str
    outbound_calls: list[str] = Field(default_factory=list)
    inbound_callers: list[str] = Field(default_factory=list)
    callers_at_risk: list[CallerAtRiskSchema] = Field(default_factory=list)
    downstream_dependent_files: list[str] = Field(default_factory=list)


class GraphNodeSchema(BaseModel):
    """Node in dependency graph."""

    changed_entity: str
    file: str
    downstream_dependent_files: list[str] = Field(default_factory=list)
    inbound_callers: list[str] = Field(default_factory=list)
    outbound_calls: list[str] = Field(default_factory=list)


class GraphEdgeSchema(BaseModel):
    """Directed edge in dependency graph."""

    caller: str
    callee: str
    relationship: str = "direct_call"


class DependencyGraphSchema(BaseModel):
    """Unified graph schema with styled Mermaid string."""

    nodes: list[GraphNodeSchema] = Field(default_factory=list)
    edges: list[GraphEdgeSchema] = Field(default_factory=list)
    mermaid: str


class RiskFactorSchema(BaseModel):
    """Individual contributing risk factor."""

    factor: str
    severity: str
    justification: str


class RemediationStepSchema(BaseModel):
    """A prioritized action item for developers."""

    step_number: int
    category: str
    action_description: str
    affected_targets: list[str] = Field(default_factory=list)


class RiskAnalysisSchema(BaseModel):
    """Complete risk profile and remediation plan."""

    risk_level: str
    key_risk_factors: list[RiskFactorSchema] = Field(default_factory=list)
    ci_cd_recommendations: list[str] = Field(default_factory=list)
    actionable_remediation_plan: list[RemediationStepSchema] = Field(default_factory=list)


class AnalysisMetadataSchema(BaseModel):
    """Run metadata and entity counts."""

    analysis_id: uuid.UUID
    repository: str
    base_commit: str
    current_commit: str
    reasoning_mode: str
    total_changed_entities: int
    total_deleted_files: int
    total_impacted_downstream_files: int
    total_callers_at_risk: int


class ImpactAnalysisResponse(BaseModel):
    """Unified 4-key JSON schema response."""

    analysis_metadata: AnalysisMetadataSchema
    impact_analysis: dict[str, Any]
    dependency_graph: DependencyGraphSchema
    risk_analysis: RiskAnalysisSchema
