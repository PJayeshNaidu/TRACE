"""Unit tests for FastAPI lifespan resource management and dependency providers."""

from trace.api.health.router import get_db_gateway, get_graph_gateway
from trace.core.config import ApplicationConfig
from trace.infrastructure.database.gateway import DatabaseGateway
from trace.infrastructure.graph.gateway import GraphGateway, UnconfiguredGraphGateway
from trace.infrastructure.llm.provider import LLMProvider
from trace.main import create_app

import pytest
from fastapi import Request


@pytest.mark.asyncio
async def test_app_lifespan_initialization_and_shutdown() -> None:
    """Verify lifespan wires app.state.db, app.state.graph, app.state.llm and disposes cleanly."""
    cfg = ApplicationConfig(
        _env_file=None,
        database_url="sqlite+aiosqlite:///:memory:",
        neo4j_uri=None,
        app_env="test",
        log_level="INFO",
    )
    test_app = create_app(config=cfg)

    # Trigger lifespan via router LifespanManager or async with test_app.router.lifespan_context
    async with test_app.router.lifespan_context(test_app):
        assert hasattr(test_app.state, "db")
        assert isinstance(test_app.state.db, DatabaseGateway)
        assert await test_app.state.db.health_check() is True

        assert hasattr(test_app.state, "graph")
        assert isinstance(test_app.state.graph, GraphGateway)
        assert isinstance(test_app.state.graph, UnconfiguredGraphGateway)

        assert hasattr(test_app.state, "llm")
        assert isinstance(test_app.state.llm, LLMProvider)

        # Test dependency functions
        mock_request = Request({"type": "http", "app": test_app})
        assert get_db_gateway(mock_request) is test_app.state.db
        assert get_graph_gateway(mock_request) is test_app.state.graph
