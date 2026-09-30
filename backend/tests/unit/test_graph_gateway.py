"""Unit tests for GraphGateway implementations."""

from trace.domain.health import GraphConnectivityState
from trace.infrastructure.graph.gateway import (
    Neo4jGraphGateway,
    StubGraphGateway,
    UnconfiguredGraphGateway,
)
from unittest.mock import AsyncMock

import pytest
from neo4j import AsyncDriver


@pytest.mark.asyncio
async def test_unconfigured_graph_gateway() -> None:
    """Verify UnconfiguredGraphGateway returns NOT_CONFIGURED without network calls."""
    gw = UnconfiguredGraphGateway()
    assert await gw.health_check() == GraphConnectivityState.NOT_CONFIGURED
    await gw.close()


@pytest.mark.asyncio
async def test_neo4j_graph_gateway_success() -> None:
    """Verify Neo4jGraphGateway returns REACHABLE when driver connects successfully."""
    mock_driver = AsyncMock(spec=AsyncDriver)
    mock_driver.verify_connectivity.return_value = None

    gw = Neo4jGraphGateway(mock_driver)
    assert gw.driver is mock_driver
    assert await gw.health_check() == GraphConnectivityState.REACHABLE

    await gw.close()
    mock_driver.close.assert_called_once()


@pytest.mark.asyncio
async def test_neo4j_graph_gateway_failure() -> None:
    """Verify Neo4jGraphGateway returns UNREACHABLE when driver raises an exception."""
    mock_driver = AsyncMock(spec=AsyncDriver)
    mock_driver.verify_connectivity.side_effect = ConnectionRefusedError("Connection failed")

    gw = Neo4jGraphGateway(mock_driver)
    assert await gw.health_check() == GraphConnectivityState.UNREACHABLE
    await gw.close()


@pytest.mark.asyncio
async def test_stub_graph_gateway_state_mutation() -> None:
    """Verify StubGraphGateway returns and updates configured state."""
    gw = StubGraphGateway(initial_state=GraphConnectivityState.NOT_CONFIGURED)
    assert await gw.health_check() == GraphConnectivityState.NOT_CONFIGURED

    gw.set_state(GraphConnectivityState.REACHABLE)
    assert await gw.health_check() == GraphConnectivityState.REACHABLE

    gw.set_state(GraphConnectivityState.UNREACHABLE)
    assert await gw.health_check() == GraphConnectivityState.UNREACHABLE

    await gw.close()
