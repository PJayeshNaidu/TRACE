"""Service layer for TRACE Repository management."""

import uuid
from datetime import UTC, datetime
from pathlib import Path
from trace.domain.exceptions import (
    DatabasePersistenceError,
    DuplicateRepositoryError,
    ProjectArchivedError,
    ProjectNotFoundError,
    RepositoryInUseError,
    RepositoryNotFoundError,
)
from trace.domain.project import ProjectStatus
from trace.domain.repository import (
    ConnectionValidationResult,
    Repository,
    RepositoryType,
    normalize_location,
)
from trace.infrastructure.database.gateway import DatabaseGateway
from trace.infrastructure.database.models import ProjectOrm, RepositoryOrm
from trace.infrastructure.git.provider import GitProvider

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

logger = structlog.get_logger(__name__)


class RepositoryService:
    """Orchestrates repository registration, retrieval, listing, deletion, and validation."""

    def __init__(self, db_gateway: DatabaseGateway, git_provider: GitProvider) -> None:
        self._db_gateway = db_gateway
        self._git_provider = git_provider

    async def register_repository(
        self,
        project_id: uuid.UUID,
        repo_type: RepositoryType,
        location: str,
        default_branch: str | None = None,
    ) -> Repository:
        """Register a new repository under an active project.

        Args:
            project_id: Parent project identifier UUID.
            repo_type: Repository type (LOCAL or REMOTE).
            location: File path or Git remote URL.
            default_branch: Optional default branch hint.

        Returns:
            The created Repository domain entity.

        Raises:
            ProjectNotFoundError: If parent project does not exist.
            ProjectArchivedError: If parent project is ARCHIVED.
            DuplicateRepositoryError: If location is already registered under this project.
            DatabasePersistenceError: On unexpected persistence failures.
        """
        normalized_location = normalize_location(location, repo_type)

        try:
            async with self._db_gateway.session() as session:
                # 1. Verify parent project existence and active status
                project_query = select(ProjectOrm).where(ProjectOrm.id == project_id)
                project_orm = (await session.execute(project_query)).scalar_one_or_none()
                if project_orm is None:
                    raise ProjectNotFoundError(project_id)
                if project_orm.status == ProjectStatus.ARCHIVED:
                    raise ProjectArchivedError(project_id, operation="register_repository")

                # 2. Check composite uniqueness on (project_id, normalized_location)
                existing_query = select(RepositoryOrm.id).where(
                    RepositoryOrm.project_id == project_id,
                    RepositoryOrm.location == normalized_location,
                )
                existing = (await session.execute(existing_query)).scalar_one_or_none()
                if existing is not None:
                    raise DuplicateRepositoryError(project_id, normalized_location)

                now = datetime.now(UTC)
                repo_orm = RepositoryOrm(
                    id=uuid.uuid4(),
                    project_id=project_id,
                    type=repo_type.value,
                    location=normalized_location,
                    default_branch=default_branch,
                    status="REGISTERED",
                    last_error=None,
                    last_validated_at=None,
                    last_analysis_run_id=None,
                    created_at=now,
                    updated_at=now,
                )
                session.add(repo_orm)
                await session.flush()
                repo = repo_orm.to_domain()
        except IntegrityError as exc:
            raise DuplicateRepositoryError(project_id, normalized_location) from exc
        except (ProjectNotFoundError, ProjectArchivedError, DuplicateRepositoryError):
            raise
        except SQLAlchemyError as exc:
            logger.error(
                "Failed to register repository",
                error=str(exc),
                project_id=str(project_id),
                location=normalized_location,
            )
            raise DatabasePersistenceError(f"Failed to register repository: {exc}") from exc

        logger.info(
            "repository_registered",
            repository_id=str(repo.id),
            id=str(repo.id),
            project_id=str(repo.project_id),
            type=repo.type.value,
            location=repo.location,
        )
        return repo

    async def get_repository(self, repository_id: uuid.UUID) -> Repository:
        """Retrieve repository details by ID.

        Args:
            repository_id: Repository identifier UUID.

        Returns:
            The Repository domain entity.

        Raises:
            RepositoryNotFoundError: If repository does not exist.
            DatabasePersistenceError: On unexpected query failures.
        """
        try:
            async with self._db_gateway.session() as session:
                query = select(RepositoryOrm).where(RepositoryOrm.id == repository_id)
                repo_orm = (await session.execute(query)).scalar_one_or_none()
                if repo_orm is None:
                    raise RepositoryNotFoundError(repository_id)
                return repo_orm.to_domain()
        except RepositoryNotFoundError:
            raise
        except SQLAlchemyError as exc:
            logger.error(
                "Failed to get repository",
                error=str(exc),
                repository_id=str(repository_id),
            )
            raise DatabasePersistenceError(f"Failed to get repository: {exc}") from exc

    async def list_repositories_for_project(self, project_id: uuid.UUID) -> list[Repository]:
        """List all repositories registered under a given project.

        Args:
            project_id: Parent project identifier UUID.

        Returns:
            List of Repository domain entities.

        Raises:
            ProjectNotFoundError: If parent project does not exist.
            DatabasePersistenceError: On unexpected query failures.
        """
        try:
            async with self._db_gateway.session() as session:
                # Confirm parent project exists
                project_query = select(ProjectOrm.id).where(ProjectOrm.id == project_id)
                project_exists = (await session.execute(project_query)).scalar_one_or_none()
                if project_exists is None:
                    raise ProjectNotFoundError(project_id)

                query = (
                    select(RepositoryOrm)
                    .where(RepositoryOrm.project_id == project_id)
                    .order_by(RepositoryOrm.created_at.asc())
                )
                rows = (await session.execute(query)).scalars().all()
                return [orm.to_domain() for orm in rows]
        except ProjectNotFoundError:
            raise
        except SQLAlchemyError as exc:
            logger.error(
                "Failed to list repositories for project",
                error=str(exc),
                project_id=str(project_id),
            )
            raise DatabasePersistenceError(
                f"Failed to list repositories for project: {exc}"
            ) from exc

    async def delete_repository(self, repository_id: uuid.UUID) -> None:
        """Delete an unanalyzed repository from PostgreSQL.

        Args:
            repository_id: Repository identifier UUID.

        Raises:
            RepositoryNotFoundError: If repository does not exist.
            RepositoryInUseError: If repository has linked analysis runs.
            DatabasePersistenceError: On unexpected persistence failures.
        """
        try:
            async with self._db_gateway.session() as session:
                query = select(RepositoryOrm).where(RepositoryOrm.id == repository_id)
                repo_orm = (await session.execute(query)).scalar_one_or_none()
                if repo_orm is None:
                    raise RepositoryNotFoundError(repository_id)

                if repo_orm.last_analysis_run_id is not None:
                    raise RepositoryInUseError(repository_id, repo_orm.last_analysis_run_id)

                project_id = repo_orm.project_id
                await session.delete(repo_orm)
        except (RepositoryNotFoundError, RepositoryInUseError):
            raise
        except SQLAlchemyError as exc:
            logger.error(
                "Failed to delete repository",
                error=str(exc),
                repository_id=str(repository_id),
            )
            raise DatabasePersistenceError(f"Failed to delete repository: {exc}") from exc

        logger.info(
            "repository_deleted",
            repository_id=str(repository_id),
            id=str(repository_id),
            project_id=str(project_id),
        )

    async def validate_repository(
        self, repository_id: uuid.UUID
    ) -> tuple[Repository, ConnectionValidationResult]:
        """Execute on-demand connectivity probe and record results without cloning.

        Args:
            repository_id: Repository identifier UUID.

        Returns:
            Tuple of (updated Repository domain entity, ConnectionValidationResult).

        Raises:
            RepositoryNotFoundError: If repository does not exist.
            ProjectArchivedError: If parent project is ARCHIVED.
            DatabasePersistenceError: On unexpected persistence failures.
        """
        try:
            async with self._db_gateway.session() as session:
                repo_query = select(RepositoryOrm).where(RepositoryOrm.id == repository_id)
                repo_orm = (await session.execute(repo_query)).scalar_one_or_none()
                if repo_orm is None:
                    raise RepositoryNotFoundError(repository_id)

                proj_query = select(ProjectOrm.status).where(ProjectOrm.id == repo_orm.project_id)
                proj_status = (await session.execute(proj_query)).scalar_one_or_none()
                if proj_status in (ProjectStatus.ARCHIVED, ProjectStatus.ARCHIVED.value):
                    raise ProjectArchivedError(repo_orm.project_id, operation="validate_repository")

                repo_type = RepositoryType(repo_orm.type)
                location = repo_orm.location
        except (RepositoryNotFoundError, ProjectArchivedError):
            raise
        except SQLAlchemyError as exc:
            logger.error(
                "Failed to query repository for validation",
                error=str(exc),
                repository_id=str(repository_id),
            )
            raise DatabasePersistenceError(
                f"Failed to query repository for validation: {exc}"
            ) from exc

        # Probe repository via GitProvider
        if repo_type == RepositoryType.LOCAL:
            probe_result = await self._git_provider.validate_local(Path(location))
        else:
            probe_result = await self._git_provider.validate_remote(location)

        # Persist validation results
        now = datetime.now(UTC)
        try:
            async with self._db_gateway.session() as session:
                repo_query = select(RepositoryOrm).where(RepositoryOrm.id == repository_id)
                repo_orm = (await session.execute(repo_query)).scalar_one()

                repo_orm.last_validated_at = now
                repo_orm.updated_at = now

                if probe_result.is_connected:
                    repo_orm.status = "CONNECTED"
                    repo_orm.last_error = None
                    if probe_result.detected_branch is not None:
                        repo_orm.default_branch = probe_result.detected_branch
                else:
                    repo_orm.status = "ERROR"
                    repo_orm.last_error = probe_result.error_message

                await session.flush()
                repo = repo_orm.to_domain()
        except SQLAlchemyError as exc:
            logger.error(
                "Failed to persist validation result",
                error=str(exc),
                repository_id=str(repository_id),
            )
            raise DatabasePersistenceError(f"Failed to persist validation result: {exc}") from exc

        if probe_result.is_connected:
            logger.info(
                "repository_validated",
                repository_id=str(repository_id),
                id=str(repository_id),
                is_connected=True,
                status=repo.status.value,
                latency_ms=probe_result.latency_ms,
            )
        else:
            logger.warning(
                "repository_validated",
                repository_id=str(repository_id),
                id=str(repository_id),
                is_connected=False,
                status=repo.status.value,
                error=probe_result.error_message,
                latency_ms=probe_result.latency_ms,
            )

        return repo, probe_result
