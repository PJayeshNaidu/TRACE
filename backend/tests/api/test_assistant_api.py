"""API contract and integration tests for TRACE AI Assistant endpoint."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from trace.api.assistant.router import get_assistant_service, get_config
from trace.api.health.router import get_db_gateway
from trace.core.config import ApplicationConfig
from trace.domain.project import ProjectStatus
from trace.infrastructure.database.gateway import InMemoryDatabaseGateway
from trace.infrastructure.database.models import ProjectOrm
from trace.main import create_app
from trace.schemas.assistant import AssistantQueryResponse, EvidenceSource
from trace.services.assistant.retrieval import CompactEvidenceBundle, GraphNeighborEvidence
from trace.services.assistant.synthesis import AssistantService, AssistantSynthesisService


@pytest.fixture
async def setup_assistant_project(
    in_memory_db_gateway: InMemoryDatabaseGateway,
) -> uuid.UUID:
    """Insert active project into test database."""
    async with in_memory_db_gateway.session() as session:
        proj_id = uuid.uuid4()
        now = datetime.now(UTC)
        proj = ProjectOrm(
            id=proj_id,
            name=f"Assistant Test Project {proj_id}",
            status=ProjectStatus.ACTIVE.value,
            created_at=now,
            updated_at=now,
        )
        session.add(proj)
        await session.commit()
        return proj_id


@pytest.fixture
def mock_assistant_service() -> AssistantService:
    """Mock AssistantService to return predictable AssistantQueryResponse."""
    mock_svc = MagicMock(spec=AssistantService)
    mock_svc.ask = AsyncMock(
        return_value=AssistantQueryResponse(
            answer="`api.routes.auth_handler` directly calls `auth_service.login`.",
            sources=[
                EvidenceSource(
                    type="graph",
                    identifier="api.routes.auth_handler -> auth_service.login",
                    summary="1-hop CALLS direct relationship",
                    metadata={"from": "api.routes.auth_handler", "to": "auth_service.login", "depth": 1},
                )
            ],
            model_used="mistralai/mistral-7b-instruct:free",
        )
    )
    return mock_svc


@pytest.mark.asyncio
async def test_assistant_ask_endpoint(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    setup_assistant_project: uuid.UUID,
    mock_assistant_service: AssistantService,
):
    """T017 & T019: Test POST /api/v1/assistant/ask happy path returns 200 with structured response."""
    app = create_app()
    app.dependency_overrides[get_db_gateway] = lambda: in_memory_db_gateway
    app.dependency_overrides[get_assistant_service] = lambda: mock_assistant_service

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        payload = {
            "project_id": str(setup_assistant_project),
            "question": "Why is api.routes.auth_handler affected?",
        }
        resp = await client.post("/api/v1/assistant/ask", json=payload)

        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data
        assert "auth_service.login" in data["answer"]
        assert "sources" in data
        assert len(data["sources"]) == 1
        assert data["sources"][0]["type"] == "graph"
        assert data["model_used"] == "mistralai/mistral-7b-instruct:free"


@pytest.mark.asyncio
async def test_assistant_ask_validation_error(
    in_memory_db_gateway: InMemoryDatabaseGateway,
):
    """Test POST /api/v1/assistant/ask validation error for invalid payloads (HTTP 422)."""
    app = create_app()
    app.dependency_overrides[get_db_gateway] = lambda: in_memory_db_gateway

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        # 1. Empty question (< 3 chars)
        payload = {
            "project_id": str(uuid.uuid4()),
            "question": "a",
        }
        resp = await client.post("/api/v1/assistant/ask", json=payload)
        assert resp.status_code == 422

        # 2. Missing project_id
        payload_missing = {
            "question": "Why is auth_handler affected?",
        }
        resp_missing = await client.post("/api/v1/assistant/ask", json=payload_missing)
        assert resp_missing.status_code == 422


@pytest.mark.asyncio
async def test_assistant_ask_project_not_found(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    setup_assistant_project: uuid.UUID,
):
    """Test POST /api/v1/assistant/ask returns 404 when project does not exist."""
    app = create_app()
    app.dependency_overrides[get_db_gateway] = lambda: in_memory_db_gateway

    non_existent_id = uuid.uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        payload = {
            "project_id": str(non_existent_id),
            "question": "Why is auth_handler affected?",
        }
        resp = await client.post("/api/v1/assistant/ask", json=payload)
        assert resp.status_code == 404
        data = resp.json()
        assert data.get("error_code") == "PROJECT_NOT_FOUND"


@pytest.mark.asyncio
async def test_assistant_ask_offline_fallback_integration(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    setup_assistant_project: uuid.UUID,
):
    """Test POST /api/v1/assistant/ask executes retrieval and offline deterministic fallback without mocks."""
    app = create_app()
    app.dependency_overrides[get_db_gateway] = lambda: in_memory_db_gateway
    app.dependency_overrides[get_config] = lambda: ApplicationConfig(llm_enable_external_calls=False)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        payload = {
            "project_id": str(setup_assistant_project),
            "question": "What is auth_service.login risk?",
        }
        resp = await client.post("/api/v1/assistant/ask", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["model_used"] == "offline-deterministic-fallback"
        assert "answer" in data
        assert isinstance(data["sources"], list)


@pytest.mark.asyncio
async def test_assistant_status_endpoint():
    """Test GET /api/v1/assistant/status returns assistant status and model info."""
    app = create_app()
    app.dependency_overrides[get_config] = lambda: ApplicationConfig(
        openrouter_api_key="sk-test-key",
        openrouter_model="nvidia/nemotron-3.5-lightning:free",
        llm_enable_external_calls=True,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        resp = await client.get("/api/v1/assistant/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "online"
        assert data["has_api_key"] is True
        assert data["model"] == "nvidia/nemotron-3.5-lightning:free"


@pytest.mark.asyncio
async def test_assistant_ask_with_history(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    setup_assistant_project: uuid.UUID,
):
    """T038 & T040: Test POST /api/v1/assistant/ask accepts conversation history and resolves follow-ups."""
    app = create_app()
    app.dependency_overrides[get_db_gateway] = lambda: in_memory_db_gateway
    app.dependency_overrides[get_config] = lambda: ApplicationConfig(llm_enable_external_calls=False)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        payload = {
            "project_id": str(setup_assistant_project),
            "question": "Why is it affected?",
            "history": [
                {"role": "user", "content": "Show details for auth_service.login"},
                {"role": "assistant", "content": "auth_service.login is a critical authentication function."},
            ],
        }
        resp = await client.post("/api/v1/assistant/ask", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data
        assert "intent" in data
        assert "grounding_status" in data
        assert "suggested_followups" in data
        assert isinstance(data["suggested_followups"], list)
        assert data["grounding_status"] in (
            "DETERMINISTIC_GROUNDED",
            "PARTIAL_EVIDENCE",
            "FALLBACK_DETERMINISTIC",
            "INSUFFICIENT_EVIDENCE",
        )


