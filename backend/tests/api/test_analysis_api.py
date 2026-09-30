"""API contract and workflow tests for TRACE Analysis API.

Endpoints: /api/v1/analyses, /api/v1/repositories/{id}/analyze.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from trace.api.analyses.router import get_artifact_store
from trace.api.health.router import get_db_gateway
from trace.api.repositories.router import get_git_provider
from trace.domain.project import ProjectStatus
from trace.domain.repository import RepositoryType
from trace.infrastructure.database.gateway import InMemoryDatabaseGateway
from trace.infrastructure.database.models import ProjectOrm, RepositoryOrm
from trace.infrastructure.storage.artifact_store import FileArtifactStore
from trace.main import create_app

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def sample_repo_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "sample_repo"


@pytest.fixture
async def setup_repo_for_api(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    sample_repo_path: Path,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Insert active project and local repo for API tests."""
    async with in_memory_db_gateway.session() as session:
        proj_id = uuid.uuid4()
        repo_id = uuid.uuid4()
        now = datetime.now(UTC)

        proj = ProjectOrm(
            id=proj_id,
            name="API Test Project",
            description="Project for API tests",
            status=ProjectStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        repo = RepositoryOrm(
            id=repo_id,
            project_id=proj_id,
            type=RepositoryType.LOCAL.value,
            location=str(sample_repo_path),
            default_branch="main",
            status="CONNECTED",
            created_at=now,
            updated_at=now,
        )
        session.add(proj)
        session.add(repo)
        await session.commit()
        return proj_id, repo_id


@pytest.fixture
async def analysis_client(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    stub_git_provider: object,
    tmp_path: Path,
) -> AsyncIterator[AsyncClient]:
    """Provide an AsyncClient configured with test stubs for analysis verification."""
    store = FileArtifactStore(tmp_path / "artifacts")
    app = create_app()
    app.dependency_overrides[get_db_gateway] = lambda: in_memory_db_gateway
    app.dependency_overrides[get_git_provider] = lambda: stub_git_provider
    app.dependency_overrides[get_artifact_store] = lambda: store

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_trigger_analysis_accepted(
    analysis_client: AsyncClient,
    setup_repo_for_api: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """POST /api/v1/repositories/{id}/analyze returns 202 Accepted with PENDING run."""
    _, repo_id = setup_repo_for_api
    response = await analysis_client.post(
        f"/api/v1/repositories/{repo_id}/analyze",
        json={"target_ref": "main", "exclude_patterns": ["tests/*"]},
    )
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "PENDING"
    assert data["repository_id"] == str(repo_id)
    assert data["target_ref"] == "main"
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_trigger_analysis_repo_not_found(analysis_client: AsyncClient) -> None:
    """POST /api/v1/repositories/{id}/analyze returns 404 for nonexistent repository."""
    nonexistent = uuid.uuid4()
    response = await analysis_client.post(
        f"/api/v1/repositories/{nonexistent}/analyze",
        json={"target_ref": "main"},
    )
    assert response.status_code == 404
    data = response.json()
    assert data["error_code"] == "REPOSITORY_NOT_FOUND"


@pytest.mark.asyncio
async def test_trigger_analysis_project_archived(
    analysis_client: AsyncClient,
    setup_repo_for_api: tuple[uuid.UUID, uuid.UUID],
    in_memory_db_gateway: InMemoryDatabaseGateway,
) -> None:
    """POST /api/v1/repositories/{id}/analyze returns 409 for archived project."""
    proj_id, repo_id = setup_repo_for_api
    async with in_memory_db_gateway.session() as session:
        from sqlalchemy import select

        proj = (
            await session.execute(select(ProjectOrm).where(ProjectOrm.id == proj_id))
        ).scalar_one()
        proj.status = ProjectStatus.ARCHIVED
        await session.commit()

    response = await analysis_client.post(
        f"/api/v1/repositories/{repo_id}/analyze",
        json={"target_ref": "main"},
    )
    assert response.status_code == 409
    data = response.json()
    assert data["error_code"] == "PROJECT_ARCHIVED"


@pytest.mark.asyncio
async def test_get_analysis_run_status(
    analysis_client: AsyncClient,
    setup_repo_for_api: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """GET /api/v1/analyses/{id} returns run details."""
    _, repo_id = setup_repo_for_api
    # Trigger run
    trigger_resp = await analysis_client.post(
        f"/api/v1/repositories/{repo_id}/analyze",
        json={},
    )
    run_id = trigger_resp.json()["id"]

    get_resp = await analysis_client.get(f"/api/v1/analyses/{run_id}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["id"] == run_id
    assert data["status"] in ("PENDING", "IN_PROGRESS", "COMPLETED")


@pytest.mark.asyncio
async def test_get_analysis_run_not_found(analysis_client: AsyncClient) -> None:
    """GET /api/v1/analyses/{id} returns 404 for missing run."""
    missing_id = uuid.uuid4()
    resp = await analysis_client.get(f"/api/v1/analyses/{missing_id}")
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "ANALYSIS_RUN_NOT_FOUND"


@pytest.mark.asyncio
async def test_list_repository_analyses(
    analysis_client: AsyncClient,
    setup_repo_for_api: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """GET /api/v1/repositories/{id}/analyses returns paginated runs."""
    _, repo_id = setup_repo_for_api
    await analysis_client.post(f"/api/v1/repositories/{repo_id}/analyze", json={})
    await analysis_client.post(f"/api/v1/repositories/{repo_id}/analyze", json={})

    resp = await analysis_client.get(f"/api/v1/repositories/{repo_id}/analyses?limit=10&offset=0")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 2
    assert len(data["items"]) >= 2
    assert data["limit"] == 10
    assert data["offset"] == 0


@pytest.mark.asyncio
async def test_full_analysis_workflow_and_inspection(
    analysis_client: AsyncClient,
    setup_repo_for_api: tuple[uuid.UUID, uuid.UUID],
    in_memory_db_gateway: InMemoryDatabaseGateway,
    stub_git_provider: object,
    tmp_path: Path,
) -> None:
    """Trigger, execute, and inspect summary, entities, relationships, diagnostics."""
    _, repo_id = setup_repo_for_api
    store = FileArtifactStore(tmp_path / "artifacts")

    from trace.analysis.analyzer import PythonCodeAnalyzer
    from trace.services.analysis import AnalysisService

    service = AnalysisService(
        db_gateway=in_memory_db_gateway,
        analyzer=PythonCodeAnalyzer(),
        artifact_store=store,
        git_provider=stub_git_provider,  # type: ignore[arg-type]
    )

    # 1. Trigger
    run = await service.trigger_analysis(repository_id=repo_id)

    # 2. Execute directly
    await service.execute_analysis_task(analysis_run_id=run.id)

    # 3. GET /analyses/{id}/summary
    summary_resp = await analysis_client.get(f"/api/v1/analyses/{run.id}/summary")
    assert summary_resp.status_code == 200
    summary_data = summary_resp.json()
    assert summary_data["status"] == "COMPLETED"
    assert summary_data["metrics"]["total_files"] >= 5
    assert summary_data["metrics"]["classes"] >= 3
    assert summary_data["metrics"]["endpoints"] >= 1

    # 4. GET /analyses/{id}/entities (all & filtered)
    entities_resp = await analysis_client.get(f"/api/v1/analyses/{run.id}/entities")
    assert entities_resp.status_code == 200
    entities_data = entities_resp.json()
    assert entities_data["total"] >= 10
    assert len(entities_data["items"]) > 0

    class_filter_resp = await analysis_client.get(f"/api/v1/analyses/{run.id}/entities?kind=CLASS")
    assert class_filter_resp.status_code == 200
    class_data = class_filter_resp.json()
    assert all(item["kind"] == "CLASS" for item in class_data["items"])
    assert any(item["name"] == "ItemService" for item in class_data["items"])

    # 5. GET /analyses/{id}/relationships
    rels_resp = await analysis_client.get(f"/api/v1/analyses/{run.id}/relationships")
    assert rels_resp.status_code == 200
    rels_data = rels_resp.json()
    assert rels_data["total"] >= 5

    # 6. GET /analyses/{id}/diagnostics
    diag_resp = await analysis_client.get(f"/api/v1/analyses/{run.id}/diagnostics")
    assert diag_resp.status_code == 200
    diag_data = diag_resp.json()
    assert diag_data["total"] == 0  # sample_repo has 0 syntax errors
