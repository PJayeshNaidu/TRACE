# API Contract: TRACE Phase 3B — F04: Version / Change Analyzer

**Feature Branch**: `Version-Change-Analyser`  
**Date**: 2026-09-29  
**Spec Reference**: [spec.md](../spec.md)

---

## 1. Endpoints

### 1.1 `GET /api/v1/repositories/{id}/branches`
Returns active branches in the repository (both local and remote).

**Response (200 OK)**:
```json
{
  "repository_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "default_branch": "main",
  "branches": ["main", "development", "feature/auth", "Version-Change-Analyser"]
}
```

---

### 1.2 `GET /api/v1/repositories/{id}/commits`
Returns recent commits for a given branch.

**Query Parameters**:
- `branch` (optional, default: default_branch)
- `limit` (optional, default: 30, max: 100)

**Response (200 OK)**:
```json
{
  "repository_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "branch": "main",
  "commits": [
    {
      "commit_hash": "a1b2c3d4e5f6...",
      "short_hash": "a1b2c3d",
      "message": "feat: add customer payment provider adapter",
      "author": "Developer <dev@trace.io>",
      "timestamp": "2026-09-29T18:30:00Z"
    }
  ]
}
```

---

### 1.3 `POST /api/v1/analyses/compare`
Trigger a version / branch / commit comparison.

**Request Body**:
```json
{
  "repository_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "base_ref": "main",
  "target_ref": "development"
}
```

**Response (201 Created)**:
```json
{
  "comparison_id": "c7a85f64-5717-4562-b3fc-2c963f66afa9",
  "repository_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "base_ref": "main",
  "target_ref": "development",
  "base_commit_hash": "a1b2c3d...",
  "target_commit_hash": "f9e8d7c...",
  "status": "COMPLETED",
  "risk_level": "HIGH",
  "summary": {
    "total_files_changed": 4,
    "total_insertions": 120,
    "total_deletions": 35,
    "total_symbols_changed": 6,
    "total_breaking_changes": 2
  }
}
```

---

### 1.4 `GET /api/v1/analyses/compare/{comparison_id}`
Retrieve full comparison details, symbol diffs, breaking changes, and blast radius.

**Response (200 OK)**:
```json
{
  "comparison_id": "c7a85f64-5717-4562-b3fc-2c963f66afa9",
  "repository_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "base_ref": "main",
  "target_ref": "development",
  "base_commit_hash": "a1b2c3d...",
  "target_commit_hash": "f9e8d7c...",
  "risk_level": "HIGH",
  "file_diffs": [
    {
      "old_path": "src/trace/services/payment.py",
      "new_path": "src/trace/services/payment.py",
      "change_type": "MODIFIED",
      "insertions": 45,
      "deletions": 12,
      "hunks": [
        {
          "old_start": 30,
          "old_lines": 10,
          "new_start": 30,
          "new_lines": 22,
          "header": "def process_transaction"
        }
      ]
    }
  ],
  "symbol_diffs": [
    {
      "symbol_id": "func:trace.services.payment.process_transaction",
      "qualified_name": "trace.services.payment.process_transaction",
      "kind": "function",
      "file_path": "src/trace/services/payment.py",
      "change_kind": "MODIFIED",
      "is_breaking": true,
      "breaking_reason": "Removed required parameter 'account_id' and changed return type",
      "old_signature": "process_transaction(account_id: str, amount: float) -> bool",
      "new_signature": "process_transaction(payment_intent_id: str, amount: float) -> TransactionReceipt"
    }
  ],
  "blast_radius": [
    {
      "target_symbol_id": "func:trace.services.payment.process_transaction",
      "affected_symbol_id": "func:trace.api.checkout.handle_payment",
      "affected_qualified_name": "trace.api.checkout.handle_payment",
      "affected_kind": "function",
      "affected_file_path": "src/trace/api/checkout.py",
      "relationship_kind": "CALLS",
      "depth": 1
    }
  ],
  "commit_messages": [
    "refactor: update payment transaction schema"
  ]
}
```
