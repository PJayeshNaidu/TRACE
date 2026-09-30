"""Unit tests for AnalysisService lifecycle, artifact persistence, and queries."""

import uuid
from datetime import UTC, datetime
from pathlib import Path
from trace.analysis.analyzer import PythonCodeAnalyzer
from trace.domain.analysis import (
    AnalysisStatus,
    RepositoryAnalysis,
)
from trace.domain.exceptions import (
    InvalidAnalysisStateError,
    ProjectArchivedError,
    RepositoryNotFoundError,
)
from trace.domain.project import ProjectStatus
from trace.domain.repository import RepositoryType
from trace.infrastructure.database.gateway import InMemoryDatabaseGateway
from trace.infrastructure.database.models import ProjectOrm, RepositoryOrm
from trace.infrastructure.storage.artifact_store import FileArtifactStore
from trace.services.analysis import AnalysisExecutor, AnalysisService
from unittest.mock import MagicMock

import pytest


class SynchronousAnalysisExecutor(AnalysisExecutor):
    """Test executor that executes tasks directly and synchronously."""

    def __init__(self, service: AnalysisService) -> None:
        self.service = service
        self.dispatched_runs: list[uuid.UUID] = []

    def dispatch(
        self,
        analysis_run_id: uuid.UUID,
        target_ref: str | None,
        exclude_patterns: tuple[str, ...],
    ) -> None:
        self.dispatched_runs.append(analysis_run_id)


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def sample_repo_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "sample_repo"


@pytest.fixture
async def setup_project_and_repo(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    sample_repo_path: Path,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Helper fixture to insert an active project and connected repository."""
    async with in_memory_db_gateway.session() as session:
        proj_id = uuid.uuid4()
        repo_id = uuid.uuid4()
        now = datetime.now(UTC)

        proj = ProjectOrm(
            id=proj_id,
            name="Test Project",
            description="Project for analysis tests",
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


@pytest.mark.asyncio
async def test_trigger_analysis_success(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    stub_git_provider: MagicMock,
    setup_project_and_repo: tuple[uuid.UUID, uuid.UUID],
    tmp_path: Path,
) -> None:
    """Verify trigger_analysis validates project/repo and queues a PENDING run."""
    _, repo_id = setup_project_and_repo
    store = FileArtifactStore(tmp_path / "artifacts")
    service = AnalysisService(
        db_gateway=in_memory_db_gateway,
        analyzer=PythonCodeAnalyzer(),
        artifact_store=store,
        git_provider=stub_git_provider,
    )
    executor = SynchronousAnalysisExecutor(service)

    run = await service.trigger_analysis(
        repository_id=repo_id,
        target_ref="main",
        exclude_patterns=["tests/*"],
        executor=executor,
    )

    assert run.id is not None
    assert run.repository_id == repo_id
    assert run.status == AnalysisStatus.PENDING
    assert run.target_ref == "main"
    assert executor.dispatched_runs == [run.id]

    # Verify persisted in database
    retrieved = await service.get_analysis_run(run.id)
    assert retrieved.id == run.id
    assert retrieved.status == AnalysisStatus.PENDING


@pytest.mark.asyncio
async def test_trigger_analysis_repo_not_found(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    stub_git_provider: MagicMock,
    tmp_path: Path,
) -> None:
    """Verify triggering analysis for nonexistent repo raises RepositoryNotFoundError."""
    store = FileArtifactStore(tmp_path / "artifacts")
    service = AnalysisService(
        db_gateway=in_memory_db_gateway,
        analyzer=PythonCodeAnalyzer(),
        artifact_store=store,
        git_provider=stub_git_provider,
    )

    with pytest.raises(RepositoryNotFoundError):
        await service.trigger_analysis(repository_id=uuid.uuid4())


@pytest.mark.asyncio
async def test_trigger_analysis_archived_project(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    stub_git_provider: MagicMock,
    setup_project_and_repo: tuple[uuid.UUID, uuid.UUID],
    tmp_path: Path,
) -> None:
    """Verify triggering analysis on an ARCHIVED project raises ProjectArchivedError."""
    proj_id, repo_id = setup_project_and_repo
    async with in_memory_db_gateway.session() as session:
        from sqlalchemy import select

        proj = (
            await session.execute(select(ProjectOrm).where(ProjectOrm.id == proj_id))
        ).scalar_one()
        proj.status = ProjectStatus.ARCHIVED
        await session.commit()

    store = FileArtifactStore(tmp_path / "artifacts")
    service = AnalysisService(
        db_gateway=in_memory_db_gateway,
        analyzer=PythonCodeAnalyzer(),
        artifact_store=store,
        git_provider=stub_git_provider,
    )

    with pytest.raises(ProjectArchivedError):
        await service.trigger_analysis(repository_id=repo_id)


@pytest.mark.asyncio
async def test_execute_analysis_task_lifecycle(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    stub_git_provider: MagicMock,
    setup_project_and_repo: tuple[uuid.UUID, uuid.UUID],
    tmp_path: Path,
) -> None:
    """Verify execute_analysis_task completes the run and writes artifact."""
    _, repo_id = setup_project_and_repo
    store = FileArtifactStore(tmp_path / "artifacts")
    service = AnalysisService(
        db_gateway=in_memory_db_gateway,
        analyzer=PythonCodeAnalyzer(),
        artifact_store=store,
        git_provider=stub_git_provider,
    )
    executor = SynchronousAnalysisExecutor(service)

    run = await service.trigger_analysis(
        repository_id=repo_id,
        target_ref="main",
        executor=executor,
    )

    # Execute analysis synchronously
    await service.execute_analysis_task(
        analysis_run_id=run.id,
        target_ref="main",
    )

    # Verify run record in DB
    completed_run = await service.get_analysis_run(run.id)
    assert completed_run.status == AnalysisStatus.COMPLETED
    assert completed_run.started_at is not None
    assert completed_run.completed_at is not None
    assert completed_run.duration_ms is not None
    assert completed_run.duration_ms >= 0
    assert completed_run.total_files >= 5
    assert completed_run.python_files >= 5
    assert completed_run.total_modules >= 5
    assert completed_run.total_classes >= 3
    assert completed_run.total_functions >= 5
    assert completed_run.total_relationships >= 5
    assert completed_run.commit_hash == "1234567890123456789012345678901234567890"

    # Verify artifact was persisted and can be reloaded
    artifact = await service.get_analysis_artifact(run.id)
    assert isinstance(artifact, RepositoryAnalysis)
    assert artifact.run_id == run.id
    assert len(artifact.files) >= 5
    assert len(artifact.classes) >= 3

    # Verify repository last_analysis_run_id was updated
    async with in_memory_db_gateway.session() as session:
        from sqlalchemy import select

        repo = (
            await session.execute(select(RepositoryOrm).where(RepositoryOrm.id == repo_id))
        ).scalar_one()
        assert repo.last_analysis_run_id == run.id


@pytest.mark.asyncio
async def test_execute_analysis_task_failure_handling(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    stub_git_provider: MagicMock,
    setup_project_and_repo: tuple[uuid.UUID, uuid.UUID],
    tmp_path: Path,
) -> None:
    """Verify fatal exception during analysis marks the run as FAILED and logs error."""
    _, repo_id = setup_project_and_repo
    store = FileArtifactStore(tmp_path / "artifacts")

    # Failing analyzer mock
    failing_analyzer = MagicMock()
    failing_analyzer.analyze.side_effect = RuntimeError("Fatal disk parse error")

    service = AnalysisService(
        db_gateway=in_memory_db_gateway,
        analyzer=failing_analyzer,
        artifact_store=store,
        git_provider=stub_git_provider,
    )
    executor = SynchronousAnalysisExecutor(service)

    run = await service.trigger_analysis(repository_id=repo_id, executor=executor)
    await service.execute_analysis_task(analysis_run_id=run.id)

    failed_run = await service.get_analysis_run(run.id)
    assert failed_run.status == AnalysisStatus.FAILED
    assert "Fatal disk parse error" in (failed_run.error_message or "")
    assert failed_run.completed_at is not None

    # Getting artifact for failed run raises InvalidAnalysisStateError
    with pytest.raises(InvalidAnalysisStateError):
        await service.get_analysis_artifact(run.id)


@pytest.mark.asyncio
async def test_list_analysis_runs_pagination(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    stub_git_provider: MagicMock,
    setup_project_and_repo: tuple[uuid.UUID, uuid.UUID],
    tmp_path: Path,
) -> None:
    """Verify list_analysis_runs supports limit, offset, and status filter."""
    _, repo_id = setup_project_and_repo
    store = FileArtifactStore(tmp_path / "artifacts")
    service = AnalysisService(
        db_gateway=in_memory_db_gateway,
        analyzer=PythonCodeAnalyzer(),
        artifact_store=store,
        git_provider=stub_git_provider,
    )
    executor = SynchronousAnalysisExecutor(service)

    # Trigger 3 runs
    await service.trigger_analysis(repository_id=repo_id, executor=executor)
    await service.trigger_analysis(repository_id=repo_id, executor=executor)
    await service.trigger_analysis(repository_id=repo_id, executor=executor)

    # List all
    runs, total = await service.list_analysis_runs(repository_id=repo_id, limit=10, offset=0)
    assert total == 3
    assert len(runs) == 3

    # Limit and offset
    runs_p1, total = await service.list_analysis_runs(repository_id=repo_id, limit=2, offset=0)
    assert len(runs_p1) == 2
    runs_p2, total = await service.list_analysis_runs(repository_id=repo_id, limit=2, offset=2)
    assert len(runs_p2) == 1

    # Filter by status
    pending_runs, pending_total = await service.list_analysis_runs(
        repository_id=repo_id, status=AnalysisStatus.PENDING
    )
    assert pending_total == 3

    completed_runs, completed_total = await service.list_analysis_runs(
        repository_id=repo_id, status=AnalysisStatus.COMPLETED
    )
    assert completed_total == 0
