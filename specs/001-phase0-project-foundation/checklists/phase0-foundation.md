# Implementation Readiness Checklist: TRACE Phase 0 — Project Foundation

**Purpose**: Validate that the Phase 0 specification provides complete, clear, measurable,
and unambiguous requirements across all 13 foundation areas — with explicit coverage of
negative constraints (no fabricated state, no hard-coded secrets, no provider coupling).
**Created**: 2026-09-25
**Feature**: [spec.md](../spec.md) | [constitution.md](../../../.specify/memory/constitution.md)

**Review Ownership**: This checklist is a reviewer-owned requirements-quality review artifact.
Mark an item `[x]` only when the reviewer determines the requirements-quality criterion is
satisfied. `[x]` means the criterion has been reviewed and satisfied for requirements quality.
It does NOT mean implementation work is complete.

---

## 1. Repository Structure

- [x] CHK001 - Does the spec define a complete, named top-level directory structure with a
  distinct location for each concern (backend source, tests, infrastructure, docs, specs)?
  [Completeness, Spec §FR-001]

- [x] CHK002 - Is the `src/` layout requirement (`backend/src/trace/`) stated with enough
  precision that a reviewer could determine unambiguously whether an implementation complies?
  [Clarity, Spec §FR-001, Clarifications §Q3]

- [x] CHK003 - Does the spec explicitly prohibit F01–F10 feature code from appearing in the
  Phase 0 codebase, and is this prohibition testable (i.e., what does "not implemented" mean
  in an inspectable sense)? [Completeness, Spec §FR-002]

- [x] CHK004 - Are the boundaries between directory concerns defined precisely enough that
  a developer could determine — without ambiguity — where a new API route, domain model,
  infrastructure adapter, or configuration value belongs? [Clarity, Spec §SC-008]

- [x] CHK005 - Does the spec state whether a `frontend/` placeholder directory is required
  or optional at Phase 0, and is that decision traceable to a ratified source?
  [Completeness, Clarifications §Engineering Decisions]

---

## 2. Python / Backend Foundation

- [x] CHK006 - Is the minimum Python version requirement stated explicitly (not implied),
  and is it tied to a rationale that prevents silent drift to an incompatible version?
  [Clarity, Spec §Assumptions, Clarifications §Q2]

- [x] CHK007 - Is the dependency management tool (`uv` + `pyproject.toml` + `uv.lock`)
  specified with sufficient precision that a developer knows exactly which files to commit
  and which commands to run for installation? [Clarity, Clarifications §Q1]

- [x] CHK008 - Does the spec define the `src/` layout import boundary clearly enough
  that the distinction between "accidental import of uninstalled package" and "correctly
  installed package" can be verified during code review? [Clarity, Spec §FR-001]

- [x] CHK009 - Are the layer responsibilities within `backend/src/trace/` (api/, core/,
  domain/, infrastructure/) named and scoped so that a reviewer can identify a
  layer-boundary violation without ambiguity? [Completeness, Gap — sub-directory
  responsibilities not enumerated in spec]

- [x] CHK010 - Is there a requirement preventing application startup when the Python
  environment is below the minimum version, or is version enforcement left unspecified?
  [Coverage, Gap]

---

## 3. Configuration

- [x] CHK011 - Are all required environment variable names listed exhaustively in the spec,
  such that a developer generating `.env.example` would know exactly which variables to
  include with no guessing? [Completeness, Spec §FR-011, FR-012]

- [x] CHK012 - Is the distinction between "required" and "optional" environment variables
  stated explicitly for each named variable, or must a reviewer infer this from context?
  [Clarity, Spec §FR-008, FR-011]

- [x] CHK013 - Does the spec define the exact behavior when a required variable is set to
  an empty string — specifically that it is treated as absent — with enough precision to
  write a deterministic test? [Clarity, Spec §Edge Cases, FR-008]

- [x] CHK014 - Is the requirement that `.env` must never be committed stated as a
  verifiable condition (i.e., the ignore configuration must prevent it), not merely as
  a policy statement? [Measurability, Spec §FR-010]

- [x] CHK015 - Does the spec define what "typed validation at startup" means for
  `ApplicationConfig` with enough precision to determine when validation passes vs. fails?
  [Clarity, Spec §FR-008, Key Entities §ApplicationConfig]

- [x] CHK016 - Is the `LLM_ENABLE_EXTERNAL_CALLS` flag requirement specified with a defined
  default value and behavior when absent? [Completeness, Spec §FR-012, Gap — default not stated]

- [x] CHK017 - Are the `LLM_FALLBACK_MODELS` parsing semantics (comma-separated list)
  documented with enough clarity to determine valid vs. invalid values?
  [Clarity, Spec §FR-011]

- [x] CHK018 - Does the spec explicitly prohibit any configuration value from appearing
  as a hardcoded literal in source files, and is this constraint stated as a testable
  negative requirement? [Completeness, Spec §FR-008, Constitution §IX]

---

## 4. LLM Abstraction

- [x] CHK019 - Is the `LLMProvider` interface defined with sufficient operation signatures
  (text completion, embedding generation) that a reviewer can determine whether an
  implementation satisfies the interface without inspecting the concrete adapter?
  [Clarity, Spec §FR-014, FR-015, Key Entities §LLMProvider]

- [x] CHK020 - Does the spec define the `LLMResponse` discriminated union states
  (`Success`, `ConfigurationError`, `ProviderError`, `TimeoutError`) with enough
  precision that a test can assert the correct state is returned for each failure mode?
  [Measurability, Spec §FR-015, Key Entities §LLMResponse]

- [x] CHK021 - Is the prohibition on application/domain code importing vendor-specific
  SDK or API client modules stated as a negative constraint that can be verified by
  static analysis or code review? [Completeness, Spec §FR-016, Constitution §V]

- [x] CHK022 - Does the spec explicitly state that the OpenRouter adapter is the only
  file permitted to contain OpenRouter URL or API key references, making this a
  verifiable single-file constraint? [Clarity, Spec §FR-017, Clarifications §Engineering Decisions]

- [x] CHK023 - Is the requirement that the abstraction never raises unhandled exceptions
  into the calling layer stated as a testable contract, not merely a design intent?
  [Measurability, Spec §FR-018]

- [x] CHK024 - Does the spec define what "provider not configured" means as a distinct
  state from "provider configured but unreachable", so that tests can assert the correct
  `LLMResponse` state for each? [Clarity, Spec §FR-018, Edge Cases]

- [x] CHK025 - Is there a requirement preventing the LLM abstraction from silently
  selecting a paid or restricted model when no model is explicitly configured?
  [Completeness, Spec §FR-013, Constitution §VI — free-first mandate]

- [x] CHK026 - Does the spec require that `LLMConfig` contains no hardcoded credential
  values, and is this stated as a verifiable constraint rather than a guideline?
  [Completeness, Spec §Key Entities §LLMConfig, Constitution §IX]

---

## 5. PostgreSQL Foundation

- [x] CHK027 - Is the `DatabaseGateway` interface defined with sufficient precision that
  a reviewer can determine whether an implementation correctly exposes an async session
  context manager without inspecting the SQLAlchemy internals?
  [Clarity, Spec §FR-019, Key Entities §DatabaseGateway]

- [x] CHK028 - Does the spec state that the test double for `DatabaseGateway` uses an
  in-memory SQLite engine (or equivalent) specifically, so that tests are deterministic
  and do not depend on a live PostgreSQL instance?
  [Completeness, Spec §Key Entities §DatabaseGateway, FR-028]

- [x] CHK029 - Is the Alembic migration mechanism requirement stated with enough
  specificity that a reviewer knows what constitutes a compliant initial migration setup
  (e.g., `alembic init`, `env.py` configuration, at least one baseline migration)?
  [Clarity, Spec §FR-020]

- [x] CHK030 - Does the spec define what "connectivity boundary" means for the relational
  database in Phase 0 — specifically whether it requires a working connection pool or
  only the interface and wiring? [Clarity, Spec §FR-019, FR-022]

- [x] CHK031 - Is there an explicit requirement that no domain-specific database tables
  (projects, analysis_runs, etc.) exist in Phase 0, stated as a negative verifiable
  constraint? [Completeness, Spec §FR-022]

- [x] CHK032 - Does the spec define the health endpoint's database connectivity report
  with enough precision to determine exactly which database operations constitute a
  successful reachability check vs. a failed one? [Measurability, Spec §FR-021]

---

## 6. Neo4j Foundation

- [x] CHK033 - Is the `GraphGateway` interface defined with enough precision that a
  reviewer can determine whether an implementation is provider-agnostic without reading
  the Neo4j driver internals? [Clarity, Spec §FR-023, FR-024, Key Entities §GraphGateway]

- [x] CHK034 - Does the spec state the replaceability constraint for `GraphGateway`
  in a verifiable form — specifically that swapping the graph store requires changes
  only to the adapter file(s)? [Measurability, Spec §FR-024, Constitution §XIV]

- [x] CHK035 - Are the three graph connectivity states (`not configured`, `configured and
  reachable`, `configured but unreachable`) defined with mutually exclusive conditions,
  such that a test can assert exactly one state for each scenario?
  [Clarity, Spec §FR-025, Edge Cases]

- [x] CHK036 - Is there an explicit requirement that no TRACE-specific graph schema
  (node labels, relationship types, indexes) exists in Phase 0, stated as a testable
  negative constraint? [Completeness, Spec §FR-026]

- [x] CHK037 - Does the spec define a test double requirement for `GraphGateway` in
  the unit test context, making Neo4j non-required for the default test run?
  [Completeness, Spec §FR-028, Key Entities §GraphGateway]

- [x] CHK038 - Is the requirement that health status must not fabricate a "connected"
  state for the graph database stated as an explicit negative constraint, not merely
  implied by the accuracy requirement? [Completeness, Spec §FR-025, Constitution §XVII
  — No Fabricated Implementation State]

---

## 7. API

- [x] CHK039 - Is the health endpoint path (route) and HTTP method stated explicitly in
  the spec, or is it left to implementation discretion? [Clarity, Spec §FR-005, Gap —
  route not named in spec body]

- [x] CHK040 - Does the spec define the exact fields of the `HealthStatus` response
  (field names, types, permitted values for each status) with enough precision to write
  a schema-validation test? [Clarity, Spec §FR-005, Key Entities §HealthStatus]

- [x] CHK041 - Is the prohibition on secrets in the health response stated as a
  verifiable negative constraint — specifically naming which data categories are
  prohibited — rather than a general guideline? [Completeness, Spec §FR-006, Constitution §IX]

- [x] CHK042 - Does the spec define the application's behavior when the health endpoint
  is called and one service is degraded (e.g., DB unreachable) — specifically whether
  the HTTP response status code is 200 or a non-2xx code?
  [Completeness, Gap — HTTP status code for degraded state not specified]

- [x] CHK043 - Is there a requirement that the backend must be startable as a native
  process (without container runtime), and is this stated with enough specificity that
  the documentation can be verified complete? [Completeness, Spec §FR-007]

- [x] CHK044 - Does the spec define the application version field in `HealthStatus`
  with enough precision to determine how it is populated (e.g., from `pyproject.toml`,
  env variable, or hardcoded)? [Clarity, Key Entities §HealthStatus, Gap]

---

## 8. Logging / Observability

- [x] CHK045 - Does the spec define what "structured logging" means in an objectively
  verifiable way — specifically whether JSON output is required in production and
  key-value in development, or whether the format is environment-controlled?
  [Clarity, Spec §FR-031]

- [x] CHK046 - Are the named log fields (`project_id`, `analysis_run_id`, `agent_name`,
  `stage`, `duration`, `status`, `model`, `provider`, `error`) defined with enough
  precision to determine valid vs. missing field coverage in an implementation?
  [Completeness, Spec §FR-032]

- [x] CHK047 - Is the prohibition on logging sensitive values stated as an exhaustive
  list of prohibited categories (API keys, passwords, tokens, credentials, raw prompt
  content), making it testable by log inspection? [Clarity, Spec §FR-033, Constitution §IX]

- [x] CHK048 - Does the spec define how the log level is controlled (via `LOG_LEVEL`
  environment variable) with enough precision to know which levels are valid inputs
  and what happens when an invalid value is supplied? [Completeness, Spec §Assumptions, Gap]

- [x] CHK049 - Is there a requirement that structured log output is machine-parseable
  (e.g., valid JSON in production mode), enabling log aggregation without post-processing?
  [Measurability, Spec §FR-031]

- [x] CHK050 - Does the spec require that `analysis_run_id` and `project_id` fields
  appear in all log entries related to an analysis operation, making trace correlation
  verifiable? [Completeness, Spec §FR-032, Constitution §XI — Observability]

---

## 9. Testing

- [x] CHK051 - Does the spec enumerate the minimum test coverage areas (configuration
  validation, health endpoint schema, LLM abstraction, provider failure, env variable
  absence) with enough specificity that a reviewer can identify a missing test area?
  [Completeness, Spec §FR-027]

- [x] CHK052 - Is the "default test run" boundary defined precisely enough that it is
  clear which pytest marker (e.g., `@pytest.mark.integration`) separates unit from
  integration tests, and what the default exclusion command is?
  [Clarity, Spec §FR-028, FR-029, Clarifications §Engineering Decisions]

- [x] CHK053 - Does the spec state that test doubles (not live services) MUST replace
  external connections in the default run, in a form that can be verified by inspecting
  test fixtures — not just by observing that tests pass without services running?
  [Measurability, Spec §FR-028]

- [x] CHK054 - Is there a requirement that the LLM abstraction test must inject a
  simulated failure and assert the correct `LLMResponse` error state — not merely
  that no exception is raised? [Clarity, Spec §FR-027, User Story 2 §Scenario 3]

- [x] CHK055 - Does the spec require a test that explicitly exercises the "empty string
  treated as absent" edge case for configuration, rather than only the "variable missing"
  case? [Completeness, Spec §Edge Cases]

- [x] CHK056 - Is the 2-minute test suite execution target (SC-002) stated with enough
  precision to serve as a CI gate — specifically whether this is wall-clock time, CPU
  time, or a default pytest timeout? [Clarity, Spec §SC-002]

- [x] CHK057 - Does the spec prohibit tests from making live LLM calls in the default
  run as an explicit negative constraint, verifiable by network inspection or mock
  assertion? [Completeness, Spec §FR-028, Constitution §VII]

- [x] CHK058 - Is there a requirement that coverage reporting is configured and a
  minimum coverage threshold is defined, or is coverage left unspecified for Phase 0?
  [Completeness, Gap — coverage threshold not stated in spec]

---

## 10. Docker

- [x] CHK059 - Does the spec define which services MUST be present in the container
  development configuration (backend, PostgreSQL, Neo4j) as a verifiable minimum set,
  and are service names consistent with the documentation?
  [Completeness, Spec §FR-034]

- [x] CHK060 - Is the "single documented command" requirement (FR-035) stated with
  enough precision that the exact command can be verified in the documentation, not
  merely that some command exists? [Clarity, Spec §FR-035, SC-007]

- [x] CHK061 - Does the spec require that container service definitions read ALL
  credentials from environment variables — specifically ruling out hardcoded values in
  compose files — as a verifiable negative constraint?
  [Completeness, Spec §FR-036, Constitution §IX]

- [x] CHK062 - Is the health check integration between the container orchestration and
  the backend health endpoint specified — i.e., does the container runtime know the
  backend is healthy? [Coverage, Gap — container-level healthcheck not mentioned in spec]

- [x] CHK063 - Does the spec require `depends_on` with `condition: service_healthy` (not just service name) for the backend on both PostgreSQL and Neo4j, and explicitly state that a plain `depends_on` without health condition is insufficient? [Completeness, Spec �FR-044]

- [x] CHK064 - Is the scope of the container configuration (development only, not
  production) stated as an explicit boundary so that no production configuration
  appears in Phase 0? [Completeness, Spec §Assumptions]

---

## 11. Documentation

- [x] CHK065 - Does the spec enumerate all eight required documentation topics (local
  setup, env var reference, test suite, backend start, container usage, LLM config,
  free-first policy, architecture boundary map) as a verifiable minimum list?
  [Completeness, Spec §FR-037]

- [x] CHK066 - Is "architecture boundary map" defined with enough precision to know
  what it must contain — specifically whether it requires a directory listing, a
  prose explanation, a diagram, or all three? [Clarity, Spec §FR-038, Gap]

- [x] CHK067 - Does the spec define the free-first model policy documentation
  requirement with enough specificity to determine what "explains the free-first model
  policy" means in a reviewable sense? [Clarity, Spec §FR-037, Constitution §VI]

- [x] CHK068 - Is the "LLM configuration guide" requirement specific enough that a
  reviewer can determine whether it covers model switching, provider replacement, and
  the `LLM_ENABLE_EXTERNAL_CALLS` flag? [Completeness, Spec §FR-037]

- [x] CHK069 - Does the spec require that environment variable documentation covers
  ALL variables in `.env.example` with no undocumented variables — making completeness
  verifiable by diff? [Completeness, Spec §FR-037, FR-009, Gap]

- [x] CHK070 - Is the SC-001 onboarding time target (30 minutes) defined with enough
  supporting documentation requirements to make it achievable in practice — or is
  this a success criterion without corresponding documentation completeness requirements?
  [Consistency, Spec §SC-001]

---

## 12. Security

- [x] CHK071 - Does the spec explicitly state that `.env` must be listed in the
  repository ignore configuration as a verifiable negative constraint — not only that
  it "must not be committed"? [Measurability, Spec §FR-010]

- [x] CHK072 - Is the prohibition on secrets in committed files stated as an exhaustive,
  named list of prohibited value types (API keys, passwords, tokens, connection strings),
  making it scannable by automated tools? [Clarity, Spec §FR-010, Constitution §IX]

- [x] CHK073 - Does the spec define what "sensitive prompt content" means in the logging
  prohibition (FR-033) with enough precision to determine whether an LLM-bound message
  body qualifies? [Clarity, Spec §FR-033]

- [x] CHK074 - Is the requirement that external repository/code transmission must be
  explicit and user-configured stated as a verifiable constraint for Phase 0, or is it
  deferred to later phases where actual analysis occurs?
  [Coverage, Constitution §IX, Gap — not addressed in Phase 0 spec]

- [x] CHK075 - Does the spec require that the OpenRouter API key is never logged,
  never appears in health endpoint responses, and never appears in error messages —
  stated as three separate verifiable negative constraints?
  [Completeness, Spec §FR-006, FR-033, Constitution §IX]

- [x] CHK076 - Is the "empty string treated as absent" rule for secret values stated
  as a security requirement (preventing accidentally-blank secrets from bypassing
  validation) in addition to a configuration correctness rule?
  [Coverage, Spec §Edge Cases, FR-008]

---

## 13. Developer Experience

- [x] CHK077 - Does the spec define the `uv` installation and usage commands with enough
  specificity that a developer on a fresh machine knows the exact sequence of steps to
  reach a running backend — or is this left to the documentation requirement (FR-037)?
  [Clarity, Spec §FR-007, Clarifications §Q1, Gap — install sequence not in spec]

- [x] CHK078 - Is the `ruff` and `mypy` configuration requirement (FR-030) stated with
  enough precision to know which `pyproject.toml` sections are required and what
  "zero violations" means for a clean baseline? [Clarity, Spec §FR-030, SC-003,
  Clarifications §Q5]

- [x] CHK079 - Does the spec define a single documented command for linting and a
  single documented command for type checking, making these discoverable without
  reading source files? [Completeness, Spec §FR-030, FR-037]

- [x] CHK080 - Is the test runner command (pytest) documented with its required flags
  for the default (unit-only) run, making it reproducible without tribal knowledge?
  [Completeness, Spec §FR-028, FR-029, Clarifications §Engineering Decisions]

- [x] CHK081 - Does the spec require that the native (non-Docker) backend start command
  is documented with exact syntax — including how to activate the virtual environment
  and set environment variables — rather than only the container start command?
  [Completeness, Spec §FR-007, SC-001]

- [x] CHK082 - Is there a requirement that a developer can identify any undocumented
  environment variable by comparing the running application's loaded config with
  `.env.example` — i.e., no variable is consumed silently?
  [Completeness, Spec §FR-009, Gap]

- [x] CHK083 - Does the spec define IDE or editor tooling requirements (e.g., `.editorconfig`,
  VS Code settings), or is developer tooling consistency explicitly out of scope for
  Phase 0? [Coverage, Gap — not addressed]

---

## Negative Constraint Coverage

*This section specifically verifies that the spec's negative requirements are explicit,
testable, and unambiguous — not merely policy statements.*

- [x] CHK084 - Is the prohibition on fabricated health status (reporting "connected"
  when a service is unreachable) stated as a named requirement with a defined test
  scenario, not only as an implication of the accuracy requirement?
  [Completeness, Spec §FR-025, FR-021, Constitution §XVII]

- [x] CHK085 - Is the prohibition on hard-coded API keys in source files stated as a
  negative requirement testable by static analysis (grep / AST scan) rather than
  only by runtime observation? [Measurability, Spec §FR-008, FR-036, Constitution §IX]

- [x] CHK086 - Is the prohibition on provider-specific business logic (OpenRouter
  assumptions in domain code) stated with enough precision to identify a violation
  during code review — specifically which files or modules are the permitted boundary?
  [Clarity, Spec §FR-016, FR-017, Constitution §V]

- [x] CHK087 - Is the prohibition on silent paid-model fallback stated as a testable
  negative requirement — specifically that the system must not select a non-free model
  when the configured model is unavailable? [Completeness, Spec §FR-013, Constitution §VI]

- [x] CHK088 - Is the prohibition on live LLM calls in the default test run stated as a
  testable network-level or mock-level constraint, not only as a description of test
  setup intent? [Measurability, Spec §FR-028, Constitution §VII]

- [x] CHK089 - Is the prohibition on fake TRACE analysis results (reporting non-existent
  analysis as complete) stated as a constitution-level constraint that applies to the
  Phase 0 codebase itself — specifically to the health endpoint and any status fields?
  [Completeness, Constitution §XVII, Spec §FR-002]

- [x] CHK090 - Is there a requirement that all environment variables consumed by the
  application appear in `.env.example`, making undocumented variable consumption a
  verifiable violation? [Completeness, Spec §FR-009, Gap — bidirectional completeness
  not explicitly required]

---

## Notes

- Mark items `[x]` only after review confirms the requirement-quality criterion is satisfied
- Leave items unchecked when they still require clarification, correction, or reviewer evaluation
- `/speckit-implement` reads checklist checkbox state as a gate and must not modify markers
- `checklists/requirements.md` has a separate built-in lifecycle maintained by `/speckit-specify`
  and `/speckit-clarify` — do not conflate the two
- Items tagged `[Gap]` identify requirements areas not currently covered by the spec; these
  may require spec amendments before planning proceeds
- Items tagged `[Ambiguity]` identify requirements that exist but are insufficiently precise
  for deterministic verification
- CHK009, CHK016, CHK039, CHK042, CHK044, CHK048, CHK058, CHK062, CHK063, CHK069, CHK074,
  CHK077, CHK082, CHK083, CHK090 are `[Gap]` items — the spec does not currently address
  these. Review whether they require spec amendments before `/speckit-plan`
