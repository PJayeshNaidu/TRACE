"""Integration tests verifying PostgreSQL persistence, migrations, and constraints for F01."""

import asyncio
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from trace.domain.exceptions import DuplicateRepositoryError, ProjectArchivedError
from trace.domain.project import ProjectStatus
from trace.domain.repository import RepositoryStatus, RepositoryType
from trace.infrastructure.database.gateway import SQLAlchemyDatabaseGateway
from trace.infrastructure.database.models import ProjectOrm, RepositoryOrm
from trace.infrastructure.git.adapters.subprocess import SubprocessGitProvider
from trace.services.project import ProjectService
from trace.services.repository import RepositoryService

import pytest
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from alembic import command


def _get_alembic_config(database_url: str) -> Config:
    alembic_ini_path = Path(__file__).resolve().parents[2] / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini_path))
    alembic_cfg.set_main_option("sqlalchemy.url", database_url)
    return alembic_cfg


@pytest.mark.integration
async def test_postgres_f01_migrations_and_lifecycle() -> None:
    """Verify F01 migrations, unique constraints, archival, and deletion on live PostgreSQL."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url or not (
        database_url.startswith("postgresql") or database_url.startswith("postgres")
    ):
        pytest.skip("Live PostgreSQL DATABASE_URL is not configured")

    alembic_cfg = _get_alembic_config(database_url)

    # 1. Apply migrations up to head (including 0002_project_repository)
    await asyncio.to_thread(command.upgrade, alembic_cfg, "head")

    gateway = SQLAlchemyDatabaseGateway(database_url)
    try:
        # Check connectivity
        is_reachable = await gateway.health_check()
        assert is_reachable is True

        project_service = ProjectService(gateway)
        repo_service = RepositoryService(gateway, SubprocessGitProvider())

        # 2. Test project and repository creation with real UUID primary keys
        proj_name = f"Postgres Project {uuid.uuid4().hex[:8]}"
        project = await project_service.create_project(
            name=proj_name, description="Postgres integration test"
        )
        assert isinstance(project.id, uuid.UUID)
        assert project.status == ProjectStatus.ACTIVE

        repo_location = f"/workspace/repo-{uuid.uuid4().hex[:8]}"
        repo = await repo_service.register_repository(
            project_id=project.id,
            repo_type=RepositoryType.LOCAL,
            location=repo_location,
        )
        assert isinstance(repo.id, uuid.UUID)
        assert repo.project_id == project.id
        assert repo.status == RepositoryStatus.REGISTERED

        # 3. Test that uq_project_location raises IntegrityError on duplicate registration
        with pytest.raises(DuplicateRepositoryError):
            await repo_service.register_repository(
                project_id=project.id,
                repo_type=RepositoryType.LOCAL,
                location=repo_location,
            )

        # Direct DB check for composite unique constraint
        async with gateway.session() as session:
            duplicate_orm = RepositoryOrm(
                id=uuid.uuid4(),
                project_id=project.id,
                type="LOCAL",
                location=repo_location,
                status="REGISTERED",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            session.add(duplicate_orm)
            with pytest.raises(IntegrityError):
                await session.flush()

        # 4. Test project archival transitions status and prevents new repository registration
        archived_proj, count = await project_service.archive_project(project.id)
        assert archived_proj.status == ProjectStatus.ARCHIVED
        assert count == 1

        with pytest.raises(ProjectArchivedError):
            await repo_service.register_repository(
                project_id=project.id,
                repo_type=RepositoryType.LOCAL,
                location="/workspace/new-repo",
            )

        # 5. Test project reactivation transitions status back to ACTIVE
        reactivated_proj, _ = await project_service.activate_project(project.id)
        assert reactivated_proj.status == ProjectStatus.ACTIVE

        # 6. Test that unanalyzed repositories can be deleted while avoiding
        # project hard-delete cascades in accordance with the archival model.
        await repo_service.delete_repository(repo.id)
        # Verify repository is deleted
        async with gateway.session() as session:
            deleted_repo = (
                await session.execute(select(RepositoryOrm).where(RepositoryOrm.id == repo.id))
            ).scalar_one_or_none()
            assert deleted_repo is None

            # Verify project still exists (archival model, no cascade delete of project)
            existing_proj = (
                await session.execute(select(ProjectOrm).where(ProjectOrm.id == project.id))
            ).scalar_one_or_none()
            assert existing_proj is not None

        # 7. Test that alembic downgrade -1 cleanly reverts to 0001_baseline
        await asyncio.to_thread(command.downgrade, alembic_cfg, "-1")

        # Re-upgrade to head to leave DB clean for subsequent runs
        await asyncio.to_thread(command.upgrade, alembic_cfg, "head")

    finally:
        await gateway.dispose()
