"""Pure domain models for the F03 Dependency Graph feature."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class GraphBuildStatus(StrEnum):
    """Lifecycle status of a dependency graph build run."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class GraphBuildRun:
    """Domain model tracking the lifecycle and outcome of a Neo4j graph build."""

    id: UUID
    analysis_run_id: UUID
    repository_id: UUID
    status: GraphBuildStatus
    nodes_created: int = 0
    relationships_created: int = 0
    duration_ms: float | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(frozen=True)
class GraphNode:
    """Read model representing a single Neo4j node returned from a graph query.

    Attributes:
        id: Stable unique node ID within the graph (e.g. ``qualified_name::run_id``).
        label: Neo4j node label (e.g. ``Module``, ``Class``, ``Function``).
        qualified_name: Human-readable primary identifier of the represented component.
        analysis_run_id: UUID of the analysis run that produced this node.
        properties: Additional label-specific properties (file_path, kind, etc.).
    """

    id: str
    label: str
    qualified_name: str
    analysis_run_id: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphRelationship:
    """Read model representing a single Neo4j directed edge.

    Attributes:
        source_id: Stable ID of the source node.
        source_label: Label of the source node.
        relationship_type: Edge type (``CALLS``, ``IMPORTS``, etc.).
        target_id: Stable ID of the target node.
        target_label: Label of the target node.
        evidence_file_path: Relative POSIX path of the file containing this relationship.
        evidence_start_line: 1-indexed line number of the relationship evidence.
        analysis_run_id: UUID of the analysis run that produced this edge.
    """

    source_id: str
    source_label: str
    relationship_type: str
    target_id: str
    target_label: str
    analysis_run_id: str
    evidence_file_path: str | None = None
    evidence_start_line: int | None = None
