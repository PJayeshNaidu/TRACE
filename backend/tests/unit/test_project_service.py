"""Unit tests for ProjectService business logic using in-memory database gateway."""

import uuid
from trace.domain.exceptions import (
    DatabasePersistenceError,
    ProjectAlreadyExistsError,
    ProjectArchivedError,
    ProjectNotFoundError,
)
from trace.domain.project import ProjectStatus
from trace.infrastructure.database.gateway import InMemoryDatabaseGateway
from trace.services.project import ProjectService
from unittest.mock import patch

import pytest
from sqlalchemy.exc import OperationalError


@pytest.mark.asyncio
async def test_create_project_success(in_memory_db_gateway: InMemoryDatabaseGateway) -> None:
    """ProjectService creates an active project and persists it."""
    service = ProjectService(in_memory_db_gateway)
    project = await service.create_project("Project Alpha", "Description Alpha")

    assert project.name == "Project Alpha"
    assert project.description == "Description Alpha"
    assert project.status == ProjectStatus.ACTIVE
    assert project.id is not None
    assert project.created_at is not None
    assert project.updated_at is not None

    # Retrieve and verify
    retrieved, repo_count = await service.get_project(project.id)
    assert retrieved.id == project.id
    assert retrieved.name == "Project Alpha"
    assert repo_count == 0


@pytest.mark.asyncio
async def test_create_project_whitespace_normalization(
    in_memory_db_gateway: InMemoryDatabaseGateway,
) -> None:
    """ProjectService strips whitespace from project names."""
    service = ProjectService(in_memory_db_gateway)
    project = await service.create_project("   Trimmed Name   ")
    assert project.name == "Trimmed Name"


@pytest.mark.asyncio
async def test_create_project_blank_name_raises(
    in_memory_db_gateway: InMemoryDatabaseGateway,
) -> None:
    """ProjectService rejects empty or whitespace-only names with ValueError."""
    service = ProjectService(in_memory_db_gateway)
    with pytest.raises(ValueError, match="blank or only whitespace"):
        await service.create_project("   ")


@pytest.mark.asyncio
async def test_create_project_duplicate_name_raises(
    in_memory_db_gateway: InMemoryDatabaseGateway,
) -> None:
    """ProjectService rejects duplicate project names with ProjectAlreadyExistsError."""
    service = ProjectService(in_memory_db_gateway)
    await service.create_project("Unique Name")

    with pytest.raises(ProjectAlreadyExistsError) as exc_info:
        await service.create_project("Unique Name")
    assert "Unique Name" in str(exc_info.value)
    assert exc_info.value.details["name"] == "Unique Name"

    # Also reject with surrounding whitespace that normalizes to existing name
    with pytest.raises(ProjectAlreadyExistsError):
        await service.create_project("  Unique Name  ")


@pytest.mark.asyncio
async def test_create_project_duplicate_archived_name_raises(
    in_memory_db_gateway: InMemoryDatabaseGateway,
) -> None:
    """ProjectService rejects name collision even if the existing project is ARCHIVED."""
    service = ProjectService(in_memory_db_gateway)
    project = await service.create_project("Archived Global Unique")
    await service.archive_project(project.id)

    with pytest.raises(ProjectAlreadyExistsError):
        await service.create_project("Archived Global Unique")


@pytest.mark.asyncio
async def test_get_project_not_found(
    in_memory_db_gateway: InMemoryDatabaseGateway,
) -> None:
    """ProjectService raises ProjectNotFoundError for non-existent IDs."""
    service = ProjectService(in_memory_db_gateway)
    missing_id = uuid.uuid4()
    with pytest.raises(ProjectNotFoundError) as exc_info:
        await service.get_project(missing_id)
    assert str(missing_id) in str(exc_info.value)
    assert exc_info.value.details["project_id"] == str(missing_id)


@pytest.mark.asyncio
async def test_list_projects_pagination_and_filter(
    in_memory_db_gateway: InMemoryDatabaseGateway,
) -> None:
    """ProjectService paginates results and filters by status."""
    service = ProjectService(in_memory_db_gateway)
    p1 = await service.create_project("Project 1")
    p2 = await service.create_project("Project 2")
    p3 = await service.create_project("Project 3")
    await service.archive_project(p2.id)

    # List all
    all_projects, total = await service.list_projects(limit=10, offset=0)
    assert total == 3
    assert len(all_projects) == 3

    # Limit and offset
    page1, total = await service.list_projects(limit=2, offset=0)
    assert total == 3
    assert len(page1) == 2

    page2, total = await service.list_projects(limit=2, offset=2)
    assert total == 3
    assert len(page2) == 1

    # Filter ACTIVE
    active_projects, active_total = await service.list_projects(status=ProjectStatus.ACTIVE)
    assert active_total == 2
    assert len(active_projects) == 2
    active_ids = {p.id for p, _ in active_projects}
    assert p1.id in active_ids
    assert p3.id in active_ids

    # Filter ARCHIVED
    archived_projects, archived_total = await service.list_projects(status=ProjectStatus.ARCHIVED)
    assert archived_total == 1
    assert len(archived_projects) == 1
    assert archived_projects[0][0].id == p2.id


@pytest.mark.asyncio
async def test_archive_and_activate_lifecycle(
    in_memory_db_gateway: InMemoryDatabaseGateway,
) -> None:
    """ProjectService correctly transitions status between ACTIVE and ARCHIVED."""
    service = ProjectService(in_memory_db_gateway)
    project = await service.create_project("Lifecycle Test")
    assert project.status == ProjectStatus.ACTIVE

    # Archive
    archived, count = await service.archive_project(project.id)
    assert archived.status == ProjectStatus.ARCHIVED
    assert archived.updated_at >= project.updated_at
    assert count == 0

    # Repeat archive raises ProjectArchivedError
    with pytest.raises(ProjectArchivedError) as exc_info:
        await service.archive_project(project.id)
    assert exc_info.value.operation == "archive"

    # Reactivate
    reactivated, count = await service.activate_project(project.id)
    assert reactivated.status == ProjectStatus.ACTIVE
    assert reactivated.updated_at >= archived.updated_at
    assert count == 0


@pytest.mark.asyncio
async def test_archive_nonexistent_project_raises(
    in_memory_db_gateway: InMemoryDatabaseGateway,
) -> None:
    """Archiving a nonexistent project raises ProjectNotFoundError."""
    service = ProjectService(in_memory_db_gateway)
    with pytest.raises(ProjectNotFoundError):
        await service.archive_project(uuid.uuid4())


@pytest.mark.asyncio
async def test_activate_nonexistent_project_raises(
    in_memory_db_gateway: InMemoryDatabaseGateway,
) -> None:
    """Activating a nonexistent project raises ProjectNotFoundError."""
    service = ProjectService(in_memory_db_gateway)
    with pytest.raises(ProjectNotFoundError):
        await service.activate_project(uuid.uuid4())


@pytest.mark.asyncio
async def test_project_service_persistence_error(
    in_memory_db_gateway: InMemoryDatabaseGateway,
) -> None:
    """ProjectService wraps unexpected database failures in DatabasePersistenceError."""
    service = ProjectService(in_memory_db_gateway)
    with patch.object(
        in_memory_db_gateway,
        "session",
        side_effect=OperationalError("mock failure", params={}, orig=Exception("crash")),
    ):
        with pytest.raises(DatabasePersistenceError):
            await service.create_project("Fail Project")

        with pytest.raises(DatabasePersistenceError):
            await service.get_project(uuid.uuid4())

        with pytest.raises(DatabasePersistenceError):
            await service.list_projects()

        with pytest.raises(DatabasePersistenceError):
            await service.archive_project(uuid.uuid4())

        with pytest.raises(DatabasePersistenceError):
            await service.activate_project(uuid.uuid4())


@pytest.mark.asyncio
async def test_create_project_integrity_error_mapped(
    in_memory_db_gateway: InMemoryDatabaseGateway,
) -> None:
    """ProjectService maps unexpected database-level IntegrityError to ProjectAlreadyExistsError."""
    from sqlalchemy.exc import IntegrityError

    service = ProjectService(in_memory_db_gateway)
    with patch.object(
        in_memory_db_gateway,
        "session",
        side_effect=IntegrityError("mock duplicate", params={}, orig=Exception("uq_violation")),
    ):
        with pytest.raises(ProjectAlreadyExistsError):
            await service.create_project("Concurrent Duplicate")
