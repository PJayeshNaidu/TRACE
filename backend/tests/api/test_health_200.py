"""API tests for successful GET /health endpoint responses."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from trace.api.health.router import get_db_gateway, get_graph_gateway
from trace.api.health.schemas import HealthStatus
from trace.core.logging import SECRET_FIELDS
from trace.domain.health import GraphConnectivityState
from trace.main import app

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


class HealthyDbStub:
    """Stub DatabaseGateway returning True for health checks."""

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        yield None  # type: ignore[misc]

    async def health_check(self) -> bool:
        return True


class NotConfiguredGraphStub:
    """Stub GraphGateway returning NOT_CONFIGURED for health checks."""

    async def health_check(self) -> GraphConnectivityState:
        return GraphConnectivityState.NOT_CONFIGURED

    async def close(self) -> None:
        pass


@pytest.mark.asyncio
async def test_health_endpoint_healthy_returns_200() -> None:
    """Verify GET /health returns HTTP 200 with healthy status and no leaked secrets."""
    app.dependency_overrides[get_db_gateway] = lambda: HealthyDbStub()
    app.dependency_overrides[get_graph_gateway] = lambda: NotConfiguredGraphStub()

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()

        # Validate schema conformity
        health_status = HealthStatus.model_validate(data)
        assert health_status.status == "healthy"
        assert health_status.version is not None
        assert "version" in data
        assert health_status.services["postgres"].status == "reachable"
        assert health_status.services["neo4j"].status == "not_configured"

        # Assert no known secret keys or passwords leaked in response
        body_text = response.text.lower()
        for secret_name in SECRET_FIELDS:
            assert secret_name.lower() not in body_text

    finally:
        app.dependency_overrides.clear()
