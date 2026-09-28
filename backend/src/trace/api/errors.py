"""Standardized error responses and exception handlers for TRACE API."""

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
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Standardized HTTP error response envelope."""

    error_code: str = Field(
        ...,
        description="Standardized machine-readable error code",
        examples=["PROJECT_NOT_FOUND", "PROJECT_ALREADY_EXISTS"],
    )
    message: str = Field(
        ...,
        description="Human-readable explanation of the error",
        examples=["Project with ID '...' was not found."],
    )
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Diagnostic details associated with the error",
    )


def create_error_response(
    status_code: int,
    error_code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    """Create a standardized JSON error response."""
    payload = ErrorResponse(
        error_code=error_code,
        message=message,
        details=details or {},
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump())


def register_exception_handlers(app: FastAPI) -> None:
    """Register domain exception handlers with the FastAPI application."""

    @app.exception_handler(ProjectNotFoundError)
    async def handle_project_not_found(_: Request, exc: ProjectNotFoundError) -> JSONResponse:
        return create_error_response(404, "PROJECT_NOT_FOUND", exc.message, exc.details)

    @app.exception_handler(RepositoryNotFoundError)
    async def handle_repository_not_found(_: Request, exc: RepositoryNotFoundError) -> JSONResponse:
        return create_error_response(404, "REPOSITORY_NOT_FOUND", exc.message, exc.details)

    @app.exception_handler(ProjectAlreadyExistsError)
    async def handle_project_already_exists(
        _: Request, exc: ProjectAlreadyExistsError
    ) -> JSONResponse:
        return create_error_response(409, "PROJECT_ALREADY_EXISTS", exc.message, exc.details)

    @app.exception_handler(ProjectArchivedError)
    async def handle_project_archived(_: Request, exc: ProjectArchivedError) -> JSONResponse:
        return create_error_response(409, "PROJECT_ARCHIVED", exc.message, exc.details)

    @app.exception_handler(DuplicateRepositoryError)
    async def handle_duplicate_repository(
        _: Request, exc: DuplicateRepositoryError
    ) -> JSONResponse:
        return create_error_response(409, "DUPLICATE_REPOSITORY", exc.message, exc.details)

    @app.exception_handler(RepositoryInUseError)
    async def handle_repository_in_use(_: Request, exc: RepositoryInUseError) -> JSONResponse:
        return create_error_response(409, "REPOSITORY_IN_USE", exc.message, exc.details)

    @app.exception_handler(InvalidRepositoryLocationError)
    async def handle_invalid_repository_location(
        _: Request, exc: InvalidRepositoryLocationError
    ) -> JSONResponse:
        return create_error_response(422, "INVALID_REPOSITORY_LOCATION", exc.message, exc.details)

    @app.exception_handler(UnsupportedRepositoryTypeError)
    async def handle_unsupported_repository_type(
        _: Request, exc: UnsupportedRepositoryTypeError
    ) -> JSONResponse:
        return create_error_response(422, "UNSUPPORTED_REPOSITORY_TYPE", exc.message, exc.details)

    @app.exception_handler(RepositoryInaccessibleError)
    async def handle_repository_inaccessible(
        _: Request, exc: RepositoryInaccessibleError
    ) -> JSONResponse:
        return create_error_response(422, "REPOSITORY_INACCESSIBLE", exc.message, exc.details)

    @app.exception_handler(DatabasePersistenceError)
    async def handle_database_persistence_error(
        _: Request, exc: DatabasePersistenceError
    ) -> JSONResponse:
        return create_error_response(500, "DATABASE_PERSISTENCE_ERROR", exc.message, exc.details)

    @app.exception_handler(TraceDomainError)
    async def handle_generic_domain_error(_: Request, exc: TraceDomainError) -> JSONResponse:
        return create_error_response(400, "DOMAIN_ERROR", exc.message, exc.details)
