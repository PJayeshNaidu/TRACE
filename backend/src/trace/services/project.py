"""Service layer for TRACE Project management."""

import uuid
from datetime import UTC, datetime
from trace.domain.exceptions import (
    DatabasePersistenceError,
    ProjectAlreadyExistsError,
    ProjectArchivedError,
    ProjectNotFoundError,
)
from trace.domain.project import Project, ProjectStatus
from trace.infrastructure.database.gateway import DatabaseGateway
from trace.infrastructure.database.models import ProjectOrm, RepositoryOrm

import structlog
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

logger = structlog.get_logger(__name__)


class ProjectService:
    """Orchestrates project lifecycle, persistence, and state transitions."""

    def __init__(self, db_gateway: DatabaseGateway) -> None:
        self._db_gateway = db_gateway

    async def create_project(self, name: str, description: str | None = None) -> Project:
        """Create a new TRACE project in ACTIVE status with globally unique name.

        Args:
            name: Human-readable unique project name.
            description: Optional descriptive text.

        Returns:
            The created Project domain entity.

        Raises:
            ProjectAlreadyExistsError: If a project with this name exists in any status.
            DatabasePersistenceError: On unexpected persistence failures.
        """
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Project name must not be blank or only whitespace.")

        try:
            async with self._db_gateway.session() as session:
                # Check for existing project across all statuses (globally unique)
                existing_query = select(ProjectOrm.id).where(ProjectOrm.name == normalized_name)
                existing = (await session.execute(existing_query)).scalar_one_or_none()
                if existing is not None:
                    raise ProjectAlreadyExistsError(normalized_name)

                now = datetime.now(UTC)
                project_orm = ProjectOrm(
                    id=uuid.uuid4(),
                    name=normalized_name,
                    description=description,
                    status=ProjectStatus.ACTIVE,
                    created_at=now,
                    updated_at=now,
                )
                session.add(project_orm)
                await session.flush()
                project = project_orm.to_domain()
        except IntegrityError as exc:
            raise ProjectAlreadyExistsError(normalized_name) from exc
        except (ProjectAlreadyExistsError, ValueError):
            raise
        except SQLAlchemyError as exc:
            logger.error("Failed to create project", error=str(exc), name=normalized_name)
            raise DatabasePersistenceError(f"Failed to create project: {exc}") from exc

        logger.info(
            "project_created",
            project_id=str(project.id),
            id=str(project.id),
            name=project.name,
        )
        return project

    async def get_project(self, project_id: uuid.UUID) -> tuple[Project, int]:
        """Retrieve project by ID along with its registered repository count.

        Args:
            project_id: Project identifier UUID.

        Returns:
            Tuple of (Project domain entity, repository count).

        Raises:
            ProjectNotFoundError: If project does not exist.
            DatabasePersistenceError: On unexpected query failures.
        """
        try:
            async with self._db_gateway.session() as session:
                repo_count_subq = (
                    select(func.count(RepositoryOrm.id))
                    .where(RepositoryOrm.project_id == ProjectOrm.id)
                    .scalar_subquery()
                )
                query = select(ProjectOrm, repo_count_subq).where(ProjectOrm.id == project_id)
                result = await session.execute(query)
                row = result.one_or_none()
                if row is None:
                    raise ProjectNotFoundError(project_id)
                project_orm, repo_count = row
                return project_orm.to_domain(), repo_count or 0
        except ProjectNotFoundError:
            raise
        except SQLAlchemyError as exc:
            logger.error("Failed to get project", error=str(exc), project_id=str(project_id))
            raise DatabasePersistenceError(f"Failed to get project: {exc}") from exc

    async def list_projects(
        self,
        limit: int = 50,
        offset: int = 0,
        status: ProjectStatus | None = None,
    ) -> tuple[list[tuple[Project, int]], int]:
        """List paginated projects with optional status filter and repository counts.

        Args:
            limit: Maximum items to return.
            offset: Number of items to skip.
            status: Optional filter by ProjectStatus.

        Returns:
            Tuple of (list of (Project, repo_count), total matching count).

        Raises:
            DatabasePersistenceError: On unexpected query failures.
        """
        try:
            async with self._db_gateway.session() as session:
                # Count query
                count_query = select(func.count(ProjectOrm.id))
                if status is not None:
                    count_query = count_query.where(ProjectOrm.status == status)
                total = (await session.execute(count_query)).scalar_one()

                # List query
                repo_count_subq = (
                    select(func.count(RepositoryOrm.id))
                    .where(RepositoryOrm.project_id == ProjectOrm.id)
                    .scalar_subquery()
                )
                query = select(ProjectOrm, repo_count_subq)
                if status is not None:
                    query = query.where(ProjectOrm.status == status)
                query = query.order_by(ProjectOrm.created_at.desc()).limit(limit).offset(offset)
                rows = (await session.execute(query)).all()
                items = [(orm.to_domain(), count or 0) for orm, count in rows]
                return items, total
        except SQLAlchemyError as exc:
            logger.error("Failed to list projects", error=str(exc))
            raise DatabasePersistenceError(f"Failed to list projects: {exc}") from exc

    async def archive_project(self, project_id: uuid.UUID) -> tuple[Project, int]:
        """Transition project status to ARCHIVED.

        Args:
            project_id: Project identifier UUID.

        Returns:
            Tuple of (updated Project domain entity, repository count).

        Raises:
            ProjectNotFoundError: If project does not exist.
            ProjectArchivedError: If project is already archived.
            DatabasePersistenceError: On unexpected persistence failures.
        """
        try:
            async with self._db_gateway.session() as session:
                query = select(ProjectOrm).where(ProjectOrm.id == project_id)
                result = await session.execute(query)
                project_orm = result.scalar_one_or_none()
                if project_orm is None:
                    raise ProjectNotFoundError(project_id)
                if project_orm.status == ProjectStatus.ARCHIVED:
                    raise ProjectArchivedError(project_id, operation="archive")

                project_orm.status = ProjectStatus.ARCHIVED
                project_orm.updated_at = datetime.now(UTC)
                await session.flush()

                repo_count_query = select(func.count(RepositoryOrm.id)).where(
                    RepositoryOrm.project_id == project_id
                )
                repo_count = (await session.execute(repo_count_query)).scalar_one()
                project = project_orm.to_domain()
        except (ProjectNotFoundError, ProjectArchivedError):
            raise
        except SQLAlchemyError as exc:
            logger.error("Failed to archive project", error=str(exc), project_id=str(project_id))
            raise DatabasePersistenceError(f"Failed to archive project: {exc}") from exc

        logger.info(
            "project_archived",
            project_id=str(project.id),
            id=str(project.id),
        )
        return project, repo_count or 0

    async def activate_project(self, project_id: uuid.UUID) -> tuple[Project, int]:
        """Transition project status back to ACTIVE.

        Args:
            project_id: Project identifier UUID.

        Returns:
            Tuple of (updated Project domain entity, repository count).

        Raises:
            ProjectNotFoundError: If project does not exist.
            DatabasePersistenceError: On unexpected persistence failures.
        """
        try:
            async with self._db_gateway.session() as session:
                query = select(ProjectOrm).where(ProjectOrm.id == project_id)
                result = await session.execute(query)
                project_orm = result.scalar_one_or_none()
                if project_orm is None:
                    raise ProjectNotFoundError(project_id)

                project_orm.status = ProjectStatus.ACTIVE
                project_orm.updated_at = datetime.now(UTC)
                await session.flush()

                repo_count_query = select(func.count(RepositoryOrm.id)).where(
                    RepositoryOrm.project_id == project_id
                )
                repo_count = (await session.execute(repo_count_query)).scalar_one()
                project = project_orm.to_domain()
        except ProjectNotFoundError:
            raise
        except SQLAlchemyError as exc:
            logger.error("Failed to activate project", error=str(exc), project_id=str(project_id))
            raise DatabasePersistenceError(f"Failed to activate project: {exc}") from exc

        logger.info(
            "project_activated",
            project_id=str(project.id),
            id=str(project.id),
        )
        return project, repo_count or 0
