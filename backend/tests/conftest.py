"""Shared pytest fixtures, stubs, and network isolation configuration."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from trace.api.health.router import get_db_gateway, get_graph_gateway
from trace.core.config import ApplicationConfig
from trace.domain.health import GraphConnectivityState
from trace.infrastructure.database.gateway import DatabaseGateway
from trace.infrastructure.graph.gateway import StubGraphGateway
from trace.infrastructure.llm.config import LLMConfig, ModelConfig
from trace.infrastructure.llm.provider import LLMProvider
from trace.infrastructure.llm.response import LLMResponse, Success, TokenUsage
from trace.main import create_app

import pytest
import pytest_socket
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture(autouse=True)
def enforce_network_isolation(request: pytest.FixtureRequest) -> None:
    """Block external network access by default for all non-integration tests."""
    if "integration" not in request.keywords and "socket_enabled" not in request.keywords:
        pytest_socket.socket_allow_hosts(["127.0.0.1", "localhost"], allow_unix_socket=True)
    else:
        pytest_socket.enable_socket()


class StubDbGateway:
    """In-memory stub database gateway returning True for health probes."""

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        yield None  # type: ignore[misc]

    async def health_check(self) -> bool:
        return True

    async def dispose(self) -> None:
        pass


class StubLLMProvider:
    """Configurable stub implementing LLMProvider Protocol."""

    def __init__(self, target_response: LLMResponse | None = None) -> None:
        self.target_response: LLMResponse = target_response or Success(
            content="stub output",
            model="test-stub",
            usage=TokenUsage(prompt_tokens=1, completion_tokens=1),
        )

    def set_response(self, response: LLMResponse) -> None:
        self.target_response = response

    async def complete(
        self,
        prompt: str,
        model: ModelConfig,
        config: LLMConfig,
    ) -> LLMResponse:
        return self.target_response

    async def embed(
        self,
        text: str,
        model: ModelConfig,
        config: LLMConfig,
    ) -> LLMResponse:
        return self.target_response


@pytest.fixture
def app_config_stub(monkeypatch: pytest.MonkeyPatch) -> ApplicationConfig:
    """Provide an isolated ApplicationConfig instance unaffected by host environment."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("NEO4J_URI", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("LLM_DEFAULT_MODEL", raising=False)
    return ApplicationConfig(
        _env_file=None,
        database_url="postgresql+asyncpg://test:test@localhost:5432/test",
        app_env="test",
        log_level="INFO",
    )


@pytest.fixture
def stub_db_gateway() -> DatabaseGateway:
    """Provide a DatabaseGateway stub returning True for health checks."""
    return StubDbGateway()


@pytest.fixture
def stub_graph_gateway() -> StubGraphGateway:
    """Provide a StubGraphGateway returning NOT_CONFIGURED by default."""
    return StubGraphGateway(initial_state=GraphConnectivityState.NOT_CONFIGURED)


@pytest.fixture
def stub_llm_provider() -> LLMProvider:
    """Provide a StubLLMProvider instance satisfying LLMProvider Protocol."""
    return StubLLMProvider()


@pytest.fixture
async def async_test_client(
    stub_db_gateway: DatabaseGateway,
    stub_graph_gateway: StubGraphGateway,
) -> AsyncIterator[AsyncClient]:
    """Provide an AsyncClient configured with test stubs for API verification."""
    app: FastAPI = create_app()
    app.dependency_overrides[get_db_gateway] = lambda: stub_db_gateway
    app.dependency_overrides[get_graph_gateway] = lambda: stub_graph_gateway

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
