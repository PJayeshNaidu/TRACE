"""Health check router reporting service connectivity and system status."""

import importlib.metadata
from trace.api.health.schemas import HealthStatus, ServiceStatus
from trace.domain.health import GraphConnectivityState, HealthState
from trace.infrastructure.database.gateway import DatabaseGateway
from trace.infrastructure.graph.gateway import GraphGateway
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

health_router = APIRouter(tags=["health"])


def get_db_gateway(request: Request) -> DatabaseGateway:
    """Dependency provider for DatabaseGateway from application state."""
    return request.app.state.db  # type: ignore[no-any-return]


def get_graph_gateway(request: Request) -> GraphGateway:
    """Dependency provider for GraphGateway from application state."""
    return request.app.state.graph  # type: ignore[no-any-return]


@health_router.get("/health", response_model=HealthStatus)
async def check_health(
    request: Request,
    db: Annotated[DatabaseGateway, Depends(get_db_gateway)],
    graph: Annotated[GraphGateway, Depends(get_graph_gateway)],
) -> JSONResponse:
    """Probe infrastructure components and return overall system health status.

    Returns:
        JSONResponse with HTTP 200 if all configured services are reachable,
        or HTTP 503 if any required or configured service is degraded.
    """
    try:
        version = importlib.metadata.version("trace")
    except Exception:
        version = "unknown"

    # Database Probe
    db_ok = await db.health_check()
    postgres_status: ServiceStatus = ServiceStatus(status="reachable" if db_ok else "unreachable")

    # Graph Database Probe
    graph_res = await graph.health_check()
    if isinstance(graph_res, GraphConnectivityState):
        neo4j_state_str = graph_res.value
    else:
        neo4j_state_str = str(graph_res)

    neo4j_status: ServiceStatus = ServiceStatus(
        status=cast(Literal["reachable", "unreachable", "not_configured"], neo4j_state_str)
    )

    # Evaluate Aggregate Health
    is_degraded = (postgres_status.status == "unreachable") or (
        neo4j_status.status == "unreachable"
    )

    overall_status = HealthState.DEGRADED if is_degraded else HealthState.HEALTHY
    status_code = 503 if is_degraded else 200

    payload = HealthStatus(
        status=overall_status.value,
        version=version,
        services={
            "postgres": postgres_status,
            "neo4j": neo4j_status,
        },
    )

    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(),
    )
