"""Unit tests for partial failure tolerance, syntax errors, and edge case repositories."""

import uuid
from datetime import UTC, datetime
from pathlib import Path
from trace.analysis.analyzer import AnalysisContext, PythonCodeAnalyzer
from trace.domain.analysis import (
    AnalysisStatus,
    DiagnosticSeverity,
)
from trace.domain.project import ProjectStatus
from trace.domain.repository import RepositoryType
from trace.infrastructure.database.gateway import InMemoryDatabaseGateway
from trace.infrastructure.database.models import ProjectOrm, RepositoryOrm
from trace.infrastructure.storage.artifact_store import FileArtifactStore
from trace.services.analysis import AnalysisService
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def syntax_error_repo_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "syntax_error_repo"


@pytest.fixture
def empty_repo_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "empty_repo"


@pytest.fixture
def ignored_dirs_repo_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "ignored_dirs_repo"


def test_syntax_error_repo_partial_success(syntax_error_repo_path: Path) -> None:
    """Verify analyzer parses valid files and records diagnostics for syntax errors."""
    analyzer = PythonCodeAnalyzer()
    context = AnalysisContext(
        run_id=uuid.uuid4(),
        repository_id=uuid.uuid4(),
        working_tree_path=syntax_error_repo_path,
        resolved_revision="1234567890123456789012345678901234567890",
    )

    result = analyzer.analyze(context)

    # valid.py was parsed
    assert len(result.modules) >= 1
    assert any(m.file_path == "valid.py" for m in result.modules)

    # broken.py generated an error diagnostic
    assert len(result.diagnostics) == 1
    diag = result.diagnostics[0]
    assert diag.file_path == "broken.py"
    assert diag.severity == DiagnosticSeverity.ERROR
    assert diag.code == "SYNTAX_ERROR"
    assert diag.line is not None

    # Summary metrics accurately reflect partial success
    assert result.summary["python_files"] == 2
    assert result.summary["total_diagnostics"] == 1
    assert result.summary["total_modules"] >= 1


def test_empty_repo_completes_cleanly(empty_repo_path: Path) -> None:
    """Verify analyzer handles empty repos cleanly with zero findings and zero diagnostics."""
    analyzer = PythonCodeAnalyzer()
    context = AnalysisContext(
        run_id=uuid.uuid4(),
        repository_id=uuid.uuid4(),
        working_tree_path=empty_repo_path,
        resolved_revision="0000000000000000000000000000000000000000",
    )

    result = analyzer.analyze(context)

    assert len(result.files) == 0
    assert len(result.modules) == 0
    assert len(result.classes) == 0
    assert len(result.functions) == 0
    assert len(result.relationships) == 0
    assert len(result.diagnostics) == 0
    assert result.summary["total_files"] == 0
    assert result.summary["total_diagnostics"] == 0


def test_ignored_dirs_repo_skips_venv_and_pycache(ignored_dirs_repo_path: Path) -> None:
    """Verify analyzer strictly prunes .venv and __pycache__ while parsing legitimate files."""
    analyzer = PythonCodeAnalyzer()
    context = AnalysisContext(
        run_id=uuid.uuid4(),
        repository_id=uuid.uuid4(),
        working_tree_path=ignored_dirs_repo_path,
        resolved_revision="0000000000000000000000000000000000000000",
    )

    result = analyzer.analyze(context)

    analyzed_paths = {f.path for f in result.files}
    assert "main.py" in analyzed_paths
    assert not any(".venv" in p for p in analyzed_paths)
    assert not any("__pycache__" in p for p in analyzed_paths)

    assert len(result.modules) == 1
    assert result.modules[0].qualified_name == "main"


@pytest.mark.asyncio
async def test_syntax_error_service_lifecycle_completes(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    stub_git_provider: MagicMock,
    syntax_error_repo_path: Path,
    tmp_path: Path,
) -> None:
    """Verify AnalysisService marks run COMPLETED even when syntax error diagnostics occur."""
    async with in_memory_db_gateway.session() as session:
        proj_id = uuid.uuid4()
        repo_id = uuid.uuid4()
        now = datetime.now(UTC)

        proj = ProjectOrm(
            id=proj_id,
            name="Error Test Proj",
            description="",
            status=ProjectStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        repo = RepositoryOrm(
            id=repo_id,
            project_id=proj_id,
            type=RepositoryType.LOCAL.value,
            location=str(syntax_error_repo_path),
            default_branch="main",
            status="CONNECTED",
            created_at=now,
            updated_at=now,
        )
        session.add(proj)
        session.add(repo)
        await session.commit()

    store = FileArtifactStore(tmp_path / "artifacts")
    service = AnalysisService(
        db_gateway=in_memory_db_gateway,
        analyzer=PythonCodeAnalyzer(),
        artifact_store=store,
        git_provider=stub_git_provider,
    )

    run = await service.trigger_analysis(repository_id=repo_id)
    await service.execute_analysis_task(analysis_run_id=run.id)

    completed_run = await service.get_analysis_run(run.id)
    assert completed_run.status == AnalysisStatus.COMPLETED
    assert completed_run.total_diagnostics == 1
    assert completed_run.python_files == 2
    assert completed_run.total_modules == 1

    artifact = await service.get_analysis_artifact(run.id)
    assert len(artifact.diagnostics) == 1
    assert artifact.diagnostics[0].code == "SYNTAX_ERROR"
