"""Domain models for F05: Impact Analysis and Risk Evaluation Engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class RiskLevel(StrEnum):
    """Overall architectural risk tier."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ReasoningMode(StrEnum):
    """Reasoning engine mode used for the analysis run."""

    HEURISTIC = "HEURISTIC"
    LLM_ENRICHED = "LLM_ENRICHED"


@dataclass(frozen=True)
class CallerAtRisk:
    """An upstream caller identified via transposed graph traversal."""

    qualified_name: str
    file_path: str
    distance: int  # Shortest path distance (1, 2, or 3)
    call_chain: tuple[str, ...] = ()


@dataclass(frozen=True)
class DetailedImpact:
    """Detailed impact analysis of a single modified code symbol."""

    file: str
    entity: str
    entity_type: str
    lines_affected: tuple[int, int]
    diff_snippet: str
    change_summary: str
    remediation_guidance: str
    justification: str
    outbound_calls: tuple[str, ...] = ()
    inbound_callers: tuple[str, ...] = ()
    callers_at_risk: tuple[CallerAtRisk, ...] = ()
    downstream_dependent_files: tuple[str, ...] = ()


@dataclass(frozen=True)
class GraphNodePayload:
    """Graph node in the unified dependency graph payload."""

    changed_entity: str
    file: str
    downstream_dependent_files: tuple[str, ...] = ()
    inbound_callers: tuple[str, ...] = ()
    outbound_calls: tuple[str, ...] = ()


@dataclass(frozen=True)
class GraphEdgePayload:
    """Graph edge representing caller-callee invocation."""

    caller: str
    callee: str
    relationship: str = "direct_call"


@dataclass(frozen=True)
class DependencyGraphPayload:
    """Structured dependency graph and styled Mermaid representation."""

    nodes: tuple[GraphNodePayload, ...]
    edges: tuple[GraphEdgePayload, ...]
    mermaid: str


@dataclass(frozen=True)
class RiskFactor:
    """Individual risk contributor with evidence justification."""

    factor: str
    severity: str
    justification: str


@dataclass(frozen=True)
class RemediationStep:
    """A prioritized actionable step for developer remediation."""

    step_number: int
    category: str  # Contract Changes, Missing Modules, Direct Callers, Integration Validation
    action_description: str
    affected_targets: tuple[str, ...] = ()


@dataclass(frozen=True)
class RiskAnalysisPayload:
    """Risk rating, contributing factors, recommendations, and remediation plan."""

    risk_level: RiskLevel
    key_risk_factors: tuple[RiskFactor, ...]
    ci_cd_recommendations: tuple[str, ...]
    actionable_remediation_plan: tuple[RemediationStep, ...]


@dataclass(frozen=True)
class AnalysisMetadataPayload:
    """Metadata summary of the impact evaluation run."""

    analysis_id: UUID
    repository: str
    base_commit: str
    current_commit: str
    reasoning_mode: ReasoningMode
    total_changed_entities: int
    total_deleted_files: int
    total_impacted_downstream_files: int
    total_callers_at_risk: int


@dataclass(frozen=True)
class ImpactAnalysisAggregate:
    """Root domain aggregate for a complete F05 Impact & Risk Evaluation."""

    metadata: AnalysisMetadataPayload
    summary: str
    detailed_impacts: tuple[DetailedImpact, ...]
    dependency_graph: DependencyGraphPayload
    risk_analysis: RiskAnalysisPayload
    created_at: datetime
    ai_directive: dict[str, Any] | None = None
