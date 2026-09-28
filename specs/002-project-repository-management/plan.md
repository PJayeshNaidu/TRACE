# Technical Implementation Plan: TRACE Phase 1 — F01: Project & Repository Management

**Branch**: `002-project-repository-management` | **Date**: 2026-09-28 | **Spec**: [spec.md](./spec.md)

---

## Summary

TRACE Phase 1 (F01: Project & Repository Management) builds the persistent foundation for all subsequent repository analysis capabilities (F02 Code Analyzer, F03 Dependency Graph, F04 Change Analyzer). F01 enables users to create and manage TRACE projects with an explicit lifecycle (`ACTIVE` ↔ `ARCHIVED`), register local filesystem repositories and remote Git repositories, store persistent repository metadata in PostgreSQL, validate repository connectivity deterministically via a replaceable `GitProvider` abstraction without cloning working trees, and manage the system via RESTful FastAPI endpoints.

---

## Technical Context

- **Language/Version**: Python 3.12 (standardized in Phase 0)
- **Primary Dependencies**: FastAPI (async HTTP), SQLAlchemy 2.0 (asyncpg), Alembic (migrations), Pydantic v2 (schemas), structlog (logging), httpx (testing), tenacity (retry logic)
- **Git Engine**: Python standard library `asyncio.subprocess` invoking system `git` CLI with `GIT_TERMINAL_PROMPT=0` (zero new external pip dependencies)
- **Storage**: PostgreSQL 16+ (authoritative application state); zero Neo4j writes in F01
- **Testing**: `pytest`, `pytest-asyncio`, `pytest-cov`, `httpx` (ASGI TestClient), SQLite in-memory via `aiosqlite`
- **Target Platform**: Linux / macOS / Windows developer workstations and containerized environments
- **Project Type**: Async REST Web Service (Backend API)
- **Performance Goals**: Sub-500ms project creation and listing response time; remote reference probe bounded by 10.0s hard timeout
- **Constraints**: 100% deterministic test execution with 0 external network requests; zero plaintext credentials in PostgreSQL or logs; strict 5-layer onion architecture

---

## Constitution Check

*GATE: Evaluation against TRACE Constitution principles before implementation.*

| Principle | Conformance Analysis | Status |
|---|---|---|
| **I. Evidence over Hallucination** | Repository facts (existence, HEAD target, remote refs) are deterministically resolved via Git CLI; no repository metadata is fabricated or guessed. | **PASS** |
| **II. Deterministic before Probabilistic** | Purely deterministic Git probes; zero LLM inference or probabilistic parsing in F01. | **PASS** |
| **III. Human-in-the-Loop** | Projects and repositories are registered and managed exclusively via explicit human user API actions. | **PASS** |
| **IV. Explainability and Evidence** | Validation failures record explicit failure diagnostics in `last_error` and return actionable failure reasons. | **PASS** |
| **V. Provider Independence** | Git operations are decoupled through the `GitProvider` Python Protocol, independent of any specific Git library or hosting provider. | **PASS** |
| **VI. Free-First Architecture** | Zero paid APIs, proprietary SDKs, or cloud services required. | **PASS** |
| **VII. Testability** | Standard test suite uses `StubGitProvider` and temporary local Git fixtures (`git init`); 0 external network calls required. | **PASS** |
| **VIII. Explicit Contracts** | Domain entities, ORM tables, API Pydantic schemas, and Git interfaces are strictly separated across layers. | **PASS** |
| **IX. Security & Secret Isolation** | Zero database secrets; embedded basic-auth URLs rejected at registration with HTTP 422; ambient host auth only; logging redacts sensitive tokens. | **PASS** |
| **X. Incremental Delivery** | Strictly delivers F01 project and repository management; excludes F02 AST parsing, F03 graph construction, and full cloning. | **PASS** |
| **XI. Observability** | All operations emit structured `structlog` events with `project_id`, `repository_id`, and `event`. | **PASS** |
| **XII. Reproducibility** | Given identical local paths or remote Git refs, validation results and default branch detection are 100% reproducible. | **PASS** |
| **XIII. Maintainability (YAGNI)** | Uses standard library `asyncio.subprocess` for Git; avoids premature credential vaults or complex multi-tenant models. | **PASS** |
| **XIV. Replaceability** | `GitProvider` is runtime-checkable protocol; concrete `SubprocessGitProvider` is swappable without domain changes. | **PASS** |
| **XV. Backward-Compatible Evolution** | Preserves Phase 0 `GET /health` and lifespan composition root; migrations chain cleanly from `0001_baseline`. | **PASS** |
| **XVI. Production Quality** | Targets ≥80% line and branch test coverage, strict `mypy` type checking, and zero Ruff linter warnings. | **PASS** |
| **XVII. No Fabricated State** | `GitProvider` defines only implemented probe operations; no dead stub methods for clone or diff. | **PASS** |

---

## Project Structure & Architecture Changes

```text
backend/
├── alembic/
│   └── versions/
│       ├── 0001_baseline.py               # Existing Phase 0 baseline
│       └── 0002_project_repository.py     # [NEW] Alembic migration for projects & repositories
├── src/trace/
│   ├── api/
│   │   ├── router.py                      # [MODIFIED] Register projects and repositories routers
│   │   ├── errors.py                      # [NEW] Global exception handlers & ErrorResponse envelope
│   │   ├── health/                        # Existing Phase 0 health check
│   │   ├── projects/                      # [NEW] Project API layer
│   │   │   ├── __init__.py
│   │   │   ├── router.py                  # FastAPI route endpoints for projects
│   │   │   └── schemas.py                 # Pydantic v2 request/response schemas
│   │   └── repositories/                  # [NEW] Repository API layer
│   │       ├── __init__.py
│   │       ├── router.py                  # FastAPI route endpoints for repositories
│   │       └── schemas.py                 # Pydantic v2 request/response schemas
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── health.py                      # Existing Phase 0 health states
│   │   ├── project.py                     # [NEW] Project domain entity and ProjectStatus enum
│   │   ├── repository.py                  # [NEW] Repository domain entity, RepositoryType, RepositoryStatus, ConnectionValidationResult
│   │   └── exceptions.py                  # [NEW] Typed domain exceptions (ProjectNotFoundError, DuplicateRepositoryError, etc.)
│   ├── infrastructure/
│   │   ├── database/
│   │   │   ├── gateway.py                 # Existing Phase 0 DatabaseGateway protocol and implementations
│   │   │   └── models/                    # [NEW] SQLAlchemy ORM Declarative Models
│   │   │       ├── __init__.py
│   │   │       ├── base.py                # DeclarativeBase class
│   │   │       ├── project.py             # ProjectOrm (projects table)
│   │   │       └── repository.py          # RepositoryOrm (repositories table)
│   │   └── git/                           # [NEW] Git boundary abstraction
│   │       ├── __init__.py
│   │       ├── provider.py                # GitProvider Protocol
│   │       └── adapters/
│   │           ├── __init__.py
│   │           └── subprocess.py          # SubprocessGitProvider implementation
│   ├── services/                          # [NEW] Domain service layer
│   │   ├── __init__.py
│   │   ├── project.py                     # ProjectService (orchestrates project lifecycle and queries)
│   │   └── repository.py                  # RepositoryService (orchestrates registration, validation, deletion)
│   └── main.py                            # [MODIFIED] Wire GitProvider and services in FastAPI lifespan
└── tests/
    ├── conftest.py                        # [MODIFIED] Add StubGitProvider, test DB gateway fixtures
    ├── api/
    │   ├── test_projects_api.py           # [NEW] API contract tests for /api/v1/projects
    │   └── test_repositories_api.py       # [NEW] API contract tests for /api/v1/repositories
    ├── integration/
    │   └── test_postgres_f01.py           # [NEW] Live PostgreSQL migration and persistence tests
    └── unit/
        ├── test_project_domain.py         # [NEW] Project domain model and validation tests
        ├── test_repository_domain.py      # [NEW] Repository domain model and normalization tests
        ├── test_subprocess_git.py         # [NEW] SubprocessGitProvider unit tests with local fixtures
        ├── test_project_service.py        # [NEW] ProjectService unit tests
        └── test_repository_service.py     # [NEW] RepositoryService unit tests
```

---

## Detailed Architectural Components

### 1. Domain Model Changes
- **`trace/domain/project.py`**:
  - `ProjectStatus(StrEnum)`: `ACTIVE`, `ARCHIVED`.
  - `Project`: Pure frozen dataclass with `id: UUID`, `name: str`, `description: str | None`, `status: ProjectStatus`, `created_at: datetime`, `updated_at: datetime`.
- **`trace/domain/repository.py`**:
  - `RepositoryType(StrEnum)`: `LOCAL`, `REMOTE`.
  - `RepositoryStatus(StrEnum)`: `REGISTERED`, `CONNECTED`, `ERROR`.
  - `ConnectionValidationResult`: Frozen dataclass with `is_connected: bool`, `detected_branch: str | None`, `error_message: str | None`, `latency_ms: float`.
  - `Repository`: Pure frozen dataclass with all metadata fields and `last_analysis_run_id: UUID | None`.
- **`trace/domain/exceptions.py`**:
  - Central hierarchy: `TraceDomainError` base class, with specialized subclasses:
    - `ProjectNotFoundError`, `ProjectAlreadyExistsError`, `ProjectArchivedError`
    - `RepositoryNotFoundError`, `DuplicateRepositoryError`, `RepositoryInUseError`, `InvalidRepositoryLocationError`, `UnsupportedRepositoryTypeError`, `RepositoryInaccessibleError`
    - `DatabasePersistenceError`

### 2. Application & Service Layer Changes
- **`trace/services/project.py` (`ProjectService`)**:
  - `create_project(name: str, description: str | None) -> Project`: Validates name, checks uniqueness, persists via `DatabaseGateway`.
  - `get_project(project_id: UUID) -> tuple[Project, int]`: Retrieves project and repository count; raises `ProjectNotFoundError` if absent.
  - `list_projects(limit: int, offset: int, status: ProjectStatus | None) -> tuple[list[tuple[Project, int]], int]`: Paginated project retrieval with repository counts.
  - `archive_project(project_id: UUID) -> Project`: Transitions `ACTIVE` → `ARCHIVED`.
  - `activate_project(project_id: UUID) -> Project`: Transitions `ARCHIVED` → `ACTIVE`.
- **`trace/services/repository.py` (`RepositoryService`)**:
  - `register_repository(project_id: UUID, repo_type: RepositoryType, location: str, default_branch: str | None) -> Repository`:
    Verifies project exists and is `ACTIVE`. Normalizes location. Enforces uniqueness. Persists with initial status `REGISTERED`.
  - `get_repository(repository_id: UUID) -> Repository`: Retrieves repository by ID.
  - `list_repositories(project_id: UUID) -> list[Repository]`: Retrieves all repositories in project.
  - `delete_repository(repository_id: UUID) -> None`: Verifies `last_analysis_run_id` is null; raises `RepositoryInUseError` if linked to analysis. Deletes row.
  - `validate_repository(repository_id: UUID) -> tuple[Repository, ConnectionValidationResult]`:
    Dispatches to `GitProvider` based on `type`. Updates `status` to `CONNECTED` or `ERROR`, updates `last_validated_at`, `last_error`, and `default_branch` if resolved.

### 3. Repository & Persistence Layer Changes
- Create SQLAlchemy ORM models in `trace/infrastructure/database/models/`:
  - `Base`: Root `DeclarativeBase`.
  - `ProjectOrm`: Maps to `projects` table with relationship to repositories (no hard-delete cascades; F01 enforces archival lifecycle).
  - `RepositoryOrm`: Maps to `repositories` table with `project_id` foreign key, composite unique constraint `uq_project_location (project_id, location)`, and nullable `last_analysis_run_id` (optional denormalized convenience reference for future F02; `analysis_runs.repository_id` will be the authoritative FK).
- Use `DatabaseGateway.session()` async context manager for all transaction boundaries with automatic commit and rollback.

### 4. PostgreSQL Schema & Alembic Migration Strategy
- Migration file: `backend/alembic/versions/0002_project_repository.py`.
- Revision dependency: `down_revision = "0001_baseline"`.
- Table DDL:
  - `projects`: `id UUID PRIMARY KEY`, `name VARCHAR(100) UNIQUE NOT NULL`, `description TEXT NULL`, `status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'`, `created_at TIMESTAMPTZ NOT NULL`, `updated_at TIMESTAMPTZ NOT NULL`.
  - `repositories`: `id UUID PRIMARY KEY`, `project_id UUID NOT NULL REFERENCES projects(id)`, `type VARCHAR(20) NOT NULL`, `location VARCHAR(500) NOT NULL`, `default_branch VARCHAR(100) NULL`, `status VARCHAR(20) NOT NULL DEFAULT 'REGISTERED'`, `last_error TEXT NULL`, `last_validated_at TIMESTAMPTZ NULL`, `last_analysis_run_id UUID NULL`, `created_at TIMESTAMPTZ NOT NULL`, `updated_at TIMESTAMPTZ NOT NULL`.
  - Indexes: `ix_projects_name` (unique), `ix_repositories_project_id`.
  - Constraint: `CONSTRAINT uq_project_location UNIQUE (project_id, location)`.
- Reversible: `downgrade()` cleanly drops `repositories` then `projects`.

### 5. Git-Provider Abstraction
- Protocol in `trace/infrastructure/git/provider.py`:
  - `validate_local(path: Path) -> ConnectionValidationResult`
  - `validate_remote(url: str, timeout_seconds: float) -> ConnectionValidationResult`
  - `detect_default_branch(location: str, repo_type: RepositoryType) -> str | None`
  - `list_remote_references(url: str, timeout_seconds: float) -> list[str]`
- Runtime checkable Protocol ensuring clean swappability.

### 6. Local Git Implementation
- In `SubprocessGitProvider`:
  - Resolves path using `path.resolve()`.
  - Validates `path.is_dir()`.
  - Executes `git -C <path> rev-parse --is-inside-work-tree` and `git -C <path> rev-parse --is-bare-repository`.
  - If valid, queries default branch: `git -C <path> symbolic-ref --short HEAD` (or reads commit hash if detached HEAD).
  - Returns `ConnectionValidationResult(is_connected=True, detected_branch=..., error_message=None, latency_ms=...)`.
  - If path does not exist or is not a git repository, catches exit code and returns `is_connected=False` with diagnostic.

### 7. Remote Repository Validation Strategy
- In `SubprocessGitProvider`:
  - Enforces URL scheme check (`http://`, `https://`, `ssh://`).
  - Executes `git ls-remote --symref <url> HEAD` with `GIT_TERMINAL_PROMPT=0` and `GIT_ASKPASS=echo`.
  - Wrapped in `asyncio.wait_for(timeout=10.0)`.
  - Parses stdout for `ref: refs/heads/<branch>\tHEAD` to extract default branch.
  - If exit code != 0 or timeout expires: captures stderr, redacts any ambient credentials, and returns `is_connected=False` with human-readable error summary.
  - Zero repository cloning to disk.

### 8. API Endpoints & Pydantic Contracts
- Routers:
  - `trace/api/projects/router.py`:
    - `POST /api/v1/projects`: 201 Created -> `ProjectResponse`
    - `GET /api/v1/projects`: 200 OK -> `ProjectListResponse`
    - `GET /api/v1/projects/{project_id}`: 200 OK -> `ProjectResponse`
    - `POST /api/v1/projects/{project_id}/archive`: 200 OK -> `ProjectResponse`
    - `POST /api/v1/projects/{project_id}/activate`: 200 OK -> `ProjectResponse`
  - `trace/api/repositories/router.py`:
    - `POST /api/v1/projects/{project_id}/repositories`: 201 Created -> `RepositoryResponse`
    - `GET /api/v1/projects/{project_id}/repositories`: 200 OK -> `RepositoryListResponse`
    - `GET /api/v1/repositories/{repository_id}`: 200 OK -> `RepositoryResponse`
    - `DELETE /api/v1/repositories/{repository_id}`: 204 No Content
    - `POST /api/v1/repositories/{repository_id}/validate`: 200 OK -> `ValidationReportResponse`
- Register both routers in `trace/api/router.py`.

### 9. Typed Error Model
- Global exception handler in `trace/api/errors.py`:
  - `ProjectNotFoundError` -> 404
  - `RepositoryNotFoundError` -> 404
  - `ProjectAlreadyExistsError` -> 409
  - `ProjectArchivedError` -> 409
  - `DuplicateRepositoryError` -> 409
  - `RepositoryInUseError` -> 409
  - `InvalidRepositoryLocationError` -> 422
  - `UnsupportedRepositoryTypeError` -> 422
  - `DatabasePersistenceError` -> 500
  - Response body format: `ErrorResponse(error_code="...", message="...", details={})`.

### 10. Configuration Changes
- `trace/core/config.py`:
  - Add optional settings with safe defaults:
    - `git_timeout_seconds: float = Field(default=10.0, description="Timeout for Git subprocess commands")`
    - `git_binary_path: str = Field(default="git", description="Path to system git executable")`
- Existing Phase 0 configuration remains 100% backward compatible.

### 11. Security Boundaries & Credential Isolation
- Remote URLs containing basic-auth tokens (`https://user:token@...`) are rejected by Pydantic validator at API boundary with HTTP 422.
- PostgreSQL tables contain zero credential columns.
- Subprocess execution environment strictly redacts any tokens.
- All loggers apply the Phase 0 credential redaction processors.

### 12. Observability & Structured Logging
- Events logged via `structlog`:
  - `project_created` (id, name)
  - `project_archived` (id)
  - `project_activated` (id)
  - `repository_registered` (id, project_id, type, location)
  - `repository_validated` (id, is_connected, latency_ms)
  - `repository_deleted` (id, project_id)
- Failed connectivity checks logged at `WARNING` with diagnostic reasons.

### 13. Test Strategy & Deterministic Fixtures
- **Unit Tests**:
  - `tests/unit/test_project_domain.py`: Entity immutability, name validation.
  - `tests/unit/test_repository_domain.py`: Status transitions, location normalization.
  - `tests/unit/test_subprocess_git.py`: Tests `SubprocessGitProvider` against temporary local Git directories created with `git init`.
  - `tests/unit/test_project_service.py` & `test_repository_service.py`: Service tests with mock database gateway and `StubGitProvider`.
- **API Tests**:
  - `tests/api/test_projects_api.py` & `tests/api/test_repositories_api.py`: FastAPI TestClient tests with in-memory SQLite gateway, verifying status codes, schema formatting, and validation failures.
- **Integration Tests**:
  - `tests/integration/test_postgres_f01.py`: Marked with `@pytest.mark.integration` to test real migrations and constraints on live PostgreSQL.
- **Coverage**: Target ≥80% overall line and branch coverage.

### 14. Documentation Changes
- Update `docs/architecture.md` to reflect F01 domain services, ORM models, and Git provider adapters.
- Document F01 API endpoints in OpenAPI schema.

### 15. Downstream Integration Points for F02 & F04
- **F02 (Repository / Code Analyzer)**: Consumes `project_id`, `repository_id`, canonical `location`, and verified `default_branch`. Links new analysis runs to `last_analysis_run_id`.
- **F04 (Version / Change Analyzer)**: Consumes repository context and extends `GitProvider` with branch/commit diff operations.

---

## Implementation Order & Phased Milestones

```mermaid
flowchart TD
    M1["Milestone 1: Domain Entities & Typed Exceptions<br>(trace/domain/project.py, repository.py, exceptions.py)"]
    M2["Milestone 2: Relational Models & Alembic Migration<br>(models/project.py, repository.py, 0002_project_repository.py)"]
    M3["Milestone 3: GitProvider Protocol & Subprocess Adapter<br>(infrastructure/git/provider.py, adapters/subprocess.py)"]
    M4["Milestone 4: Domain Services Layer<br>(services/project.py, services/repository.py)"]
    M5["Milestone 5: API Layer, Pydantic Schemas & Error Handlers<br>(api/projects/, api/repositories/, api/errors.py)"]
    M6["Milestone 6: Lifespan Composition Wiring<br>(trace/main.py, trace/api/router.py)"]
    M7["Milestone 7: Comprehensive Test Suite & Verification<br>(unit, service, API, fixture tests)"]

    M1 --> M2
    M1 --> M3
    M2 --> M4
    M3 --> M4
    M4 --> M5
    M5 --> M6
    M6 --> M7
```

---

## Risk Analysis & Mitigation

| Risk | Impact | Mitigation Strategy |
|---|---|---|
| **Subprocess Git hanging on remote network call** | Worker blocked, HTTP request timeout | Hard kernel timeout (10.0s) via `asyncio.wait_for`; `GIT_TERMINAL_PROMPT=0` to block interactive prompts. |
| **Path traversal in local repository registration** | Security vulnerability (arbitrary host inspection) | Canonical path resolution (`Path.resolve()`) and directory existence verification; disallow null bytes. |
| **Inadvertent plaintext credential storage** | Security violation (Constitution §IX) | Regex validation rejecting basic-auth tokens in remote URLs at the API schema boundary (HTTP 422). |
| **Cross-database UUID incompatibility in tests** | SQLite tests fail on PostgreSQL UUID types | Use `sqlalchemy.Uuid` type which adapts to native UUID in PostgreSQL and string in SQLite. |
| **Premature analysis run triggers** | Resource exhaustion, violates F01 boundary | F01 registration explicitly leaves `last_analysis_run_id` as null; zero cloning or AST parsing code added. |
