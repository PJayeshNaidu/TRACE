"""Unit tests for RepositoryService business logic with test doubles."""

import uuid
from datetime import UTC, datetime
from trace.domain.exceptions import (
    DatabasePersistenceError,
    DuplicateRepositoryError,
    ProjectArchivedError,
    ProjectNotFoundError,
    RepositoryInUseError,
    RepositoryNotFoundError,
)
from trace.domain.repository import (
    ConnectionValidationResult,
    RepositoryStatus,
    RepositoryType,
)
from trace.infrastructure.database.gateway import InMemoryDatabaseGateway
from trace.infrastructure.database.models import RepositoryOrm
from trace.services.project import ProjectService
from trace.services.repository import RepositoryService

import pytest
from sqlalchemy import select

from tests.conftest import StubGitProvider


@pytest.mark.asyncio
async def test_register_repository_success(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    stub_git_provider: StubGitProvider,
) -> None:
    """RepositoryService registers a repository under an active project."""
    project_svc = ProjectService(in_memory_db_gateway)
    repo_svc = RepositoryService(in_memory_db_gateway, stub_git_provider)

    project = await project_svc.create_project("Project For Repo")
    repo = await repo_svc.register_repository(
        project_id=project.id,
        repo_type=RepositoryType.REMOTE,
        location="https://github.com/my-org/my-repo.git",
        default_branch="main",
    )

    assert repo.project_id == project.id
    assert repo.type == RepositoryType.REMOTE
    assert repo.location == "https://github.com/my-org/my-repo"  # normalized
    assert repo.default_branch == "main"
    assert repo.status == RepositoryStatus.REGISTERED
    assert repo.last_analysis_run_id is None
    assert repo.last_error is None
    assert repo.last_validated_at is None


@pytest.mark.asyncio
async def test_register_repository_on_missing_project_raises(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    stub_git_provider: StubGitProvider,
) -> None:
    """Registering under a non-existent project raises ProjectNotFoundError."""
    repo_svc = RepositoryService(in_memory_db_gateway, stub_git_provider)
    missing_pid = uuid.uuid4()
    with pytest.raises(ProjectNotFoundError) as exc_info:
        await repo_svc.register_repository(
            project_id=missing_pid,
            repo_type=RepositoryType.LOCAL,
            location="/some/path",
        )
    assert str(missing_pid) in str(exc_info.value)


@pytest.mark.asyncio
async def test_register_repository_on_archived_project_raises(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    stub_git_provider: StubGitProvider,
) -> None:
    """Registering under an ARCHIVED project raises ProjectArchivedError."""
    project_svc = ProjectService(in_memory_db_gateway)
    repo_svc = RepositoryService(in_memory_db_gateway, stub_git_provider)

    project = await project_svc.create_project("Archived Project")
    await project_svc.archive_project(project.id)

    with pytest.raises(ProjectArchivedError) as exc_info:
        await repo_svc.register_repository(
            project_id=project.id,
            repo_type=RepositoryType.REMOTE,
            location="https://github.com/org/repo",
        )
    assert exc_info.value.operation == "register_repository"


@pytest.mark.asyncio
async def test_register_duplicate_repository_raises(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    stub_git_provider: StubGitProvider,
) -> None:
    """Registering duplicate location in same project raises DuplicateRepositoryError."""
    project_svc = ProjectService(in_memory_db_gateway)
    repo_svc = RepositoryService(in_memory_db_gateway, stub_git_provider)

    project = await project_svc.create_project("Dup Repo Project")
    await repo_svc.register_repository(
        project_id=project.id,
        repo_type=RepositoryType.REMOTE,
        location="https://github.com/org/repo.git",
    )

    # Re-registering exact same URL
    with pytest.raises(DuplicateRepositoryError) as exc_info:
        await repo_svc.register_repository(
            project_id=project.id,
            repo_type=RepositoryType.REMOTE,
            location="https://github.com/org/repo.git",
        )
    assert exc_info.value.details["location"] == "https://github.com/org/repo"

    # Re-registering with trailing slash or diff casing normalizes and detects conflict
    with pytest.raises(DuplicateRepositoryError):
        await repo_svc.register_repository(
            project_id=project.id,
            repo_type=RepositoryType.REMOTE,
            location="HTTPS://GITHUB.COM/org/repo/",
        )


@pytest.mark.asyncio
async def test_register_same_location_across_different_projects(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    stub_git_provider: StubGitProvider,
) -> None:
    """Distinct projects MAY register the same Git repository without collision."""
    project_svc = ProjectService(in_memory_db_gateway)
    repo_svc = RepositoryService(in_memory_db_gateway, stub_git_provider)

    p1 = await project_svc.create_project("Project 1")
    p2 = await project_svc.create_project("Project 2")

    url = "https://github.com/shared/repo"
    r1 = await repo_svc.register_repository(
        project_id=p1.id, repo_type=RepositoryType.REMOTE, location=url
    )
    r2 = await repo_svc.register_repository(
        project_id=p2.id, repo_type=RepositoryType.REMOTE, location=url
    )

    assert r1.id != r2.id
    assert r1.project_id == p1.id
    assert r2.project_id == p2.id
    assert r1.location == r2.location


@pytest.mark.asyncio
async def test_get_repository_and_not_found(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    stub_git_provider: StubGitProvider,
) -> None:
    """get_repository retrieves entity or raises RepositoryNotFoundError."""
    project_svc = ProjectService(in_memory_db_gateway)
    repo_svc = RepositoryService(in_memory_db_gateway, stub_git_provider)

    project = await project_svc.create_project("Get Repo Project")
    registered = await repo_svc.register_repository(
        project_id=project.id,
        repo_type=RepositoryType.LOCAL,
        location="/tmp/test-repo",
    )

    fetched = await repo_svc.get_repository(registered.id)
    assert fetched.id == registered.id
    assert fetched.project_id == project.id

    missing_id = uuid.uuid4()
    with pytest.raises(RepositoryNotFoundError):
        await repo_svc.get_repository(missing_id)


@pytest.mark.asyncio
async def test_list_repositories_for_project(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    stub_git_provider: StubGitProvider,
) -> None:
    """list_repositories_for_project returns linked repositories or raises if missing project."""
    project_svc = ProjectService(in_memory_db_gateway)
    repo_svc = RepositoryService(in_memory_db_gateway, stub_git_provider)

    project = await project_svc.create_project("List Repos Project")
    r1 = await repo_svc.register_repository(
        project_id=project.id, repo_type=RepositoryType.LOCAL, location="/repo/a"
    )
    r2 = await repo_svc.register_repository(
        project_id=project.id, repo_type=RepositoryType.LOCAL, location="/repo/b"
    )

    repos = await repo_svc.list_repositories_for_project(project.id)
    assert len(repos) == 2
    repo_ids = {r.id for r in repos}
    assert r1.id in repo_ids
    assert r2.id in repo_ids

    # Querying repos for nonexistent project raises ProjectNotFoundError
    with pytest.raises(ProjectNotFoundError):
        await repo_svc.list_repositories_for_project(uuid.uuid4())


@pytest.mark.asyncio
async def test_delete_unanalyzed_repository(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    stub_git_provider: StubGitProvider,
) -> None:
    """delete_repository successfully removes an unanalyzed repository."""
    project_svc = ProjectService(in_memory_db_gateway)
    repo_svc = RepositoryService(in_memory_db_gateway, stub_git_provider)

    project = await project_svc.create_project("Delete Repo Project")
    repo = await repo_svc.register_repository(
        project_id=project.id,
        repo_type=RepositoryType.LOCAL,
        location="/repo/to-delete",
    )

    await repo_svc.delete_repository(repo.id)

    # Repository no longer exists
    with pytest.raises(RepositoryNotFoundError):
        await repo_svc.get_repository(repo.id)


@pytest.mark.asyncio
async def test_delete_analyzed_repository_rejected(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    stub_git_provider: StubGitProvider,
) -> None:
    """delete_repository rejects deletion when last_analysis_run_id is set."""
    project_svc = ProjectService(in_memory_db_gateway)
    repo_svc = RepositoryService(in_memory_db_gateway, stub_git_provider)

    project = await project_svc.create_project("Analyzed Repo Project")
    repo = await repo_svc.register_repository(
        project_id=project.id,
        repo_type=RepositoryType.LOCAL,
        location="/repo/analyzed",
    )

    # Simulate an F02 analysis run having touched this repository
    fake_run_id = uuid.uuid4()
    async with in_memory_db_gateway.session() as session:
        query = select(RepositoryOrm).where(RepositoryOrm.id == repo.id)
        repo_orm = (await session.execute(query)).scalar_one()
        repo_orm.last_analysis_run_id = fake_run_id
        repo_orm.updated_at = datetime.now(UTC)

    with pytest.raises(RepositoryInUseError) as exc_info:
        await repo_svc.delete_repository(repo.id)
    assert exc_info.value.last_analysis_run_id == str(fake_run_id)


@pytest.mark.asyncio
async def test_delete_nonexistent_repository_raises(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    stub_git_provider: StubGitProvider,
) -> None:
    """Deleting a non-existent repository raises RepositoryNotFoundError."""
    repo_svc = RepositoryService(in_memory_db_gateway, stub_git_provider)
    with pytest.raises(RepositoryNotFoundError):
        await repo_svc.delete_repository(uuid.uuid4())


@pytest.mark.asyncio
async def test_repository_service_persistence_error(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    stub_git_provider: StubGitProvider,
) -> None:
    """RepositoryService wraps database errors in DatabasePersistenceError."""
    from unittest.mock import patch

    from sqlalchemy.exc import OperationalError

    repo_svc = RepositoryService(in_memory_db_gateway, stub_git_provider)
    with patch.object(
        in_memory_db_gateway,
        "session",
        side_effect=OperationalError("mock failure", params={}, orig=Exception("crash")),
    ):
        with pytest.raises(DatabasePersistenceError):
            await repo_svc.register_repository(uuid.uuid4(), RepositoryType.LOCAL, "/workspace/err")

        with pytest.raises(DatabasePersistenceError):
            await repo_svc.get_repository(uuid.uuid4())

        with pytest.raises(DatabasePersistenceError):
            await repo_svc.list_repositories_for_project(uuid.uuid4())

        with pytest.raises(DatabasePersistenceError):
            await repo_svc.delete_repository(uuid.uuid4())

        with pytest.raises(DatabasePersistenceError):
            await repo_svc.validate_repository(uuid.uuid4())


@pytest.mark.asyncio
async def test_register_repository_integrity_error_mapped(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    stub_git_provider: StubGitProvider,
) -> None:
    """RepositoryService maps unexpected IntegrityError to DuplicateRepositoryError."""
    from trace.domain.exceptions import DuplicateRepositoryError
    from unittest.mock import patch

    from sqlalchemy.exc import IntegrityError

    repo_svc = RepositoryService(in_memory_db_gateway, stub_git_provider)
    with patch.object(
        in_memory_db_gateway,
        "session",
        side_effect=IntegrityError("mock duplicate", params={}, orig=Exception("uq_violation")),
    ):
        with pytest.raises(DuplicateRepositoryError):
            await repo_svc.register_repository(uuid.uuid4(), RepositoryType.LOCAL, "/workspace/dup")


@pytest.mark.asyncio
async def test_validate_remote_repository_success(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    stub_git_provider: StubGitProvider,
) -> None:
    """validate_repository dispatches to validate_remote when repo type is REMOTE."""
    project_svc = ProjectService(in_memory_db_gateway)
    repo_svc = RepositoryService(in_memory_db_gateway, stub_git_provider)

    project = await project_svc.create_project("Remote Valid Project")
    repo = await repo_svc.register_repository(
        project_id=project.id,
        repo_type=RepositoryType.REMOTE,
        location="https://github.com/org/remote-repo.git",
    )

    stub_git_provider.remote_result = ConnectionValidationResult(
        is_connected=True,
        detected_branch="main",
        latency_ms=45.2,
    )

    validated_repo, result = await repo_svc.validate_repository(repo.id)
    assert validated_repo.status == RepositoryStatus.CONNECTED
    assert validated_repo.default_branch == "main"
    assert result.is_connected is True
