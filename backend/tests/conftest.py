"""Shared pytest fixtures, stubs, and network isolation configuration."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from trace.api.health.router import get_db_gateway, get_graph_gateway
from trace.core.config import ApplicationConfig
from trace.domain.health import GraphConnectivityState
from trace.domain.repository import ConnectionValidationResult, RepositoryType
from trace.infrastructure.database.gateway import DatabaseGateway, InMemoryDatabaseGateway
from trace.infrastructure.database.models import Base
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


class StubGitProvider:
    """Configurable test double implementing GitProvider Protocol."""

    def __init__(
        self,
        local_result: ConnectionValidationResult | None = None,
        remote_result: ConnectionValidationResult | None = None,
        default_branch: str | None = "main",
        remote_refs: list[str] | None = None,
    ) -> None:
        self.local_result = local_result or ConnectionValidationResult(
            is_connected=True, detected_branch="main", latency_ms=1.0
        )
        self.remote_result = remote_result or ConnectionValidationResult(
            is_connected=True, detected_branch="main", latency_ms=2.0
        )
        self.default_branch = default_branch
        self.remote_refs = remote_refs or ["refs/heads/main"]

    async def validate_local(self, path: Path) -> ConnectionValidationResult:
        return self.local_result

    async def validate_remote(
        self, url: str, timeout_seconds: float = 10.0
    ) -> ConnectionValidationResult:
        return self.remote_result

    async def detect_default_branch(self, location: str, repo_type: RepositoryType) -> str | None:
        return self.default_branch

    async def list_remote_references(self, url: str, timeout_seconds: float = 10.0) -> list[str]:
        return self.remote_refs

    async def resolve_revision(self, location: str | Path, ref: str = "HEAD") -> str | None:
        return "1234567890123456789012345678901234567890"


@pytest.fixture
def stub_git_provider() -> StubGitProvider:
    """Provide a configurable StubGitProvider satisfying GitProvider Protocol."""
    return StubGitProvider()


@pytest.fixture
async def in_memory_db_gateway() -> AsyncIterator[InMemoryDatabaseGateway]:
    """Provide an in-memory SQLite database gateway with initialized ORM schema."""
    gateway = InMemoryDatabaseGateway()
    async with gateway._engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield gateway
    finally:
        async with gateway._engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await gateway.dispose()


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
