"""API tests for repository connectivity validation endpoints."""

import uuid
from collections.abc import AsyncIterator
from trace.api.health.router import get_db_gateway
from trace.api.repositories.router import get_git_provider
from trace.domain.repository import ConnectionValidationResult
from trace.infrastructure.database.gateway import InMemoryDatabaseGateway
from trace.main import create_app

import pytest
from httpx import ASGITransport, AsyncClient

from tests.conftest import StubGitProvider


@pytest.fixture
def configurable_git_provider() -> StubGitProvider:
    """Configurable test double implementing GitProvider."""
    return StubGitProvider()


@pytest.fixture
async def validation_client(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    configurable_git_provider: StubGitProvider,
) -> AsyncIterator[AsyncClient]:
    """Provide an AsyncClient configured with an in-memory DB and configurable Git stub."""
    app = create_app()
    app.dependency_overrides[get_db_gateway] = lambda: in_memory_db_gateway
    app.dependency_overrides[get_git_provider] = lambda: configurable_git_provider
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_validate_repository_success(
    validation_client: AsyncClient,
    configurable_git_provider: StubGitProvider,
) -> None:
    """POST /repositories/{id}/validate returns 200 with CONNECTED status on successful probe."""
    # Create project and repository
    p_resp = await validation_client.post("/api/v1/projects", json={"name": "Validating Project"})
    pid = p_resp.json()["id"]

    r_resp = await validation_client.post(
        f"/api/v1/projects/{pid}/repositories",
        json={"type": "REMOTE", "location": "https://github.com/org/repo"},
    )
    rid = r_resp.json()["id"]

    # Configure stub to succeed
    configurable_git_provider.remote_result = ConnectionValidationResult(
        is_connected=True,
        detected_branch="release-1.0",
        latency_ms=145.2,
    )

    # Validate
    val_resp = await validation_client.post(f"/api/v1/repositories/{rid}/validate")
    assert val_resp.status_code == 200
    val_data = val_resp.json()
    assert val_data["repository_id"] == rid
    assert val_data["is_connected"] is True
    assert val_data["status"] == "CONNECTED"
    assert val_data["detected_branch"] == "release-1.0"
    assert val_data["error_message"] is None
    assert val_data["latency_ms"] == 145.2
    assert "validated_at" in val_data

    # Verify repository status in database was updated
    get_resp = await validation_client.get(f"/api/v1/repositories/{rid}")
    get_data = get_resp.json()
    assert get_data["status"] == "CONNECTED"
    assert get_data["default_branch"] == "release-1.0"
    assert get_data["last_validated_at"] is not None
    assert get_data["last_error"] is None


@pytest.mark.asyncio
async def test_validate_repository_failure(
    validation_client: AsyncClient,
    configurable_git_provider: StubGitProvider,
) -> None:
    """POST /repositories/{id}/validate returns 200 with ERROR status on probe failure."""
    p_resp = await validation_client.post("/api/v1/projects", json={"name": "Failing Project"})
    pid = p_resp.json()["id"]

    r_resp = await validation_client.post(
        f"/api/v1/projects/{pid}/repositories",
        json={"type": "REMOTE", "location": "https://github.com/org/private-repo"},
    )
    rid = r_resp.json()["id"]

    # Configure stub to fail
    configurable_git_provider.remote_result = ConnectionValidationResult(
        is_connected=False,
        error_message="Remote repository not found or access denied.",
        latency_ms=88.5,
    )

    # Validate returns HTTP 200 with failure details inside payload
    val_resp = await validation_client.post(f"/api/v1/repositories/{rid}/validate")
    assert val_resp.status_code == 200
    val_data = val_resp.json()
    assert val_data["repository_id"] == rid
    assert val_data["is_connected"] is False
    assert val_data["status"] == "ERROR"
    assert val_data["detected_branch"] is None
    assert "access denied" in val_data["error_message"].lower()

    # Verify repository status in database was updated to ERROR
    get_resp = await validation_client.get(f"/api/v1/repositories/{rid}")
    get_data = get_resp.json()
    assert get_data["status"] == "ERROR"
    assert get_data["last_error"] == "Remote repository not found or access denied."


@pytest.mark.asyncio
async def test_validate_repository_not_found(validation_client: AsyncClient) -> None:
    """POST /repositories/{id}/validate returns 404 for non-existent repository."""
    missing_id = uuid.uuid4()
    resp = await validation_client.post(f"/api/v1/repositories/{missing_id}/validate")
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "REPOSITORY_NOT_FOUND"


@pytest.mark.asyncio
async def test_validate_repository_on_archived_project_conflict(
    validation_client: AsyncClient,
) -> None:
    """POST /repositories/{id}/validate returns 409 Conflict if parent project is ARCHIVED."""
    p_resp = await validation_client.post("/api/v1/projects", json={"name": "Archived Parent"})
    pid = p_resp.json()["id"]

    r_resp = await validation_client.post(
        f"/api/v1/projects/{pid}/repositories",
        json={"type": "LOCAL", "location": "/some/path"},
    )
    rid = r_resp.json()["id"]

    # Archive parent project
    await validation_client.post(f"/api/v1/projects/{pid}/archive")

    # Validate should now be rejected
    val_resp = await validation_client.post(f"/api/v1/repositories/{rid}/validate")
    assert val_resp.status_code == 409
    assert val_resp.json()["error_code"] == "PROJECT_ARCHIVED"
