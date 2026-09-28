# TRACE Architecture — Phase 0

## 1. Overview and Core Purpose

TRACE (Transformation Risk Analysis & Change Evaluation) is an agentic system that analyzes Python codebases, evaluates semantic and operational risks of proposed changes, and plans safe upgrade migrations.

Phase 0 establishes the foundational architectural boundaries, configuration management, structured logging, database connectivity, and LLM abstraction layers without implementing future intelligence features (AST extraction, graph schema, multi-agent orchestration).

---

## 2. 5-Layer Architectural Hierarchy

TRACE follows a strict onion/clean architecture model with 5 conceptual layers:

```
[ HTTP / REST Clients ]
           │
           ▼
┌────────────────────────────────────────────────────────┐
│ 1. API Layer (trace/api/)                             │
│    - FastAPI routers, request/response Pydantic models │
│    - OpenAPI schema generation, HTTP status mapping   │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ 2. Application / Service Layer (trace/services/)       │
│    - Cross-boundary orchestration                      │
│    - Phase 0: minimal health service logic in router   │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ 3. Domain Layer (trace/domain/)                        │
│    - Pure Python models, StrEnum states, domain rules  │
│    - ZERO framework imports, ZERO I/O dependencies     │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ 4. Ports / Interfaces (trace/infrastructure/*/gateway) │
│    - Protocol definitions (runtime_checkable)          │
│    - DatabaseGateway, GraphGateway, LLMProvider        │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ 5. Infrastructure Adapters (trace/infrastructure/)    │
│    - Concrete implementations of gateway protocols     │
│    - PostgreSQL (asyncpg), Neo4j driver, OpenRouter    │
│    - pydantic-settings, structlog                     │
└────────────────────────────────────────────────────────┘
```

---

## 3. Directory Responsibility Map

Every directory under `backend/src/trace/` has a single, unambiguous responsibility:

| Directory | Responsibility |
|---|---|
| `trace/core/` | Centralized typed configuration (`ApplicationConfig`) and structured logging with credential redaction. |
| `trace/domain/` | Pure business domain entities, value objects, and states (e.g., `HealthState`, `GraphConnectivityState`). |
| `trace/api/` | HTTP transport layer containing FastAPI routers, route dependencies, and Pydantic validation schemas. |
| `trace/api/health/` | Health check endpoint (`GET /health`) and response schemas (`HealthStatus`, `ServiceStatus`). |
| `trace/infrastructure/` | External boundary integrations and gateway protocols. |
| `trace/infrastructure/database/` | Relational database gateway protocol and SQLAlchemy 2.x async engine implementations. |
| `trace/infrastructure/graph/` | Graph database gateway protocol and Neo4j async driver implementations. |
| `trace/infrastructure/llm/` | LLM abstraction protocol (`LLMProvider`), response union (`LLMResponse`), and model configuration. |
| `trace/infrastructure/llm/adapters/` | Vendor-specific provider adapters (e.g., `OpenRouterAdapter` using `httpx` and `tenacity`). |

---

## 4. Architectural Boundary Rules

1. **Strict Direction of Dependency**:
   No layer may import from a layer above it. Specifically:
   - `trace/domain/` MUST NOT import from `trace/core/`, `trace/api/`, or `trace/infrastructure/`. Domain code is pure Python stdlib.
   - `trace/api/` MUST ONLY import interfaces (`LLMProvider`, `DatabaseGateway`, `GraphGateway`) and domain entities. `trace/api/` MUST NEVER import concrete adapters such as `OpenRouterAdapter`.
2. **Composition Root Instantiation Boundary**:
   `backend/src/trace/main.py` (specifically within the `@asynccontextmanager` lifespan) is the **only permitted location** for instantiating concrete adapters.
   - `OpenRouterAdapter` is imported and instantiated ONLY in `main.py`.
   - `ApplicationConfig` is injected directly into the adapter constructor: `OpenRouterAdapter(config=cfg, http_client=client)`.
   - Domain and API code interact with LLM providers exclusively through the `LLMProvider` Protocol stored in application state or dependency injection.
3. **Replaceability Guarantees**:
   - Swapping PostgreSQL or Neo4j requires modifying only their respective adapter implementations under `trace/infrastructure/`.
   - Swapping LLM vendors requires implementing the `LLMProvider` Protocol in a new adapter and updating the lifespan wiring in `main.py`.

---

## 5. Concern Placement Reference Table

| Concern | Correct Location | Prohibited Locations |
|---|---|---|
| HTTP Routing & Status Codes | `trace/api/` | `trace/domain/`, `trace/infrastructure/` |
| Business States & Enums | `trace/domain/` | `trace/api/`, `trace/infrastructure/` |
| Database Queries & Sessions | `trace/infrastructure/database/` | `trace/api/`, `trace/domain/` |
| Graph Traversal & Drivers | `trace/infrastructure/graph/` | `trace/api/`, `trace/domain/` |
| LLM API Calls & Retries | `trace/infrastructure/llm/adapters/` | `trace/api/`, `trace/domain/`, `trace/services/` |
| Environment Variable Reading | `trace/core/config.py` | Anywhere else via `os.environ` or `os.getenv` |
| Secret Redaction & Log Formatting | `trace/core/logging.py` | Individual route handlers |

---

## 6. Contract Specifications

For formal Protocol specifications, see the contract documents:
- [LLMProvider Contract](../specs/001-phase0-project-foundation/contracts/llm-provider.md)
