"""API contract and workflow tests for TRACE Projects API (/api/v1/projects)."""

import uuid
from collections.abc import AsyncIterator
from trace.api.health.router import get_db_gateway
from trace.infrastructure.database.gateway import InMemoryDatabaseGateway
from trace.main import create_app

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def project_client(
    in_memory_db_gateway: InMemoryDatabaseGateway,
) -> AsyncIterator[AsyncClient]:
    """Provide an AsyncClient configured with an isolated in-memory database."""
    app = create_app()
    app.dependency_overrides[get_db_gateway] = lambda: in_memory_db_gateway
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_project_success(project_client: AsyncClient) -> None:
    """POST /api/v1/projects creates a project and returns 201 Created."""
    response = await project_client.post(
        "/api/v1/projects",
        json={"name": "TRACE Platform", "description": "Core analysis system"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "TRACE Platform"
    assert data["description"] == "Core analysis system"
    assert data["status"] == "ACTIVE"
    assert data["repository_count"] == 0
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_create_project_whitespace_normalization(project_client: AsyncClient) -> None:
    """POST /api/v1/projects strips surrounding whitespace from project name."""
    response = await project_client.post(
        "/api/v1/projects",
        json={"name": "   Trimmed Project   "},
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Trimmed Project"


@pytest.mark.asyncio
async def test_create_project_validation_errors(project_client: AsyncClient) -> None:
    """POST /api/v1/projects returns 422 for invalid payloads."""
    # Blank name
    resp = await project_client.post("/api/v1/projects", json={"name": ""})
    assert resp.status_code == 422

    # Whitespace-only name
    resp = await project_client.post("/api/v1/projects", json={"name": "   "})
    assert resp.status_code == 422

    # Name exceeding 100 characters
    resp = await project_client.post("/api/v1/projects", json={"name": "a" * 101})
    assert resp.status_code == 422

    # Description exceeding 1000 characters
    resp = await project_client.post(
        "/api/v1/projects",
        json={"name": "Valid", "description": "d" * 1001},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_project_duplicate_name_conflict(project_client: AsyncClient) -> None:
    """POST /api/v1/projects returns 409 Conflict with standard error envelope on duplicate name."""
    resp1 = await project_client.post(
        "/api/v1/projects",
        json={"name": "Duplicate System"},
    )
    assert resp1.status_code == 201

    resp2 = await project_client.post(
        "/api/v1/projects",
        json={"name": "Duplicate System"},
    )
    assert resp2.status_code == 409
    error_body = resp2.json()
    assert error_body["error_code"] == "PROJECT_ALREADY_EXISTS"
    assert "Duplicate System" in error_body["message"]


@pytest.mark.asyncio
async def test_get_project_success_and_not_found(project_client: AsyncClient) -> None:
    """GET /api/v1/projects/{project_id} returns 200 for existing, 404 for missing."""
    create_resp = await project_client.post(
        "/api/v1/projects",
        json={"name": "Query Project"},
    )
    pid = create_resp.json()["id"]

    get_resp = await project_client.get(f"/api/v1/projects/{pid}")
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Query Project"

    missing_pid = uuid.uuid4()
    not_found_resp = await project_client.get(f"/api/v1/projects/{missing_pid}")
    assert not_found_resp.status_code == 404
    error_data = not_found_resp.json()
    assert error_data["error_code"] == "PROJECT_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_project_invalid_uuid(project_client: AsyncClient) -> None:
    """GET /api/v1/projects/{project_id} returns 422 for non-UUID parameter."""
    resp = await project_client.get("/api/v1/projects/not-a-uuid")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_projects_pagination_and_filter(project_client: AsyncClient) -> None:
    """GET /api/v1/projects supports limit, offset, and status filter."""
    for i in range(5):
        await project_client.post("/api/v1/projects", json={"name": f"Batch Project {i}"})

    # Fetch first page of 3
    resp_page1 = await project_client.get("/api/v1/projects?limit=3&offset=0")
    assert resp_page1.status_code == 200
    body1 = resp_page1.json()
    assert len(body1["items"]) == 3
    assert body1["total"] == 5
    assert body1["limit"] == 3
    assert body1["offset"] == 0

    # Fetch second page of 2
    resp_page2 = await project_client.get("/api/v1/projects?limit=3&offset=3")
    assert resp_page2.status_code == 200
    body2 = resp_page2.json()
    assert len(body2["items"]) == 2
    assert body2["total"] == 5

    # Filter ACTIVE
    active_resp = await project_client.get("/api/v1/projects?status=ACTIVE")
    assert active_resp.status_code == 200
    assert active_resp.json()["total"] == 5

    # Filter ARCHIVED
    archived_resp = await project_client.get("/api/v1/projects?status=ARCHIVED")
    assert archived_resp.status_code == 200
    assert archived_resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_archive_and_activate_endpoints(project_client: AsyncClient) -> None:
    """POST /archive and /activate manage lifecycle transitions."""
    create_resp = await project_client.post(
        "/api/v1/projects",
        json={"name": "Lifecycle Transition API"},
    )
    pid = create_resp.json()["id"]

    # Archive
    archive_resp = await project_client.post(f"/api/v1/projects/{pid}/archive")
    assert archive_resp.status_code == 200
    assert archive_resp.json()["status"] == "ARCHIVED"

    # Re-archiving returns 409
    repeat_archive = await project_client.post(f"/api/v1/projects/{pid}/archive")
    assert repeat_archive.status_code == 409
    assert repeat_archive.json()["error_code"] == "PROJECT_ARCHIVED"

    # Activate
    activate_resp = await project_client.post(f"/api/v1/projects/{pid}/activate")
    assert activate_resp.status_code == 200
    assert activate_resp.json()["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_archive_missing_project_returns_404(project_client: AsyncClient) -> None:
    """POST /api/v1/projects/{id}/archive returns 404 for non-existent project."""
    resp = await project_client.post(f"/api/v1/projects/{uuid.uuid4()}/archive")
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "PROJECT_NOT_FOUND"


@pytest.mark.asyncio
async def test_activate_missing_project_returns_404(project_client: AsyncClient) -> None:
    """POST /api/v1/projects/{id}/activate returns 404 for non-existent project."""
    resp = await project_client.post(f"/api/v1/projects/{uuid.uuid4()}/activate")
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "PROJECT_NOT_FOUND"
