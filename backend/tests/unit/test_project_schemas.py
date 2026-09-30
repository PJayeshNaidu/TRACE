"""Unit tests for Project API request and response Pydantic schemas."""

import uuid
from datetime import UTC, datetime
from trace.api.projects.schemas import (
    ProjectCreateRequest,
    ProjectListResponse,
    ProjectResponse,
)
from trace.domain.project import ProjectStatus

import pytest
from pydantic import ValidationError


def test_project_create_request_valid() -> None:
    """ProjectCreateRequest strips whitespace and accepts valid inputs."""
    req = ProjectCreateRequest(name="  Core System  ", description="  System description  ")
    assert req.name == "Core System"
    assert req.description == "  System description  "


def test_project_create_request_optional_description() -> None:
    """ProjectCreateRequest allows omitting description."""
    req = ProjectCreateRequest(name="Platform")
    assert req.name == "Platform"
    assert req.description is None


def test_project_create_request_empty_or_whitespace_name() -> None:
    """ProjectCreateRequest rejects empty and whitespace-only names."""
    with pytest.raises(ValidationError) as exc_info:
        ProjectCreateRequest(name="")
    assert "name" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
        ProjectCreateRequest(name="   \t\n  ")
    assert "Project name must not be blank" in str(exc_info.value)


def test_project_create_request_length_bounds() -> None:
    """ProjectCreateRequest enforces length limits on name and description."""
    with pytest.raises(ValidationError):
        ProjectCreateRequest(name="x" * 101)

    with pytest.raises(ValidationError):
        ProjectCreateRequest(name="Valid Name", description="x" * 1001)

    valid = ProjectCreateRequest(name="x" * 100, description="x" * 1000)
    assert len(valid.name) == 100
    assert len(valid.description or "") == 1000


def test_project_response_serialization() -> None:
    """ProjectResponse serializes project attributes and ISO datetime properly."""
    pid = uuid.uuid4()
    now = datetime.now(UTC)
    resp = ProjectResponse(
        id=pid,
        name="Platform Core",
        description="Core services",
        status=ProjectStatus.ACTIVE,
        repository_count=3,
        created_at=now,
        updated_at=now,
    )
    data = resp.model_dump(mode="json")
    assert data["id"] == str(pid)
    assert data["name"] == "Platform Core"
    assert data["description"] == "Core services"
    assert data["status"] == "ACTIVE"
    assert data["repository_count"] == 3
    assert datetime.fromisoformat(data["created_at"]) == now
    assert datetime.fromisoformat(data["updated_at"]) == now


def test_project_list_response() -> None:
    """ProjectListResponse holds items and pagination metadata."""
    pid = uuid.uuid4()
    now = datetime.now(UTC)
    item = ProjectResponse(
        id=pid,
        name="Platform Core",
        description=None,
        status=ProjectStatus.ACTIVE,
        repository_count=0,
        created_at=now,
        updated_at=now,
    )
    list_resp = ProjectListResponse(items=[item], total=1, limit=50, offset=0)
    assert len(list_resp.items) == 1
    assert list_resp.total == 1
    assert list_resp.limit == 50
    assert list_resp.offset == 0
