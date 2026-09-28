"""API tests for degraded GET /health endpoint responses."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from trace.api.health.router import get_db_gateway, get_graph_gateway
from trace.api.health.schemas import HealthStatus
from trace.domain.health import GraphConnectivityState
from trace.main import app

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


class UnhealthyDbStub:
    """Stub DatabaseGateway returning False for health checks."""

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        yield None  # type: ignore[misc]

    async def health_check(self) -> bool:
        return False


class HealthyDbStub:
    """Stub DatabaseGateway returning True for health checks."""

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        yield None  # type: ignore[misc]

    async def health_check(self) -> bool:
        return True


class UnreachableGraphStub:
    """Stub GraphGateway returning UNREACHABLE for health checks."""

    async def health_check(self) -> GraphConnectivityState:
        return GraphConnectivityState.UNREACHABLE

    async def close(self) -> None:
        pass


class ReachableGraphStub:
    """Stub GraphGateway returning REACHABLE for health checks."""

    async def health_check(self) -> GraphConnectivityState:
        return GraphConnectivityState.REACHABLE

    async def close(self) -> None:
        pass


@pytest.mark.asyncio
async def test_health_503_when_database_unreachable() -> None:
    """Scenario (a): DB stub returns False -> HTTP 503 and degraded status."""
    app.dependency_overrides[get_db_gateway] = lambda: UnhealthyDbStub()
    app.dependency_overrides[get_graph_gateway] = lambda: ReachableGraphStub()

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")

        assert response.status_code == 503
        data = response.json()
        status_model = HealthStatus.model_validate(data)
        assert status_model.status == "degraded"
        assert status_model.services["postgres"].status == "unreachable"
        assert status_model.services["neo4j"].status == "reachable"

    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_health_503_when_graph_unreachable() -> None:
    """Scenario (b): Graph stub returns UNREACHABLE -> HTTP 503 and degraded status."""
    app.dependency_overrides[get_db_gateway] = lambda: HealthyDbStub()
    app.dependency_overrides[get_graph_gateway] = lambda: UnreachableGraphStub()

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")

        assert response.status_code == 503
        data = response.json()
        status_model = HealthStatus.model_validate(data)
        assert status_model.status == "degraded"
        assert status_model.services["postgres"].status == "reachable"
        assert status_model.services["neo4j"].status == "unreachable"

    finally:
        app.dependency_overrides.clear()
