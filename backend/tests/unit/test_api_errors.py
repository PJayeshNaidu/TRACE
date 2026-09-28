"""Unit tests for standardized API error responses and exception handlers."""

import uuid
from trace.api.errors import ErrorResponse, register_exception_handlers
from trace.domain.exceptions import (
    DatabasePersistenceError,
    DuplicateRepositoryError,
    InvalidRepositoryLocationError,
    ProjectAlreadyExistsError,
    ProjectArchivedError,
    ProjectNotFoundError,
    RepositoryInaccessibleError,
    RepositoryInUseError,
    RepositoryNotFoundError,
    TraceDomainError,
    UnsupportedRepositoryTypeError,
)

import httpx
import pytest
from fastapi import FastAPI


def create_test_error_app() -> FastAPI:
    """Create a minimal FastAPI test app with error handlers and test routes."""
    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/test/project-not-found")
    async def route_project_not_found() -> None:
        raise ProjectNotFoundError(uuid.UUID("11111111-1111-1111-1111-111111111111"))

    @test_app.get("/test/repository-not-found")
    async def route_repository_not_found() -> None:
        raise RepositoryNotFoundError(uuid.UUID("22222222-2222-2222-2222-222222222222"))

    @test_app.get("/test/project-exists")
    async def route_project_exists() -> None:
        raise ProjectAlreadyExistsError("Duplicate Project")

    @test_app.get("/test/project-archived")
    async def route_project_archived() -> None:
        raise ProjectArchivedError(uuid.UUID("33333333-3333-3333-3333-333333333333"), "update")

    @test_app.get("/test/duplicate-repo")
    async def route_duplicate_repo() -> None:
        raise DuplicateRepositoryError(
            uuid.UUID("44444444-4444-4444-4444-444444444444"), "/repos/path"
        )

    @test_app.get("/test/repo-in-use")
    async def route_repo_in_use() -> None:
        raise RepositoryInUseError(uuid.UUID("55555555-5555-5555-5555-555555555555"))

    @test_app.get("/test/invalid-location")
    async def route_invalid_location() -> None:
        raise InvalidRepositoryLocationError("https://u:p@host", "contains embedded credentials")

    @test_app.get("/test/unsupported-type")
    async def route_unsupported_type() -> None:
        raise UnsupportedRepositoryTypeError("MERCURIAL")

    @test_app.get("/test/repo-inaccessible")
    async def route_repo_inaccessible() -> None:
        raise RepositoryInaccessibleError("/tmp/missing", "Path does not exist")

    @test_app.get("/test/db-persistence")
    async def route_db_persistence() -> None:
        raise DatabasePersistenceError("Deadlock detected")

    @test_app.get("/test/generic-domain")
    async def route_generic_domain() -> None:
        raise TraceDomainError("Generic domain failure")

    return test_app


@pytest.mark.asyncio
async def test_error_handlers_status_and_schema() -> None:
    """Verify that domain exceptions are mapped to the correct status codes and schema."""
    app = create_test_error_app()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 404 ProjectNotFoundError
        r = await client.get("/test/project-not-found")
        assert r.status_code == 404
        data = r.json()
        assert data["error_code"] == "PROJECT_NOT_FOUND"
        assert "11111111-1111-1111-1111-111111111111" in data["message"]
        ErrorResponse.model_validate(data)

        # 404 RepositoryNotFoundError
        r = await client.get("/test/repository-not-found")
        assert r.status_code == 404
        data = r.json()
        assert data["error_code"] == "REPOSITORY_NOT_FOUND"

        # 409 ProjectAlreadyExistsError
        r = await client.get("/test/project-exists")
        assert r.status_code == 409
        data = r.json()
        assert data["error_code"] == "PROJECT_ALREADY_EXISTS"

        # 409 ProjectArchivedError
        r = await client.get("/test/project-archived")
        assert r.status_code == 409
        data = r.json()
        assert data["error_code"] == "PROJECT_ARCHIVED"

        # 409 DuplicateRepositoryError
        r = await client.get("/test/duplicate-repo")
        assert r.status_code == 409
        data = r.json()
        assert data["error_code"] == "DUPLICATE_REPOSITORY"

        # 409 RepositoryInUseError
        r = await client.get("/test/repo-in-use")
        assert r.status_code == 409
        data = r.json()
        assert data["error_code"] == "REPOSITORY_IN_USE"

        # 422 InvalidRepositoryLocationError
        r = await client.get("/test/invalid-location")
        assert r.status_code == 422
        data = r.json()
        assert data["error_code"] == "INVALID_REPOSITORY_LOCATION"

        # 422 UnsupportedRepositoryTypeError
        r = await client.get("/test/unsupported-type")
        assert r.status_code == 422
        data = r.json()
        assert data["error_code"] == "UNSUPPORTED_REPOSITORY_TYPE"

        # 422 RepositoryInaccessibleError
        r = await client.get("/test/repo-inaccessible")
        assert r.status_code == 422
        data = r.json()
        assert data["error_code"] == "REPOSITORY_INACCESSIBLE"

        # 500 DatabasePersistenceError
        r = await client.get("/test/db-persistence")
        assert r.status_code == 500
        data = r.json()
        assert data["error_code"] == "DATABASE_PERSISTENCE_ERROR"

        # 400 TraceDomainError
        r = await client.get("/test/generic-domain")
        assert r.status_code == 400
        data = r.json()
        assert data["error_code"] == "DOMAIN_ERROR"
