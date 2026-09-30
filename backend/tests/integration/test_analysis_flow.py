"""End-to-end integration test verifying full F01->F02 analysis journey.

Uses live PostgreSQL and filesystem artifact store.
"""

import asyncio
import os
import uuid
from pathlib import Path
from trace.analysis.analyzer import PythonCodeAnalyzer
from trace.domain.analysis import AnalysisStatus
from trace.domain.repository import RepositoryType
from trace.infrastructure.database.gateway import SQLAlchemyDatabaseGateway
from trace.infrastructure.database.models import AnalysisRunOrm, ProjectOrm, RepositoryOrm
from trace.infrastructure.git.adapters.subprocess import SubprocessGitProvider
from trace.infrastructure.storage.artifact_store import FileArtifactStore
from trace.services.analysis import AnalysisService
from trace.services.project import ProjectService
from trace.services.repository import RepositoryService

import pytest
from alembic.config import Config
from sqlalchemy import select

from alembic import command


def _get_alembic_config(database_url: str) -> Config:
    alembic_ini_path = Path(__file__).resolve().parents[2] / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini_path))
    alembic_cfg.set_main_option("sqlalchemy.url", database_url)
    return alembic_cfg


@pytest.mark.integration
async def test_full_analysis_journey_live_postgres(tmp_path: Path) -> None:
    """Validate full journey: Project -> Repo -> Static Analysis -> DB -> Artifact."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url or not (
        database_url.startswith("postgresql") or database_url.startswith("postgres")
    ):
        pytest.skip("Live PostgreSQL DATABASE_URL is not configured")

    # 1. Apply all migrations up to head (including 0003_analysis_runs)
    alembic_cfg = _get_alembic_config(database_url)
    await asyncio.to_thread(command.upgrade, alembic_cfg, "head")

    gateway = SQLAlchemyDatabaseGateway(database_url)
    sample_repo_path = Path(__file__).resolve().parents[1] / "fixtures" / "sample_repo"
    artifact_store = FileArtifactStore(tmp_path / "artifacts")
    git_provider = SubprocessGitProvider()
    analyzer = PythonCodeAnalyzer()

    project_service = ProjectService(gateway)
    repo_service = RepositoryService(gateway, git_provider)
    analysis_service = AnalysisService(
        db_gateway=gateway,
        analyzer=analyzer,
        artifact_store=artifact_store,
        git_provider=git_provider,
    )

    created_project_id: uuid.UUID | None = None
    created_repo_id: uuid.UUID | None = None
    analysis_run_id: uuid.UUID | None = None

    try:
        # 2. Register project
        proj_name = f"F02 Flow Project {uuid.uuid4().hex[:8]}"
        project = await project_service.create_project(
            name=proj_name, description="E2E Analysis Test"
        )
        created_project_id = project.id

        # 3. Register repository
        repo = await repo_service.register_repository(
            project_id=project.id,
            repo_type=RepositoryType.LOCAL,
            location=str(sample_repo_path),
            default_branch="main",
        )
        created_repo_id = repo.id

        # 4. Trigger analysis
        run = await analysis_service.trigger_analysis(
            repository_id=repo.id,
            target_ref="main",
        )
        analysis_run_id = run.id
        assert run.status == AnalysisStatus.PENDING

        # 5. Execute analysis task
        await analysis_service.execute_analysis_task(analysis_run_id=run.id, target_ref="main")

        # 6. Verify AnalysisRunOrm in PostgreSQL
        async with gateway.session() as session:
            stmt = select(AnalysisRunOrm).where(AnalysisRunOrm.id == run.id)
            run_orm = (await session.execute(stmt)).scalar_one()

            assert run_orm.status == AnalysisStatus.COMPLETED
            assert run_orm.duration_ms is not None
            assert run_orm.duration_ms > 0
            assert run_orm.total_files >= 5
            assert run_orm.python_files >= 5
            assert run_orm.total_modules >= 5
            assert run_orm.total_classes >= 3
            assert run_orm.total_functions >= 5
            assert run_orm.total_relationships >= 5
            assert run_orm.total_diagnostics == 0

            # Verify repository last_analysis_run_id
            repo_stmt = select(RepositoryOrm).where(RepositoryOrm.id == repo.id)
            repo_orm = (await session.execute(repo_stmt)).scalar_one()
            assert repo_orm.last_analysis_run_id == run.id

        # 7. Verify JSON artifact exists on filesystem
        assert artifact_store.exists(run.id)
        artifact = await analysis_service.get_analysis_artifact(run.id)
        assert artifact.run_id == run.id
        assert len(artifact.modules) >= 5
        assert len(artifact.classes) >= 3

    finally:
        # Cleanup created records in PostgreSQL
        if created_repo_id and analysis_run_id:
            async with gateway.session() as session:
                await session.execute(
                    AnalysisRunOrm.__table__.delete().where(AnalysisRunOrm.id == analysis_run_id)
                )
                await session.execute(
                    RepositoryOrm.__table__.delete().where(RepositoryOrm.id == created_repo_id)
                )
                if created_project_id:
                    await session.execute(
                        ProjectOrm.__table__.delete().where(ProjectOrm.id == created_project_id)
                    )
                await session.commit()
        await gateway.dispose()
