# Contract: HTTP API — Phase 0

**Version**: 0.1.0 | **Phase**: 0 | **Date**: 2026-09-25

This document is the authoritative HTTP API contract for the Phase 0 TRACE backend.
Changes to this contract require a version bump and documented migration path (Constitution §XV).

---

## Endpoints

### `GET /health`

**Purpose**: Returns the application health status including service connectivity.

**Authentication**: None required.

**Route**: `GET /health`

**Framework**: FastAPI router registered in `trace/api/router.py`.

---

#### Request

No request body. No query parameters. No authentication headers required.

```http
GET /health HTTP/1.1
Host: localhost:8000
Accept: application/json
```

---

#### Response: 200 OK (healthy)

Returned when all monitored services are reachable or not configured (Neo4j optional in Phase 0).

```http
HTTP/1.1 200 OK
Content-Type: application/json
```

```json
{
  "status": "healthy",
  "version": "0.1.0",
  "services": {
    "postgres": { "status": "reachable" },
    "neo4j":    { "status": "not_configured" }
  }
}
```

---

#### Response: 503 Service Unavailable (degraded)

Returned when any monitored service dependency is unreachable.
The response body **always** conforms to the `HealthStatus` schema — even on 503.

```http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json
```

```json
{
  "status": "degraded",
  "version": "0.1.0",
  "services": {
    "postgres": { "status": "unreachable" },
    "neo4j":    { "status": "reachable" }
  }
}
```

---

#### `HealthStatus` Schema

| Field | Type | Required | Description |
|---|---|---|---|
| `status` | `"healthy"` \| `"degraded"` | Yes | Overall application health |
| `version` | `string` | Yes | Package version from `importlib.metadata`; `"unknown"` if unavailable |
| `services` | `object` | Yes | Map of service name → `ServiceStatus` |

#### `ServiceStatus` Schema

| Field | Type | Required | Description |
|---|---|---|---|
| `status` | `"reachable"` \| `"unreachable"` \| `"not_configured"` | Yes | Service connectivity state |

---

#### Status Code Decision Logic

```
IF postgres.status == "reachable"
  AND (neo4j.status == "reachable" OR neo4j.status == "not_configured")
→ HTTP 200, HealthStatus.status = "healthy"

IF postgres.status == "unreachable"
  OR neo4j.status == "unreachable"
→ HTTP 503, HealthStatus.status = "degraded"
```

---

#### Prohibited Response Content

The health endpoint MUST NOT return:
- API keys or tokens
- Database connection strings or passwords
- Neo4j credentials
- Any value from `ApplicationConfig.SecretStr` fields
- Internal stack traces or exception messages

---

#### OpenAPI Location

When the backend is running, the OpenAPI specification is available at:
- `GET /docs` — Swagger UI
- `GET /openapi.json` — raw OpenAPI JSON

---

## Future Endpoints (Phase 1+)

The following endpoint prefixes are reserved for future phases and MUST NOT be implemented
in Phase 0:

```
/api/v1/projects/        (Phase 1 — F01)
/api/v1/repositories/    (Phase 1 — F01)
/api/v1/analysis/        (Phase 2 — F02/F03)
/api/v1/risk/            (Phase 2 — F05)
/api/v1/upgrades/        (Phase 3 — F06/F07)
/api/v1/reviews/         (Phase 3 — F08)
```

---

## Versioning Policy

This contract uses semantic versioning:
- **PATCH**: Non-breaking additions (new optional response fields).
- **MINOR**: New endpoints; new optional request parameters.
- **MAJOR**: Breaking changes to existing endpoint behaviour, required fields, or status codes.

Current version: **0.1.0** (Phase 0 initial contract)
