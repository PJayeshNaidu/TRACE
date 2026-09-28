# API Contract: Projects API (`/api/v1/projects`)

**Branch**: `002-project-repository-management` | **Date**: 2026-09-28 | **Feature**: F01 Project & Repository Management

This document defines the formal OpenAPI REST contract and Pydantic schemas for TRACE Project management endpoints.

---

## 1. Endpoints

| Method | Path | Summary | Success Status | Error Statuses |
|---|---|---|---|---|
| `POST` | `/api/v1/projects` | Create a new TRACE project | `201 Created` | `400`, `409`, `422`, `500` |
| `GET` | `/api/v1/projects` | List projects (paginated) | `200 OK` | `422`, `500` |
| `GET` | `/api/v1/projects/{project_id}` | Retrieve project details | `200 OK` | `404`, `422`, `500` |
| `POST` | `/api/v1/projects/{project_id}/archive` | Archive an active project | `200 OK` | `404`, `409`, `422`, `500` |
| `POST` | `/api/v1/projects/{project_id}/activate` | Reactivate an archived project | `200 OK` | `404`, `409`, `422`, `500` |

---

## 2. Pydantic Schemas (`trace/api/projects/schemas.py`)

```python
from datetime import datetime
import uuid
from pydantic import BaseModel, Field, field_validator
from trace.domain.project import ProjectStatus

class ProjectCreateRequest(BaseModel):
    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Unique name for the TRACE project",
        examples=["E-Commerce Platform", "TRACE Backend Core"]
    )
    description: str | None = Field(
        default=None,
        max_length=1000,
        description="Optional human-readable project description",
        examples=["Core backend microservices and analysis pipeline"]
    )

    @field_validator("name")
    @classmethod
    def validate_name_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Project name must not be blank or only whitespace.")
        return stripped


class ProjectResponse(BaseModel):
    id: uuid.UUID = Field(..., description="Unique immutable project identifier")
    name: str = Field(..., description="Project name")
    description: str | None = Field(default=None, description="Project description")
    status: ProjectStatus = Field(..., description="Current lifecycle status (ACTIVE or ARCHIVED)")
    repository_count: int = Field(default=0, description="Total count of registered repositories")
    created_at: datetime = Field(..., description="UTC creation timestamp in ISO 8601")
    updated_at: datetime = Field(..., description="UTC last updated timestamp in ISO 8601")


class ProjectListResponse(BaseModel):
    items: list[ProjectResponse] = Field(..., description="List of projects matching query")
    total: int = Field(..., description="Total count of projects matching filter")
    limit: int = Field(..., description="Pagination limit")
    offset: int = Field(..., description="Pagination offset")
```

---

## 3. Request & Response Payloads

### `POST /api/v1/projects`
**Request Body**:
```json
{
  "name": "E-Commerce Core",
  "description": "Primary transactional platform"
}
```

**Response (`201 Created`)**:
```json
{
  "id": "7f8b919a-2ef4-4f01-b8d9-23ef8902b4d1",
  "name": "E-Commerce Core",
  "description": "Primary transactional platform",
  "status": "ACTIVE",
  "repository_count": 0,
  "created_at": "2026-09-28T14:00:00Z",
  "updated_at": "2026-09-28T14:00:00Z"
}
```

### `GET /api/v1/projects?limit=50&offset=0&status=ACTIVE`
**Response (`200 OK`)**:
```json
{
  "items": [
    {
      "id": "7f8b919a-2ef4-4f01-b8d9-23ef8902b4d1",
      "name": "E-Commerce Core",
      "description": "Primary transactional platform",
      "status": "ACTIVE",
      "repository_count": 2,
      "created_at": "2026-09-28T14:00:00Z",
      "updated_at": "2026-09-28T14:05:00Z"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

### `POST /api/v1/projects/{project_id}/archive`
**Response (`200 OK`)**:
```json
{
  "id": "7f8b919a-2ef4-4f01-b8d9-23ef8902b4d1",
  "name": "E-Commerce Core",
  "description": "Primary transactional platform",
  "status": "ARCHIVED",
  "repository_count": 2,
  "created_at": "2026-09-28T14:00:00Z",
  "updated_at": "2026-09-28T14:15:00Z"
}
```
