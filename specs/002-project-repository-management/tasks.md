# Implementation Tasks: TRACE Phase 1 — F01: Project & Repository Management

**Branch**: `002-project-repository-management` | **Date**: 2026-09-28 | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

This document contains the actionable, dependency-ordered task breakdown for implementing TRACE Phase 1 — F01 (Project & Repository Management). All tasks follow the strict checklist format and are grouped into Setup, Foundational, User Story phases (P1, P2, P3), and Polish/Integration.

---

## Task Summary & Execution Roadmap

```text
Phase 1: Setup & Configuration (T001 - T003)
     ↓
Phase 2: Foundational Data Models, Migrations & Shared Infrastructure (T004 - T007)
     ↓
Phase 3: User Story 1 - Create & Manage TRACE Projects (P1 - MVP) (T008 - T013)
     ↓
Phase 4: User Story 2 - Register, Inspect & Delete Repositories (P2) (T014 - T019)
     ↓
Phase 5: User Story 3 - Repository Connectivity Validation & Git Abstraction (P3) (T020 - T025)
     ↓
Phase 6: Polish, Integration, Observability & Final Verification (T026 - T030)
```

---

## Phase 1: Setup & Configuration

**Purpose**: Establish configuration settings, domain exception hierarchy, and API error response envelopes required across all user stories.

- [x] T001 Add Git execution settings to ApplicationConfig in backend/src/trace/core/config.py
  - **Objective**: Extend application configuration to support Git subprocess timeouts and executable paths without breaking existing Phase 0 settings.
  - **Affected Area**: `backend/src/trace/core/config.py`
  - **Dependencies**: None
  - **Implementation Requirements**: Add `git_timeout_seconds: float = Field(default=10.0, description="...")` and `git_binary_path: str = Field(default="git", description="...")`. Ensure empty-string validator treats empty strings as default values.
  - **Verification Criteria**: Unit tests in `backend/tests/unit/test_config.py` pass and confirm default values are populated when env vars are absent.

- [x] T002 [P] Implement typed domain exception hierarchy in backend/src/trace/domain/exceptions.py
  - **Objective**: Define centralized, typed domain exceptions decoupling business error states from HTTP transport layers.
  - **Affected Area**: `backend/src/trace/domain/exceptions.py`
  - **Dependencies**: None
  - **Implementation Requirements**: Implement `TraceDomainError` base class. Implement subclasses: `ProjectNotFoundError`, `ProjectAlreadyExistsError`, `ProjectArchivedError`, `RepositoryNotFoundError`, `DuplicateRepositoryError`, `RepositoryInUseError`, `InvalidRepositoryLocationError`, `UnsupportedRepositoryTypeError`, `RepositoryInaccessibleError`, and `DatabasePersistenceError`. Include docstrings and entity identifier attributes on exceptions.
  - **Verification Criteria**: Exceptions can be instantiated with custom messages and IDs; unit tests verify inheritance from `TraceDomainError`.

- [x] T003 [P] Implement standardized ErrorResponse schema and exception handlers in backend/src/trace/api/errors.py
  - **Objective**: Create the HTTP error response envelope and FastAPI exception handlers mapping domain exceptions to HTTP status codes.
  - **Affected Area**: `backend/src/trace/api/errors.py`
  - **Dependencies**: T002
  - **Implementation Requirements**: Create Pydantic model `ErrorResponse` with fields `error_code: str`, `message: str`, and `details: dict[str, str]`. Implement `register_exception_handlers(app: FastAPI)` mapping: `ProjectNotFoundError`/`RepositoryNotFoundError` → 404, `ProjectAlreadyExistsError`/`ProjectArchivedError`/`DuplicateRepositoryError`/`RepositoryInUseError` → 409, `InvalidRepositoryLocationError`/`UnsupportedRepositoryTypeError` → 422, `DatabasePersistenceError` → 500.
  - **Verification Criteria**: Unit test verifies that raising `ProjectNotFoundError` in a test route yields a 404 response matching the `ErrorResponse` schema.

---

## Phase 2: Foundational (Data Models, Migrations & Shared Infrastructure)

**Purpose**: Create pure domain models, SQLAlchemy ORM mappings, Alembic migration `0002_project_repository`, and test fixtures.

**⚠️ CRITICAL**: Must be completed before implementing user stories.

- [x] T004 Implement Project and Repository domain models and enums in backend/src/trace/domain/project.py and backend/src/trace/domain/repository.py
  - **Objective**: Define immutable pure Python domain models and StrEnums with zero framework imports.
  - **Affected Area**: `backend/src/trace/domain/project.py`, `backend/src/trace/domain/repository.py`
  - **Dependencies**: None
  - **Implementation Requirements**: In `project.py`: define `ProjectStatus(StrEnum)` (`ACTIVE`, `ARCHIVED`) and frozen dataclass `Project(id, name, description, status, created_at, updated_at)`. In `repository.py`: define `RepositoryType(StrEnum)` (`LOCAL`, `REMOTE`), `RepositoryStatus(StrEnum)` (`REGISTERED`, `CONNECTED`, `ERROR`), frozen dataclass `ConnectionValidationResult(is_connected, detected_branch, error_message, latency_ms)`, and frozen dataclass `Repository(id, project_id, type, location, default_branch, status, last_error, last_validated_at, last_analysis_run_id, created_at, updated_at)`.
  - **Verification Criteria**: `test_project_domain.py` verifies dataclass immutability, enum member values, and zero third-party framework imports.

- [x] T005 [P] Create SQLAlchemy ORM models for Project and Repository in backend/src/trace/infrastructure/database/models/
  - **Objective**: Define SQLAlchemy 2.0 declarative ORM models mapping domain entities to PostgreSQL tables.
  - **Affected Area**: `backend/src/trace/infrastructure/database/models/base.py`, `backend/src/trace/infrastructure/database/models/project.py`, `backend/src/trace/infrastructure/database/models/repository.py`, `backend/src/trace/infrastructure/database/models/__init__.py`
  - **Dependencies**: T004
  - **Implementation Requirements**: In `base.py`, create `Base(DeclarativeBase)`. In `project.py`, define `ProjectOrm` (`__tablename__ = "projects"`) with `id: Mapped[uuid.UUID]`, `name: Mapped[str]` (globally unique via `unique=True, index=True`, preserving audit integrity across active and archived projects), `status: Mapped[str]`, timestamps, and relationship to `repositories` (without hard-delete cascades, reflecting F01's archival lifecycle). In `repository.py`, define `RepositoryOrm` (`__tablename__ = "repositories"`) with `id`, `project_id` (foreign key `projects.id`), `type`, `location`, `default_branch`, `status`, `last_error`, `last_validated_at`, `last_analysis_run_id` (nullable UUID column as an optional denormalized convenience reference for future F02; `analysis_runs.repository_id` will be the authoritative FK relationship in F02), timestamps, and `UniqueConstraint("project_id", "location", name="uq_project_location")`.
  - **Verification Criteria**: Models instantiate without errors; metadata reflects global project name uniqueness, `uq_project_location` constraint, and absence of hard-delete cascades.

- [x] T006 Create Alembic migration 0002_project_repository in backend/alembic/versions/0002_project_repository.py
  - **Objective**: Write bidirectional database schema migration for `projects` and `repositories` tables chained from baseline.
  - **Affected Area**: `backend/alembic/versions/0002_project_repository.py`
  - **Dependencies**: T005
  - **Implementation Requirements**: Define `revision = "0002_project_repository"`, `down_revision = "0001_baseline"`. In `upgrade()`: create `projects` table with unique index on `name`, create `repositories` table with foreign key `projects.id` and index on `project_id`, nullable `last_analysis_run_id` UUID column, and composite unique constraint `uq_project_location (project_id, location)`. In `downgrade()`: drop `repositories` table, drop `projects` table.
  - **Verification Criteria**: `uv run alembic upgrade head` succeeds in clean test database; `uv run alembic downgrade -1` cleanly rolls back.

- [x] T007 Configure test doubles and database fixtures in backend/tests/conftest.py
  - **Objective**: Confirm and wire Phase 0 in-memory test doubles and GitProvider test stubs for deterministic test execution.
  - **Affected Area**: `backend/tests/conftest.py`
  - **Dependencies**: T005
  - **Implementation Requirements**: Use `InMemoryDatabaseGateway` (the established Phase 0 SQLite-backed double from `trace/infrastructure/database/gateway.py` using `sqlite+aiosqlite:///:memory:`) for unit and service test isolation, creating ORM tables via `Base.metadata.create_all`. Add `stub_git_provider` fixture implementing `GitProvider` Protocol with configurable probe return values. Reserve PostgreSQL fixtures strictly for live integration tests.
  - **Verification Criteria**: Existing Phase 0 tests continue to pass; new test fixtures execute queries against the established Phase 0 in-memory double without network or PostgreSQL dependencies.

---

## Phase 3: User Story 1 - Create & Manage TRACE Projects (Priority: P1) 🎯 MVP

**Goal**: Enable users to create a project, list projects with pagination, retrieve project details by ID, archive a project, and reactivate an archived project.

**Independent Test**: Run `pytest tests/api/test_projects_api.py` and `tests/unit/test_project_service.py` to verify full project lifecycle without requiring repositories or Git interactions.

- [x] T008 [P] [US1] Implement Project API request and response schemas in backend/src/trace/api/projects/schemas.py
  - **Objective**: Define Pydantic v2 schemas for project creation, details, and paginated listing.
  - **Affected Area**: `backend/src/trace/api/projects/schemas.py`, `backend/src/trace/api/projects/__init__.py`
  - **Dependencies**: T004
  - **Implementation Requirements**: Implement `ProjectCreateRequest` with `name: str` (1–100 chars, `@field_validator` stripping whitespace and rejecting blank strings) and optional `description: str` (max 1000 chars). Implement `ProjectResponse` matching domain fields plus `repository_count: int` and ISO 8601 UTC timestamps. Implement `ProjectListResponse` with `items: list[ProjectResponse]`, `total: int`, `limit: int`, and `offset: int`.
  - **Verification Criteria**: Schema validation rejects blank names, names > 100 chars, and serializes valid datetime objects to ISO 8601 format.

- [x] T009 [P] [US1] Create unit tests for Project domain model and lifecycle in backend/tests/unit/test_project_domain.py
  - **Objective**: Test Project entity instantiation, immutability, and state representation.
  - **Affected Area**: `backend/tests/unit/test_project_domain.py`
  - **Dependencies**: T004
  - **Implementation Requirements**: Write unit tests verifying: frozen dataclass behavior (cannot mutate attributes), default `ProjectStatus.ACTIVE`, `ProjectStatus.ARCHIVED` values, and string representations.
  - **Verification Criteria**: `uv run pytest tests/unit/test_project_domain.py` passes with 100% assertion success.

- [x] T010 [US1] Implement ProjectService in backend/src/trace/services/project.py
  - **Objective**: Orchestrate project creation, unique name checking, retrieval, listing, archival, and reactivation using DatabaseGateway.
  - **Affected Area**: `backend/src/trace/services/project.py`, `backend/src/trace/services/__init__.py`
  - **Dependencies**: T002, T004, T005
  - **Implementation Requirements**: Implement `ProjectService(db_gateway: DatabaseGateway)`:
    - `create_project(name, description) -> Project`: Normalizes name, queries for existing project by name across all statuses (globally unique), raises `ProjectAlreadyExistsError` if the name already exists in active or archived state, inserts `ProjectOrm`, returns domain `Project`.
    - `get_project(project_id) -> tuple[Project, int]`: Queries project with count of linked repositories. Raises `ProjectNotFoundError` if absent.
    - `list_projects(limit, offset, status) -> tuple[list[tuple[Project, int]], int]`: Queries paginated projects with optional status filter and total count.
    - `archive_project(project_id) -> tuple[Project, int]`: Checks project exists; if already `ARCHIVED`, raises `ProjectArchivedError`; updates status to `ARCHIVED` and `updated_at`.
    - `activate_project(project_id) -> tuple[Project, int]`: Checks project exists; updates status to `ACTIVE` and `updated_at`.
  - **Verification Criteria**: `test_project_service.py` verifies all service methods against in-memory database gateway.

- [x] T011 [P] [US1] Create unit tests for ProjectService in backend/tests/unit/test_project_service.py
  - **Objective**: Thoroughly test ProjectService business logic and error handling.
  - **Affected Area**: `backend/tests/unit/test_project_service.py`
  - **Dependencies**: T010
  - **Implementation Requirements**: Write unit tests for: successful creation, duplicate name rejection, retrieval of existing/missing project, pagination limits/offsets, archival, repeated archival rejection, and reactivation.
  - **Verification Criteria**: `uv run pytest tests/unit/test_project_service.py` passes with zero failures.

- [x] T012 [US1] Implement Project API router endpoints in backend/src/trace/api/projects/router.py
  - **Objective**: Expose FastAPI routes for project management.
  - **Affected Area**: `backend/src/trace/api/projects/router.py`
  - **Dependencies**: T003, T008, T010
  - **Implementation Requirements**: Create `projects_router = APIRouter(prefix="/projects", tags=["projects"])`:
    - `POST /`: `create_project` (HTTP 201 Created -> `ProjectResponse`)
    - `GET /`: `list_projects` (HTTP 200 OK -> `ProjectListResponse`) with query params `limit=50`, `offset=0`, `status=None`
    - `GET /{project_id}`: `get_project` (HTTP 200 OK -> `ProjectResponse`)
    - `POST /{project_id}/archive`: `archive_project` (HTTP 200 OK -> `ProjectResponse`)
    - `POST /{project_id}/activate`: `activate_project` (HTTP 200 OK -> `ProjectResponse`)
    Inject `ProjectService` via FastAPI `Depends()`.
  - **Verification Criteria**: FastAPI OpenAPI schema documents all 5 endpoints with request/response models.

- [x] T013 [US1] Create API contract and integration tests for Projects in backend/tests/api/test_projects_api.py
  - **Objective**: Test HTTP status codes, schema validation, and error envelopes for all Project endpoints.
  - **Affected Area**: `backend/tests/api/test_projects_api.py`
  - **Dependencies**: T012
  - **Implementation Requirements**: Write API tests using `httpx.AsyncClient`:
    - `POST /api/v1/projects`: 201 Created on valid input; 422 on blank/whitespace name; 409 on duplicate name.
    - `GET /api/v1/projects/{project_id}`: 200 on existing ID; 404 on missing UUID.
    - `GET /api/v1/projects`: 200 with pagination items and total count.
    - `POST /api/v1/projects/{id}/archive`: 200 with status `ARCHIVED`; 409 on second archive call.
    - `POST /api/v1/projects/{id}/activate`: 200 with status `ACTIVE`.
  - **Verification Criteria**: `uv run pytest tests/api/test_projects_api.py` passes with 100% green tests.

---

## Phase 4: User Story 2 - Register, Inspect & Delete Repositories (Priority: P2)

**Goal**: Allow users to register local or remote Git repositories under an active project, inspect repository details, list repositories for a project, and delete unanalyzed repositories.

**Independent Test**: Run `pytest tests/api/test_repositories_api.py` and `tests/unit/test_repository_service.py` to verify repository registration, location normalization, duplicate prevention, and deletion protection.

- [x] T014 [P] [US2] Implement Repository API schemas with embedded-credential rejection in backend/src/trace/api/repositories/schemas.py
  - **Objective**: Define Pydantic v2 schemas for repository registration, details, listing, and validation reports with rigorous credential isolation.
  - **Affected Area**: `backend/src/trace/api/repositories/schemas.py`, `backend/src/trace/api/repositories/__init__.py`
  - **Dependencies**: T004
  - **Implementation Requirements**: Implement `RepositoryRegisterRequest` with `type: RepositoryType`, `location: str` (1–500 chars), and optional `default_branch: str`. Implement `@field_validator("location")` that rejects empty strings, null bytes (`\0`), and parses both URI formats (`urllib.parse.urlsplit`) and SCP-style syntax (`user:pass@host:path`) to strictly reject any embedded passwords, tokens, or basic-auth credentials with a clear error directing users to ambient host authentication. Permit ambient SSH usernames without passwords (e.g., `git@github.com:...` or `ssh://git@github.com/...`). Implement `RepositoryResponse`, `RepositoryListResponse`, and `ValidationReportResponse`.
  - **Verification Criteria**: Schema validation rejects `https://user:token@github.com/org/repo`, `https://user:password@host/repo`, and `git:secret@host:org/repo` with HTTP 422; allows clean HTTPS, SSH (including standard `git@host:...` SCP syntax), and local paths.

- [x] T015 [P] [US2] Create unit tests for Repository domain model & normalization logic in backend/tests/unit/test_repository_domain.py
  - **Objective**: Verify Repository entity behavior, status enum, and location normalization utility functions.
  - **Affected Area**: `backend/tests/unit/test_repository_domain.py`
  - **Dependencies**: T004
  - **Implementation Requirements**: Write unit tests verifying: frozen dataclass properties, default status `REGISTERED`, `last_analysis_run_id` null initialization. Test normalization function: local paths resolved to absolute paths; remote URLs lowercased, trailing `.git` stripped, trailing `/` stripped.
  - **Verification Criteria**: `uv run pytest tests/unit/test_repository_domain.py` passes.

- [x] T016 [US2] Implement RepositoryService registration, retrieval, listing & deletion in backend/src/trace/services/repository.py
  - **Objective**: Orchestrate repository registration under active projects, composite uniqueness enforcement, and deletion guard.
  - **Affected Area**: `backend/src/trace/services/repository.py`
  - **Dependencies**: T002, T004, T005, T010
  - **Implementation Requirements**: Implement `RepositoryService(db_gateway: DatabaseGateway, git_provider: GitProvider)`:
    - `register_repository(project_id, repo_type, location, default_branch) -> Repository`:
      Checks project exists and status is `ACTIVE` (raises `ProjectArchivedError` if `ARCHIVED`).
      Normalizes location. Checks `(project_id, normalized_location)` uniqueness; raises `DuplicateRepositoryError` if duplicate.
      Inserts `RepositoryOrm` with status `REGISTERED` and `last_analysis_run_id=None`.
    - `get_repository(repository_id) -> Repository`: Queries repository by ID; raises `RepositoryNotFoundError` if missing.
    - `list_repositories_for_project(project_id) -> list[Repository]`: Verifies project exists, returns all linked repositories.
    - `delete_repository(repository_id) -> None`: Queries repository; if `last_analysis_run_id` is not None, raises `RepositoryInUseError`; deletes row from database.
  - **Verification Criteria**: `test_repository_service.py` confirms successful registration, rejection on archived project, duplicate prevention, and deletion guard.

- [x] T017 [P] [US2] Create unit tests for RepositoryService in backend/tests/unit/test_repository_service.py
  - **Objective**: Thoroughly test repository business rules and edge cases in isolation.
  - **Affected Area**: `backend/tests/unit/test_repository_service.py`
  - **Dependencies**: T016
  - **Implementation Requirements**: Write unit tests for: registration in active project, registration rejection in archived project, duplicate registration rejection in same project, permitted registration of same location across different projects, deletion of unanalyzed repository, and rejection of deletion when `last_analysis_run_id` is set.
  - **Verification Criteria**: `uv run pytest tests/unit/test_repository_service.py` passes with zero errors.

- [x] T018 [US2] Implement Repository API router registration, list, get, and delete routes in backend/src/trace/api/repositories/router.py
  - **Objective**: Expose FastAPI endpoints for repository registration, retrieval, and deletion.
  - **Affected Area**: `backend/src/trace/api/repositories/router.py`, `backend/src/trace/api/projects/router.py`
  - **Dependencies**: T003, T014, T016
  - **Implementation Requirements**:
    - Under `projects_router` (`/projects/{project_id}/repositories`):
      - `POST /`: `register_repository` (HTTP 201 Created -> `RepositoryResponse`)
      - `GET /`: `list_repositories_for_project` (HTTP 200 OK -> `RepositoryListResponse`)
    - Under `repositories_router` (`/repositories`):
      - `GET /{repository_id}`: `get_repository` (HTTP 200 OK -> `RepositoryResponse`)
      - `DELETE /{repository_id}`: `delete_repository` (HTTP 204 No Content)
  - **Verification Criteria**: Endpoints respond with correct schemas; 204 status returned on deletion.

- [x] T019 [US2] Create API contract tests for Repository registration and deletion in backend/tests/api/test_repositories_api.py
  - **Objective**: Test HTTP responses, duplicate rejection, and credential protection for repository routes.
  - **Affected Area**: `backend/tests/api/test_repositories_api.py`
  - **Dependencies**: T018
  - **Implementation Requirements**: Write API tests:
    - Register valid local path: 201 Created with status `REGISTERED`.
    - Register valid remote HTTPS URL: 201 Created.
    - Register URL with embedded token (`https://u:p@host`): 422 Unprocessable Entity.
    - Register duplicate location under same project: 409 Conflict.
    - Register duplicate location under different project: 201 Created.
    - Register to non-existent project: 404 Not Found.
    - Register to archived project: 409 Conflict.
    - `DELETE /repositories/{id}` on unanalyzed repo: 204 No Content; subsequent `GET` gives 404.
  - **Verification Criteria**: `uv run pytest tests/api/test_repositories_api.py` passes with 100% coverage of negative and positive paths.

---

## Phase 5: User Story 3 - Repository Connectivity Validation & Git Abstraction (Priority: P3)

**Goal**: Provide deterministic verification that registered local and remote repositories can be accessed, updating repository status to `CONNECTED` or `ERROR` without cloning codebases.

**Independent Test**: Run `pytest tests/api/test_repositories_validation_api.py` and `tests/unit/test_subprocess_git.py` using local Git fixtures and mock remote probes.

- [x] T020 [P] [US3] Define GitProvider Protocol interface in backend/src/trace/infrastructure/git/provider.py
  - **Objective**: Establish the replaceable Git provider abstraction boundary strictly for probe operations per Constitution §XIV and §XVII.
  - **Affected Area**: `backend/src/trace/infrastructure/git/provider.py`, `backend/src/trace/infrastructure/git/__init__.py`
  - **Dependencies**: T004
  - **Implementation Requirements**: Define `@runtime_checkable class GitProvider(Protocol)` with strictly probe-only methods:
    - `async def validate_local(self, path: Path) -> ConnectionValidationResult: ...`
    - `async def validate_remote(self, url: str, timeout_seconds: float = 10.0) -> ConnectionValidationResult: ...`
    - `async def detect_default_branch(self, location: str, repo_type: RepositoryType) -> str | None: ...`
    - `async def list_remote_references(self, url: str, timeout_seconds: float = 10.0) -> list[str]: ...`
    Strictly avoid declaring stubbed or unimplemented future F02/F04 methods (e.g., clone, checkout, diff, AST extraction).
  - **Verification Criteria**: `isinstance(adapter, GitProvider)` returns True for conforming classes; protocol definition contains zero unimplemented stubs.

- [x] T021 [US3] Implement SubprocessGitProvider adapter in backend/src/trace/infrastructure/git/adapters/subprocess.py
  - **Objective**: Implement asynchronous, non-destructive Git probe operations using system Git CLI.
  - **Affected Area**: `backend/src/trace/infrastructure/git/adapters/subprocess.py`, `backend/src/trace/infrastructure/git/adapters/__init__.py`
  - **Dependencies**: T001, T004, T020
  - **Implementation Requirements**: Implement `SubprocessGitProvider(config: ApplicationConfig)`:
    - `validate_local(path)`:
      - Checks `path.exists()` and `path.is_dir()`. If missing or permission denied, returns `is_connected=False` with descriptive error.
      - Executes `git -C <path> rev-parse --is-inside-work-tree` and `git -C <path> rev-parse --is-bare-repository`.
      - Explicit bare-repository behavior: If either command returns `"true"`, path is recognized as a valid Git repository (`is_connected=True`). If neither succeeds, returns `is_connected=False` with error message `"Not a valid Git repository"`.
      - Prohibit default-branch fallback: Executes `git -C <path> symbolic-ref --short HEAD`. If successful, returns the detected branch name. If unresolvable (e.g., detached HEAD, empty repository, or failure), returns `detected_branch=None` (never fallback to `"main"`, `"master"`, or any hardcoded value). Measures probe latency. Returns `ConnectionValidationResult`.
    - `validate_remote(url, timeout)`: Executes `git ls-remote --symref <url> HEAD` with `GIT_TERMINAL_PROMPT=0` and `GIT_ASKPASS=echo` wrapped in `asyncio.wait_for`. Parses stdout for `ref: refs/heads/<branch>\tHEAD`. If no symref is parsed, returns `detected_branch=None` (no fallback). Captures stderr diagnostics on non-zero exit codes. Returns `ConnectionValidationResult`.
    - `detect_default_branch(location, repo_type)`: Dispatches to local symbolic-ref or remote ls-remote; returns `None` if unresolvable.
    - `list_remote_references(url, timeout)`: Executes `git ls-remote --heads --tags <url>` and returns ref names.
  - **Verification Criteria**: Unit tests verify command arguments, timeout handling, output parsing, bare repo recognition, and absence of default branch synthesis.

- [x] T022 [P] [US3] Create unit and fixture tests for SubprocessGitProvider in backend/tests/unit/test_subprocess_git.py
  - **Objective**: Test SubprocessGitProvider against real temporary Git repositories and simulated remote responses without external network access.
  - **Affected Area**: `backend/tests/unit/test_subprocess_git.py`
  - **Dependencies**: T021
  - **Implementation Requirements**: Use `tmp_path` fixture with `subprocess.run(["git", "init", ...])` to create valid local standard repository and bare repository (`git init --bare`) fixtures. Test: valid local working-tree repo returns `is_connected=True` with correct branch; valid bare repo returns `is_connected=True`; detached HEAD returns `is_connected=True` with `detected_branch=None`; non-existent path returns `is_connected=False` with error message; non-git folder returns `is_connected=False` with error message. Remote tests must be strictly mock/stub only: simulate subprocess stdout/stderr for success, timeout, exit 128, and authentication failure without making live external network calls.
  - **Verification Criteria**: `uv run pytest tests/unit/test_subprocess_git.py` passes 100% deterministically with zero live network calls to GitHub, GitLab, or external hosts.

- [x] T023 [US3] Implement validate_repository workflow in RepositoryService in backend/src/trace/services/repository.py
  - **Objective**: Connect repository entity to GitProvider probe, updating lifecycle status and timestamps without cloning codebase or touching Neo4j.
  - **Affected Area**: `backend/src/trace/services/repository.py`
  - **Dependencies**: T016, T020, T021
  - **Implementation Requirements**: Implement `validate_repository(repository_id: UUID) -> tuple[Repository, ConnectionValidationResult]` in `RepositoryService`:
    - Strictly probe-only: zero repository cloning, revision checkout, AST extraction, or Neo4j graph operations.
    - Queries repository; raises `RepositoryNotFoundError` if missing.
    - Checks parent project status; if `ARCHIVED`, raises `ProjectArchivedError`.
    - If `type == LOCAL`, calls `git_provider.validate_local(Path(location))`.
    - If `type == REMOTE`, calls `git_provider.validate_remote(location)`.
    - Updates `last_validated_at` to current UTC time.
    - If `is_connected == True`: updates `status = CONNECTED`, `last_error = None`, and updates `default_branch` if resolved from probe.
    - If `is_connected == False`: updates `status = ERROR`, `last_error = result.error_message`.
    - Commits transaction and returns updated `Repository` and `ConnectionValidationResult`.
  - **Verification Criteria**: Unit tests in `test_repository_service.py` confirm status transitions to `CONNECTED` and `ERROR` matching provider results.

- [x] T024 [US3] Add POST /api/v1/repositories/{repository_id}/validate endpoint in backend/src/trace/api/repositories/router.py
  - **Objective**: Expose the connectivity validation endpoint over HTTP.
  - **Affected Area**: `backend/src/trace/api/repositories/router.py`
  - **Dependencies**: T018, T023
  - **Implementation Requirements**: Add route `POST /{repository_id}/validate` responding with HTTP 200 OK and `ValidationReportResponse`. Ensure HTTP 200 is returned even when `is_connected` is False (returning diagnostic status inside the payload).
  - **Verification Criteria**: Endpoint returns `ValidationReportResponse` matching schema specifications.

- [x] T025 [US3] Create API tests for repository validation in backend/tests/api/test_repositories_validation_api.py
  - **Objective**: Test HTTP validation endpoint with stubbed GitProvider for reachable and unreachable scenarios.
  - **Affected Area**: `backend/tests/api/test_repositories_validation_api.py`
  - **Dependencies**: T024
  - **Implementation Requirements**: Write API tests using FastAPI TestClient with `StubGitProvider`:
    - Successful local repository validation: 200 OK, `is_connected: true`, status `CONNECTED`, `detected_branch: "main"`.
    - Failed local validation: 200 OK, `is_connected: false`, status `ERROR`, `error_message` present.
    - Successful remote probe: 200 OK, `is_connected: true`, status `CONNECTED`.
    - Failed remote probe (e.g. timeout / exit 128): 200 OK, `is_connected: false`, status `ERROR`.
    - Validation on archived project: 409 Conflict.
  - **Verification Criteria**: `uv run pytest tests/api/test_repositories_validation_api.py` passes with zero network requests.

---

## Phase 6: Polish, Integration, Observability & Final Verification

**Purpose**: Wire components into the FastAPI application lifespan, add structured logging, verify live database persistence, and validate end-to-end quickstart scenarios.

- [x] T026 Wire GitProvider, services, and routers in FastAPI Lifespan composition root in backend/src/trace/main.py and backend/src/trace/api/router.py
  - **Objective**: Instantiate `SubprocessGitProvider`, wire dependencies into application state, and register new API routers.
  - **Affected Area**: `backend/src/trace/main.py`, `backend/src/trace/api/router.py`
  - **Dependencies**: T003, T012, T018, T021
  - **Implementation Requirements**: In `trace/main.py` lifespan: instantiate `SubprocessGitProvider(config=cfg)`, store in `app.state.git`. Register exception handlers from `trace.api.errors`. In `trace/api/router.py`: include `projects_router` and `repositories_router` under `/api/v1`. Preserve existing `health_router` unchanged.
  - **Verification Criteria**: Application starts cleanly with `uv run uvicorn trace.main:app`; `GET /health` continues to return 200 OK (preserved Phase 0 endpoint); OpenAPI `/docs` displays all 10 new F01 endpoints across projects and repositories (5 project routes and 5 repository routes).

- [x] T027 [P] Add structured logging events for all project and repository operations in backend/src/trace/services/
  - **Objective**: Emit structured `structlog` events for lifecycle actions per Constitution §XI and NFR-009.
  - **Affected Area**: `backend/src/trace/services/project.py`, `backend/src/trace/services/repository.py`
  - **Dependencies**: T010, T016, T023
  - **Implementation Requirements**: Emit structured log events with `logger.info()` / `logger.warning()`:
    - `project_created` (project_id, name)
    - `project_archived` (project_id)
    - `project_activated` (project_id)
    - `repository_registered` (repository_id, project_id, type, location)
    - `repository_validated` (repository_id, is_connected, status, latency_ms)
    - `repository_deleted` (repository_id, project_id)
    Ensure zero plaintext secrets or tokens are emitted.
  - **Verification Criteria**: Unit tests in `tests/unit/test_logging_redaction.py` confirm structured log format and credential redaction.

- [x] T028 [P] Implement PostgreSQL live integration tests in backend/tests/integration/test_postgres_f01.py
  - **Objective**: Verify migrations, composite unique constraints, archival state persistence, and unanalyzed repository deletion against real PostgreSQL.
  - **Affected Area**: `backend/tests/integration/test_postgres_f01.py`
  - **Dependencies**: T006, T010, T016
  - **Implementation Requirements**: Add integration tests marked with `@pytest.mark.integration`:
    - Apply `0002_project_repository` migration to PostgreSQL.
    - Test project creation and repository creation with real UUID primary keys.
    - Test that `uq_project_location` raises `IntegrityError` on duplicate registration under the same project in PostgreSQL.
    - Test that project archival transitions status to `ARCHIVED`, updates timestamp, and prevents new repository registration in PostgreSQL.
    - Test that project reactivation transitions status back to `ACTIVE` in PostgreSQL.
    - Test that unanalyzed repositories can be deleted via `DELETE /repositories/{id}`, while avoiding project hard-delete cascades in accordance with the archival model.
    - Test that `alembic downgrade -1` cleanly reverts to `0001_baseline`.
  - **Verification Criteria**: Integration tests pass against live PostgreSQL; skipped during default unit test runs; verify archival semantics, constraint integrity, and rollback capability without reliance on project hard-delete cascades.

- [x] T029 [P] Update documentation with F01 architecture and API reference in docs/architecture.md
  - **Objective**: Update architectural documentation reflecting the implemented F01 domain services, ORM models, and Git probe abstraction.
  - **Affected Area**: `docs/architecture.md`
  - **Dependencies**: T026
  - **Implementation Requirements**: Update the 5-layer hierarchy diagram to document `trace/services/project.py`, `trace/services/repository.py`, `trace/infrastructure/git/`, and `trace/infrastructure/database/models/`. Document `GitProvider` Protocol (probe-only) and the 10 `projects`/`repositories` REST endpoints. Strictly document implemented F01 behavior without claiming unbuilt future features (F02, F03, F04).
  - **Verification Criteria**: `docs/architecture.md` accurately describes current codebase state without documenting unbuilt F02+ features.

- [x] T030 Execute end-to-end quickstart validation and coverage gate in backend/
  - **Objective**: Verify that all 10 scenarios from quickstart.md succeed and overall test coverage exceeds 80%.
  - **Affected Area**: Whole backend test suite
  - **Dependencies**: T001–T029
  - **Implementation Requirements**: Validate all 10 scenarios in `quickstart.md` (Scenario 1: migrations, Scenario 2: service startup & /health, Scenario 3: project creation, Scenario 4: local repo registration, Scenario 5: embedded credential rejection, Scenario 6: local repo validation, Scenario 7: remote repo validation, Scenario 8: project archival & reactivation, Scenario 9: unanalyzed repo deletion, Scenario 10: deterministic test suite execution). Run `uv run pytest` to execute unit, service, and API tests. Confirm coverage report shows ≥80% line and branch coverage across all new modules (`trace.domain.project`, `trace.domain.repository`, `trace.services.*`, `trace.infrastructure.git.*`, `trace.api.projects.*`, `trace.api.repositories.*`). Run `uv run ruff check .` and `uv run mypy src`.
  - **Verification Criteria**: All 10 quickstart scenarios verified; Pytest passes 100% with ≥80% coverage; Ruff and mypy report zero violations.

---

## Dependencies & Execution Order

### Phase Dependencies
- **Phase 1 (Setup)**: No dependencies. Can start immediately.
- **Phase 2 (Foundational)**: Depends on Phase 1 completion. Blocks all User Stories.
- **Phase 3 (User Story 1 - P1)**: Depends on Phase 2 completion. Delivers the core project management MVP.
- **Phase 4 (User Story 2 - P2)**: Depends on Phase 2 and Phase 3 completion. Delivers repository registration and metadata persistence.
- **Phase 5 (User Story 3 - P3)**: Depends on Phase 2 and Phase 4 completion. Delivers Git provider probing and connectivity validation.
- **Phase 6 (Polish & Verification)**: Depends on Phase 3, 4, and 5 completion. Integrates lifespan wiring, logging, documentation, and coverage gates.

### Parallel Opportunities
- In Phase 1: `T002` (exceptions) and `T003` (errors) can proceed in parallel.
- In Phase 2: `T005` (ORM models) can be developed alongside `T004` (domain entities).
- In Phase 3: `T008` (schemas) and `T009` (domain tests) can run in parallel before `T010` (service).
- In Phase 4: `T014` (schemas) and `T015` (normalization tests) can run in parallel.
- In Phase 5: `T020` (protocol) and `T022` (fixtures) can proceed in parallel.
- In Phase 6: `T027` (logging), `T028` (Postgres integration), and `T029` (docs) can execute in parallel.

---

## Verification Criteria Checklist

- [x] `uv run pytest` runs deterministically without network calls and passes with ≥ 80% coverage.
- [x] `uv run ruff check .` passes with zero linting warnings.
- [x] `uv run mypy src` passes in strict mode with zero type errors.
- [x] `uv run alembic upgrade head` and `uv run alembic downgrade -1` run cleanly against PostgreSQL.
- [x] Registered repositories remain strictly unanalyzed (`last_analysis_run_id` is null).
- [x] Zero repository credentials or access tokens are persisted to PostgreSQL or logged.
