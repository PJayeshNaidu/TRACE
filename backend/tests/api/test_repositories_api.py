"""API contract and workflow tests for TRACE Repositories API."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from trace.api.health.router import get_db_gateway
from trace.api.repositories.router import get_git_provider
from trace.infrastructure.database.gateway import InMemoryDatabaseGateway
from trace.infrastructure.database.models import RepositoryOrm
from trace.main import create_app

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from tests.conftest import StubGitProvider


@pytest.fixture
async def repo_client(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    stub_git_provider: StubGitProvider,
) -> AsyncIterator[AsyncClient]:
    """Provide an AsyncClient configured with an in-memory database double and stub Git provider."""
    app = create_app()
    app.dependency_overrides[get_db_gateway] = lambda: in_memory_db_gateway
    app.dependency_overrides[get_git_provider] = lambda: stub_git_provider
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_register_repository_success(repo_client: AsyncClient) -> None:
    """POST /projects/{id}/repositories registers a repository and returns 201 Created."""
    # Create project
    proj_resp = await repo_client.post("/api/v1/projects", json={"name": "Repo Host Project"})
    pid = proj_resp.json()["id"]

    # Register local repo
    loc_resp = await repo_client.post(
        f"/api/v1/projects/{pid}/repositories",
        json={"type": "LOCAL", "location": "/workspace/src/app"},
    )
    assert loc_resp.status_code == 201
    loc_data = loc_resp.json()
    assert loc_data["project_id"] == pid
    assert loc_data["type"] == "LOCAL"
    assert loc_data["status"] == "REGISTERED"
    assert loc_data["last_analysis_run_id"] is None
    assert "id" in loc_data

    # Register remote repo
    rem_resp = await repo_client.post(
        f"/api/v1/projects/{pid}/repositories",
        json={
            "type": "REMOTE",
            "location": "https://github.com/Example-Org/Service.git/",
            "default_branch": "main",
        },
    )
    assert rem_resp.status_code == 201
    rem_data = rem_resp.json()
    assert rem_data["location"] == "https://github.com/Example-Org/Service"  # normalized
    assert rem_data["default_branch"] == "main"


@pytest.mark.asyncio
async def test_register_repository_rejects_embedded_credentials(
    repo_client: AsyncClient,
) -> None:
    """POST /projects/{id}/repositories returns 422 when URL contains embedded credentials."""
    proj_resp = await repo_client.post("/api/v1/projects", json={"name": "Cred Test Project"})
    pid = proj_resp.json()["id"]

    resp = await repo_client.post(
        f"/api/v1/projects/{pid}/repositories",
        json={"type": "REMOTE", "location": "https://user:token123@github.com/org/repo.git"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_register_repository_rejects_duplicate_location_in_same_project(
    repo_client: AsyncClient,
) -> None:
    """POST /projects/{id}/repositories returns 409 on duplicate location in same project."""
    proj_resp = await repo_client.post("/api/v1/projects", json={"name": "Dup Project"})
    pid = proj_resp.json()["id"]

    url = "https://github.com/test-org/test-repo.git"
    resp1 = await repo_client.post(
        f"/api/v1/projects/{pid}/repositories",
        json={"type": "REMOTE", "location": url},
    )
    assert resp1.status_code == 201

    resp2 = await repo_client.post(
        f"/api/v1/projects/{pid}/repositories",
        json={"type": "REMOTE", "location": url},
    )
    assert resp2.status_code == 409
    assert resp2.json()["error_code"] == "DUPLICATE_REPOSITORY"


@pytest.mark.asyncio
async def test_register_same_repository_across_different_projects(
    repo_client: AsyncClient,
) -> None:
    """Different projects can register the same repository without conflict."""
    p1 = (await repo_client.post("/api/v1/projects", json={"name": "Multi Project 1"})).json()["id"]
    p2 = (await repo_client.post("/api/v1/projects", json={"name": "Multi Project 2"})).json()["id"]

    url = "https://github.com/shared/code"
    r1 = await repo_client.post(
        f"/api/v1/projects/{p1}/repositories",
        json={"type": "REMOTE", "location": url},
    )
    r2 = await repo_client.post(
        f"/api/v1/projects/{p2}/repositories",
        json={"type": "REMOTE", "location": url},
    )
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] != r2.json()["id"]


@pytest.mark.asyncio
async def test_register_repository_on_archived_project_fails(
    repo_client: AsyncClient,
) -> None:
    """Registering repository on ARCHIVED project returns 409 Conflict."""
    proj_resp = await repo_client.post("/api/v1/projects", json={"name": "To Archive Project"})
    pid = proj_resp.json()["id"]
    await repo_client.post(f"/api/v1/projects/{pid}/archive")

    resp = await repo_client.post(
        f"/api/v1/projects/{pid}/repositories",
        json={"type": "REMOTE", "location": "https://github.com/org/repo"},
    )
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "PROJECT_ARCHIVED"


@pytest.mark.asyncio
async def test_list_repositories_for_project(repo_client: AsyncClient) -> None:
    """GET /projects/{project_id}/repositories lists all repositories registered to project."""
    proj_resp = await repo_client.post("/api/v1/projects", json={"name": "List Project"})
    pid = proj_resp.json()["id"]

    await repo_client.post(
        f"/api/v1/projects/{pid}/repositories",
        json={"type": "LOCAL", "location": "/repo/one"},
    )
    await repo_client.post(
        f"/api/v1/projects/{pid}/repositories",
        json={"type": "LOCAL", "location": "/repo/two"},
    )

    list_resp = await repo_client.get(f"/api/v1/projects/{pid}/repositories")
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2

    # Querying nonexistent project returns 404
    missing_resp = await repo_client.get(f"/api/v1/projects/{uuid.uuid4()}/repositories")
    assert missing_resp.status_code == 404


@pytest.mark.asyncio
async def test_get_repository_by_id(repo_client: AsyncClient) -> None:
    """GET /repositories/{id} returns repository details or 404."""
    proj = (await repo_client.post("/api/v1/projects", json={"name": "Get Repo Direct"})).json()
    reg_resp = await repo_client.post(
        f"/api/v1/projects/{proj['id']}/repositories",
        json={"type": "LOCAL", "location": "/repo/direct"},
    )
    rid = reg_resp.json()["id"]

    get_resp = await repo_client.get(f"/api/v1/repositories/{rid}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == rid

    missing_resp = await repo_client.get(f"/api/v1/repositories/{uuid.uuid4()}")
    assert missing_resp.status_code == 404
    assert missing_resp.json()["error_code"] == "REPOSITORY_NOT_FOUND"


@pytest.mark.asyncio
async def test_delete_repository_success(repo_client: AsyncClient) -> None:
    """DELETE /repositories/{id} returns 204 No Content for unanalyzed repository."""
    proj = (await repo_client.post("/api/v1/projects", json={"name": "Delete API Project"})).json()
    reg_resp = await repo_client.post(
        f"/api/v1/projects/{proj['id']}/repositories",
        json={"type": "LOCAL", "location": "/repo/del"},
    )
    rid = reg_resp.json()["id"]

    del_resp = await repo_client.delete(f"/api/v1/repositories/{rid}")
    assert del_resp.status_code == 204

    # Subsequent GET returns 404
    get_resp = await repo_client.get(f"/api/v1/repositories/{rid}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_repository_in_use_rejected(
    repo_client: AsyncClient,
    in_memory_db_gateway: InMemoryDatabaseGateway,
) -> None:
    """DELETE /repositories/{id} returns 409 Conflict if repository has linked analysis run."""
    proj = (await repo_client.post("/api/v1/projects", json={"name": "In Use Project"})).json()
    reg_resp = await repo_client.post(
        f"/api/v1/projects/{proj['id']}/repositories",
        json={"type": "LOCAL", "location": "/repo/in-use"},
    )
    rid = reg_resp.json()["id"]

    # Mark repository as analyzed
    fake_run_id = uuid.uuid4()
    async with in_memory_db_gateway.session() as session:
        query = select(RepositoryOrm).where(RepositoryOrm.id == uuid.UUID(rid))
        repo_orm = (await session.execute(query)).scalar_one()
        repo_orm.last_analysis_run_id = fake_run_id
        repo_orm.updated_at = datetime.now(UTC)

    del_resp = await repo_client.delete(f"/api/v1/repositories/{rid}")
    assert del_resp.status_code == 409
    assert del_resp.json()["error_code"] == "REPOSITORY_IN_USE"
