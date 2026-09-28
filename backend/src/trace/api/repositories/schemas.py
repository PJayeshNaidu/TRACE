"""Pydantic schemas for Repository API endpoints."""

import re
import urllib.parse
import uuid
from datetime import datetime
from trace.domain.repository import RepositoryStatus, RepositoryType

from pydantic import BaseModel, ConfigDict, Field, field_validator

_CREDENTIAL_ERROR_MSG = (
    "Repository URL must not contain embedded basic-auth credentials or tokens. "
    "Configure host-level ambient authentication (SSH keys or Git credential helper) instead."
)


class RepositoryRegisterRequest(BaseModel):
    """Payload for registering a repository under a project."""

    type: RepositoryType = Field(..., description="Repository type: LOCAL or REMOTE")
    location: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Filesystem directory path (for LOCAL) or Git URL (for REMOTE)",
        examples=["/repos/my-service", "https://github.com/my-org/my-service.git"],
    )
    default_branch: str | None = Field(
        default=None,
        max_length=100,
        description="Optional default branch hint if known upfront",
        examples=["main", "master"],
    )

    @field_validator("location")
    @classmethod
    def validate_location(cls, v: str) -> str:
        """Validate location syntax and reject any embedded credentials."""
        stripped = v.strip()
        if not stripped:
            raise ValueError("Repository location cannot be empty.")
        if "\0" in stripped:
            raise ValueError("Repository location cannot contain null bytes.")

        # Rejection of embedded credentials/tokens:
        # 1. URI formats (http://, https://, ssh://, etc.)
        if "://" in stripped:
            parsed = urllib.parse.urlsplit(stripped)
            scheme = parsed.scheme.lower()
            if scheme in ("http", "https"):
                if parsed.username or parsed.password:
                    raise ValueError(_CREDENTIAL_ERROR_MSG)
            elif parsed.password:
                raise ValueError(_CREDENTIAL_ERROR_MSG)

        # 2. SCP-style syntax: user:password@host:path
        if re.search(r"^[^@/:]+:[^@/]+@", stripped):
            raise ValueError(_CREDENTIAL_ERROR_MSG)

        # 3. Fallback regex for embedded userinfo with colon in URI
        if re.search(r"://[^@]+:[^@]+@", stripped):
            raise ValueError(_CREDENTIAL_ERROR_MSG)

        return stripped


class RepositoryResponse(BaseModel):
    """Representation of a registered repository."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Unique repository identifier")
    project_id: uuid.UUID = Field(..., description="Parent project identifier")
    type: RepositoryType = Field(..., description="Repository source type")
    location: str = Field(..., description="Normalized repository path or sanitized URL")
    default_branch: str | None = Field(
        default=None, description="Detected or configured default branch"
    )
    status: RepositoryStatus = Field(
        ..., description="Lifecycle status: REGISTERED, CONNECTED, or ERROR"
    )
    last_error: str | None = Field(
        default=None, description="Diagnostic error message from last failed validation"
    )
    last_validated_at: datetime | None = Field(
        default=None, description="UTC timestamp of last validation probe"
    )
    last_analysis_run_id: uuid.UUID | None = Field(
        default=None, description="Reserved for F02 analysis linkage"
    )
    created_at: datetime = Field(..., description="UTC creation timestamp")
    updated_at: datetime = Field(..., description="UTC update timestamp")


class RepositoryListResponse(BaseModel):
    """List of repositories registered in a project."""

    items: list[RepositoryResponse] = Field(
        ..., description="List of repositories registered in project"
    )
    total: int = Field(..., description="Total count of repositories")


class ValidationReportResponse(BaseModel):
    """Results of an on-demand repository connectivity validation probe."""

    repository_id: uuid.UUID = Field(..., description="Repository identifier")
    is_connected: bool = Field(..., description="True if repository is verified accessible")
    status: RepositoryStatus = Field(..., description="Resulting status: CONNECTED or ERROR")
    detected_branch: str | None = Field(
        default=None, description="Default branch discovered from probe"
    )
    error_message: str | None = Field(
        default=None, description="Failure diagnostic message if inaccessible"
    )
    latency_ms: float = Field(..., description="Validation probe elapsed time in milliseconds")
    validated_at: datetime = Field(..., description="UTC timestamp of validation probe")
