import uuid
from datetime import UTC, datetime
from trace.api.health.router import get_db_gateway
from trace.api.repositories.schemas import (
    RepositoryResponse,
    ValidationReportResponse,
)
from trace.infrastructure.database.gateway import DatabaseGateway
from trace.infrastructure.git.provider import GitProvider
from trace.services.repository import RepositoryService
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

repositories_router = APIRouter(prefix="/repositories", tags=["repositories"])


def get_git_provider(request: Request) -> GitProvider:
    """Dependency provider for GitProvider from application state."""
    git = getattr(request.app.state, "git", None)
    if git is not None:
        return git  # type: ignore[no-any-return]
    from trace.infrastructure.git.adapters.subprocess import SubprocessGitProvider

    return SubprocessGitProvider()


def get_repository_service(
    db: Annotated[DatabaseGateway, Depends(get_db_gateway)],
    git: Annotated[GitProvider, Depends(get_git_provider)],
) -> RepositoryService:
    """Dependency provider for RepositoryService."""
    return RepositoryService(db_gateway=db, git_provider=git)


@repositories_router.get(
    "/{repository_id}",
    response_model=RepositoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve repository details",
)
async def get_repository(
    repository_id: uuid.UUID,
    service: Annotated[RepositoryService, Depends(get_repository_service)],
) -> RepositoryResponse:
    """Retrieve repository details by unique repository identifier."""
    repo = await service.get_repository(repository_id)
    return RepositoryResponse.model_validate(repo)


@repositories_router.delete(
    "/{repository_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an unanalyzed repository",
)
async def delete_repository(
    repository_id: uuid.UUID,
    service: Annotated[RepositoryService, Depends(get_repository_service)],
) -> None:
    """Delete an unanalyzed repository record."""
    await service.delete_repository(repository_id)


@repositories_router.post(
    "/{repository_id}/validate",
    response_model=ValidationReportResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate repository connectivity",
)
async def validate_repository(
    repository_id: uuid.UUID,
    service: Annotated[RepositoryService, Depends(get_repository_service)],
) -> ValidationReportResponse:
    """Trigger an on-demand connectivity validation probe for a registered repository."""
    repo, probe_result = await service.validate_repository(repository_id)
    return ValidationReportResponse(
        repository_id=repo.id,
        is_connected=probe_result.is_connected,
        status=repo.status,
        detected_branch=probe_result.detected_branch,
        error_message=probe_result.error_message,
        latency_ms=probe_result.latency_ms,
        validated_at=repo.last_validated_at or datetime.now(UTC),
    )
