"""Pure domain entity and lifecycle status for TRACE projects.

Per Constitution §XIV, domain entities contain zero framework, database, or I/O imports.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ProjectStatus(StrEnum):
    """Lifecycle status of a TRACE project."""

    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


@dataclass(frozen=True)
class Project:
    """Immutable TRACE project domain entity."""

    id: uuid.UUID
    name: str
    description: str | None
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime
