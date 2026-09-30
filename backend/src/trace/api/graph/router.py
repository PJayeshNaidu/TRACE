"""FastAPI router for F03 Dependency Graph endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, status

from trace.api.analyses.router import get_analysis_service
from trace.api.graph.schemas import (
    GraphBuildRunResponse,
    GraphBuildTriggerResponse,
    GraphNodeItem,
    GraphNodeListResponse,
    GraphRelationshipItem,
    GraphRelationshipListResponse,
    GraphTraversalItem,
    GraphTraversalResponse,
)
from trace.domain.graph import GraphBuildRun, GraphBuildStatus, GraphNode, GraphRelationship
from trace.infrastructure.graph.gateway import GraphGateway
from trace.services.analysis import AnalysisService
from trace.services.graph import GraphBuildRunNotFoundError, GraphService

logger = structlog.get_logger(__name__)

graph_router = APIRouter(tags=["dependency-graph"])


# ---------------------------------------------------------------------------
# Dependency providers
# ---------------------------------------------------------------------------


def get_graph_gateway(request: Request) -> GraphGateway:
    """Dependency provider for GraphGateway from application state."""
    return request.app.state.graph  # type: ignore[no-any-return]


def get_graph_service(request: Request) -> GraphService:
    """Dependency provider for GraphService from application state."""
    svc = getattr(request.app.state, "graph_service", None)
    if svc is None:
        raise RuntimeError(
            "GraphService is not initialised. Ensure main.py wires graph_service into app.state."
        )
    return svc  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Background task executor
# ---------------------------------------------------------------------------


class BackgroundGraphBuildExecutor:
    """Dispatches graph build execution via FastAPI BackgroundTasks."""

    def __init__(self, background_tasks: BackgroundTasks, service: GraphService) -> None:
        self._bg = background_tasks
        self._service = service

    def dispatch(self, analysis_run_id: uuid.UUID) -> None:
        self._bg.add_task(self._service.build_dependency_graph, analysis_run_id)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@graph_router.post(
    "/analyses/{analysis_run_id}/graph/build",
    response_model=GraphBuildTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger or re-trigger the dependency graph build for a completed analysis run",
)
async def trigger_graph_build(
    analysis_run_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    graph_svc: Annotated[GraphService, Depends(get_graph_service)],
) -> GraphBuildTriggerResponse:
    """Dispatch a graph build for the specified analysis run.

    The build runs asynchronously. Poll ``GET /graph/status`` to track progress.
    """
    # Create the PENDING record immediately so the caller gets a build_run_id
    # to poll. The actual build runs in the background.
    executor = BackgroundGraphBuildExecutor(background_tasks, graph_svc)
    executor.dispatch(analysis_run_id)

    # Fetch the latest build run (may be None if the background task hasn't created
    # the record yet — return a synthetic response in that case)
    latest = await graph_svc.get_latest_build_run(analysis_run_id)

    if latest is not None:
        return GraphBuildTriggerResponse(
            build_run_id=latest.id,
            analysis_run_id=analysis_run_id,
            status=latest.status,
            message="Graph build dispatched successfully.",
        )

    return GraphBuildTriggerResponse(
        build_run_id=uuid.uuid4(),
        analysis_run_id=analysis_run_id,
        status=GraphBuildStatus.PENDING,
        message="Graph build dispatched. Poll /graph/status for progress.",
    )


@graph_router.get(
    "/analyses/{analysis_run_id}/graph/status",
    response_model=GraphBuildRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Get the latest dependency graph build status for an analysis run",
)
async def get_graph_build_status(
    analysis_run_id: uuid.UUID,
    graph_svc: Annotated[GraphService, Depends(get_graph_service)],
) -> GraphBuildRunResponse:
    """Return the most recent graph build run for the given analysis run.

    Returns 404 if no build has been triggered yet.
    """
    from fastapi import HTTPException

    latest = await graph_svc.get_latest_build_run(analysis_run_id)
    if latest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No graph build found for analysis run {analysis_run_id}.",
        )
    return GraphBuildRunResponse.from_domain(latest)


@graph_router.get(
    "/analyses/{analysis_run_id}/graph/nodes",
    response_model=GraphNodeListResponse,
    status_code=status.HTTP_200_OK,
    summary="List nodes in the dependency graph for an analysis run",
)
async def list_graph_nodes(
    analysis_run_id: uuid.UUID,
    graph_gateway: Annotated[GraphGateway, Depends(get_graph_gateway)],
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
    offset: Annotated[int, Query(ge=0)] = 0,
    label: Annotated[str | None, Query(description="Filter by node label (e.g. Module, Class, Function)")] = None,
) -> GraphNodeListResponse:
    """Query Neo4j nodes scoped to the given analysis_run_id.

    Optionally filter by a specific node label. Results are paginated.
    """
    nodes = await _query_nodes(graph_gateway, str(analysis_run_id), label)
    total = len(nodes)
    paginated = nodes[offset : offset + limit]
    return GraphNodeListResponse(
        items=[GraphNodeItem.from_domain(n) for n in paginated],
        total=total,
        limit=limit,
        offset=offset,
    )


@graph_router.get(
    "/analyses/{analysis_run_id}/graph/relationships",
    response_model=GraphRelationshipListResponse,
    status_code=status.HTTP_200_OK,
    summary="List relationships in the dependency graph for an analysis run",
)
async def list_graph_relationships(
    analysis_run_id: uuid.UUID,
    graph_gateway: Annotated[GraphGateway, Depends(get_graph_gateway)],
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
    offset: Annotated[int, Query(ge=0)] = 0,
    rel_type: Annotated[str | None, Query(description="Filter by relationship type (e.g. CALLS, IMPORTS)")] = None,
) -> GraphRelationshipListResponse:
    """Query Neo4j relationships scoped to the given analysis_run_id.

    Optionally filter by relationship type. Results are paginated.
    """
    rels = await _query_relationships(graph_gateway, str(analysis_run_id), rel_type)
    total = len(rels)
    paginated = rels[offset : offset + limit]
    return GraphRelationshipListResponse(
        items=[GraphRelationshipItem.from_domain(r) for r in paginated],
        total=total,
        limit=limit,
        offset=offset,
    )


@graph_router.get(
    "/analyses/{analysis_run_id}/graph/dependents/{node_id:path}",
    response_model=GraphTraversalResponse,
    status_code=status.HTTP_200_OK,
    summary="Find all components that depend ON the given node",
)
async def get_dependents(
    analysis_run_id: uuid.UUID,
    node_id: str,
    graph_gateway: Annotated[GraphGateway, Depends(get_graph_gateway)],
    depth: Annotated[int, Query(ge=1, le=5)] = 1,
) -> GraphTraversalResponse:
    """Return all nodes that have an outgoing relationship TO node_id.

    This answers: *"What components depend on X?"*
    """
    connected = await _traverse(
        graph_gateway,
        node_id=node_id,
        run_id=str(analysis_run_id),
        direction="dependents",
        depth=depth,
    )
    return GraphTraversalResponse(
        origin_node_id=node_id,
        direction="dependents",
        analysis_run_id=str(analysis_run_id),
        connected=connected,
        total=len(connected),
    )


@graph_router.get(
    "/analyses/{analysis_run_id}/graph/dependencies/{node_id:path}",
    response_model=GraphTraversalResponse,
    status_code=status.HTTP_200_OK,
    summary="Find all components that the given node depends ON",
)
async def get_dependencies(
    analysis_run_id: uuid.UUID,
    node_id: str,
    graph_gateway: Annotated[GraphGateway, Depends(get_graph_gateway)],
    depth: Annotated[int, Query(ge=1, le=5)] = 1,
) -> GraphTraversalResponse:
    """Return all nodes that node_id points to.

    This answers: *"What does X depend on?"*
    """
    connected = await _traverse(
        graph_gateway,
        node_id=node_id,
        run_id=str(analysis_run_id),
        direction="dependencies",
        depth=depth,
    )
    return GraphTraversalResponse(
        origin_node_id=node_id,
        direction="dependencies",
        analysis_run_id=str(analysis_run_id),
        connected=connected,
        total=len(connected),
    )


# ---------------------------------------------------------------------------
# Internal Cypher query helpers
# (These live here rather than in the gateway to keep query logic close to the
#  API layer and avoid polluting the Protocol with read-query methods that may
#  change frequently as the query API evolves.)
# ---------------------------------------------------------------------------

_QUERY_NODES_CYPHER = """
MATCH (n {analysis_run_id: $run_id})
WHERE $label IS NULL OR $label IN labels(n)
RETURN n, labels(n) AS lbls
ORDER BY n.qualified_name
"""

_QUERY_RELS_CYPHER = """
MATCH (src {analysis_run_id: $run_id})-[r]->(tgt {analysis_run_id: $run_id})
WHERE $rel_type IS NULL OR type(r) = $rel_type
RETURN src, labels(src) AS src_lbls,
       type(r) AS rel_type,
       r.evidence_file_path AS efp,
       r.evidence_start_line AS esl,
       tgt, labels(tgt) AS tgt_lbls
ORDER BY CASE type(r)
  WHEN 'CALLS' THEN 1
  WHEN 'EXTENDS' THEN 2
  WHEN 'IMPORTS' THEN 3
  WHEN 'EXPOSES' THEN 4
  WHEN 'DEFINES' THEN 5
  ELSE 6 END
"""

_QUERY_DEPENDENTS_CYPHER = """
MATCH (origin {id: $node_id})<-[r*1..$depth]-(dep {analysis_run_id: $run_id})
RETURN DISTINCT dep, labels(dep) AS lbls, type(last(r)) AS rel_type
"""

_QUERY_DEPENDENCIES_CYPHER = """
MATCH (origin {id: $node_id})-[r*1..$depth]->(dep {analysis_run_id: $run_id})
RETURN DISTINCT dep, labels(dep) AS lbls, type(last(r)) AS rel_type
"""


async def _query_nodes(
    gateway: GraphGateway,
    run_id: str,
    label: str | None,
) -> list[GraphNode]:
    """Run a Cypher node query against Neo4j via the gateway's underlying driver."""
    from trace.infrastructure.graph.gateway import (
        Neo4jGraphGateway,
        UnconfiguredGraphGateway,
    )

    if isinstance(gateway, UnconfiguredGraphGateway):
        return []

    if not isinstance(gateway, Neo4jGraphGateway):
        # Stub or unknown — return empty
        return []

    driver = gateway.driver
    results: list[GraphNode] = []

    async with driver.session() as session:
        cursor = await session.run(
            _QUERY_NODES_CYPHER, run_id=run_id, label=label
        )
        async for record in cursor:
            node = record["n"]
            lbls: list[str] = record["lbls"]
            primary_label = _primary_label(lbls)
            qn = node.get("qualified_name") or node.get("id", "")
            props = dict(node)
            results.append(
                GraphNode(
                    id=node.get("id", ""),
                    label=primary_label,
                    qualified_name=qn,
                    analysis_run_id=run_id,
                    properties=props,
                )
            )
    return results


async def _query_relationships(
    gateway: GraphGateway,
    run_id: str,
    rel_type: str | None,
) -> list[GraphRelationship]:
    """Run a Cypher relationship query via the gateway's underlying driver."""
    from trace.infrastructure.graph.gateway import (
        Neo4jGraphGateway,
        UnconfiguredGraphGateway,
    )

    if isinstance(gateway, UnconfiguredGraphGateway):
        return []

    if not isinstance(gateway, Neo4jGraphGateway):
        return []

    driver = gateway.driver
    results: list[GraphRelationship] = []

    async with driver.session() as session:
        cursor = await session.run(
            _QUERY_RELS_CYPHER, run_id=run_id, rel_type=rel_type
        )
        async for record in cursor:
            src = record["src"]
            tgt = record["tgt"]
            results.append(
                GraphRelationship(
                    source_id=src.get("id", ""),
                    source_label=_primary_label(record["src_lbls"]),
                    relationship_type=record["rel_type"],
                    target_id=tgt.get("id", ""),
                    target_label=_primary_label(record["tgt_lbls"]),
                    analysis_run_id=run_id,
                    evidence_file_path=record.get("efp"),
                    evidence_start_line=record.get("esl"),
                )
            )
    return results


async def _traverse(
    gateway: GraphGateway,
    node_id: str,
    run_id: str,
    direction: str,
    depth: int,
) -> list[GraphTraversalItem]:
    """Traverse the graph outward from node_id in the given direction."""
    from trace.infrastructure.graph.gateway import (
        Neo4jGraphGateway,
        UnconfiguredGraphGateway,
    )

    if isinstance(gateway, UnconfiguredGraphGateway):
        return []
    if not isinstance(gateway, Neo4jGraphGateway):
        return []

    query = (
        _QUERY_DEPENDENTS_CYPHER
        if direction == "dependents"
        else _QUERY_DEPENDENCIES_CYPHER
    )

    driver = gateway.driver
    results: list[GraphTraversalItem] = []

    async with driver.session() as session:
        cursor = await session.run(
            query, node_id=node_id, run_id=run_id, depth=depth
        )
        async for record in cursor:
            node = record["dep"]
            lbls: list[str] = record["lbls"]
            primary_label = _primary_label(lbls)
            qn = node.get("qualified_name") or node.get("id", "")
            results.append(
                GraphTraversalItem(
                    node=GraphNodeItem(
                        id=node.get("id", ""),
                        label=primary_label,
                        qualified_name=qn,
                        analysis_run_id=run_id,
                        properties=dict(node),
                    ),
                    via_relationship=record["rel_type"],
                )
            )
    return results


def _primary_label(labels: list[str]) -> str:
    """Pick the most specific (non-generic) label from a node's label list."""
    # Neo4j nodes may have multiple labels; exclude generic ones
    skip = {"AnalysisRoot"}
    specific = [lb for lb in labels if lb not in skip]
    return specific[0] if specific else (labels[0] if labels else "Unknown")
