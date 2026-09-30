# Implementation Plan: TRACE Phase 3B — F04: Version / Change Analyzer

**Feature Branch**: `Version-Change-Analyser`  
**Date**: 2026-09-29  
**Spec Reference**: [spec.md](spec.md) | [data-model.md](data-model.md)

---

## 1. Technical Architecture & Component Flow

```text
[HTTP Request: /analyses/compare]
         │
         ▼
[FastAPI Router: trace/api/diff/router.py]
         │
         ▼
[Service: VersionChangeService (trace/services/diff.py)]
         ├──► 1. GitProvider (Resolve base_ref & target_ref -> commit hashes)
         ├──► 2. SubprocessGitProvider.get_diff(base_ref, target_ref) -> raw diff
         ├──► 3. DiffParser (trace/analysis/diff_parser.py) -> list[FileDiff]
         ├──► 4. SymbolDiffEngine (trace/analysis/symbol_diff.py)
         │       ├── Load/Generate AST analysis for base & target revisions
         │       ├── Match DiffHunks to SourceLocations of functions/classes/endpoints
         │       └── Detect signature alterations & breaking changes
         ├──► 5. GraphService / Neo4j (Query blast radius for affected symbols)
         ├──► 6. DatabaseGateway / FileArtifactStore (Persist comparison run & artifact)
         └──► 7. Return VersionComparison domain response
```

---

## 2. Directory & Module Structure

```text
backend/src/trace/
├── domain/
│   └── diff.py                    # Domain models: FileDiff, SymbolDiff, BlastRadiusItem, VersionComparison
├── analysis/
│   ├── diff_parser.py             # Parses Unified Git Diff into structured FileDiff + DiffHunk models
│   └── symbol_diff.py             # Intersects DiffHunk intervals with AST symbols & detects breaking changes
├── infrastructure/
│   ├── git/
│   │   ├── provider.py            # Extended GitProvider protocol (get_diff, list_branches, list_commits)
│   │   └── adapters/subprocess.py # SubprocessGitProvider implementations
│   └── database/models/
│       └── version_comparison.py  # SQLAlchemy ORM model for version_comparisons table
├── services/
│   └── diff.py                    # VersionChangeService orchestrating diffing, AST delta, and blast radius
└── api/
    └── diff/
        ├── router.py              # Endpoints: /analyses/compare, /repositories/{id}/branches, /commits
        └── schemas.py             # Pydantic request/response schemas
```

---

## 3. Implementation Phases & Milestones

- **Phase 1: Domain & Git Infrastructure Extensions**:
  - Add domain models in `trace.domain.diff`.
  - Extend `GitProvider` and `SubprocessGitProvider` to support:
    - `get_diff(location, base_ref, target_ref)`
    - `list_branches(location)`
    - `list_commits(location, branch, limit)`
  - Unit tests for git provider extensions.

- **Phase 2: Unified Diff Parser**:
  - Implement `DiffParser` in `trace.analysis.diff_parser` to parse git diff output into files, change types, and hunk line intervals.
  - Unit tests for diff parser handling added/modified/deleted files, binary files, renames.

- **Phase 3: AST Symbol Diff & Breaking Change Engine**:
  - Implement `SymbolDiffEngine` in `trace.analysis.symbol_diff`.
  - Intersect hunk line intervals with AST symbols from `RepositoryAnalysis`.
  - Implement signature diffing (parameter additions/deletions/defaults, return types) and route diffing.
  - Unit tests for symbol diffing & breaking change rules.

- **Phase 4: Service Orchestration & Graph Blast Radius**:
  - Implement `VersionChangeService` in `trace.services.diff`.
  - Integrate Neo4j caller/dependent traversal for changed symbols.
  - Compute risk level (LOW, MEDIUM, HIGH, CRITICAL).
  - Add database migration & ORM model for comparison runs.

- **Phase 5: API Layer & FastAPI Router**:
  - Implement schemas in `trace.api.diff.schemas`.
  - Implement endpoints in `trace.api.diff.router`.
  - Register router with main FastAPI application.
  - Integration tests for API endpoints.

- **Phase 6: Frontend Observatory Integration**:
  - Add "Version & Change Analyzer" panel to `frontend/app.py`.
  - Implement Branch Selector (`Base Branch` vs `Target Branch`), Commit Log picker, and Quick Diff (`HEAD~1` vs `HEAD`).
  - Visual display of changed symbols, breaking changes, and interactive blast radius graph overlay.
