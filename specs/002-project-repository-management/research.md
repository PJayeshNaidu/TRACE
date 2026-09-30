# Research: TRACE Phase 1 — Technical Decisions & Architecture Analysis

**Branch**: `002-project-repository-management` | **Date**: 2026-09-28 | **Feature**: F01 Project & Repository Management

This document records the architectural evaluations, technology decisions, and rationale for implementing TRACE Phase 1 — F01 (Project & Repository Management) on top of the Phase 0 foundation.

---

## 1. Git Execution Engine for `GitProvider`

### Decision
Use Python's native `asyncio.create_subprocess_exec` to execute the system `git` CLI with `GIT_TERMINAL_PROMPT=0` inside an asynchronous `SubprocessGitProvider` adapter.

### Rationale
- **Zero Third-Party Dependencies**: Avoids introducing heavy C-extension dependencies (such as `pygit2`) or synchronous blocking libraries (such as `GitPython`) that would bloat `pyproject.toml`.
- **True Asynchronous Non-Blocking Execution**: `asyncio.subprocess` integrates natively with FastAPI's event loop, preventing thread pool exhaustion during remote probes.
- **Strict Process Isolation & Timeouts**: `asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)` provides hard kernel-level timeout enforcement (default 10s), ensuring hanging remote servers never block application workers.
- **Terminal Prompt Suppression**: Passing `env={"GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "echo"}` guarantees that if a private remote repository requires credentials not present in the ambient environment, Git immediately exits with return code 128 rather than hanging on stdin prompting for user/password.
- **Deterministic Testing**: Testing requires only mocking the `GitProvider` Protocol or pointing to temporary local directories initialized via `git init` in pytest fixtures.

### Alternatives Considered
- **`GitPython`**: High-level and mature, but fundamentally synchronous. Running GitPython calls in an async FastAPI service requires offloading every command to `asyncio.to_thread()`, adding thread scheduling overhead and complex exception hierarchies.
- **`pygit2` (libgit2)**: Extremely fast C-library, but introduces binary compilation hurdles on Windows development machines and container builds, and requires implementing custom C-level credential callbacks for SSH/TLS.
- **`dulwich`**: Pure Python Git implementation; however, remote protocol support over HTTPS/SSH can diverge from system Git behavior, adding maintenance burden.

---

## 2. Database Schema & UUID Field Mapping

### Decision
Use SQLAlchemy 2.0 `sqlalchemy.Uuid` type for all primary keys and foreign keys (`id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)`), coupled with declarative models inheriting from a central `Base` (`DeclarativeBase`).

### Rationale
- **Cross-Database Compatibility**: `sqlalchemy.Uuid` automatically maps to native `UUID` in PostgreSQL 16+ (Phase 0 production target) while seamlessly falling back to `CHAR(32)` in SQLite for `InMemoryDatabaseGateway` test runs.
- **Type Safety**: Enforces native Python `uuid.UUID` objects in domain models and services, preventing string formatting bugs (hyphenated vs unhyphenated).
- **Alembic Native Support**: Generates clean, standard PostgreSQL migration scripts (`postgresql.UUID(as_uuid=True)`).

### Alternatives Considered
- **`String(36)` columns**: Requires manual UUID conversion and validation on every read/write, and wastes index space in PostgreSQL compared to native 16-byte UUID types.
- **Auto-incrementing Integer IDs**: Unsuitable for distributed analysis runs, enables enumeration attacks on public API endpoints, and contradicts Phase 0 architecture.

---

## 3. Location Normalization & Composite Uniqueness

### Decision
Normalize repository locations deterministically prior to persistence and enforce a database-level composite unique constraint `uq_project_location (project_id, location)` on the `repositories` table.

### Rationale
- **Local Normalization**: `Path(location).resolve()` resolves all relative path components (`.`, `..`), resolves symbolic links, and normalizes path separators for the host OS.
- **Remote Normalization**: Parse the URL via `urllib.parse`, convert scheme and hostname to lowercase, strip trailing `.git` extension, strip trailing `/` slash, and verify that scheme is strictly in `{"http", "https", "ssh"}`.
- **Collision Prevention**: Prevents a developer from registering `https://github.com/org/repo` and `https://github.com/org/repo.git/` as two separate repositories under the same project.
- **Project Isolation**: Distinct projects can register the same physical repository without cross-project state pollution or foreign key conflicts.

### Alternatives Considered
- **Global Unique Constraint on `location`**: Rejected during clarification session because different TRACE projects represent distinct risk analysis scopes (e.g. comparing a library upgrade vs an architectural audit) and must maintain independent analysis histories.
- **No Normalization (Raw URL Comparison)**: Vulnerable to duplicate records differing only by trailing slashes or case.

---

## 4. Secret Isolation & Ambient Authentication

### Decision
Enforce zero database secrets. Reject remote URLs containing embedded userinfo (`user:token@host`) at registration with HTTP 422 Unprocessable Entity. Remote Git operations rely exclusively on host ambient authentication (system SSH agent, user SSH keys, system Git credential helper, or environment variables).

### Rationale
- **TRACE Constitution §IX Compliance**: Secrets must never be stored in plaintext. Phase 0 has no database column encryption or secret vault infrastructure. Storing personal access tokens in PostgreSQL would violate Constitution §IX.
- **Accidental Leakage Prevention**: Rejecting embedded credentials at registration guarantees that tokens cannot leak into PostgreSQL database dumps, unhandled exception tracebacks, or API JSON responses.
- **Standard Enterprise Git Practice**: CI/CD runners, container deployments, and developer workstations natively manage Git access through mounted SSH keys (`/root/.ssh/id_rsa`), environment tokens (`GITHUB_TOKEN`), or Git credential helpers.

### Alternatives Considered
- **Database Column Encryption (Fernet / AES-GCM)**: Rejected for F01 as premature infrastructure (violating Constitution §XIII YAGNI). Encryption key management, key rotation, and secure enclave storage belong in a dedicated platform security phase.
- **Plaintext URL Sanitization / Masking**: Stripping the password and saving the username would still leave the repository non-functional without credentials. Failing fast with HTTP 422 clearly instructs the user to configure host authentication.

---

## 5. Service Layer Architecture & Onion Dependency Rules

### Decision
Introduce dedicated domain services `ProjectService` and `RepositoryService` under `trace/services/` that orchestrate business logic between API routers, domain entities, `DatabaseGateway`, and `GitProvider`.

### Rationale
- **Separation of Concerns**: Prevents API routers from embedding SQL queries, session management, or subprocess execution.
- **Testability**: Service methods accept interface protocols (`DatabaseGateway`, `GitProvider`), allowing full unit testing with stubbed adapters without spinning up FastAPI or PostgreSQL.
- **Dependency Flow**:
  ```text
  FastAPI Router (trace/api/projects/, trace/api/repositories/)
       │  depends on
       ▼
  Domain Services (trace/services/)
       │  orchestrates
       ▼
  Domain Entities & Enums (trace/domain/) [PURE PYTHON]
       ▲
       │  implements
  Infrastructure Gateways (trace/infrastructure/database/, trace/infrastructure/git/)
  ```

### Alternatives Considered
- **Direct Router-to-Database Logic**: Monolithic route handlers; harms testability and code reuse by future LangGraph agents.
- **ActiveRecord Pattern**: Coupling domain entities directly to SQLAlchemy ORM classes; violates Constitution architecture rules requiring pure Python domain models.

---

## 6. Remote Reference Probing Strategy

### Decision
Execute `git ls-remote --symref <url> HEAD` via subprocess. Parse output for `ref: refs/heads/<branch>\tHEAD` to detect the remote default branch without cloning working tree files.

### Rationale
- **Lightweight Non-Destructive Probe**: Queries Git remote advertisement over the network (typically transferring <2 KB of metadata).
- **Default Branch Accuracy**: The `--symref` flag causes the remote Git server to report the actual symbolic target of `HEAD` (e.g., `main` or `master`), eliminating heuristic guessing.
- **Zero Disk Footprint**: Does not download blobs, trees, or commit history to the server filesystem, strictly preserving the boundary between F01 (registration/connectivity) and F02 (code analysis).

### Alternatives Considered
- **Shallow Clone (`git clone --depth 1`)**: Downloads repository files and writes hundreds of MBs to disk, violating the architectural boundary that F01 does not perform cloning.
- **GitHub / GitLab REST API Probes**: Couples TRACE to specific proprietary hosting APIs, violating provider independence (Constitution §V and §XIV). System Git protocol works identically across GitHub, GitLab, Bitbucket, Gitea, and self-hosted bare servers.

---

## 7. Migration Sequencing

### Decision
Create Alembic revision `0002_project_repository.py` down-revisioned from `0001_baseline`.

### Schema Created
- Table `projects`:
  - `id` (UUID, primary key)
  - `name` (VARCHAR(100), unique, not null)
  - `description` (TEXT, nullable)
  - `status` (VARCHAR(20), not null, default 'ACTIVE')
  - `created_at` (TIMESTAMP WITH TIME ZONE, not null)
  - `updated_at` (TIMESTAMP WITH TIME ZONE, not null)
- Table `repositories`:
  - `id` (UUID, primary key)
  - `project_id` (UUID, foreign key referencing `projects.id`, not null, indexed)
  - `type` (VARCHAR(20), not null)
  - `location` (VARCHAR(500), not null)
  - `default_branch` (VARCHAR(100), nullable)
  - `status` (VARCHAR(20), not null, default 'REGISTERED')
  - `last_error` (TEXT, nullable)
  - `last_validated_at` (TIMESTAMP WITH TIME ZONE, nullable)
  - `last_analysis_run_id` (UUID, nullable, denormalized convenience reference for F02)
  - `created_at` (TIMESTAMP WITH TIME ZONE, not null)
  - `updated_at` (TIMESTAMP WITH TIME ZONE, not null)
  - Constraint: `CONSTRAINT uq_project_location UNIQUE (project_id, location)`

### Rollback Strategy
`downgrade()` drops `repositories` table first, then drops `projects` table, returning PostgreSQL schema cleanly to `0001_baseline`.
