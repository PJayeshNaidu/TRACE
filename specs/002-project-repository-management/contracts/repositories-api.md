# API Contract: Repositories API (`/api/v1/repositories`)

**Branch**: `002-project-repository-management` | **Date**: 2026-09-28 | **Feature**: F01 Project & Repository Management

This document defines the formal OpenAPI REST contract and Pydantic schemas for TRACE Repository management and validation endpoints.

---

## 1. Endpoints

| Method | Path | Summary | Success Status | Error Statuses |
|---|---|---|---|---|
| `POST` | `/api/v1/projects/{project_id}/repositories` | Register repository to a project | `201 Created` | `400`, `404`, `409`, `422`, `500` |
| `GET` | `/api/v1/projects/{project_id}/repositories` | List repositories in project | `200 OK` | `404`, `422`, `500` |
| `GET` | `/api/v1/repositories/{repository_id}` | Retrieve repository details | `200 OK` | `404`, `422`, `500` |
| `DELETE` | `/api/v1/repositories/{repository_id}` | Delete an unanalyzed repository | `204 No Content` | `404`, `409`, `422`, `500` |
| `POST` | `/api/v1/repositories/{repository_id}/validate` | Validate repository connectivity | `200 OK` | `404`, `422`, `500` |

---

## 2. Pydantic Schemas (`trace/api/repositories/schemas.py`)

```python
from datetime import datetime
import re
import uuid
from pydantic import BaseModel, Field, field_validator
from trace.domain.repository import RepositoryStatus, RepositoryType

class RepositoryRegisterRequest(BaseModel):
    type: RepositoryType = Field(..., description="Repository type: LOCAL or REMOTE")
    location: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Filesystem directory path (for LOCAL) or Git URL (for REMOTE)",
        examples=["/repos/my-service", "https://github.com/my-org/my-service.git"]
    )
    default_branch: str | None = Field(
        default=None,
        max_length=100,
        description="Optional default branch hint if known upfront",
        examples=["main", "master"]
    )

    @field_validator("location")
    @classmethod
    def validate_location(cls, v: str, info) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Repository location cannot be empty.")
        if "\0" in stripped:
            raise ValueError("Repository location cannot contain null bytes.")
        
        # Embedded credentials rejection: check both standard URI userinfo and SCP-style syntax
        # e.g., https://user:pass@host, http://token@host, or git:pass@host:repo
        if re.search(r"://[^@]+@", stripped) or re.search(r"^[^@/:]+:[^@/]+@", stripped):
            raise ValueError(
                "Repository URL must not contain embedded basic-auth credentials or tokens. "
                "Configure host-level ambient authentication (SSH keys or Git credential helper) instead."
            )
        return stripped


class RepositoryResponse(BaseModel):
    id: uuid.UUID = Field(..., description="Unique repository identifier")
    project_id: uuid.UUID = Field(..., description="Parent project identifier")
    type: RepositoryType = Field(..., description="Repository source type")
    location: str = Field(..., description="Normalized repository path or sanitized URL")
    default_branch: str | None = Field(default=None, description="Detected or configured default branch")
    status: RepositoryStatus = Field(..., description="Lifecycle status: REGISTERED, CONNECTED, or ERROR")
    last_error: str | None = Field(default=None, description="Diagnostic error message from last failed validation")
    last_validated_at: datetime | None = Field(default=None, description="UTC timestamp of last validation probe")
    last_analysis_run_id: uuid.UUID | None = Field(default=None, description="Reserved for F02 analysis linkage")
    created_at: datetime = Field(..., description="UTC creation timestamp")
    updated_at: datetime = Field(..., description="UTC update timestamp")


class RepositoryListResponse(BaseModel):
    items: list[RepositoryResponse] = Field(..., description="List of repositories registered in project")
    total: int = Field(..., description="Total count of repositories")


class ValidationReportResponse(BaseModel):
    repository_id: uuid.UUID = Field(..., description="Repository identifier")
    is_connected: bool = Field(..., description="True if repository is verified accessible")
    status: RepositoryStatus = Field(..., description="Resulting status: CONNECTED or ERROR")
    detected_branch: str | None = Field(default=None, description="Default branch discovered from probe")
    error_message: str | None = Field(default=None, description="Failure diagnostic message if inaccessible")
    latency_ms: float = Field(..., description="Validation probe elapsed time in milliseconds")
    validated_at: datetime = Field(..., description="UTC timestamp of validation probe")
```

---

## 3. Standard Error Envelope (`trace/api/errors.py`)

```python
class ErrorResponse(BaseModel):
    error_code: str = Field(..., description="Machine-readable error code", examples=["PROJECT_NOT_FOUND"])
    message: str = Field(..., description="Human-readable explanation of failure")
    details: dict[str, str] = Field(default_factory=dict, description="Additional context or diagnostics")
```

---

## 4. Example Payloads

### `POST /api/v1/projects/{project_id}/repositories`
**Request Body**:
```json
{
  "type": "REMOTE",
  "location": "https://github.com/example/shop.git",
  "default_branch": "main"
}
```

**Response (`201 Created`)**:
```json
{
  "id": "1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d",
  "project_id": "7f8b919a-2ef4-4f01-b8d9-23ef8902b4d1",
  "type": "REMOTE",
  "location": "https://github.com/example/shop",
  "default_branch": "main",
  "status": "REGISTERED",
  "last_error": null,
  "last_validated_at": null,
  "last_analysis_run_id": null,
  "created_at": "2026-09-28T14:10:00Z",
  "updated_at": "2026-09-28T14:10:00Z"
}
```

### `POST /api/v1/repositories/{repository_id}/validate`
**Response (`200 OK`) — Successful Connection**:
```json
{
  "repository_id": "1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d",
  "is_connected": true,
  "status": "CONNECTED",
  "detected_branch": "main",
  "error_message": null,
  "latency_ms": 234.5,
  "validated_at": "2026-09-28T14:12:00Z"
}
```

**Response (`200 OK`) — Failed Connection**:
```json
{
  "repository_id": "1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d",
  "is_connected": false,
  "status": "ERROR",
  "detected_branch": null,
  "error_message": "Remote repository returned exit code 128: Repository not found or access denied.",
  "latency_ms": 154.2,
  "validated_at": "2026-09-28T14:12:00Z"
}
```
