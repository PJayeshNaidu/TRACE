# REST API Contract: TRACE Phase 6 — F07: Upgrade Planner

**Feature**: [spec.md](../spec.md) | [plan.md](../plan.md)  
**Base Path**: `/api/v1`  
**Content-Type**: `application/json`  

---

## 1. Endpoints Overview

| Method | Path | Description |
| :--- | :--- | :--- |
| `POST` | `/api/v1/upgrade-plans/generate` | Generates a new upgrade plan from impact analysis data. |
| `GET` | `/api/v1/upgrade-plans/{plan_id}` | Retrieves plan header, progress metrics, and ordered task DAG. |
| `GET` | `/api/v1/upgrade-plans/{plan_id}/tasks` | Retrieves filtered and paginated tasks for a plan. |
| `PATCH` | `/api/v1/upgrade-plans/{plan_id}/tasks/{task_id}` | Updates task lifecycle status, notes, or execution state. |
| `GET` | `/api/v1/repositories/{repository_id}/upgrade-plans` | Lists all historical upgrade plans for a repository. |

---

## 2. Detailed Schemas & Payload Contracts

### `POST /api/v1/upgrade-plans/generate`

#### Request Body (`GenerateUpgradePlanRequest`)
```json
{
  "repository_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "impact_analysis_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "base_ref": "v1.0.0",
  "target_ref": "v2.0.0",
  "title": "Upgrade Plan: v1.0.0 ➜ v2.0.0",
  "llm_config": {
    "enabled": false,
    "api_key": null,
    "model": "nvidia/nemotron-3.5-lightning:free"
  }
}
```

*Note: If `impact_analysis_id` is omitted, the service will automatically run or resolve the impact analysis for the given `repository_id`, `base_ref`, and `target_ref`.*

#### Response Body: `201 Created` (`UpgradePlanResponse`)
```json
{
  "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "repository_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "impact_analysis_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "title": "Upgrade Plan: v1.0.0 ➜ v2.0.0",
  "base_commit": "abc1234567890abcdef1234567890abcdef1234",
  "target_commit": "def567890abcdef1234567890abcdef12345678",
  "risk_level": "HIGH",
  "status": "DRAFT",
  "reasoning_mode": "HEURISTIC",
  "created_at": "2026-10-01T12:00:00Z",
  "updated_at": "2026-10-01T12:00:00Z",
  "summary_metrics": {
    "total_tasks": 5,
    "completed_tasks": 0,
    "in_progress_tasks": 0,
    "pending_tasks": 5,
    "blocked_tasks": 0,
    "skipped_tasks": 0,
    "progress_percentage": 0.0
  },
  "tasks": [
    {
      "id": "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d",
      "step_number": 1,
      "component": "src/api/payment.py::PaymentAPI",
      "component_type": "endpoint",
      "category": "CONTRACT_API",
      "reason": "Payment endpoint signature altered; parameter payment_id renamed to transaction_id.",
      "dependencies": [],
      "expected_changes": "Update route definition and parameter parsing to accept transaction_id.",
      "required_tests": [
        "tests/test_api.py::test_payment_api"
      ],
      "risk_level": "HIGH",
      "status": "PENDING",
      "is_circular": false,
      "parallel_group_id": 1,
      "notes": null,
      "evidence": {
        "diff_snippet": "- def pay(payment_id):\n+ def pay(transaction_id):",
        "lines_affected": [14, 18],
        "file_path": "src/api/payment.py"
      }
    },
    {
      "id": "b2c3d4e5-f6a7-4b6c-9d0e-1f2a3b4c5d6e",
      "step_number": 2,
      "component": "src/services/payment.py::PaymentService",
      "component_type": "class",
      "category": "CORE_LOGIC",
      "reason": "Invokes PaymentAPI; affected by parameter renaming.",
      "dependencies": [
        "src/api/payment.py::PaymentAPI"
      ],
      "expected_changes": "Update method invocations of PaymentAPI to supply transaction_id.",
      "required_tests": [
        "tests/test_payment_service.py::test_process_payment"
      ],
      "risk_level": "HIGH",
      "status": "PENDING",
      "is_circular": false,
      "parallel_group_id": 1,
      "notes": null,
      "evidence": {
        "call_chain": [
          "PaymentService.process",
          "PaymentAPI.pay"
        ],
        "file_path": "src/services/payment.py"
      }
    }
  ]
}
```

---

### `GET /api/v1/upgrade-plans/{plan_id}`

Retrieves the complete upgrade plan including all tasks, dependencies, and real-time metrics.

#### Response: `200 OK`
Returns the `UpgradePlanResponse` schema shown above.

#### Errors:
- `404 Not Found`: Plan does not exist.

---

### `GET /api/v1/upgrade-plans/{plan_id}/tasks`

#### Query Parameters:
- `status` (optional): Filter by task status (`PENDING`, `IN_PROGRESS`, `COMPLETED`, `BLOCKED`, `SKIPPED`).
- `category` (optional): Filter by category (`CONTRACT_API`, `CORE_LOGIC`, etc.).
- `risk_level` (optional): Filter by risk level (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
- `limit` (default: 50): Number of tasks to return.
- `offset` (default: 0): Pagination offset.

#### Response: `200 OK`
```json
{
  "plan_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "total": 5,
  "limit": 50,
  "offset": 0,
  "items": [
    {
      "id": "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d",
      "step_number": 1,
      "component": "src/api/payment.py::PaymentAPI",
      "component_type": "endpoint",
      "category": "CONTRACT_API",
      "reason": "Payment endpoint signature altered.",
      "dependencies": [],
      "expected_changes": "Update parameter parsing.",
      "required_tests": ["tests/test_api.py::test_payment_api"],
      "risk_level": "HIGH",
      "status": "COMPLETED",
      "is_circular": false,
      "parallel_group_id": 1,
      "notes": "Verified in staging",
      "evidence": {}
    }
  ]
}
```

---

### `PATCH /api/v1/upgrade-plans/{plan_id}/tasks/{task_id}`

Updates an individual task's lifecycle state or notes.

#### Request Body (`UpdateTaskStatusRequest`):
```json
{
  "status": "COMPLETED",
  "notes": "Contract updated and unit tests pass."
}
```

#### Response: `200 OK` (`UpgradeTaskResponse`):
```json
{
  "id": "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d",
  "plan_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "step_number": 1,
  "component": "src/api/payment.py::PaymentAPI",
  "status": "COMPLETED",
  "notes": "Contract updated and unit tests pass.",
  "updated_at": "2026-10-01T12:15:00Z"
}
```

#### Errors:
- `400 Bad Request`: Invalid status value.
- `404 Not Found`: Plan or task does not exist.

---

### `GET /api/v1/repositories/{repository_id}/upgrade-plans`

Lists historical plans for a repository.

#### Response: `200 OK`:
```json
{
  "repository_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "total": 1,
  "items": [
    {
      "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
      "title": "Upgrade Plan: v1.0.0 ➜ v2.0.0",
      "base_commit": "abc1234",
      "target_commit": "def5678",
      "risk_level": "HIGH",
      "status": "IN_PROGRESS",
      "total_tasks": 5,
      "completed_tasks": 1,
      "progress_percentage": 20.0,
      "created_at": "2026-10-01T12:00:00Z"
    }
  ]
}
```
