"""Pydantic schemas for Project API endpoints."""

import uuid
from datetime import datetime
from trace.domain.project import ProjectStatus

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProjectCreateRequest(BaseModel):
    """Payload for creating a new TRACE project."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Unique name for the TRACE project",
        examples=["E-Commerce Platform", "TRACE Backend Core"],
    )
    description: str | None = Field(
        default=None,
        max_length=1000,
        description="Optional human-readable project description",
        examples=["Core backend microservices and analysis pipeline"],
    )

    @field_validator("name")
    @classmethod
    def validate_name_not_blank(cls, v: str) -> str:
        """Ensure name is non-empty and stripped of surrounding whitespace."""
        stripped = v.strip()
        if not stripped:
            raise ValueError("Project name must not be blank or only whitespace.")
        return stripped


class ProjectResponse(BaseModel):
    """Detailed response representation of a TRACE project."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Unique immutable project identifier")
    name: str = Field(..., description="Project name")
    description: str | None = Field(default=None, description="Project description")
    status: ProjectStatus = Field(..., description="Current lifecycle status (ACTIVE or ARCHIVED)")
    repository_count: int = Field(default=0, description="Total count of registered repositories")
    created_at: datetime = Field(..., description="UTC creation timestamp in ISO 8601")
    updated_at: datetime = Field(..., description="UTC last updated timestamp in ISO 8601")


class ProjectListResponse(BaseModel):
    """Paginated list of TRACE projects."""

    items: list[ProjectResponse] = Field(..., description="List of projects matching query")
    total: int = Field(..., description="Total count of projects matching filter")
    limit: int = Field(..., description="Pagination limit")
    offset: int = Field(..., description="Pagination offset")
