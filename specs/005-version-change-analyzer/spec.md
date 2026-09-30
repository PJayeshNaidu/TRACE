# Feature Specification: TRACE Phase 3B — F04: Version / Change Analyzer

**Feature Branch**: `Version-Change-Analyser`  
**Date**: 2026-09-29  
**Phase**: 3B  
**Status**: In Development  
**Depends On**: F01 (Project & Repository Management), F02 (Repository / Code Analyzer), F03 (Dependency Graph)  
**Feeds Into**: F05 (Impact Analysis & Blast Radius Engine), F06 (Upgrade Plan Generator), F10 (AI Assistant)

---

## 1. Executive Summary & Scope

F04 (Version / Change Analyzer) is the semantic delta engine of TRACE. 

While traditional Git diff tools display raw line changes (`+` and `-`), F04 translates physical line modifications into **high-level semantic code symbols** (Modules, Classes, Methods, Functions, Endpoints, Database Schemas, Dependencies) and evaluates **breaking changes** and **architectural blast radius**.

F04 natively supports:
1. **Branch-to-Branch Comparison** (e.g., comparing `feature/auth` or `development` against `main` for PR / Release review).
2. **Commit-to-Commit Comparison** (e.g., comparing commit `a1b2c3d` against `e4f5g6h`).
3. **Quick / Default Comparison** (e.g., comparing `HEAD~1` against `HEAD` on the current branch).

---

## 2. Scope Boundaries

### What F04 Does
- Compares any two Git revisions (`base_ref` vs `target_ref`, supporting branches, tags, commit SHAs, or relative refs like `HEAD~1`).
- Extracts physical file diffs (added, modified, deleted, renamed files) and hunks (line ranges).
- Maps diff hunks to AST code entities extracted by F02 (`RepositoryAnalysis`).
- Classifies code symbol changes (`ADDED`, `MODIFIED`, `DELETED`, `RENAMED`).
- Detects signature changes (parameters added/removed/reordered, default value alterations, return type changes).
- Identifies API Endpoint changes (HTTP method changes, path changes, deleted/added endpoints).
- Traverses Neo4j graph (built by F03) to calculate the **Immediate Blast Radius** (direct callers, extending classes, dependent modules).
- Calculates a deterministic **Risk Score** (LOW, MEDIUM, HIGH, CRITICAL).
- Exposes REST APIs for branch/commit listing, triggering comparisons, and querying diff results.
- Integrates into the Observatory frontend with branch/commit comparison selectors and visual change badges.

### What F04 Does NOT Do
- F04 does **not** generate multi-step automated remediation plans (owned by F06).
- F04 does **not** call LLMs for code synthesis (owned by F10).
- F04 does **not** mutate the target Git repository or execute merges.

---

## 3. Functional Requirements

### FR-001 — Flexible Git Revision Comparison
The system SHALL accept `base_ref` and `target_ref` as branch names (e.g. `main`, `development`), commit SHAs (full or short), tags (e.g. `v1.0.0`), or relative references (e.g. `HEAD~1`).
If `base_ref` is omitted, it SHALL default to `HEAD~1`. If `target_ref` is omitted, it SHALL default to `HEAD`.

### FR-002 — Git Diff Extraction & Parsing
The system SHALL run non-destructive Git diffing between `base_ref` and `target_ref` in the repository working tree and parse:
- File status: `ADDED`, `MODIFIED`, `DELETED`, `RENAMED`
- Insertion count, deletion count, and hunk line intervals `(old_start, old_lines, new_start, new_lines)`

### FR-003 — Semantic AST Symbol Mapping
The system SHALL intersect diff hunk line intervals with F02 symbol source locations (`SourceLocation.start_line` to `end_line`) to identify:
- **Modified Functions / Methods**: Functions whose body or signature falls within a changed hunk.
- **Added Functions / Classes**: Symbols present in `target_ref` but not in `base_ref`.
- **Deleted Functions / Classes**: Symbols present in `base_ref` but not in `target_ref`.
- **Modified Classes**: Classes where methods or attributes were added, removed, or altered.
- **API Endpoint Diffs**: Added, modified, or removed API routes.

### FR-004 — Breaking Change Detection
The system SHALL flag a symbol change as **Breaking** (`is_breaking = True`) if:
1. A function / method parameter was removed.
2. A required parameter (no default value) was added to an existing function.
3. A public API endpoint route or HTTP method was altered or deleted.
4. An existing class / function was deleted or renamed.
5. A return type annotation was changed incompatibly.

### FR-005 — Graph-Powered Blast Radius Traversal
For all modified or deleted symbols, the system SHALL query the Neo4j dependency graph (from F03) to discover:
- Upstream direct callers (`CALLS` incoming).
- Downstream dependencies (`CALLS`, `IMPORTS`, `DEPENDS_ON` outgoing).
- Inheriting classes (`EXTENDS` incoming).
- Affected test units (`TESTED_BY` incoming).

### FR-006 — Risk Score Calculation
The system SHALL compute a deterministic risk score:
- **CRITICAL**: Breaking change in public API endpoint or core domain service with $>5$ dependents.
- **HIGH**: Breaking change in internal function/class with $>2$ dependents, or $>10$ affected downstream nodes.
- **MEDIUM**: Non-breaking modification in functions/classes with active callers.
- **LOW**: Internal modification with 0 direct callers or test-only changes.

### FR-007 — Branch & Commit Listing APIs
The system SHALL provide endpoints:
- `GET /api/v1/repositories/{id}/branches`: Returns list of local and remote branches.
- `GET /api/v1/repositories/{id}/commits?limit=50&branch=main`: Returns recent commit log (SHA, message, author, timestamp).

### FR-008 — Comparison Trigger & Query APIs
The system SHALL provide endpoints:
- `POST /api/v1/analyses/compare`: Triggers a version diff run between `base_ref` and `target_ref`.
- `GET /api/v1/analyses/compare/{comparison_id}`: Retrieves the structured diff, symbol changes, breaking changes, and blast radius.

---

## 4. Non-Functional Requirements

- **Performance**: Diff parsing and AST symbol mapping SHALL complete in $< 1.5\text{s}$ for changesets under 100 files.
- **Safety**: All Git operations SHALL be read-only and non-destructive.
- **Deterministic**: Given the same two commit SHAs and AST artifacts, F04 SHALL produce identical diff payloads.
