"""Unit tests for VersionChangeService (F04)."""

import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from trace.analysis.analyzer import PythonCodeAnalyzer
from trace.domain.diff import RiskLevel
from trace.domain.exceptions import RepositoryNotFoundError
from trace.domain.project import ProjectStatus
from trace.domain.repository import RepositoryStatus, RepositoryType
from trace.infrastructure.database.gateway import InMemoryDatabaseGateway
from trace.infrastructure.database.models import ProjectOrm, RepositoryOrm
from trace.infrastructure.git.adapters.subprocess import SubprocessGitProvider
from trace.infrastructure.storage.artifact_store import FileArtifactStore
from trace.services.diff import ComparisonNotFoundError, VersionChangeService

import pytest


@pytest.fixture
def setup_git_repo_with_branches(tmp_path: Path) -> Path:
    """Create a temporary real git repo with 'main' and 'feature/upgrade' branches."""
    repo_dir = tmp_path / "sample_git_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo_dir)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo_dir), "config", "user.name", "Tester"], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "config", "user.email", "test@trace.io"], check=True)

    # Initial file on main
    calc_file = repo_dir / "calculator.py"
    calc_file.write_text("def compute(x: int, y: int) -> int:\n    return x + y\n")
    subprocess.run(["git", "-C", str(repo_dir), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "commit", "-m", "feat: initial calculator"], check=True)

    # Create and commit on feature branch (breaking change: removed parameter y)
    subprocess.run(["git", "-C", str(repo_dir), "checkout", "-b", "feature/upgrade"], check=True)
    calc_file.write_text("def compute(x: int) -> int:\n    return x * 2\n")
    subprocess.run(["git", "-C", str(repo_dir), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "commit", "-m", "refactor: simplify compute to single param"], check=True)

    return repo_dir


@pytest.mark.asyncio
async def test_trigger_comparison_branch_to_branch(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    setup_git_repo_with_branches: Path,
    tmp_path: Path,
) -> None:
    """Compare 'main' vs 'feature/upgrade' detecting breaking change and risk score."""
    repo_dir = setup_git_repo_with_branches
    project_id = uuid.uuid4()
    repo_id = uuid.uuid4()

    async with in_memory_db_gateway.session() as session:
        proj = ProjectOrm(
            id=project_id,
            name="Test Proj",
            status=ProjectStatus.ACTIVE.value,
        )
        session.add(proj)
        repo = RepositoryOrm(
            id=repo_id,
            project_id=project_id,
            type=RepositoryType.LOCAL.value,
            location=str(repo_dir),
            default_branch="main",
            status=RepositoryStatus.CONNECTED.value,
        )
        session.add(repo)
        await session.commit()

    git_provider = SubprocessGitProvider()
    store = FileArtifactStore(tmp_path / "artifacts")
    service = VersionChangeService(
        db_gateway=in_memory_db_gateway,
        git_provider=git_provider,
        artifact_store=store,
        analyzer=PythonCodeAnalyzer(),
    )

    # 1. Trigger branch comparison
    comparison = await service.trigger_comparison(
        repository_id=repo_id,
        base_ref="main",
        target_ref="feature/upgrade",
    )

    assert comparison.repository_id == repo_id
    assert comparison.base_ref == "main"
    assert comparison.target_ref == "feature/upgrade"
    assert comparison.total_files_changed >= 1
    assert comparison.total_symbols_changed >= 1
    assert comparison.total_breaking_changes >= 1
    assert comparison.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
    assert len(comparison.commit_messages) >= 1

    # 2. Retrieve comparison by ID
    retrieved = await service.get_comparison(comparison.id)
    assert retrieved.id == comparison.id
    assert retrieved.total_breaking_changes == comparison.total_breaking_changes

    # 3. List branches
    branches = await service.list_branches(repo_id)
    assert "main" in branches
    assert "feature/upgrade" in branches

    # 4. List commits
    commits = await service.list_commits(repo_id, branch="feature/upgrade", limit=5)
    assert len(commits) >= 2


@pytest.mark.asyncio
async def test_comparison_not_found(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    tmp_path: Path,
) -> None:
    """Non-existent comparison ID raises ComparisonNotFoundError."""
    service = VersionChangeService(
        db_gateway=in_memory_db_gateway,
        git_provider=SubprocessGitProvider(),
        artifact_store=FileArtifactStore(tmp_path / "artifacts"),
    )
    with pytest.raises(ComparisonNotFoundError):
        await service.get_comparison(uuid.uuid4())


@pytest.mark.asyncio
async def test_trigger_comparison_repo_not_found(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    tmp_path: Path,
) -> None:
    """Triggering comparison for non-existent repo raises RepositoryNotFoundError."""
    service = VersionChangeService(
        db_gateway=in_memory_db_gateway,
        git_provider=SubprocessGitProvider(),
        artifact_store=FileArtifactStore(tmp_path / "artifacts"),
    )
    with pytest.raises(RepositoryNotFoundError):
        await service.trigger_comparison(repository_id=uuid.uuid4())
