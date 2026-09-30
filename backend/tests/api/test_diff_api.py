"""API integration tests for F04 Version & Change Analyzer endpoints."""

import subprocess
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from trace.api.analyses.router import get_artifact_store, get_code_analyzer
from trace.api.diff.router import get_diff_service
from trace.api.health.router import get_db_gateway
from trace.api.repositories.router import get_git_provider
from trace.domain.project import ProjectStatus
from trace.domain.repository import RepositoryStatus, RepositoryType
from trace.infrastructure.database.gateway import InMemoryDatabaseGateway
from trace.infrastructure.database.models import ProjectOrm, RepositoryOrm
from trace.infrastructure.git.adapters.subprocess import SubprocessGitProvider
from trace.infrastructure.storage.artifact_store import FileArtifactStore
from trace.main import create_app
from trace.services.diff import VersionChangeService

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def diff_git_repo(tmp_path: Path) -> Path:
    """Create a temporary real git repo with 'main' and 'feature/login' branches."""
    repo_dir = tmp_path / "api_diff_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo_dir)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo_dir), "config", "user.name", "Diff Tester"], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "config", "user.email", "tester@trace.io"], check=True)

    # Initial commit on main
    auth_file = repo_dir / "auth.py"
    auth_file.write_text("def authenticate(user: str, token: str) -> bool:\n    return user == 'admin'\n")
    subprocess.run(["git", "-C", str(repo_dir), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "commit", "-m", "feat: initial auth module"], check=True)

    # Commit on feature branch with breaking change (removed token param, added required secret param)
    subprocess.run(["git", "-C", str(repo_dir), "checkout", "-b", "feature/login"], check=True)
    auth_file.write_text("def authenticate(user: str, secret: str) -> bool:\n    return secret == 'secret'\n")
    subprocess.run(["git", "-C", str(repo_dir), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "commit", "-m", "refactor: use secret instead of token"], check=True)

    return repo_dir


@pytest.fixture
async def setup_diff_api_repo(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    diff_git_repo: Path,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Insert active project and connected repo."""
    async with in_memory_db_gateway.session() as session:
        proj_id = uuid.uuid4()
        repo_id = uuid.uuid4()
        now = datetime.now(UTC)

        proj = ProjectOrm(
            id=proj_id,
            name="Diff API Project",
            status=ProjectStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        repo = RepositoryOrm(
            id=repo_id,
            project_id=proj_id,
            type=RepositoryType.LOCAL.value,
            location=str(diff_git_repo),
            default_branch="main",
            status=RepositoryStatus.CONNECTED.value,
            created_at=now,
            updated_at=now,
        )
        session.add(proj)
        session.add(repo)
        await session.commit()
        return proj_id, repo_id


@pytest.fixture
async def api_client(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    tmp_path: Path,
) -> AsyncIterator[AsyncClient]:
    """Create FastAPI test client with dependency overrides."""
    app = create_app()
    git_provider = SubprocessGitProvider()
    artifact_store = FileArtifactStore(tmp_path / "artifacts")
    diff_service = VersionChangeService(
        db_gateway=in_memory_db_gateway,
        git_provider=git_provider,
        artifact_store=artifact_store,
    )

    app.dependency_overrides[get_db_gateway] = lambda: in_memory_db_gateway
    app.dependency_overrides[get_git_provider] = lambda: git_provider
    app.dependency_overrides[get_artifact_store] = lambda: artifact_store
    app.dependency_overrides[get_diff_service] = lambda: diff_service

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_compare_branches_workflow(
    api_client: AsyncClient,
    setup_diff_api_repo: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """Test full comparison lifecycle: trigger -> detail -> branch list -> commit list."""
    _, repo_id = setup_diff_api_repo

    # 1. Trigger branch-to-branch comparison
    resp = await api_client.post(
        "/api/v1/analyses/compare",
        json={
            "repository_id": str(repo_id),
            "base_ref": "main",
            "target_ref": "feature/login",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    comparison_id = data["comparison_id"]
    assert data["base_ref"] == "main"
    assert data["target_ref"] == "feature/login"
    assert data["risk_level"] in ("HIGH", "CRITICAL")
    assert data["summary"]["total_files_changed"] >= 1
    assert data["summary"]["total_breaking_changes"] >= 1

    # 2. Get comparison detail
    detail_resp = await api_client.get(f"/api/v1/analyses/compare/{comparison_id}")
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()
    assert detail_data["comparison_id"] == comparison_id
    assert len(detail_data["symbol_diffs"]) >= 1
    assert detail_data["symbol_diffs"][0]["is_breaking"] is True
    assert len(detail_data["commit_messages"]) >= 1

    # 3. List branches
    branches_resp = await api_client.get(f"/api/v1/repositories/{repo_id}/branches")
    assert branches_resp.status_code == 200
    branches_data = branches_resp.json()
    assert "main" in branches_data["branches"]
    assert "feature/login" in branches_data["branches"]

    # 4. List commits
    commits_resp = await api_client.get(f"/api/v1/repositories/{repo_id}/commits?branch=feature/login&limit=10")
    assert commits_resp.status_code == 200
    commits_data = commits_resp.json()
    assert len(commits_data["commits"]) >= 2
    assert commits_data["commits"][0]["message"] == "refactor: use secret instead of token"


@pytest.mark.asyncio
async def test_get_comparison_not_found(api_client: AsyncClient) -> None:
    """Non-existent comparison ID returns 404."""
    resp = await api_client.get(f"/api/v1/analyses/compare/{uuid.uuid4()}")
    assert resp.status_code == 404
