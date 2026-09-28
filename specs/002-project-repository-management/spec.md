# Feature Specification: TRACE Phase 1 — F01: Project & Repository Management

**Feature Branch**: `002-project-repository-management`

**Created**: 2026-09-28

**Status**: Draft

**Input**: User description: "TRACE Phase 1 — F01: Project & Repository Management. Build persistent Project & Repository Management capability allowing users to create and manage TRACE projects and connect Git repositories for later F02 analysis."

---

## Overview & Scope Boundaries

TRACE (Transformation Risk Analysis & Change Evaluation) requires a persistent Project & Repository Management capability that serves as the entry point and foundational context for the entire platform. F01 enables users to establish projects, register Git repositories (both local filesystem paths and remote URLs), inspect repository metadata, and verify repository connectivity deterministically.

### Architectural Boundaries

**F01 Owns**:
- Project lifecycle management (creation, listing, retrieval, archiving).
- Repository registration under projects (1-to-many relationship).
- Persistent repository metadata storage in PostgreSQL.
- Deterministic repository connectivity validation (local and remote accessibility probes).
- Git-provider abstraction interface (`GitProvider` protocol) to isolate Git operations from domain logic.
- REST API endpoints for all project and repository management operations.
- Credential masking and secret isolation for repository URLs in storage, responses, and logs.
- Typed domain and HTTP error mappings with structured logging.

**F01 Explicitly Does NOT Own (Out of Scope)**:
- Python AST extraction or code parsing (owned by F02).
- Structural dependency graph construction or Neo4j node creation (owned by F03).
- Commit history diffing, semantic change evaluation, or version comparisons (owned by F04).
- Impact analysis, blast radius calculation, or downstream risk assessment (owned by F05/F06).
- Automated repository cloning of entire codebases to disk during registration.
- AI/LLM-based repository reasoning, summaries, or chatbot assistants.
- Production React-based Observatory UI (initial interaction via FastAPI REST contracts).

---

## Clarifications

### Session 2026-09-28

- Q: How should authentication credentials for private Git repositories be handled and stored in F01 given that Phase 0 does not include a database encryption layer? → A: Option A — Ambient host credentials only (no DB secrets). F01 stores no credentials or tokens in PostgreSQL. Authentication relies entirely on ambient environment credentials (host SSH agent/keys, system Git credential helper, or environment variables). URLs containing embedded basic-auth credentials or tokens are rejected at registration with HTTP 422 to prevent accidental plaintext leakage.
- Q: Should F01 support deletion (unregistration) of repositories and projects, or should it enforce non-destructive archiving only? → A: Option A — Project archiving + unanalyzed repository deletion. Projects use non-destructive archiving (`POST /projects/{id}/archive` and `POST /projects/{id}/activate` for reactivation). Individual repositories can be deleted via `DELETE /api/v1/repositories/{id}` provided they have not yet been linked to an analysis run (`last_analysis_run_id` is null).
- Q: How should repository identity and uniqueness be scoped when the same physical repository is registered across different TRACE projects? → A: Option A — Project-scoped repository records (1-to-many). Each repository record belongs to exactly one project with a composite unique constraint on `(project_id, normalized_location)`. Distinct projects may register the same Git repository independently without cross-project state pollution.
- Q: How should the Git provider abstraction boundary be structured in F01 to support current connectivity validation while ensuring clean extensibility for future F02 cloning and F04 change analysis? → A: Option A — Targeted probe interface in F01 (incremental extension). Define `GitProvider` protocol with methods strictly needed for F01 (local validation, remote reference probe, default branch detection, reference listing). F02 and F04 will extend the protocol or add workspace/diff protocols in their respective phases without stubbing unimplemented methods now.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Create and Manage a TRACE Project (Priority: P1)

An engineering lead or developer wants to define a new software project in TRACE so they can group and manage the codebase repositories undergoing transformation risk evaluation. They can create a project with a unique name and description, view project details, list all active projects, and archive projects when they are no longer actively monitored.

**Why this priority**: Without a persistent project entity, no repository can be registered and no subsequent analysis runs can be organized or associated with a business domain.

**Independent Test**: Can be fully tested through API and persistence layers by creating a project with valid metadata, verifying its retrieval by identifier, listing available projects, updating its status to archived, and ensuring duplicate project names/identifiers are rejected.

**Acceptance Scenarios**:

1. **Given** a valid project name and optional description, **When** a user submits a creation request, **Then** the system creates a new project with a unique identifier, status `ACTIVE`, created and updated timestamps, and persists it to the database.
2. **Given** an existing project in the system, **When** a user requests the project by its unique identifier, **Then** the system returns the complete project details including its identifier, name, description, status, and repository count.
3. **Given** multiple registered projects, **When** a user requests a list of projects, **Then** the system returns a collection of project summaries sorted by creation date with status indicators.
4. **Given** an attempt to create a project with a name that is empty, exceeds 100 characters, or contains only whitespace, **When** the request is submitted, **Then** the system rejects the request with a descriptive validation error and creates no record.
5. **Given** an existing active project, **When** a user requests to archive the project, **Then** the system transitions the project status to `ARCHIVED`, updates the timestamp, and retains all associated historical data without deleting records.
6. **Given** an archived project, **When** a user requests to reactivate the project, **Then** the system transitions the project status back to `ACTIVE`, updates the timestamp, and allows repository registration to resume.
7. **Given** an archived project, **When** a user attempts to register new repositories or archive it again without reactivating, **Then** the system rejects the operation with a conflict error stating that archived projects are immutable.

---

### User Story 2 - Register and Inspect a Repository in a Project (Priority: P2)

A developer wants to associate one or more Git repositories with an existing project. They provide either a local filesystem path (for local development and evaluation) or a remote Git URL (e.g., HTTPS), along with an optional default branch hint. The system registers the repository, captures initial metadata, and records its status as `REGISTERED` without triggering expensive code analysis.

**Why this priority**: Repositories are the primary physical artifact that TRACE analyzes. Registering repositories cleanly with clear separation from analysis is essential to prevent unintended heavy workloads.

**Independent Test**: Can be fully tested by registering a local path or remote URL under an existing project, verifying that repository metadata is persisted, checking that the repository lists under the parent project, and confirming that no analysis runs or graph nodes are created.

**Acceptance Scenarios**:

1. **Given** an active project and a valid local filesystem repository path, **When** a user registers the repository, **Then** the system stores the repository record associated with the project, sets its type to `LOCAL`, sets status to `REGISTERED`, records the timestamp, and returns the registered metadata.
2. **Given** an active project and a valid remote Git URL (HTTPS/SSH), **When** a user registers the repository, **Then** the system stores the repository record, sets its type to `REMOTE`, sets status to `REGISTERED`, and rejects any URL containing embedded basic-auth credentials or tokens with an HTTP 422 error.
3. **Given** a repository already registered under a project with the same path/URL, **When** a user attempts to register the identical repository under that same project, **Then** the system rejects the registration with a conflict error to prevent duplicates.
4. **Given** a non-existent project identifier, **When** a user attempts to register a repository, **Then** the system returns a project-not-found error without persisting any repository data.
5. **Given** a registered repository, **When** a user views its details, **Then** the system displays the repository location, type, current status, default branch (if specified), timestamps, and a null or empty last-analysis reference, explicitly confirming it has not yet undergone analysis.
6. **Given** an unanalyzed repository (`last_analysis_run_id` is null), **When** a user submits a deletion request via `DELETE /api/v1/repositories/{repository_id}`, **Then** the system removes the repository record from PostgreSQL and returns HTTP 204 No Content.
7. **Given** a repository that has been analyzed and linked to an analysis run, **When** a user submits a deletion request, **Then** the system rejects the deletion with HTTP 409 Conflict, preserving historical integrity per TRACE Constitution §I and §XI.

---

### User Story 3 - Validate Repository Connectivity Deterministically (Priority: P3)

A developer or automated workflow wants to verify that TRACE can access a registered repository before initiating deep code analysis. They trigger a connectivity validation check. For local repositories, TRACE verifies that the directory exists on disk and is a valid Git repository. For remote repositories, TRACE executes a lightweight network connectivity probe (e.g., querying remote references) without cloning files or executing Python code.

**Why this priority**: Validating access deterministically prevents failed downstream analysis pipelines, surfacing network or filesystem access issues early with clear diagnostic reasons.

**Independent Test**: Can be fully tested by running validation against a valid local Git directory fixture, an invalid local directory, a reachable remote URL, and an unreachable/invalid remote URL, verifying that status transitions to `CONNECTED` or `ERROR` with actionable error diagnostics.

**Acceptance Scenarios**:

1. **Given** a registered local repository whose filesystem path is an initialized Git repository, **When** a connectivity validation is triggered, **Then** the system verifies the Git control files, transitions status to `CONNECTED`, records the detected default branch, and returns a successful validation report.
2. **Given** a registered local repository whose filesystem path does not exist or is not a Git repository, **When** connectivity validation is triggered, **Then** the system transitions repository status to `ERROR`, records an explicit error diagnostic (e.g., path not found or not a git repository), and returns the failure diagnostic without raising unhandled exceptions.
3. **Given** a registered remote repository with a valid and reachable URL, **When** connectivity validation is triggered, **Then** the system queries the remote Git references using the Git provider abstraction, transitions status to `CONNECTED`, discovers the default branch, and returns a successful validation report.
4. **Given** a registered remote repository that is unreachable (e.g., non-existent host or authentication required), **When** connectivity validation is triggered, **Then** the system transitions status to `ERROR`, records an explicit access error diagnostic, and returns the diagnostic without leaking sensitive network or credential data.
5. **Given** a repository connectivity check, **When** the validation completes (success or failure), **Then** no source code files are parsed, no AST nodes are generated, and no Neo4j transactions are issued.

---

### Edge Cases

- **Path Traversal & Relative Paths**: What happens when a local repository path contains `../` or relative path segments? The system resolves and normalizes paths to absolute paths and rejects paths outside permitted directory roots in restricted environments.
- **Embedded Credentials in URLs**: How does the system handle remote URLs containing basic authentication tokens (e.g., `https://user:ghp_secret@github.com/org/repo.git`)? The system parses remote URLs and explicitly rejects any URL containing embedded user credentials or tokens with HTTP 422 Unprocessable Entity, requiring credentials to be provided via host ambient authentication (SSH keys or Git credential helpers) and strictly preventing plaintext credential storage in PostgreSQL.
- **Dangling Repositories on Project Archival**: How does the system handle repositories belonging to an archived project? Repositories remain read-only; new repository registrations and modifications are blocked.
- **Database Unavailability**: How does the system behave when PostgreSQL is unreachable during project creation or repository registration? The system returns HTTP 503 / persistence error with structured error logging, without corrupting state.
- **Validation of Bare vs. Non-Bare Repositories**: How does local validation handle bare Git repositories? The system recognizes both standard working trees (`.git` directory) and bare Git repositories (`HEAD`, `refs/`, `objects/`) as valid Git sources.
- **Unresponsive Remote Hosts**: How does the system handle remote Git hosts that hang indefinitely? Connectivity validation enforces a strict, configurable network timeout (default 10 seconds), transitioning to `ERROR` status with a `timeout` diagnostic rather than blocking the worker.
- **Non-ASCII and Unicode Project Names**: How are Unicode project names handled? The system validates project names using standard UTF-8 encoding, trimming leading/trailing whitespace and enforcing length bounds.

---

## Requirements *(mandatory)*

### Functional Requirements

#### Project Management
- **FR-001**: The system MUST allow users to create a new TRACE project with a required `name` (1–100 characters) and an optional `description` (up to 1,000 characters).
- **FR-002**: The system MUST assign every project a unique, immutable UUIDv4 identifier upon creation.
- **FR-003**: The system MUST reject project creation if the project name is empty, contains only whitespace, or exceeds 100 characters.
- **FR-004**: The system MUST enforce project name uniqueness across active projects, rejecting duplicate names with an HTTP 409 Conflict error.
- **FR-005**: The system MUST support an explicit project lifecycle status: `ACTIVE` and `ARCHIVED`. Newly created projects MUST have status `ACTIVE`.
- **FR-006**: The system MUST allow transitioning a project between `ACTIVE` and `ARCHIVED`:
  - `POST /api/v1/projects/{project_id}/archive` transitions an `ACTIVE` project to `ARCHIVED`.
  - `POST /api/v1/projects/{project_id}/activate` transitions an `ARCHIVED` project back to `ACTIVE`.
  - In both transitions, the system MUST record the updated timestamp.
- **FR-007**: The system MUST prevent modification or registration of repositories to a project that is in `ARCHIVED` status.
- **FR-008**: The system MUST allow retrieving a project by its unique identifier, returning its identifier, name, description, status, creation timestamp, update timestamp, and the count of registered repositories.
- **FR-009**: The system MUST allow listing projects, supporting pagination (`limit` default 50, `offset` default 0) and optional status filtering (`status=ACTIVE|ARCHIVED`).
- **FR-010**: The system MUST return an HTTP 404 Not Found response when a requested project identifier does not exist.

#### Repository Registration & Metadata
- **FR-011**: The system MUST allow registering one or more repositories under an active project (1-to-many relationship). Each repository row belongs to exactly one project (`project_id` foreign key). Distinct projects MAY register the same Git repository independently without cross-project state collision.
- **FR-012**: The system MUST assign each registered repository a unique, immutable UUIDv4 identifier.
- **FR-013**: The system MUST support repository types `LOCAL` (filesystem path) and `REMOTE` (Git URL).
- **FR-014**: The system MUST capture and store the following metadata for each repository:
  - `id`: UUIDv4
  - `project_id`: UUIDv4 foreign key referencing the parent project
  - `type`: `LOCAL` or `REMOTE`
  - `location`: File path (for local) or sanitized Git URL (for remote)
  - `default_branch`: String or null (detected or user-supplied hint)
  - `status`: Lifecycle state (`REGISTERED`, `CONNECTED`, `ERROR`)
  - `last_error`: Text or null (capturing latest validation failure reason)
  - `last_validated_at`: ISO 8601 timestamp or null
  - `last_analysis_run_id`: UUIDv4 or null (reserved for F02 analysis linkage; always null upon registration)
  - `created_at`: ISO 8601 timestamp
  - `updated_at`: ISO 8601 timestamp
  *(Note: No credential, personal access token, or password columns are defined or stored in PostgreSQL; F01 enforces zero database secrets per Constitution §IX).*
- **FR-015**: Newly registered repositories MUST be assigned the initial status `REGISTERED`.
- **FR-016**: Registering a repository MUST NOT trigger AST extraction, code intelligence analysis, dependency graph generation, or repository cloning.
- **FR-017**: The system MUST prevent registering duplicate repositories under the same project by enforcing a composite unique constraint on `(project_id, normalized_location)`:
  - Location normalization rules:
    - For `LOCAL` repositories: resolve canonical absolute filesystem path (symlinks resolved, case normalized per host OS).
    - For `REMOTE` repositories: lowercase scheme and host, strip trailing `.git` suffix, strip trailing `/` slash.
  - Attempting to register an already-registered repository location within the same project MUST return HTTP 409 Conflict (`DuplicateRepositoryError`).
- **FR-018**: The system MUST allow retrieving repository details by repository identifier.
- **FR-019**: The system MUST allow listing all repositories associated with a given project identifier.
- **FR-020**: The system MUST return an HTTP 404 Not Found error when accessing a repository identifier that does not exist.
- **FR-020a**: The system MUST allow deleting an unanalyzed repository via `DELETE /api/v1/repositories/{repository_id}`:
  - If `last_analysis_run_id` is null, the repository record is deleted from PostgreSQL, returning HTTP 204 No Content.
  - If `last_analysis_run_id` is not null (repository has linked analysis runs), the system MUST reject deletion with HTTP 409 Conflict (`RepositoryInUseError`).

#### Repository Connectivity Validation & Git Abstraction
- **FR-021**: The system MUST provide an explicit endpoint and domain operation to validate repository connectivity on demand.
- **FR-022**: The system MUST define a domain interface (`GitProvider` protocol) for Git interactions, decoupling business logic from concrete Git tools (e.g., Git CLI, GitPython, pygit2). In F01, this protocol defines targeted probe and discovery operations:
  - `validate_local(path: Path) -> ConnectionValidationResult`: Inspects local filesystem path, confirms valid Git directory or bare repository, and resolves default branch.
  - `validate_remote(url: str, timeout_seconds: float = 10.0) -> ConnectionValidationResult`: Queries remote Git references without cloning files, validating reachability and resolving default branch.
  - `detect_default_branch(location: str, repo_type: RepositoryType) -> str | None`: Resolves the default branch name deterministically from HEAD reference.
  - `list_remote_references(url: str, timeout_seconds: float = 10.0) -> list[str]`: Lists available remote branch/tag reference names.
  *(The protocol MUST NOT declare stubbed or unimplemented methods for cloning, revision checkout, or diff extraction in F01, upholding Constitution §XVII. F02 and F04 will incrementally extend the protocol or provide dedicated workspace protocols when their implementation phases begin).*
- **FR-023**: For `LOCAL` repositories, connectivity validation MUST verify that the filesystem path exists, is accessible by the application process, and contains a valid Git repository structure (`.git` directory or bare Git repository files).
- **FR-024**: For `REMOTE` repositories, connectivity validation MUST execute a non-destructive reference query (e.g., remote reference discovery / probe) to confirm network reachability and access without cloning the repository working tree.
- **FR-025**: Upon successful connectivity validation, the system MUST update repository `status` to `CONNECTED`, record `last_validated_at` timestamp, clear `last_error`, and update `default_branch` if resolved from the probe.
- **FR-026**: Upon unsuccessful connectivity validation, the system MUST update repository `status` to `ERROR`, record `last_validated_at` timestamp, store a sanitized, human-readable error summary in `last_error`, and return a 200 OK with the validation report (indicating `is_connected: false` and the diagnostic failure reason).
- **FR-027**: Connectivity validation MUST NOT synthesize or fabricate default branch names or repository metadata if they cannot be deterministically verified from the repository.
- **FR-028**: Remote connectivity checks MUST enforce a strict timeout (maximum 10 seconds) to prevent hanging requests.

#### API Endpoints & Contracts
- **FR-029**: The system MUST expose the following RESTful API endpoints under `/api/v1`:
  - `POST /api/v1/projects`: Create a project
  - `GET /api/v1/projects`: List projects (with query params `limit`, `offset`, `status`)
  - `GET /api/v1/projects/{project_id}`: Retrieve project details
  - `POST /api/v1/projects/{project_id}/archive`: Archive a project
  - `POST /api/v1/projects/{project_id}/activate`: Reactivate an archived project
  - `POST /api/v1/projects/{project_id}/repositories`: Register a repository to a project
  - `GET /api/v1/projects/{project_id}/repositories`: List all repositories for a project
  - `GET /api/v1/repositories/{repository_id}`: Retrieve repository details by repository ID
  - `DELETE /api/v1/repositories/{repository_id}`: Delete an unanalyzed repository
  - `POST /api/v1/repositories/{repository_id}/validate`: Trigger repository connectivity validation
- **FR-030**: All API request and response bodies MUST use strongly typed Pydantic models with explicit field descriptions and validation constraints.
- **FR-031**: All timestamps in API responses MUST conform to ISO 8601 in UTC (`YYYY-MM-DDTHH:MM:SSZ`).
- **FR-032**: All error responses MUST follow a standardized JSON envelope containing `error_code`, `message`, and optional `details` dictionary.

#### Error Handling & Validation
- **FR-033**: The system MUST define domain-specific exceptions mapped to appropriate HTTP status codes:
  - `ProjectNotFoundError` → HTTP 404
  - `ProjectAlreadyExistsError` → HTTP 409
  - `ProjectArchivedError` → HTTP 409
  - `RepositoryNotFoundError` → HTTP 404
  - `DuplicateRepositoryError` → HTTP 409
  - `RepositoryInUseError` → HTTP 409
  - `InvalidRepositoryLocationError` → HTTP 422
  - `RepositoryInaccessibleError` → Returned in validation payload with `status: ERROR`
  - `UnsupportedRepositoryTypeError` → HTTP 422
  - `DatabasePersistenceError` → HTTP 500
- **FR-034**: The system MUST validate repository locations at registration:
  - Local paths must be non-empty strings without forbidden null bytes.
  - Remote URLs must use valid `http://`, `https://`, or `ssh://` schemes, or standard SCP-style SSH syntax (`git@host:org/repo.git`).
  - Remote URLs containing embedded passwords, tokens, or basic-auth credentials (e.g., `https://user:pass@host` or `user:pass@host:repo`) MUST be rejected with HTTP 422 Unprocessable Entity. Ambient SSH usernames without passwords (e.g., `git@host:...`) are permitted.

---

### Non-Functional Requirements

#### Persistence & Architecture
- **NFR-001**: PostgreSQL MUST be the authoritative source of application state for all projects and repositories.
- **NFR-002**: Database schema changes for projects and repositories MUST be implemented exclusively via Alembic migration scripts. Direct SQL mutations outside migrations are prohibited.
- **NFR-003**: Persistence code MUST utilize SQLAlchemy 2.x async session management via the existing `DatabaseGateway` abstraction.
- **NFR-004**: F01 MUST NOT execute any write operations, create node labels, or establish relationship edges in Neo4j.
- **NFR-005**: Architecture MUST follow the strict 5-layer onion architecture established in Phase 0: domain entities must contain zero framework or I/O imports; API layer interacts with services and interfaces.

#### Security & Secret Isolation
- **NFR-006**: The system MUST NOT persist repository credentials, access tokens, or passwords in PostgreSQL. Private repository operations MUST authenticate exclusively via ambient host environment configuration (host SSH keys/agent or system Git credential helpers).
- **NFR-007**: Structured logs MUST NOT contain plaintext credentials, private keys, or personal access tokens.
- **NFR-008**: Local filesystem validation MUST restrict repository access to allowed filesystem boundaries when configured in multi-user or hosted environments to prevent directory traversal.

#### Observability & Structured Logging
- **NFR-009**: All project and repository operations MUST emit structured log events using `structlog` containing `project_id`, `repository_id` (where applicable), `event`, and `timestamp`.
- **NFR-010**: Failed connectivity checks MUST be logged at `WARNING` level with failure diagnostic reasons (with credentials redacted).

#### Deterministic Testability
- **NFR-011**: All unit, API, and service tests MUST execute deterministically without connecting to live external Git hosting platforms (e.g., GitHub, GitLab) or external networks.
- **NFR-012**: Local Git validation tests MUST use temporary, deterministic local Git repository fixtures generated in test setup.
- **NFR-013**: Remote Git validation tests MUST use test doubles / mocks implementing the `GitProvider` protocol to simulate reachable and unreachable remote scenarios.
- **NFR-014**: The test suite MUST achieve minimum 80% line and branch test coverage across all new F01 modules.

---

### Key Entities

```
┌────────────────────────────────────────────────────────┐
│                        Project                         │
├────────────────────────────────────────────────────────┤
│ id: UUIDv4 [PK]                                        │
│ name: String(100) [Unique, Indexed]                    │
│ description: Text [Nullable]                           │
│ status: ProjectStatus (ACTIVE | ARCHIVED)              │
│ created_at: DateTime (UTC)                             │
│ updated_at: DateTime (UTC)                             │
└──────────────────────────┬─────────────────────────────┘
                           │ 1
                           │
                           │ has many
                           │
                           ▼ *
┌────────────────────────────────────────────────────────┐
│                       Repository                       │
├────────────────────────────────────────────────────────┤
│ id: UUIDv4 [PK]                                        │
│ project_id: UUIDv4 [FK -> Project.id, Indexed]         │
│ type: RepositoryType (LOCAL | REMOTE)                  │
│ location: String(500)                                  │
│ default_branch: String(100) [Nullable]                 │
│ status: RepositoryStatus (REGISTERED|CONNECTED|ERROR)  │
│ last_error: Text [Nullable]                            │
│ last_validated_at: DateTime [Nullable]                 │
│ last_analysis_run_id: UUIDv4 [Nullable]               │
│ created_at: DateTime (UTC)                             │
│ updated_at: DateTime (UTC)                             │
├────────────────────────────────────────────────────────┤
│ CONSTRAINT uq_project_location (project_id, location)  │
└────────────────────────────────────────────────────────┘
```

#### Entity Details

- **`Project`**: Represents an organizational workspace grouping software repositories under analysis.
  - Lifecycle: `ACTIVE` ↔ `ARCHIVED` (non-destructive archival and reactivation). While `ARCHIVED`, mutations and new repository registrations are prohibited.
- **`ProjectStatus`**: Enumeration of project states:
  - `ACTIVE`: Active project eligible for repository registration, connectivity validation, and future analysis.
  - `ARCHIVED`: Archived project preserved for historical reference; read-only.
- **`Repository`**: Represents a software code repository registered within a project.
  - Relationship: Belongs to exactly one `Project` (1-to-many). Unique per `(project_id, normalized_location)`. Distinct projects can independently register the same Git repository without state collision.
  - Deletion: Can be unregistered/deleted via `DELETE /api/v1/repositories/{id}` only when unanalyzed (`last_analysis_run_id` is null). Deletion is blocked once linked to analysis runs.
- **`RepositoryType`**: Enumeration of supported repository source kinds:
  - `LOCAL`: Filesystem directory located on the local host.
  - `REMOTE`: Git URL located on a remote Git host (HTTPS/SSH).
- **`RepositoryStatus`**: Enumeration of repository operational connectivity states:
  - `REGISTERED`: Repository has been registered but connectivity has not yet been validated.
  - `CONNECTED`: Connectivity validation succeeded; repository is verified and reachable.
  - `ERROR`: Connectivity validation failed; diagnostic error retained in `last_error`.
- **`GitProvider` (Protocol)**: Abstract interface defining Git boundary probe operations in F01 (incrementally extended in F02/F04):
  - `validate_local(path: Path) -> ConnectionValidationResult`
  - `validate_remote(url: str, timeout_seconds: float = 10.0) -> ConnectionValidationResult`
  - `detect_default_branch(location: str, repo_type: RepositoryType) -> str | None`
  - `list_remote_references(url: str, timeout_seconds: float = 10.0) -> list[str]`
- **`ConnectionValidationResult` (Value Object)**: Immutable result object containing:
  - `is_connected: bool`
  - `detected_branch: str | None`
  - `error_message: str | None`
  - `latency_ms: float`

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can create a project and receive the full persisted record in under 500 milliseconds under standard operational conditions.
- **SC-002**: 100% of invalid repository URLs, non-existent filesystem paths, and malformed identifiers produce deterministic, actionable error messages with zero unhandled 500 server crashes.
- **SC-003**: 100% of repository access credentials, personal tokens, or passwords embedded in remote URLs are masked in stored data, API payloads, and log lines.
- **SC-004**: The complete test suite for project and repository management passes deterministically with 0 external network requests, utilizing local fixtures and provider test doubles.
- **SC-005**: 100% of newly registered repositories remain in an unanalyzed state, confirming zero premature AST parsing or graph database mutations prior to explicit F02 analysis invocations.
- **SC-006**: A user can register at least 20 distinct repositories under a single project, and retrieve the full repository list in under 500 milliseconds.

---

## Assumptions

- **Persistence Layer**: PostgreSQL 16+ is running and accessible via the existing Phase 0 `DatabaseGateway` and async SQLAlchemy engine.
- **Alembic Migrations**: All schema updates for `projects` and `repositories` tables will be managed via migration `0002_project_repository.py`.
- **Local Filesystem Permissions**: In local deployment mode, the TRACE backend process has read access to local repository paths configured by the user.
- **Git Availability**: The local environment has access to standard Git CLI or a compatible pure-Python Git library for reference probing without external dependencies.
- **Remote Access Scope**: Remote repository connectivity checks verify Git reference reachability (e.g. `git ls-remote` probe); full repository cloning is deferred to F02 when an analysis run is explicitly initiated.
- **Single-Tenant Foundation**: Projects are managed within a single-tenant or internal team model without user-level authentication in this phase, matching Phase 0 architecture. User authorization layers may wrap these endpoints in subsequent security phases.
