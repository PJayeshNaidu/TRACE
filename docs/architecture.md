# TRACE Architecture — Phase 0 & Phase 1 (F01: Project & Repository Management)

## 1. Overview and Core Purpose

TRACE (Transformation Risk Analysis & Change Evaluation) is an agentic system that analyzes Python codebases, evaluates semantic and operational risks of proposed changes, and plans safe upgrade migrations.

- **Phase 0** established foundational architectural boundaries, configuration management, structured logging, database connectivity, and LLM abstraction layers.
- **Phase 1 (F01)** implements Project & Repository Management: creating projects, managing project lifecycles (active/archival/reactivation), registering local and remote Git repositories, executing non-destructive connectivity validation probes, and safely managing repository lifecycle.

---

## 2. 5-Layer Architectural Hierarchy

TRACE follows a strict onion/clean architecture model with 5 conceptual layers:

```
[ HTTP / REST Clients ]
           │
           ▼
┌────────────────────────────────────────────────────────┐
│ 1. API Layer (trace/api/)                             │
│    - FastAPI routers: health, projects, repositories  │
│    - Request & response Pydantic models with validation│
│    - OpenAPI schema generation, HTTP status mapping   │
│    - Global exception handlers for domain errors       │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ 2. Application / Service Layer (trace/services/)       │
│    - Cross-boundary orchestration & transaction flows  │
│    - ProjectService: project lifecycle & archival     │
│    - RepositoryService: repo registration & validation│
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ 3. Domain Layer (trace/domain/)                        │
│    - Pure Python models: Project, Repository          │
│    - Value objects: ConnectionValidationResult         │
│    - StrEnum states: ProjectStatus, RepositoryStatus  │
│    - Typed exceptions hierarchy: trace/domain/exceptions│
│    - ZERO framework imports, ZERO I/O dependencies     │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ 4. Ports / Interfaces (trace/infrastructure/*/gateway) │
│    - Protocol definitions (runtime_checkable)          │
│    - DatabaseGateway: relational DB session management │
│    - GitProvider: probe-only connectivity interface    │
│    - GraphGateway, LLMProvider                         │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ 5. Infrastructure Adapters (trace/infrastructure/)    │
│    - Concrete implementations of gateway protocols     │
│    - SQLAlchemyDatabaseGateway & ORM models (models/)  │
│    - SubprocessGitProvider: non-destructive CLI probe  │
│    - PostgreSQL (asyncpg), Neo4j driver, OpenRouter    │
│    - pydantic-settings, structlog with secret redacting│
└────────────────────────────────────────────────────────┘
```

---

## 3. Directory Responsibility Map

Every directory under `backend/src/trace/` has a single, unambiguous responsibility:

| Directory | Responsibility |
|---|---|
| `trace/core/` | Centralized typed configuration (`ApplicationConfig`) and structured logging with secret redaction. |
| `trace/domain/` | Pure business domain entities (`Project`, `Repository`), value objects (`ConnectionValidationResult`), domain exceptions, and states. |
| `trace/services/` | Application service layer orchestrating domain workflows (`ProjectService`, `RepositoryService`). |
| `trace/api/` | HTTP transport layer containing FastAPI routers, route dependencies, and Pydantic validation schemas. |
| `trace/api/health/` | Health check endpoint (`GET /health`) and response schemas (`HealthStatus`, `ServiceStatus`). |
| `trace/api/projects/` | Project endpoints (`/api/v1/projects`) and project-scoped repository routes. |
| `trace/api/repositories/` | Repository endpoints (`/api/v1/repositories`) for detail retrieval, deletion, and validation. |
| `trace/infrastructure/` | External boundary integrations and gateway protocols. |
| `trace/infrastructure/database/` | Relational database gateway protocol and SQLAlchemy 2.x async engine implementations. |
| `trace/infrastructure/database/models/` | SQLAlchemy ORM declarative models (`ProjectOrm`, `RepositoryOrm`) mapping tables to domain models. |
| `trace/infrastructure/git/` | Git probe interface definitions (`GitProvider` Protocol). |
| `trace/infrastructure/git/adapters/` | Concrete Git provider implementations (`SubprocessGitProvider`). |
| `trace/infrastructure/graph/` | Graph database gateway protocol and Neo4j async driver implementations. |
| `trace/infrastructure/llm/` | LLM abstraction protocol (`LLMProvider`), response union (`LLMResponse`), and model configuration. |
| `trace/infrastructure/llm/adapters/` | Vendor-specific provider adapters (`OpenRouterAdapter` using `httpx` and `tenacity`). |

---

## 4. F01 API Endpoints Reference

TRACE exposes 10 REST endpoints for Project and Repository management under `/api/v1`, alongside the Phase 0 `/health` endpoint:

### Project Management (`trace/api/projects/router.py`)

| Method | Endpoint | Description | Status Code |
|---|---|---|---|
| `POST` | `/api/v1/projects` | Create a new project in `ACTIVE` status | 201 Created |
| `GET` | `/api/v1/projects` | List projects paginated, optional filter by `status` | 200 OK |
| `GET` | `/api/v1/projects/{project_id}` | Retrieve project details and repository count | 200 OK |
| `POST` | `/api/v1/projects/{project_id}/archive` | Archive project (prevents new repo registration/validation) | 200 OK |
| `POST` | `/api/v1/projects/{project_id}/activate` | Reactivate an archived project | 200 OK |
| `POST` | `/api/v1/projects/{project_id}/repositories` | Register a new local or remote repository under project | 201 Created |
| `GET` | `/api/v1/projects/{project_id}/repositories` | List all repositories registered under a project | 200 OK |

### Repository Management (`trace/api/repositories/router.py`)

| Method | Endpoint | Description | Status Code |
|---|---|---|---|
| `GET` | `/api/v1/repositories/{repository_id}` | Retrieve repository metadata, status, and validation history | 200 OK |
| `DELETE` | `/api/v1/repositories/{repository_id}` | Delete unanalyzed repository (`last_analysis_run_id` is null) | 204 No Content |
| `POST` | `/api/v1/repositories/{repository_id}/validate` | Trigger on-demand probe-only connectivity validation | 200 OK |

---

## 5. Git Provider Abstraction (`trace/infrastructure/git/`)

The `GitProvider` interface is a probe-only, non-destructive boundary:

```python
@runtime_checkable
class GitProvider(Protocol):
    async def validate_local(self, path: Path) -> ConnectionValidationResult: ...
    async def validate_remote(self, url: str) -> ConnectionValidationResult: ...
```

### Key Behavioral Constraints:
1. **Probe-Only**: Zero repository cloning, zero revision checkout, zero AST extraction, and zero Neo4j graph operations in F01.
2. **Local Validation**: Inspects directory existence, uses `git rev-parse --is-inside-work-tree` (scoped to `--git-dir <path>/.git`) or checks bare repositories via `git --git-dir <path> rev-parse --is-bare-repository`. Discovers branch via `git symbolic-ref --short HEAD`. No fallback to arbitrary default branch names on failure or detached HEAD.
3. **Remote Validation**: Probes connectivity via `git ls-remote --symref <url> HEAD` with `GIT_TERMINAL_PROMPT=0` and timeout enforcement. Extracts default branch target if advertised.
4. **Security & Secrets**: Strictly rejects embedded credentials (user/password in URL userinfo) at the API schema boundary (HTTP 422). Zero plaintext tokens or credentials stored in the database or emitted in logs.

---

## 6. Architectural Boundary Rules

1. **Strict Direction of Dependency**:
   - `trace/domain/` MUST NOT import from `trace/core/`, `trace/api/`, `trace/services/`, or `trace/infrastructure/`. Domain code is pure Python stdlib.
   - `trace/services/` coordinates domain models and communicates with infrastructure only via Protocols (`DatabaseGateway`, `GitProvider`).
   - `trace/api/` depends only on services, dependency injection, and Pydantic schemas. It MUST NOT import concrete adapters.
2. **Composition Root Instantiation Boundary**:
   - `backend/src/trace/main.py` lifespan is the **only permitted location** for instantiating concrete adapters (`SQLAlchemyDatabaseGateway`, `SubprocessGitProvider`, `OpenRouterAdapter`).
3. **Replaceability Guarantees**:
   - Swapping Git CLI for a library or native provider requires implementing `GitProvider` and updating `main.py`.
   - Swapping PostgreSQL requires changing only database gateway/ORM mapping.

---

## 7. Concern Placement Reference Table

| Concern | Correct Location | Prohibited Locations |
|---|---|---|
| HTTP Routing & Status Codes | `trace/api/` | `trace/domain/`, `trace/infrastructure/`, `trace/services/` |
| Business Rules & Entity Invariants | `trace/domain/` | `trace/api/`, `trace/infrastructure/` |
| Workflow & Transaction Orchestration | `trace/services/` | `trace/api/`, `trace/domain/` |
| Database Queries & ORM Models | `trace/infrastructure/database/` | `trace/api/`, `trace/domain/` |
| Git Subprocess & Probes | `trace/infrastructure/git/adapters/` | `trace/api/`, `trace/services/`, `trace/domain/` |
| Graph Traversal & Drivers | `trace/infrastructure/graph/` | `trace/api/`, `trace/domain/` |
| LLM API Calls & Retries | `trace/infrastructure/llm/adapters/` | `trace/api/`, `trace/domain/`, `trace/services/` |
| Environment Variable Reading | `trace/core/config.py` | Anywhere else via `os.environ` or `os.getenv` |
| Secret Redaction & Log Formatting | `trace/core/logging.py` | Individual route handlers or services |
