<!--
SYNC IMPACT REPORT
==================
Version change  : (blank template) → 1.0.0
Modified        : All placeholder tokens replaced; no prior named principles to rename.
Added sections  : Core Principles (I–XVII), Architecture Constraints, Quality Gates, Governance
Removed         : All [PLACEHOLDER] tokens (template scaffold only, no real content lost)
TODOs deferred  : None — all fields resolved from README and user-supplied principles.
Suggested commit: docs: establish TRACE constitution v1.0.0 (initial ratification)
-->

# TRACE Constitution

**Transformation Risk Analysis & Change Evaluation**

> This document is the supreme governing engineering document for the TRACE project.
> All implementation decisions, architectural choices, and process definitions MUST
> comply with the principles stated here. Amendments require the procedure defined
> in the Governance section.

---

## Core Principles

### I. Evidence over Hallucination

Repository evidence, Git history, deterministic static analysis, database state, and
validated analysis results are the authoritative source of truth for TRACE.

- LLM output is **never** treated as authoritative project state.
- Every finding presented to users MUST be traceable to a concrete, inspectable source
  (a Git commit, an AST node, a graph edge, a database record, or a confirmed human decision).
- Unverified LLM inferences MUST be clearly labelled as inferences, not facts.

**Rationale:** TRACE's value proposition is trustworthy impact analysis. Fabricated or
hallucinated state destroys that trust and can cause developers to make incorrect decisions.

---

### II. Deterministic Analysis before Probabilistic Inference

The analysis pipeline MUST exhaust deterministic methods before invoking probabilistic
or LLM-based reasoning:

- **Git facts** MUST be obtained via Git (libgit2 / GitPython / subprocess), never inferred.
- **Python structure** MUST be extracted via AST or static analysis tools, not guessed.
- **Structural dependencies** MUST be resolved via graph traversal (Neo4j Cypher), not
  estimated.
- **Persisted application state** MUST be read from the database, not derived from memory.
- **LLMs** are permitted only for interpretation, semantic reasoning, explanation, natural-
  language interaction, and planning — roles that require inference over structured evidence.

**Rationale:** Deterministic methods produce reproducible, auditable results. Probabilistic
methods supplement but must not replace them.

---

### III. Human-in-the-Loop

Ambiguous or consequential findings MUST support human review before influencing project state.

- The system MUST expose a review interface (API + UI) that allows humans to confirm,
  reject, or annotate findings.
- Human decisions MUST be persisted in the authoritative database and treated as auditable
  records.
- The system MUST NOT autonomously modify any external repository or production system
  without explicit human approval.

**Rationale:** TRACE is a decision-support platform. Its primary contract with users is
that it informs, not commands. Consequential automation without human oversight violates
that contract.

---

### IV. Explainability and Evidence

Every important finding MUST present its supporting evidence in a structured,
human-interpretable form.

- Findings MUST distinguish between: **Observed Evidence**, **Inference**, **Recommendation**,
  and **Uncertainty**.
- TRACE MUST be able to explain why a component was identified as affected, including the
  traversal path through the dependency graph.
- Risk scores MUST include the evidence factors that produced them; raw numeric scores
  without evidence rationale are not acceptable.

**Rationale:** Developers need to judge whether TRACE's conclusions are correct. Opaque
scores break trust and make verification impossible.

---

### V. Provider and Model Independence

Business logic MUST NOT depend directly on any specific LLM provider, model name, or
SDK (e.g. OpenRouter, Nemotron, DeepSeek, Qwen, Anthropic, OpenAI).

- All LLM access MUST go through a stable, internal abstraction layer (e.g. `LLMProvider`
  interface / gateway).
- The abstraction MUST support at minimum: text completion, chat completion, and embedding
  generation.
- Concrete provider implementations MUST be in dedicated, swappable adapter modules.

**Rationale:** Provider landscapes change rapidly. Coupling to a specific provider creates
migration risk and makes testing harder.

---

### VI. Free-First LLM Architecture

Free and open-weight models are the default for all LLM operations.

- The system MUST NOT silently upgrade to a paid model.
- Paid or rate-limited models MUST be opt-in and configured explicitly by the user.
- Model selection MUST be configuration-driven (environment variables or configuration
  file), not hardcoded.
- A clearly documented default configuration MUST use only freely available models.

**Rationale:** TRACE should be usable without a paid API subscription. Cost surprises
erode trust and accessibility.

---

### VII. Testability

All external services and non-deterministic dependencies MUST have deterministic
interfaces and replaceable test doubles.

- Normal (unit and integration) tests MUST NOT depend on live LLM availability,
  live Neo4j instances, or live Git remotes.
- Each domain boundary MUST expose an interface against which test doubles can be
  registered.
- Tests that require real external services MUST be clearly labelled (e.g.
  `@pytest.mark.integration`) and excluded from the default test run.

**Rationale:** A test suite that requires live external services is fragile, slow, and
cannot be run in CI without secrets. Deterministic tests enable confident iteration.

---

### VIII. Explicit Contracts

Domain boundaries MUST be expressed as explicit, versioned contracts.

The following contract categories MUST remain separated:

| Contract Layer | Examples |
|---|---|
| **API contracts** | FastAPI route schemas, request/response models |
| **Domain contracts** | Core domain entities, value objects, aggregates |
| **Persistence contracts** | SQLAlchemy models, migration scripts |
| **Graph contracts** | Neo4j node/relationship schemas |
| **Analysis contracts** | Code intelligence output schemas |
| **Agent-state contracts** | LangGraph state types |
| **Provider contracts** | LLM/embedding provider interfaces |

Changes to any contract layer MUST be intentional and documented.

**Rationale:** Implicit coupling between layers makes changes unpredictably expensive
and testing difficult.

---

### IX. Security and Secret Isolation

Secrets MUST be treated as sensitive infrastructure and MUST never appear in code or logs.

- API keys, database credentials, and tokens MUST be supplied exclusively through
  environment variables or a secrets manager.
- Secrets MUST NOT be committed to version control under any circumstances.
- Logging MUST explicitly redact secret values before output.
- Transmission of source code or repository content to external LLM providers MUST be:
  (a) explicit in configuration, and (b) disclosed to users before the first transmission.
- Sensitive data (PII, credentials, proprietary code) MUST NOT be sent to external models
  unless the user has explicitly configured and consented to it.

**Rationale:** Security incidents caused by accidental secret leakage are among the most
damaging and most preventable. TRACE handles third-party code and must respect its
confidentiality.

---

### X. Incremental Delivery

Features MUST be implemented one phase at a time, in dependency order.

- A downstream feature (e.g. F05 Impact Analysis) MUST NOT be implemented before its
  upstream dependencies (F01, F02, F03/F04) are stable.
- Each phase MUST produce a usable, testable increment — not just scaffolding.
- Placeholder implementations that claim functionality not yet built are forbidden.

**Rationale:** Premature integration hides dependency problems and produces code that
cannot be verified. Phased delivery keeps risk visible.

---

### XI. Observability

Every analysis run and every significant system operation MUST be traceable.

- Analysis runs MUST be assigned unique, persistent identifiers.
- Run status MUST be stored in the authoritative database and queryable through the API.
- Structured logging MUST be used throughout; log lines MUST include at minimum:
  timestamp, run ID, component name, and severity.
- Agent state transitions MUST be observable through the LangGraph state schema.

**Rationale:** When a complex analysis produces unexpected results, operators and
developers must be able to understand exactly what happened and when.

---

### XII. Reproducibility

Analysis results SHOULD be reproducible from the same repository reference and
configuration.

- Given the same Git commit hash and the same TRACE configuration, the deterministic
  layers of analysis (AST parsing, graph construction, change detection) MUST produce
  identical output.
- LLM-produced inferences (inherently non-deterministic) MUST be clearly separated from
  deterministic results and stored independently.
- Analysis inputs (repository ref, configuration snapshot) MUST be persisted alongside
  results.

**Rationale:** Reproducibility is essential for debugging, auditing, and user trust.

---

### XIII. Maintainability

Simple, modular architecture MUST be preferred over premature distributed infrastructure.

- Each module MUST have a single, clearly documented responsibility.
- YAGNI (You Aren't Gonna Need It): infrastructure complexity MUST not be introduced
  before a concrete, demonstrated need exists.
- The technology stack MUST remain as small as necessary — each new dependency requires
  justification.
- Documentation MUST be maintained alongside code; undocumented public interfaces are
  not acceptable.

**Rationale:** TRACE is a greenfield project. Premature complexity makes onboarding,
debugging, and testing expensive.

---

### XIV. Replaceability

All major infrastructure components MUST be replaceable through well-defined interfaces.

The following MUST be replaceable without changes to business logic:

- LLM provider (e.g. switch from local Ollama to OpenRouter)
- Embedding provider
- Vector store (e.g. Chroma → Weaviate)
- Graph store (e.g. Neo4j → alternative graph DB)
- Git provider / hosting integration
- Language analyzer / AST toolkit

Each replaceable component MUST have a corresponding interface or abstract base class.
Concrete implementations MUST be in dedicated adapter modules.

**Rationale:** Technology choice is a business risk. Infrastructure lock-in prevents
cost optimisation and adaptation to better tools.

---

### XV. Backward-Compatible Evolution

Contract changes MUST be deliberate, documented, and communicated before release.

- Breaking changes to API, domain, persistence, or graph contracts MUST be preceded
  by a documented migration path.
- Semantic versioning MUST govern all public contract changes.
- Database schema changes MUST use migration scripts (e.g. Alembic); direct schema
  mutation in production is forbidden.
- Deprecated interfaces MUST be retained for at least one release cycle with clear
  deprecation warnings before removal.

**Rationale:** Downstream consumers (UI, agents, tests) must be able to adapt to
changes without unexpected failures.

---

### XVI. Production Quality

Generated or implemented code is not considered complete until all of the following
are present and passing:

- [ ] Unit tests covering the feature's core logic
- [ ] Integration tests verifying the feature's external contracts
- [ ] Static analysis / linting passing with zero violations
- [ ] Type annotations present and type-checker clean
- [ ] Documentation (docstrings + updated API/architecture docs)
- [ ] Runtime verification confirming the feature operates correctly end-to-end

Incomplete implementations MUST be clearly marked with `TODO(phase)` comments and
MUST NOT be represented as finished in project status.

**Rationale:** Technical debt accumulates fastest when "good enough" replaces "done".
TRACE analysis accuracy depends on the reliability of its own codebase.

---

### XVII. No Fabricated Implementation State

It is forbidden to claim that a feature, test, integration, dependency, analysis result,
or data record exists unless it has been actually implemented and verified.

- Documentation MUST reflect actual project state, not aspirational state.
- Task/spec status fields MUST be updated only when the described functionality is
  demonstrably present in the codebase.
- This applies to agents, human contributors, and automated tooling alike.

**Rationale:** False implementation state is the single most disruptive form of technical
debt. It causes downstream work to be built on non-existent foundations.

---

## Architecture Constraints

The following architectural decisions are ratified as part of this constitution and MUST
be respected during implementation:

### Technology Stack (Phase 0 baseline)

| Layer | Technology | Notes |
|---|---|---|
| Backend API | FastAPI (Python) | REST; async-first |
| Orchestration | LangGraph | Agent workflow management |
| Relational DB | PostgreSQL | Authoritative application state |
| Graph DB | Neo4j | Structural dependency graph |
| Vector Store | Configurable (default: open-source) | Semantic retrieval; replaceable |
| Early UI | Streamlit | Internal analysis laboratory only |
| Production UI | React + TypeScript | Project Observatory (later phases) |
| LLM Gateway | Internal abstraction | Never call provider SDK directly |
| Config | Environment variables + config file | No hardcoded secrets or model names |
| Testing | pytest | Unit + integration, with markers |
| Migrations | Alembic | No direct schema mutation |

### Separation of Concerns

```
UI Layer          ← React / Streamlit
     ↓
API Layer         ← FastAPI (request/response contracts)
     ↓
Orchestration     ← LangGraph (agent state + workflow)
     ↓
Domain Layer      ← Pure business logic, no framework deps
     ↓
Infrastructure    ← PostgreSQL, Neo4j, Vector Store, LLM Gateway, Git
```

No layer MUST import from a layer above it.

---

## Quality Gates

Before any phase is considered complete, all of the following MUST be verified:

1. **Tests pass**: `pytest` suite (unit + integration) passes with zero failures.
2. **Static analysis clean**: linter (ruff or equivalent) + type checker (mypy or equivalent)
   report zero violations.
3. **API contracts documented**: All new endpoints have OpenAPI docs and response schemas.
4. **Graph contracts documented**: New node types and relationship types are recorded.
5. **No fabricated state**: All task statuses in `tasks.md` reflect actual implementation.
6. **Secrets not present**: `git secrets` or equivalent scan confirms no credentials in diff.
7. **Feature observable**: Analysis runs for the new feature produce traceable run IDs.

---

## Governance

This constitution supersedes all other project practices, conventions, and informal
agreements. When a conflict exists between the constitution and any other document, the
constitution takes precedence.

### Amendment Procedure

1. Propose the amendment in writing, referencing the specific principle(s) affected.
2. Document the rationale for the change.
3. If the amendment is a **breaking change** (removal or redefinition of a principle),
   document the migration plan for existing code and tests.
4. Record the amendment in this file with an updated version and `LAST_AMENDED_DATE`.
5. Communicate the amendment to all active contributors before merging.

### Versioning Policy

This document uses semantic versioning:

- **MAJOR**: Backward-incompatible removal or redefinition of a principle.
- **MINOR**: Addition of a new principle or materially expanded guidance.
- **PATCH**: Clarifications, wording improvements, typo fixes, non-semantic refinements.

### Compliance Review

- Every pull request / feature implementation MUST include a self-attestation that it
  complies with this constitution.
- Any code review that identifies a constitution violation MUST block merge until
  resolved or an explicit, documented exception is ratified.
- The constitution MUST be reviewed at the start of each new development phase to
  confirm it remains appropriate.

---

**Version**: 1.0.0 | **Ratified**: 2026-09-25 | **Last Amended**: 2026-09-25
