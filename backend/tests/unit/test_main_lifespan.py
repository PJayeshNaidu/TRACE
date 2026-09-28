"""Unit tests for FastAPI lifespan resource management and dependency providers."""

from trace.api.health.router import get_db_gateway, get_graph_gateway
from trace.api.repositories.router import get_git_provider
from trace.core.config import ApplicationConfig
from trace.infrastructure.database.gateway import DatabaseGateway
from trace.infrastructure.git.provider import GitProvider
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

        assert hasattr(test_app.state, "git")
        assert isinstance(test_app.state.git, GitProvider)

        # Test dependency functions
        mock_request = Request({"type": "http", "app": test_app})
        assert get_db_gateway(mock_request) is test_app.state.db
        assert get_graph_gateway(mock_request) is test_app.state.graph
        assert get_git_provider(mock_request) is test_app.state.git


@pytest.mark.asyncio
async def test_app_lifespan_with_neo4j_configured() -> None:
    """Verify lifespan initializes Neo4j driver when neo4j_uri is provided."""
    from unittest.mock import AsyncMock, MagicMock, patch

    mock_driver = MagicMock()
    mock_driver.close = AsyncMock()

    cfg = ApplicationConfig(
        _env_file=None,
        database_url="sqlite+aiosqlite:///:memory:",
        neo4j_uri="bolt://localhost:7687",
        neo4j_username="neo4j",
        neo4j_password="password",
        app_env="test",
        log_level="INFO",
    )
    with patch("neo4j.AsyncGraphDatabase.driver", return_value=mock_driver):
        test_app = create_app(config=cfg)
        async with test_app.router.lifespan_context(test_app):
            assert hasattr(test_app.state, "graph")
            assert not isinstance(test_app.state.graph, UnconfiguredGraphGateway)


def test_get_git_provider_fallback() -> None:
    """Verify get_git_provider creates default SubprocessGitProvider if not set on app.state."""
    from trace.infrastructure.git.adapters.subprocess import SubprocessGitProvider

    from fastapi import FastAPI

    plain_app = FastAPI()
    req = Request({"type": "http", "app": plain_app})
    provider = get_git_provider(req)
    assert isinstance(provider, SubprocessGitProvider)
