"""Integration test verifying live Neo4j connectivity via Neo4jGraphGateway."""

import os
from trace.domain.health import GraphConnectivityState
from trace.infrastructure.graph.gateway import Neo4jGraphGateway

import pytest
from neo4j import AsyncGraphDatabase


@pytest.mark.integration
async def test_neo4j_live_connectivity() -> None:
    """Connect to a live Neo4j service defined by NEO4J_URI and assert REACHABLE state."""
    neo4j_uri = os.getenv("NEO4J_URI")
    if not neo4j_uri:
        pytest.skip("NEO4J_URI environment variable is not set")

    username = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")

    driver = AsyncGraphDatabase.driver(neo4j_uri, auth=(username, password))
    gateway = Neo4jGraphGateway(driver)
    try:
        state = await gateway.health_check()
        assert state == GraphConnectivityState.REACHABLE
    finally:
        await gateway.close()
