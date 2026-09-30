"""API test for version fallback in GET /health when package metadata is missing."""

import importlib.metadata
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from trace.api.health.router import get_db_gateway, get_graph_gateway
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
async def test_health_version_fallback_to_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock importlib.metadata.version raising PackageNotFoundError.

    Assert version is 'unknown' and HTTP status is 200.
    """

    def mock_version(pkg: str) -> str:
        raise importlib.metadata.PackageNotFoundError(pkg)

    monkeypatch.setattr(importlib.metadata, "version", mock_version)

    app.dependency_overrides[get_db_gateway] = lambda: HealthyDbStub()
    app.dependency_overrides[get_graph_gateway] = lambda: NotConfiguredGraphStub()

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "unknown"
        assert data["status"] == "healthy"

    finally:
        app.dependency_overrides.clear()
