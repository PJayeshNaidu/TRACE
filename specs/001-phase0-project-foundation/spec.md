# Feature Specification: TRACE Phase 0 — Project Foundation

**Feature Branch**: `001-phase0-project-foundation`

**Created**: 2026-09-25

**Status**: Draft

---

## Overview

Phase 0 establishes a clean, runnable, testable engineering foundation for the TRACE platform
(Transformation Risk Analysis & Change Evaluation). It does not implement any TRACE intelligence
feature (F01–F10). Its sole purpose is to create the structural, configuration, connectivity,
and quality scaffolding that every subsequent phase will depend upon.

A developer who completes Phase 0 should be able to:

- Clone the repository and follow documented instructions to run the system locally.
- Verify that the application starts and returns a healthy status response.
- Execute the test suite and see all tests pass without connecting to any live external service.
- Understand where every future concern (database, graph, LLM, API, agents) will live
  in the project structure.

---

## Clarifications

### Session 2026-09-25

- Q: Which dependency management tool should TRACE use for the Python backend? → A: `uv` + `pyproject.toml` + `uv.lock`
- Q: Which Python version should TRACE target as its minimum required runtime? → A: Python 3.12
- Q: Which top-level backend project layout should TRACE adopt for the Python source code? → A: `src/` layout — `backend/src/trace/` (PyPA-recommended)
- Q: Which ORM and database migration stack should TRACE use for the PostgreSQL relational layer? → A: SQLAlchemy 2.x (async) + `asyncpg` driver + Alembic migrations
- Q: Which linting and type-checking toolchain should TRACE enforce for FR-030 static analysis? → A: `ruff` (lint + format) + `mypy` (type checking)
- Q: Gap CHK039 — Health endpoint route → A: `GET /health`, exposed by the FastAPI router, returns `HealthStatus`, no authentication required
- Q: Gap CHK042 — HTTP status semantics for health states → A: healthy → HTTP 200; any degraded/unreachable dependency → HTTP 503; body always conforms to `HealthStatus` schema
- Q: Gap CHK044 — Application version source in `HealthStatus` → A: populated from installed package metadata (`importlib.metadata`) using the canonical `pyproject.toml` version; never hardcoded; returns `"unknown"` if metadata is unavailable rather than raising an exception
- Q: Gap CHK058 — Test coverage threshold → A: 80% minimum overall (line + branch) enforced by `pytest-cov` via the designated Phase 0 release gate command (`--cov-fail-under=80`); intermediate/default test runs measure coverage without failing solely for sub-80% coverage; future phases may set a stricter threshold
- Q: Gap CHK062 — Container health check → A: backend container MUST define a healthcheck polling `GET /health`; PostgreSQL MUST define a native connectivity probe (`pg_isready`); Neo4j MUST define a verified image-native healthcheck using `cypher-shell`
- Q: Gap CHK063 — Service startup order → A: backend MUST declare `depends_on` PostgreSQL and Neo4j with `condition: service_healthy`; simple `depends_on` without health condition is insufficient
- Q: Gap CHK074 — External code transmission → A: source code MUST NOT be transmitted to external LLM/provider by default; requires explicit opt-in via named config flag; every transmission event MUST be logged at WARNING level with provider and content-length/file-count (never content itself); secrets and prohibited values are never transmitted regardless of config
- Q: Gap CHK090 — `.env.example` bidirectional completeness → A: (a) every app-consumed env var MUST appear in `.env.example` with a safe placeholder; (b) every `.env.example` entry MUST be consumed or annotated as optional/dev-only; (c) `.env.example` MUST contain no real credentials

### Engineering Decisions (no human input required)

The following were resolved by the engineering agent from repository evidence, the TRACE
master specification, and the project constitution:

- **Existing repository state**: Confirmed empty of application code (single initial commit,
  documentation and Spec Kit only). No existing conventions conflict with the proposed structure.
- **Configuration mechanism**: `pydantic-settings` — the standard typed settings library for
  FastAPI applications; reads from environment variables and `.env` files with validation.
- **Structured logging library**: `structlog` — the dominant structured logging library for
  Python; produces JSON or key-value output and integrates cleanly with the named fields
  defined in FR-032.
- **Neo4j driver**: Official `neo4j` Python driver (async session support) — the only
  production-grade driver for Neo4j, implementing the Bolt protocol. The graph gateway
  abstraction wraps it to maintain replaceability per Constitution §XIV.
- **Test framework**: `pytest` + `pytest-asyncio` (async test support) + `httpx` (ASGI
  test client for FastAPI) — the standard combination for testing async FastAPI applications.
  `pytest-cov` for coverage reporting and enforcement.
- **OpenRouter integration boundary**: An `httpx`-based async HTTP client wrapped in the
  OpenRouter adapter module. No OpenRouter SDK is used; the adapter speaks plain HTTP to
  the OpenRouter completions endpoint, maintaining full abstraction-layer independence.
- **LLM provider failure representation**: A structured `LLMResponse` with a discriminated
  union of success / configuration-error / provider-error / timeout-error states. The
  abstraction never raises unhandled exceptions into the calling layer.
- **Streamlit and frontend scaffolding**: Confirmed out of scope for Phase 0. No frontend
  directory, no Streamlit dependency. A placeholder `frontend/` directory may be created
  with only a `README.md` to document its intended future purpose.
- **LangGraph**: Declared as a project dependency in `pyproject.toml` for future agent
  workflow use. No LangGraph agent workflows are implemented in Phase 0.
- **External transmission default**: The `LLM_ENABLE_EXTERNAL_TRANSMISSION` flag defaults
  to `false` (disabled) when absent or unset. The system must never transmit source code
  to an external provider in an unconfigured state.

---

## User Scenarios & Testing

### User Story 1 — Developer Onboards and Verifies the System Runs (Priority: P1)

A developer joins the TRACE project for the first time. They follow the setup documentation,
configure their environment using the provided example file, install dependencies, start the
backend service, and confirm it is healthy by checking a well-known endpoint. They can do
this without access to any external paid service.

**Why this priority**: Every subsequent development action depends on a runnable system.
If onboarding fails, no other work can proceed.

**Independent Test**: A developer with no prior TRACE context can follow the README,
start the backend, and receive a successful health response within 30 minutes.

**Acceptance Scenarios**:

1. **Given** a freshly cloned repository with no prior setup, **When** the developer copies
   `.env.example` to `.env`, fills in local database credentials, and starts the backend,
   **Then** the backend starts without errors and is reachable.

2. **Given** the backend is running with all dependencies healthy, **When** `GET /health`
   is called, **Then** the response is HTTP 200 with a `HealthStatus` body confirming all
   services are operational.

3. **Given** a missing or misconfigured required environment variable, **When** the backend
   attempts to start, **Then** it fails with a clear, actionable error message identifying
   the missing variable — it does not start in a silently broken state.

---

### User Story 2 — Developer Runs the Test Suite Deterministically (Priority: P2)

A developer makes a change to the foundation and wants to verify correctness before
committing. They run the test suite and receive a deterministic pass/fail result without
needing a live database, graph store, or LLM service.

**Why this priority**: Deterministic testing is a non-negotiable foundation requirement
(Constitution §VII). Without it, no reliable development iteration is possible.

**Independent Test**: Running the test suite command in a freshly checked-out environment
(with only local tooling installed) produces a complete pass/fail result within 2 minutes,
including coverage enforcement.

**Acceptance Scenarios**:

1. **Given** a developer has installed project dependencies but has not started any external
   service, **When** they execute the unit test suite command, **Then** all unit tests
   pass and no test fails due to a missing external connection.

2. **Given** a test that verifies configuration loading, **When** a required environment
   variable is absent, **Then** the test asserts that the configuration layer raises a
   descriptive error — the test itself passes.

3. **Given** a test that verifies the LLM abstraction layer, **When** a simulated provider
   failure is injected, **Then** the abstraction layer reports a structured failure and the
   test passes — no live LLM call is made.

4. **Given** a test that verifies the health endpoint, **When** `GET /health` is called
   against the running test application, **Then** the response matches the `HealthStatus`
   schema with the correct HTTP status code and the test passes.

5. **Given** the test suite runs to completion, **When** the Phase 0 release gate test command
   is executed with coverage enforcement (`--cov-fail-under=80`), **Then** overall coverage
   is at or above 80% and the command exits with code 0. If coverage falls below 80%,
   the release gate command exits with a non-zero code. (Default development test invocations
   measure coverage without failing solely due to incomplete intermediate implementation.)

---

### User Story 3 — Developer Understands the Architecture Boundaries (Priority: P3)

A developer needs to implement the first TRACE feature (F01 — Project & Repository
Management) in Phase 1. Before writing a single line of feature code they need to understand
where it belongs, what patterns to follow, and what already exists. They read the
architecture documentation and inspect the project structure to orient themselves.

**Why this priority**: Without clear boundaries and documentation, each Phase 1+ developer
will make incompatible structural choices that create accumulating technical debt.

**Independent Test**: A developer unfamiliar with TRACE can identify the correct location
for any of the following — a new API endpoint, a new database entity, a new domain model,
a new LLM call — by reading only the project documentation and inspecting the directory
structure.

**Acceptance Scenarios**:

1. **Given** a developer reads the local setup documentation, **When** they look for
   instructions on environment variables, running tests, starting the backend, and Docker
   usage, **Then** all four topics are covered with accurate, step-by-step instructions.

2. **Given** a developer inspects the project directory, **When** they need to locate the
   appropriate layer for API routes, domain models, infrastructure adapters, and
   configuration, **Then** each concern maps unambiguously to a distinct directory.

3. **Given** a developer reads the LLM configuration documentation, **When** they need to
   understand how to select a different model or switch providers, **Then** the documentation
   explains the configuration keys and the free-first model policy without referring to a
   specific paid provider as the default.

---

### User Story 4 — Operator Starts the Local Development Environment via Docker (Priority: P4)

A developer or operator wants to run the full local development stack (backend, relational
database, graph database) using a single command without installing each service individually.

**Why this priority**: Local environment consistency prevents "works on my machine"
problems and is required for integration test scenarios.

**Independent Test**: On a machine with only the container runtime installed, executing the
documented compose command starts the required services and the backend becomes reachable.

**Acceptance Scenarios**:

1. **Given** a machine with only the container runtime and the project repository,
   **When** the documented compose command is executed, **Then** the backend, relational
   database, and graph database services start in dependency order — infrastructure
   services first, backend only after they report healthy.

2. **Given** the compose environment is running with all services healthy, **When**
   `GET /health` is called, **Then** it returns HTTP 200 with a `HealthStatus` body
   reflecting the connectivity status of both database services.

3. **Given** the graph database is not running or not configured, **When** `GET /health`
   is called, **Then** the response body clearly distinguishes between "not configured",
   "configured but unreachable", and "configured and reachable" — and the HTTP status
   code is 503 when any required service is unavailable.

---

### Edge Cases

- What happens when all required environment variables are present but the database is
  unreachable? The application must start and `GET /health` must return HTTP 503 with
  a `HealthStatus` body reporting degraded status — the application must not crash on startup.
- What happens when the graph database is not configured? The health endpoint must return
  the `not_configured` state for that service — not `unreachable`. The HTTP status code
  returned depends on whether Neo4j is a required service; if it is optional in Phase 0,
  its absence must not produce a 503.
- What happens when an LLM provider API key is absent? The abstraction layer must return
  a `ConfigurationError` `LLMResponse` — it must not raise an unhandled exception.
- What happens when a secret value is accidentally set to an empty string? The configuration
  layer must treat an empty string as absent for required fields and report the variable missing.
- What happens when the test suite is run without any environment file? The tests must not
  fail with unhandled environment errors; configuration tests must validate the absent-variable
  condition as a first-class scenario.
- What happens when static analysis or type checking is run on the codebase? Both `ruff`
  and `mypy` must produce zero violations.
- What happens when `importlib.metadata.version("trace")` cannot find the installed package?
  The `HealthStatus.version` field must return `"unknown"` rather than raising an exception;
  this must be tested with a mock.
- What happens when `LLM_ENABLE_EXTERNAL_TRANSMISSION` is absent from the environment?
  The system must treat this as `false` — external source-code transmission must be disabled
  by default and must never occur in an unconfigured state.
- What happens if source code is present in an LLM request payload? If external transmission
  is disabled, the request must be rejected before it reaches any HTTP client, and the
  rejection must be logged. This is a security gate, not a best-effort advisory.

---

## Requirements

### Functional Requirements

**Repository Structure**

- **FR-001**: The repository MUST have a documented top-level directory structure that
  separates backend source code, tests, infrastructure configuration, documentation,
  and specifications into distinct, named directories. The backend package MUST use the
  `src/` layout (`backend/src/trace/`) to enforce clean import boundaries.

- **FR-002**: The repository MUST NOT contain source code implementing any F01–F10
  TRACE feature at the end of Phase 0.

**Backend Application**

- **FR-003**: The backend application MUST start successfully when all required
  environment variables are present and correctly formatted.

- **FR-004**: The backend application MUST fail at startup with a descriptive error
  message when any required environment variable is absent or invalid.

- **FR-005**: The backend MUST expose a health check endpoint (defined in FR-039) that
  returns a structured `HealthStatus` response (defined in FR-040 and Key Entities)
  including at minimum: overall application status, relational database connectivity
  status, and graph database connectivity status.

- **FR-006**: The health endpoint MUST NOT expose secret values, credentials, raw
  connection strings, or any value from the prohibited categories defined in FR-033.

- **FR-007**: The backend MUST be startable locally without a container runtime
  (i.e., native process execution must be documented and supported for development).

**Configuration**

- **FR-008**: All application configuration MUST be supplied through environment variables.
  No configuration value MUST be hardcoded in source files. Configuration MUST be loaded
  through a typed settings object (`ApplicationConfig`) that validates all values at startup
  using `pydantic-settings`. An empty string MUST be treated as absent for required fields.

- **FR-009**: A `.env.example` file MUST exist in the repository root satisfying the
  bidirectional completeness constraint defined in FR-046.

- **FR-010**: A `.env` file containing real credentials MUST NOT be committed to the
  repository. The repository ignore configuration MUST list `.env` explicitly to prevent
  accidental commitment.

- **FR-011**: The configuration system MUST support at minimum the following named
  variables: `DATABASE_URL` (PostgreSQL), `NEO4J_URI`, `NEO4J_USERNAME`,
  `NEO4J_PASSWORD`, `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL`,
  `LLM_DEFAULT_MODEL`, `LLM_REASONING_MODEL`, `LLM_FAST_MODEL`,
  `LLM_FALLBACK_MODELS` (comma-separated list).

- **FR-012**: The configuration system MUST also define named slots for:
  `VECTOR_STORE_URL` (vector store, optional), `APP_ENV`
  (application environment: `development` / `production` / `test`), `LOG_LEVEL`
  (valid values: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`),
  `LLM_ENABLE_EXTERNAL_CALLS` (boolean flag to permit or block live LLM calls),
  and `LLM_ENABLE_EXTERNAL_TRANSMISSION` (boolean flag to permit or block sending
  source-code content to external providers — see FR-045).

- **FR-013**: The default value for `LLM_DEFAULT_MODEL` MUST reference a freely available
  open-weight model (specifically `mistralai/mistral-7b-instruct:free` on OpenRouter's free tier).
  The application default MUST serve as a safe, free fallback when the environment variable
  is unset, while setting `LLM_DEFAULT_MODEL` MUST override the application default without
  source-code modification. Paid or restricted models MUST require explicit configuration by the
  operator. The model name MUST never be hardcoded in business logic.

**LLM Abstraction**

- **FR-014**: The codebase MUST define an `LLMProvider` interface (abstract base class or
  Protocol) that separates application and agent logic from any specific LLM vendor.
  All LLM interactions in the codebase MUST flow through this interface.

- **FR-015**: The abstraction MUST define at minimum: an `LLMProvider` interface with
  text-completion and embedding-generation operations; an `LLMConfig` configuration object;
  a `ModelConfig` object; and an `LLMResponse` type with a discriminated union of
  `Success`, `ConfigurationError`, `ProviderError`, and `TimeoutError` states.

- **FR-016**: Application and domain code MUST import and call only the `LLMProvider`
  interface and `LLMResponse` type. No code outside the designated adapter module(s) MUST
  import any vendor-specific SDK, HTTP client binding, or vendor URL.

- **FR-017**: The codebase MUST include a concrete OpenRouter provider adapter that
  implements `LLMProvider` using a plain `httpx` async HTTP client. This adapter is the
  only file permitted to contain the OpenRouter base URL, endpoint paths, and API key
  references. The domain layer MUST have no knowledge of OpenRouter-specific details.

- **FR-018**: When an LLM provider is not configured (`LLM_ENABLE_EXTERNAL_CALLS` is
  `false` or the API key is absent) or not reachable, the abstraction MUST return the
  appropriate `LLMResponse` error state. It MUST NOT raise an unhandled exception into
  the calling layer.

**Relational Database**

- **FR-019**: The codebase MUST define a `DatabaseGateway` boundary using a SQLAlchemy
  2.x async engine with the `asyncpg` driver. All relational persistence operations in
  later phases MUST flow through an async session context manager provided by this gateway.
  Unit tests MUST substitute an in-memory SQLite engine via the same interface.

- **FR-020**: The codebase MUST include Alembic configured for the SQLAlchemy async engine.
  The initial Alembic environment (`alembic/` directory, `env.py`, and a baseline
  migration) MUST be present. Schema changes in all phases MUST use Alembic migration
  scripts; direct schema mutation is prohibited.

- **FR-021**: The `GET /health` endpoint MUST accurately report PostgreSQL reachability
  by executing a lightweight connectivity probe (e.g., `SELECT 1`) at request time and
  reflecting the actual result in the `HealthStatus` response.

- **FR-022**: No domain-specific database tables or entities (projects, analysis_runs,
  etc.) need to exist in Phase 0. Only the Alembic environment and connectivity
  infrastructure are required.

**Graph Database**

- **FR-023**: The codebase MUST define a `GraphGateway` boundary that wraps the official
  `neo4j` async Python driver. All graph database operations in later phases MUST flow
  through this gateway. The gateway MUST expose an async session/driver context that
  callers use without direct driver imports.

- **FR-024**: The `GraphGateway` interface MUST be the sole graph-access surface. Swapping
  the underlying graph store MUST require changes only to the `GraphGateway` adapter
  implementation — no changes to any caller. This replaceability constraint is a
  non-negotiable architectural boundary (Constitution §XIV).

- **FR-025**: The `GET /health` endpoint MUST report graph database connectivity as
  exactly one of three mutually exclusive states: `not_configured` (Neo4j URI is absent
  from configuration), `reachable` (connectivity probe succeeded), or `unreachable`
  (Neo4j URI is configured but the probe failed). The health endpoint MUST NOT report
  `reachable` unless a connectivity probe actually succeeded.

- **FR-026**: No TRACE graph schema (node labels, relationship types, indexes, constraints)
  MUST exist in Phase 0. Only the `GraphGateway` connectivity boundary and health-check
  probe are required.

**API**

- **FR-039**: The backend MUST expose the health endpoint at the exact path `GET /health`
  using the FastAPI application router. The endpoint MUST be accessible without
  authentication. No other path or HTTP method MUST be treated as the health endpoint.

- **FR-040**: The `GET /health` endpoint MUST return HTTP 200 when all monitored services
  are reachable and the application is fully operational. It MUST return HTTP 503 when
  any monitored service dependency reports a degraded or unreachable state. In both cases
  the response body MUST conform to the `HealthStatus` schema.

- **FR-041**: The `version` field in the `HealthStatus` response MUST be populated at
  runtime from the installed TRACE package metadata using `importlib.metadata.version()`
  (or an equivalent stdlib mechanism), reading the canonical version declared in
  `pyproject.toml`. The version string MUST NOT be hardcoded in application source code.
  If the package metadata is unavailable (e.g., package not installed in editable mode),
  the `version` field MUST return the string `"unknown"` rather than raising an exception.

**Testing**

- **FR-027**: A test suite MUST exist covering at minimum: configuration validation
  (including required-variable absence and empty-string-as-absent), domain model
  validation (if any models exist), the `GET /health` endpoint response schema and HTTP
  status codes (200 and 503 scenarios), LLM abstraction behaviour including provider
  failure simulation (`ConfigurationError`, `ProviderError`, `TimeoutError` states),
  and the `HealthStatus.version` fallback to `"unknown"` when metadata is unavailable.

- **FR-028**: The default test run MUST complete without requiring any live external
  service. All external connections (PostgreSQL, Neo4j, LLM provider) MUST be replaced
  with in-process test doubles registered through the gateway interfaces for the default run.

- **FR-029**: Tests that require live external services MUST be marked with
  `@pytest.mark.integration` and MUST be excluded from the default test run via pytest
  configuration. The default `pytest` command MUST add `-m "not integration"` or equivalent.

- **FR-030**: Static analysis and type checks MUST be runnable as documented commands:
  `ruff check` (lint), `ruff format --check` (format), and `mypy src/` (type checking).
  All three MUST produce zero violations on the Phase 0 codebase.

- **FR-042**: The Phase 0 test suite MUST enforce a minimum overall coverage threshold of
  80% (line + branch coverage as measured by `pytest-cov`). Coverage measurement is configured
  in `backend/pyproject.toml`, but the 80% minimum is enforced explicitly at the Phase 0
  verification/release gate using the designated verification command (`--cov-fail-under=80`).
  Intermediate development test invocations MUST NOT fail solely because incomplete Phase 0
  implementation has not yet reached 80% coverage. If overall coverage falls below 80% during
  the release gate execution, the command MUST exit with a non-zero status code. Future phases
  may set a stricter threshold and MUST document the change when doing so.

**Logging**

- **FR-031**: The application MUST use `structlog` for structured logging, configured to
  emit JSON output in `production` and `test` environments and human-readable key-value
  output in `development`. The log format MUST be controlled by `APP_ENV`, not hardcoded.

- **FR-032**: The logging configuration MUST support the following named context fields:
  `project_id`, `analysis_run_id`, `agent_name`, `stage`, `duration`, `status`,
  `model`, `provider`, `error`. These fields MUST be bindable as structured context,
  not interpolated into unstructured strings.

- **FR-033**: The logging layer MUST never emit API keys, passwords, tokens, credentials,
  raw connection strings, or raw LLM prompt/completion content. These categories are
  prohibited from appearing in any log output at any severity level.

**Docker / Local Development Environment**

- **FR-034**: A Docker Compose local development configuration MUST exist defining at
  minimum three services: `backend`, `postgres`, and `neo4j`. All service credentials
  MUST be read from environment variables via the Compose `environment` block — no
  hardcoded values in compose files.

- **FR-035**: The local development configuration MUST be startable with a single
  documented command (e.g., `docker compose up`). The documented command MUST be included
  in the developer setup documentation.

- **FR-036**: Container service definitions MUST read all credentials from environment
  variables. Hardcoded credential values in compose files or Dockerfiles are prohibited.

- **FR-043**: The `backend` service in the Docker Compose configuration MUST define a
  container-level `healthcheck` that periodically issues an HTTP request to `GET /health`
  and treats a 200 response as healthy. The `postgres` service MUST define a `healthcheck`
  using a native PostgreSQL connectivity probe (e.g., `pg_isready`). The `neo4j` service
  MUST define a container-level `healthcheck` using the verified image-native tool `cypher-shell`
  (e.g., `cypher-shell -u ${NEO4J_USERNAME:-neo4j} -p ${NEO4J_PASSWORD:-password} 'RETURN 1'`)
  to ensure database readiness without assuming external HTTP utilities (`curl`/`wget`) in
  the minimal official container image.

- **FR-044**: The `backend` service in the Docker Compose configuration MUST declare a
  `depends_on` block for both `postgres` and `neo4j` with `condition: service_healthy`.
  A `depends_on` declaration without a health condition is insufficient to satisfy this
  requirement. The backend container MUST NOT be considered started until both
  infrastructure services report a healthy state.

**Security**

- **FR-045**: Repository source-code content and file contents MUST NOT be transmitted
  to any external LLM or provider endpoint unless `LLM_ENABLE_EXTERNAL_TRANSMISSION`
  is explicitly set to `true` in the application configuration. When transmission is
  disabled (the default), any attempt to include source-code content in an outbound
  LLM request MUST be intercepted before the HTTP client sends it, and the event MUST
  be logged at `WARNING` level including the provider name and content volume (file count
  or byte count) but never the content itself. Secrets, credentials, and any value from
  the prohibited categories in FR-033 MUST never be transmitted regardless of the value
  of `LLM_ENABLE_EXTERNAL_TRANSMISSION`. This requirement applies in Phase 0 even though
  no source-code analysis is performed; it establishes the architectural gate that later
  phases will rely upon.

**Configuration Completeness**

- **FR-046**: The `.env.example` file and the application configuration MUST satisfy a
  bidirectional completeness constraint: (a) every environment variable consumed by
  `ApplicationConfig` MUST have a corresponding entry in `.env.example` with a safe
  placeholder or example value and a one-line comment explaining the variable's purpose;
  (b) every entry in `.env.example` MUST either be consumed by `ApplicationConfig` or
  annotated with a comment explicitly stating it is optional or development-only;
  (c) `.env.example` MUST contain no real credentials, tokens, API keys, or passwords —
  only clearly identifiable placeholder values (e.g., `your-api-key-here`,
  `postgresql://user:password@localhost:5432/trace`).

**Technology Contracts**

- **FR-047**: The backend application MUST require Python ≥ 3.12 as a declared constraint
  in `pyproject.toml`. Container images used for the backend MUST use a Python 3.12 base
  image. Local development documentation MUST state the minimum Python version explicitly.

- **FR-048**: The HTTP API layer MUST be implemented using FastAPI (ASGI-compatible). All
  API routes, request body validation, response serialisation, and OpenAPI schema generation
  MUST use FastAPI's router and Pydantic model mechanisms. No other HTTP framework MUST be
  introduced in the backend.

- **FR-049**: PostgreSQL MUST serve as the sole authoritative application state store.
  No other data store — including Neo4j, any vector store, or any LLM-generated output —
  MUST be treated as the source of truth for application-level state (projects, analysis
  runs, tasks, human reviews, or any other persisted entity). LLM output is never
  authoritative project state (Constitution §I).

- **FR-050**: Neo4j MUST serve as the graph database for structural software relationships
  (to be populated in Phase 3A). Neo4j MUST NOT be used as a substitute for authoritative
  application state. The architectural distinction between PostgreSQL (application state)
  and Neo4j (structural intelligence graph) MUST be documented and maintained across all
  phases without exception.

---

### Key Entities

- **ApplicationConfig**: The central typed settings object derived from environment
  variables at startup via `pydantic-settings`. All fields are validated at load time.
  An empty string is treated as absent for required fields. Raises an explicit, descriptive
  error if required values are absent or invalid. Contains no hardcoded defaults for
  secret values. Includes `LLM_ENABLE_EXTERNAL_TRANSMISSION` as a required boolean field
  with a default of `false`.

- **HealthStatus**: The structured response returned by `GET /health`. Contains:
  `status` (overall: `healthy` | `degraded`), `version` (string populated from
  installed package metadata via `importlib.metadata`; `"unknown"` if unavailable),
  `services` (map of service name to connectivity state). The `services` map MUST include
  at minimum `postgres` and `neo4j`. Neo4j connectivity state is one of: `not_configured`,
  `reachable`, `unreachable`. Contains no secrets or connection strings.

- **LLMProvider** *(interface)*: The abstraction through which all LLM interactions flow.
  Defines at minimum: a `complete(prompt: str, model: ModelConfig) -> LLMResponse` operation
  and an `embed(text: str, model: ModelConfig) -> LLMResponse` operation. Both operations
  return `LLMResponse` and never raise unhandled exceptions.

- **LLMConfig**: A configuration object describing how to connect to a provider (base URL,
  API key reference, timeout in seconds, retry count). Contains no hardcoded credentials.

- **ModelConfig**: A configuration object describing which model to use for a given role
  (default, reasoning, fast, fallback list). All values are configuration-driven. The
  default role MUST reference a freely available model.

- **LLMResponse**: A structured result from a provider call. Uses a discriminated union
  with exactly four states: `Success` (contains response content and token usage),
  `ConfigurationError` (provider not configured or API key absent),
  `ProviderError` (provider returned an error response),
  `TimeoutError` (request exceeded configured timeout). Callers pattern-match on the state
  rather than catching exceptions.

- **DatabaseGateway** *(interface)*: The boundary through which all relational database
  interactions flow. Exposes an async SQLAlchemy session context manager. Backed by an
  async SQLAlchemy engine with `asyncpg` driver in production/development, and an
  in-memory SQLite engine in unit tests.

- **GraphGateway** *(interface)*: The boundary through which all graph database interactions
  flow. Exposes an async Neo4j driver/session context. Backed by the official `neo4j`
  async driver in production/development, and a test double in unit tests. The interface
  MUST expose a `health_check() -> GraphConnectivityState` operation used by the health
  endpoint. `GraphConnectivityState` is one of: `not_configured`, `reachable`, `unreachable`.

---

## Success Criteria

### Measurable Outcomes

- **SC-001**: A developer with no prior TRACE context can follow the setup documentation,
  configure the environment using only the provided `.env.example` file, and receive a
  successful `GET /health` HTTP 200 response within 30 minutes of cloning the repository.

- **SC-002**: The complete default unit test suite executes and passes in under 2 minutes
  on a standard developer workstation without any external service running.

- **SC-003**: `ruff check`, `ruff format --check`, and `mypy src/` each produce zero
  violations when run against the Phase 0 codebase.

- **SC-004**: The `GET /health` endpoint returns HTTP 200 when all monitored services are
  reachable and HTTP 503 when any monitored service is unavailable. The response body
  correctly reflects the actual connectivity state of both database services in 100% of
  unit test scenarios.

- **SC-005**: Zero secrets, credentials, or sensitive values appear in any committed file,
  log output, or `GET /health` response across all verified scenarios.

- **SC-006**: All Phase 0 success criteria (SC-001 through SC-009) and functional requirements
  (FR-001 through FR-050) are verifiably met and documented before Phase 0 is declared complete,
  with explicit verification commands and without fabricating implementation state. Checklist
  items assess specification and requirements quality and do not imply implementation completion.

- **SC-007**: Starting the local container environment and receiving a successful
  `GET /health` HTTP 200 response requires at most one command after environment
  configuration (e.g., `docker compose up`).

- **SC-008**: Every application layer (API, domain, infrastructure, configuration) maps
  to a distinct, named directory under `backend/src/trace/` — no layer concern bleeds
  into another directory as confirmed by code review.

- **SC-009**: The designated Phase 0 release-gate test command (`--cov-fail-under=80`)
  enforces the 80% coverage gate. The command exits with a non-zero status code when coverage
  falls below 80%. A passing test run at Phase 0 completion MUST demonstrate ≥ 80% overall
  coverage (line + branch).

---

## Assumptions

- The repository is a new project with a single initial commit containing only documentation
  and Spec Kit infrastructure; no application source code exists. No existing conventions
  conflict with the proposed structure.

- Python 3.12 is the minimum required runtime, targeting the current stable release for
  its performance improvements, typing features, and broad ecosystem compatibility.

- Dependency management uses `uv` with `pyproject.toml` and `uv.lock` for reproducible,
  fast dependency installation across local and container environments.

- The backend package follows the `src/` layout: `backend/src/trace/` is the importable
  package root, with `backend/pyproject.toml` and `backend/uv.lock` at the project level.

- The relational database is PostgreSQL, as specified in the TRACE architecture. The
  async ORM is SQLAlchemy 2.x with the `asyncpg` driver. Schema migrations are managed
  with Alembic.

- The graph database is Neo4j, as specified in the TRACE architecture. The async Neo4j
  Python driver provides the concrete implementation behind the `GraphGateway` interface.

- Application configuration is loaded through `pydantic-settings`, which reads from
  environment variables (and optionally a `.env` file) and validates all fields at
  import time.

- Structured logging uses `structlog` configured to emit JSON in production/test
  environments and human-readable key-value output in development. The log level is
  controlled by the `LOG_LEVEL` environment variable.

- The test framework is `pytest` with `pytest-asyncio` for async test support, `httpx`
  as the ASGI test client for FastAPI endpoints, and `pytest-cov` for coverage measurement
  and enforcement (80% minimum gate). Integration tests are marked with
  `@pytest.mark.integration` and excluded from the default run via pytest configuration.

- Static analysis uses `ruff` for linting and formatting (`ruff check` and
  `ruff format --check`), and `mypy` for type checking (`mypy src/`). Both are configured
  in `pyproject.toml` and must produce zero violations before Phase 0 is declared complete.

- The OpenRouter adapter uses a plain `httpx` async HTTP client to call the OpenRouter
  completions endpoint. No OpenRouter-specific SDK is introduced. The adapter is the
  only file that contains OpenRouter URL or API key references.

- External source-code transmission to LLM providers is disabled by default
  (`LLM_ENABLE_EXTERNAL_TRANSMISSION` defaults to `false`). No source-code content is
  transmitted in the Phase 0 test suite or baseline operation. The transmission gate is
  established architecturally so later phases do not need to introduce it retroactively.

- The default free LLM model is a publicly available open-weight model accessible through
  OpenRouter's free tier; the specific model name is configuration-driven and not hardcoded.

- LangGraph is declared as a project dependency in `pyproject.toml` for future agent
  workflow use. No LangGraph agent workflows are implemented in Phase 0.

- Frontend infrastructure (Streamlit, React) is explicitly out of scope for Phase 0.
  A `frontend/` directory may be created with only a `README.md` noting its future role.

- The Phase 0 database schema contains no domain tables; only the Alembic environment,
  baseline migration, and connectivity boundary are required.

- Integration tests (requiring live services) are explicitly labelled and excluded from
  the default test run; they may exist but must not block the default CI pipeline.

- The container configuration covers development use only; production deployment
  configuration is out of scope for Phase 0.

- Documentation is written in Markdown within the repository and does not require a
  separate documentation site or build tool in Phase 0.

- Neo4j is treated as optional for `GET /health` HTTP status purposes in Phase 0:
  if Neo4j URI is not configured, the health endpoint reports `not_configured` for that
  service and returns HTTP 200 (not 503), since Neo4j graph features are not functional
  until Phase 3A. If Neo4j is configured but unreachable, the endpoint returns HTTP 503.
