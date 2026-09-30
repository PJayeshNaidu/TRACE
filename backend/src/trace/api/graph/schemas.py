"""Pydantic schemas for the F03 Dependency Graph API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from trace.domain.graph import GraphBuildRun, GraphBuildStatus, GraphNode, GraphRelationship


class GraphBuildRunResponse(BaseModel):
    """Response schema representing a graph build run's lifecycle and stats."""

    id: uuid.UUID
    analysis_run_id: uuid.UUID
    repository_id: uuid.UUID
    status: GraphBuildStatus
    nodes_created: int
    relationships_created: int
    duration_ms: float | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, run: GraphBuildRun) -> "GraphBuildRunResponse":
        """Construct from a GraphBuildRun domain model."""
        return cls(
            id=run.id,
            analysis_run_id=run.analysis_run_id,
            repository_id=run.repository_id,
            status=run.status,
            nodes_created=run.nodes_created,
            relationships_created=run.relationships_created,
            duration_ms=run.duration_ms,
            error_message=run.error_message,
            started_at=run.started_at,
            completed_at=run.completed_at,
            created_at=run.created_at,
            updated_at=run.updated_at,
        )

    model_config = {"from_attributes": True}


class GraphBuildTriggerResponse(BaseModel):
    """Lightweight response confirming that a graph build has been dispatched."""

    build_run_id: uuid.UUID
    analysis_run_id: uuid.UUID
    status: GraphBuildStatus
    message: str


class GraphNodeItem(BaseModel):
    """Single Neo4j node returned from a graph query."""

    id: str
    label: str
    qualified_name: str
    analysis_run_id: str
    properties: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_domain(cls, node: GraphNode) -> "GraphNodeItem":
        return cls(
            id=node.id,
            label=node.label,
            qualified_name=node.qualified_name,
            analysis_run_id=node.analysis_run_id,
            properties=node.properties,
        )


class GraphNodeListResponse(BaseModel):
    """Paginated list of graph nodes."""

    items: list[GraphNodeItem]
    total: int
    limit: int
    offset: int


class GraphRelationshipItem(BaseModel):
    """Single Neo4j directed edge returned from a graph query."""

    source_id: str
    source_label: str
    relationship_type: str
    target_id: str
    target_label: str
    analysis_run_id: str
    evidence_file_path: str | None = None
    evidence_start_line: int | None = None

    @classmethod
    def from_domain(cls, rel: GraphRelationship) -> "GraphRelationshipItem":
        return cls(
            source_id=rel.source_id,
            source_label=rel.source_label,
            relationship_type=rel.relationship_type,
            target_id=rel.target_id,
            target_label=rel.target_label,
            analysis_run_id=rel.analysis_run_id,
            evidence_file_path=rel.evidence_file_path,
            evidence_start_line=rel.evidence_start_line,
        )


class GraphRelationshipListResponse(BaseModel):
    """Paginated list of graph relationships."""

    items: list[GraphRelationshipItem]
    total: int
    limit: int
    offset: int


class GraphTraversalItem(BaseModel):
    """A node reached during traversal, annotated with the relationship type."""

    node: GraphNodeItem
    via_relationship: str


class GraphTraversalResponse(BaseModel):
    """Result of a forward (dependencies) or backward (dependents) traversal."""

    origin_node_id: str
    direction: str   # 'dependents' or 'dependencies'
    analysis_run_id: str
    connected: list[GraphTraversalItem]
    total: int
