# Contract: REST API Specifications for Analysis

**Feature Branch**: `003-repository-code-analyzer`  
**Date**: 2026-09-29  
**Spec Reference**: [spec.md](../spec.md)

---

## 1. Endpoints Overview

All endpoints are mounted under `/api/v1` and use standard JSON request/response formats.

| Method | Path | Status Code | Description |
|---|---|---|---|
| `POST` | `/api/v1/repositories/{repository_id}/analyze` | `202 Accepted` | Trigger an asynchronous repository analysis run |
| `GET` | `/api/v1/repositories/{repository_id}/analyses` | `200 OK` | List analysis runs for a repository with pagination |
| `GET` | `/api/v1/analyses/{analysis_run_id}` | `200 OK` | Get metadata, status, and execution metrics of a run |
| `GET` | `/api/v1/analyses/{analysis_run_id}/summary` | `200 OK` | Get high-level entity, file, and relationship counts |
| `GET` | `/api/v1/analyses/{analysis_run_id}/entities` | `200 OK` | List discovered code entities with pagination and type filtering |
| `GET` | `/api/v1/analyses/{analysis_run_id}/relationships` | `200 OK` | List structural relationships with pagination and type filtering |
| `GET` | `/api/v1/analyses/{analysis_run_id}/diagnostics` | `200 OK` | List parser errors, warnings, and analysis diagnostics |

---

## 2. Request & Response Schemas

### 2.1 Trigger Analysis: `POST /api/v1/repositories/{repository_id}/analyze`

#### Request Body (`AnalysisTriggerRequest`)
```json
{
  "target_ref": "main",
  "exclude_patterns": [
    "custom_cache/*",
    "legacy_scripts/*.py"
  ]
}
```

#### Response Body (`AnalysisRunResponse` — HTTP 202 Accepted)
```json
{
  "id": "7f8b3c20-1a2b-4c3d-8e4f-5a6b7c8d9e0f",
  "repository_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "project_id": "1fa85f64-5717-4562-b3fc-2c963f66afa1",
  "status": "PENDING",
  "target_ref": "main",
  "commit_hash": null,
  "started_at": null,
  "completed_at": null,
  "duration_ms": null,
  "total_files": 0,
  "python_files": 0,
  "total_modules": 0,
  "total_classes": 0,
  "total_functions": 0,
  "total_relationships": 0,
  "total_diagnostics": 0,
  "error_message": null,
  "created_at": "2026-09-29T08:30:00Z",
  "updated_at": "2026-09-29T08:30:00Z"
}
```

---

### 2.2 Get Analysis Run Status: `GET /api/v1/analyses/{analysis_run_id}`

#### Response Body (`AnalysisRunResponse` — HTTP 200 OK)
```json
{
  "id": "7f8b3c20-1a2b-4c3d-8e4f-5a6b7c8d9e0f",
  "repository_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "project_id": "1fa85f64-5717-4562-b3fc-2c963f66afa1",
  "status": "COMPLETED",
  "target_ref": "main",
  "commit_hash": "a1b2c3d4e5f67890123456789012345678901234",
  "started_at": "2026-09-29T08:30:01Z",
  "completed_at": "2026-09-29T08:30:03Z",
  "duration_ms": 1845.2,
  "total_files": 48,
  "python_files": 36,
  "total_modules": 36,
  "total_classes": 18,
  "total_functions": 92,
  "total_relationships": 145,
  "total_diagnostics": 1,
  "error_message": null,
  "created_at": "2026-09-29T08:30:00Z",
  "updated_at": "2026-09-29T08:30:03Z"
}
```

---

### 2.3 Get Analysis Summary: `GET /api/v1/analyses/{analysis_run_id}/summary`

#### Response Body (`AnalysisSummaryResponse` — HTTP 200 OK)
```json
{
  "analysis_run_id": "7f8b3c20-1a2b-4c3d-8e4f-5a6b7c8d9e0f",
  "repository_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "COMPLETED",
  "duration_ms": 1845.2,
  "metrics": {
    "total_files": 48,
    "python_files": 36,
    "modules": 36,
    "packages": 8,
    "classes": 18,
    "functions": 92,
    "methods": 54,
    "endpoints": 12,
    "database_models": 6,
    "test_functions": 28,
    "external_dependencies": 15,
    "total_relationships": 145,
    "diagnostics_count": 1
  }
}
```

---

### 2.4 Get Discovered Entities: `GET /api/v1/analyses/{analysis_run_id}/entities`

Query Parameters:
- `limit`: int = 50 (max 500)
- `offset`: int = 0
- `kind`: Optional[str] (`MODULE`, `CLASS`, `FUNCTION`, `ENDPOINT`, `DATABASE`, `TEST`, `DEPENDENCY`)

#### Response Body (`EntityListResponse` — HTTP 200 OK)
```json
{
  "items": [
    {
      "kind": "CLASS",
      "name": "PaymentService",
      "qualified_name": "payments.service.PaymentService",
      "module_name": "payments.service",
      "location": {
        "file_path": "payments/service.py",
        "start_line": 15,
        "end_line": 85,
        "start_column": 0,
        "end_column": 0
      },
      "attributes": {
        "parent_classes": ["BaseService"],
        "decorators": ["@injectable()"],
        "methods_count": 5
      }
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

---

### 2.5 Get Structural Relationships: `GET /api/v1/analyses/{analysis_run_id}/relationships`

Query Parameters:
- `limit`: int = 50
- `offset`: int = 0
- `relationship_type`: Optional[str] (`IMPORTS`, `CALLS`, `EXTENDS`, `EXPOSES`, `READS`, `WRITES`, `TESTED_BY`, `DEPENDS_ON`, `CONFIGURED_BY`, `DOCUMENTED_BY`)

#### Response Body (`RelationshipListResponse` — HTTP 200 OK)
```json
{
  "items": [
    {
      "source_type": "FUNCTION",
      "source_identifier": "payments.service.PaymentService.charge",
      "relationship_type": "CALLS",
      "target_type": "FUNCTION",
      "target_identifier": "payments.gateway.StripeClient.create_charge",
      "evidence_location": {
        "file_path": "payments/service.py",
        "start_line": 42,
        "end_line": 42,
        "start_column": 12,
        "end_column": 48
      }
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

---

### 2.6 Get Diagnostics: `GET /api/v1/analyses/{analysis_run_id}/diagnostics`

Query Parameters:
- `severity`: Optional[str] (`ERROR`, `WARNING`, `INFO`)
- `limit`: int = 50
- `offset`: int = 0

#### Response Body (`DiagnosticListResponse` — HTTP 200 OK)
```json
{
  "items": [
    {
      "file_path": "legacy/broken_syntax.py",
      "severity": "ERROR",
      "code": "SYNTAX_ERROR",
      "message": "invalid syntax (line 12, col 4): def invalid_func(",
      "line": 12,
      "column": 4
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```
