"""FastAPI router for TRACE Project management endpoints."""

import uuid
from trace.api.health.router import get_db_gateway
from trace.api.projects.schemas import (
    ProjectCreateRequest,
    ProjectListResponse,
    ProjectResponse,
)
from trace.api.repositories.router import get_repository_service
from trace.api.repositories.schemas import (
    RepositoryListResponse,
    RepositoryRegisterRequest,
    RepositoryResponse,
)
from trace.domain.project import ProjectStatus
from trace.infrastructure.database.gateway import DatabaseGateway
from trace.services.project import ProjectService
from trace.services.repository import RepositoryService
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

projects_router = APIRouter(prefix="/projects", tags=["projects"])


def get_project_service(
    db: Annotated[DatabaseGateway, Depends(get_db_gateway)],
) -> ProjectService:
    """Dependency provider for ProjectService."""
    return ProjectService(db)


@projects_router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new TRACE project",
)
async def create_project(
    request: ProjectCreateRequest,
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectResponse:
    """Create a new TRACE project in ACTIVE status."""
    project = await service.create_project(name=request.name, description=request.description)
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        status=project.status,
        repository_count=0,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@projects_router.get(
    "",
    response_model=ProjectListResponse,
    status_code=status.HTTP_200_OK,
    summary="List projects (paginated)",
)
async def list_projects(
    service: Annotated[ProjectService, Depends(get_project_service)],
    limit: Annotated[int, Query(ge=1, le=100, description="Max items to return")] = 50,
    offset: Annotated[int, Query(ge=0, description="Items to skip")] = 0,
    status_filter: Annotated[
        ProjectStatus | None, Query(alias="status", description="Filter by project status")
    ] = None,
) -> ProjectListResponse:
    """Retrieve paginated list of projects with optional status filter."""
    projects_with_counts, total = await service.list_projects(
        limit=limit, offset=offset, status=status_filter
    )
    items = [
        ProjectResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            status=p.status,
            repository_count=count,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p, count in projects_with_counts
    ]
    return ProjectListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@projects_router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve project details",
)
async def get_project(
    project_id: uuid.UUID,
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectResponse:
    """Retrieve project details by unique project ID."""
    project, repo_count = await service.get_project(project_id)
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        status=project.status,
        repository_count=repo_count,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@projects_router.post(
    "/{project_id}/archive",
    response_model=ProjectResponse,
    status_code=status.HTTP_200_OK,
    summary="Archive an active project",
)
async def archive_project(
    project_id: uuid.UUID,
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectResponse:
    """Transition an active project to ARCHIVED."""
    project, repo_count = await service.archive_project(project_id)
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        status=project.status,
        repository_count=repo_count,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@projects_router.post(
    "/{project_id}/activate",
    response_model=ProjectResponse,
    status_code=status.HTTP_200_OK,
    summary="Reactivate an archived project",
)
async def activate_project(
    project_id: uuid.UUID,
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectResponse:
    """Transition an archived project back to ACTIVE."""
    project, repo_count = await service.activate_project(project_id)
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        status=project.status,
        repository_count=repo_count,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@projects_router.post(
    "/{project_id}/repositories",
    response_model=RepositoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register repository to a project",
)
async def register_repository(
    project_id: uuid.UUID,
    request: RepositoryRegisterRequest,
    service: Annotated[RepositoryService, Depends(get_repository_service)],
) -> RepositoryResponse:
    """Register a new repository under an active project."""
    repo = await service.register_repository(
        project_id=project_id,
        repo_type=request.type,
        location=request.location,
        default_branch=request.default_branch,
    )
    return RepositoryResponse.model_validate(repo)


@projects_router.get(
    "/{project_id}/repositories",
    response_model=RepositoryListResponse,
    status_code=status.HTTP_200_OK,
    summary="List repositories in project",
)
async def list_repositories_for_project(
    project_id: uuid.UUID,
    service: Annotated[RepositoryService, Depends(get_repository_service)],
) -> RepositoryListResponse:
    """List all repositories registered in a project."""
    repos = await service.list_repositories_for_project(project_id)
    return RepositoryListResponse(
        items=[RepositoryResponse.model_validate(r) for r in repos],
        total=len(repos),
    )
