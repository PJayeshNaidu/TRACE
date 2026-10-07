# API Contract: Feature 008 — AI Assistant (TRACE F10)

**Feature Branch**: `008-ai-assistant` | **Date**: 2026-10-05 | **Spec Reference**: [spec.md](../spec.md)

This document specifies the REST API contract for the **TRACE F10 AI Assistant** endpoint exposed under `backend/src/trace/api/assistant/router.py`.

---

## Endpoint Overview

| Method | Path | Summary | Auth | Rate Limit |
|:---|:---|:---|:---|:---|
| `POST` | `/api/v1/assistant/ask` | Submit a natural-language question and receive grounded synthesis with sources | Optional / Session | 30 req/min |

---

## 1. POST `/api/v1/assistant/ask`

Executes deterministic evidence retrieval across Neo4j, PostgreSQL, and F02–F07 analysis caches, then synthesizes a grounded answer using the configured OpenRouter model (or deterministic fallback engine if offline).

### Request Headers
- `Content-Type: application/json`
- `Accept: application/json`

### Request Body (`AssistantQueryRequest`)

```json
{
  "project_id": "b3e0c0c8-4796-419b-980e-360e5670868f",
  "analysis_run_id": "8c15d748-8ad5-4e5b-821e-6143992e4513",
  "question": "Why is api.routes.auth_handler affected by this change?"
}
```

#### Field Specifications:
| Field | Type | Required | Description |
|:---|:---|:---|:---|
| `project_id` | `UUID` | **Yes** | Active project identifier |
| `analysis_run_id` | `UUID` | No | Optional analysis run ID to scope retrieval to a specific snapshot |
| `question` | `string` | **Yes** | Natural-language question (length: 3..1000 characters) |

---

### Response Body (`AssistantQueryResponse`)

#### Status Code: `200 OK`

```json
{
  "answer": "`api.routes.auth_handler` is directly affected because it invokes `auth_service.login`, whose method signature was modified in commit `1234567` (parameter `timeout` was added). Furthermore, `auth_handler` has 2 downstream callers (`web_ui.login_view` and `cli.auth_cmd`), contributing to a Moderate blast radius.",
  "sources": [
    {
      "type": "graph",
      "identifier": "api.routes.auth_handler -> auth_service.login",
      "summary": "1-hop direct call edge (CALLS) resolved in dependency graph",
      "metadata": {
        "from": "api.routes.auth_handler",
        "to": "auth_service.login",
        "depth": 1,
        "relationship": "CALLS"
      }
    },
    {
      "type": "diff",
      "identifier": "auth_service.login",
      "summary": "AST syntax delta: signature parameter change (added 'timeout')",
      "metadata": {
        "is_breaking": true,
        "file": "src/services/auth.py",
        "line": 45
      }
    },
    {
      "type": "risk",
      "identifier": "auth_service.login",
      "summary": "Assessed Risk: HIGH (Score: 75.0, Factors: breaking_signature, blast_radius_4)",
      "metadata": {
        "risk_level": "HIGH",
        "risk_score": 75.0
      }
    }
  ],
  "model_used": "mistralai/mistral-7b-instruct:free"
}
```

---

## 2. Error Responses

### 2.1 Project Not Found: `404 Not Found`
```json
{
  "error_code": "PROJECT_NOT_FOUND",
  "message": "Project 'b3e0c0c8-4796-419b-980e-360e5670868f' was not found.",
  "timestamp": "2026-10-05T17:15:00.000Z"
}
```

### 2.2 Validation Error: `422 Unprocessable Entity`
```json
{
  "error_code": "VALIDATION_ERROR",
  "message": "Validation failed for request body.",
  "details": [
    {
      "field": "question",
      "issue": "String should have at least 3 characters"
    }
  ],
  "timestamp": "2026-10-05T17:15:00.000Z"
}
```

### 2.3 Upstream Degradation Fallback: `200 OK` (Graceful Fallback Mode)
When OpenRouter is unreachable or API keys are not supplied, the system returns HTTP 200 with `model_used: "deterministic-fallback"` rather than a 500 server error:
```json
{
  "answer": "### Deterministic Evidence Summary\n\n- **Target Symbol**: `api.routes.auth_handler`\n- **Relationship**: Directly calls `auth_service.login` (depth 1)\n- **Breaking Changes**: Parameter addition in `auth_service.login`\n- **Risk Tier**: HIGH (Score: 75.0)",
  "sources": [
    {
      "type": "graph",
      "identifier": "api.routes.auth_handler -> auth_service.login",
      "summary": "1-hop direct call edge (CALLS)",
      "metadata": {"depth": 1}
    }
  ],
  "model_used": "deterministic-fallback"
}
```

---

## 3. Client Invocation Examples

### Python (`httpx`)
```python
import httpx

async with httpx.AsyncClient() as client:
    response = await client.post(
        "http://localhost:8000/api/v1/assistant/ask",
        json={
            "project_id": "b3e0c0c8-4796-419b-980e-360e5670868f",
            "question": "Why is checkout_service high risk?",
        },
        timeout=10.0,
    )
    data = response.json()
    print(data["answer"])
    for src in data["sources"]:
        print(f" - [{src['type'].upper()}] {src['summary']}")
```

### cURL
```bash
curl -X POST http://localhost:8000/api/v1/assistant/ask \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "b3e0c0c8-4796-419b-980e-360e5670868f",
    "question": "Show all callers of process_payment"
  }'
```
