# Tasks: TRACE Phase 3B — F04: Version / Change Analyzer

**Feature Branch**: `Version-Change-Analyser`  
**Date**: 2026-09-29  
**Spec Reference**: [spec.md](spec.md) | [plan.md](plan.md)

---

## Task Matrix & Implementation Checklist

### Iteration 1: Domain Models & Git Infrastructure
- [x] **T01-01**: Define domain models and enums in `trace.domain.diff` (`FileChangeType`, `SymbolChangeKind`, `RiskLevel`, `DiffHunk`, `FileDiff`, `SymbolDiff`, `BlastRadiusItem`, `VersionComparison`).
- [x] **T01-02**: Extend `GitProvider` interface in `trace.infrastructure.git.provider` with `get_diff`, `list_branches`, and `list_commits`.
- [x] **T01-03**: Implement `get_diff`, `list_branches`, and `list_commits` in `SubprocessGitProvider` (`trace.infrastructure.git.adapters.subprocess`).
- [x] **T01-04**: Write unit tests for GitProvider diff and branch/commit extraction in `tests/unit/test_subprocess_git.py`.

### Iteration 2: Unified Diff Parser
- [x] **T02-01**: Implement `GitDiffParser` in `trace.analysis.diff_parser` to parse unified diff outputs into structured `FileDiff` and `DiffHunk` instances.
- [x] **T02-02**: Support edge cases: new files, deleted files, renamed files, empty diffs, multiple hunks per file.
- [x] **T02-03**: Write unit tests in `tests/unit/test_diff_parser.py`.

### Iteration 3: AST Symbol Diff & Breaking Change Engine
- [x] **T03-01**: Implement `SymbolDiffEngine` in `trace.analysis.symbol_diff` mapping hunk line intervals to F02 AST code symbols (`Function`, `Class`, `APIEndpoint`, etc.).
- [x] **T03-02**: Implement symbol comparison logic: detect added/modified/deleted symbols between base and target analyses.
- [x] **T03-03**: Implement breaking change rules (removed parameters, added required parameters, altered return types, altered endpoint paths/methods).
- [x] **T03-04**: Write comprehensive unit tests in `tests/unit/test_symbol_diff.py`.

### Iteration 4: Service Orchestration & Graph Blast Radius
- [x] **T04-01**: Add `VersionComparisonOrm` model in `trace.infrastructure.database.models.version_comparison` and Alembic migration.
- [x] **T04-02**: Implement `VersionChangeService` in `trace.services.diff` orchestrating diffing, AST analysis extraction, and Neo4j blast radius traversal.
- [x] **T04-03**: Implement risk level evaluation (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
- [x] **T04-04**: Write unit tests for `VersionChangeService` in `tests/unit/test_diff_service.py`.

### Iteration 5: API Layer & FastAPI Router
- [x] **T05-01**: Implement Pydantic request & response schemas in `trace.api.diff.schemas`.
- [x] **T05-02**: Implement FastAPI router in `trace.api.diff.router` (`/analyses/compare`, `/repositories/{id}/branches`, `/repositories/{id}/commits`).
- [x] **T05-03**: Wire router into `trace.api.router` and `trace.main`.
- [x] **T05-04**: Write API integration tests in `tests/api/test_diff_api.py`.

### Iteration 6: Frontend Observatory Integration & E2E Validation
- [x] **T06-01**: Add "Version & Change Analyzer" tab to `frontend/app.py`.
- [x] **T06-02**: Add Branch vs Branch comparison selectors, Commit pickers, and Quick 2-commit comparison mode.
- [x] **T06-03**: Display symbol changes, breaking change indicators, and interactive blast radius graph view.
- [x] **T06-04**: Rebuild Docker containers and verify end-to-end functionality.
- [x] **T06-05**: Update `guide.md` with F04 usage instructions.
