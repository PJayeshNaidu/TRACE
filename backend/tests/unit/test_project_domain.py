"""Unit tests for Project domain entity and ProjectStatus enum."""

import uuid
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from trace.domain.project import Project, ProjectStatus

import pytest


def test_project_status_enum_values() -> None:
    """ProjectStatus contains ACTIVE and ARCHIVED members."""
    assert ProjectStatus.ACTIVE == "ACTIVE"
    assert ProjectStatus.ARCHIVED == "ARCHIVED"
    assert list(ProjectStatus) == [ProjectStatus.ACTIVE, ProjectStatus.ARCHIVED]


def test_project_entity_creation_and_attributes() -> None:
    """Project entity can be instantiated with valid attributes."""
    pid = uuid.uuid4()
    now = datetime.now(UTC)
    project = Project(
        id=pid,
        name="TRACE Backend",
        description="Core risk analysis engine",
        status=ProjectStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    assert project.id == pid
    assert project.name == "TRACE Backend"
    assert project.description == "Core risk analysis engine"
    assert project.status == ProjectStatus.ACTIVE
    assert project.created_at == now
    assert project.updated_at == now


def test_project_entity_is_immutable() -> None:
    """Project entity is a frozen dataclass and rejects attribute mutation."""
    pid = uuid.uuid4()
    now = datetime.now(UTC)
    project = Project(
        id=pid,
        name="Immutable Project",
        description=None,
        status=ProjectStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    with pytest.raises(FrozenInstanceError):
        project.name = "Mutated Name"  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        project.status = ProjectStatus.ARCHIVED  # type: ignore[misc]


def test_project_representation() -> None:
    """Project entity has descriptive string representation containing name and id."""
    pid = uuid.uuid4()
    now = datetime.now(UTC)
    project = Project(
        id=pid,
        name="RepTest",
        description=None,
        status=ProjectStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    rep = repr(project)
    assert "RepTest" in rep
    assert str(pid) in rep
