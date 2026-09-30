# Data Model: TRACE Phase 4 — F05: Impact Analysis & Risk Evaluation Engine

**Feature**: [spec.md](spec.md) | [plan.md](plan.md)  
**Date**: 2026-09-30  

---

## 1. Domain Entities (`trace.domain.impact`)

### `DetailedImpact`
Represents an individual code entity whose AST boundaries intersect a diff hunk:

| Field | Type | Description |
| :--- | :--- | :--- |
| `file` | `str` | Relative file path containing the entity. |
| `entity` | `str` | Short name of the function, method, class, or endpoint. |
| `entity_type` | `str` | Type of entity (`function`, `method`, `class`, `endpoint`). |
| `lines_affected` | `tuple[int, int]` | Inclusive 1-indexed interval `[start_line, end_line]` of affected lines. |
| `diff_snippet` | `str` | Raw unified diff patch lines (`+`, `-`) affecting this entity. |
| `change_summary` | `str` | Concise sentence describing the nature of the change. |
| `remediation_guidance` | `str` | Prescriptive advice for updating upstream callers. |
| `justification` | `str` | Detailed rationale explaining architectural propagation. |
| `outbound_calls` | `tuple[str, ...]` | List of functions/methods called by this entity. |
| `inbound_callers` | `tuple[str, ...]` | Upstream direct callers identified via $G^T$. |
| `callers_at_risk` | `tuple[CallerAtRisk, ...]` | Upstream callers up to depth 3 with path distance. |
| `downstream_dependent_files` | `tuple[str, ...]` | Files containing text or import references to this entity. |

### `CallerAtRisk`
Represents an upstream caller identified through transposed BFS:

| Field | Type | Description |
| :--- | :--- | :--- |
| `qualified_name` | `str` | Fully qualified symbol name. |
| `file_path` | `str` | File where the caller is defined. |
| `distance` | `int` | Shortest path distance from modified entity (1, 2, or 3). |
| `call_chain` | `tuple[str, ...]` | Sequence of invocations leading to the modified entity. |

### `RiskFactor`
Individual risk contributor:

| Field | Type | Description |
| :--- | :--- | :--- |
| `factor` | `str` | Factor title (e.g., "Public API Endpoint Modified", "High Blast Radius"). |
| `severity` | `str` | `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`. |
| `justification` | `str` | Evidence-based reasoning for the severity score. |

### `RemediationStep`
A single action in the prioritized remediation plan:

| Field | Type | Description |
| :--- | :--- | :--- |
| `step_number` | `int` | Sequential priority (1..4). |
| `category` | `str` | `Contract Changes`, `Missing Modules`, `Direct Callers`, `Integration Validation`. |
| `action_description` | `str` | Clear instruction for the developer. |
| `affected_targets` | `tuple[str, ...]` | Symbols or files targeted by this step. |

### `ImpactAnalysisAggregate`
The complete root aggregate for an impact analysis run:

| Field | Type | Description |
| :--- | :--- | :--- |
| `id` | `UUID` | Unique identifier of the analysis run. |
| `repository_id` | `UUID` | Repository ID under analysis. |
| `base_commit` | `str` | Base Git commit SHA. |
| `current_commit` | `str` | Target/current Git commit SHA. |
| `created_at` | `datetime` | UTC timestamp of completion. |
| `reasoning_mode` | `str` | `HEURISTIC` (offline) or `LLM_ENRICHED` (OpenRouter). |
| `summary` | `str` | High-level summary of total impacts. |
| `detailed_impacts` | `tuple[DetailedImpact, ...]` | Array of per-entity impact records. |
| `dependency_graph` | `DependencyGraphPayload` | Nodes, edges, and Mermaid string. |
| `risk_level` | `str` | `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`. |
| `key_risk_factors` | `tuple[RiskFactor, ...]` | Structured risk factors. |
| `ci_cd_recommendations` | `tuple[str, ...]` | Test suite execution suggestions. |
| `actionable_remediation_plan` | `tuple[RemediationStep, ...]` | Ordered developer checklist. |
| `ai_directive` | `dict[str, Any] \| None` | Optional AI-synthesized directive specifying where and what to change. |

---

## 2. Relational Database Schema (`impact_analyses` table)

```sql
CREATE TABLE impact_analyses (
    id UUID PRIMARY KEY,
    repository_id UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    base_commit VARCHAR(64) NOT NULL,
    current_commit VARCHAR(64) NOT NULL,
    risk_level VARCHAR(20) NOT NULL DEFAULT 'LOW',
    reasoning_mode VARCHAR(20) NOT NULL DEFAULT 'HEURISTIC',
    total_changed_entities INTEGER NOT NULL DEFAULT 0,
    total_deleted_files INTEGER NOT NULL DEFAULT 0,
    total_impacted_downstream_files INTEGER NOT NULL DEFAULT 0,
    total_callers_at_risk INTEGER NOT NULL DEFAULT 0,
    artifact_path TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX ix_impact_analyses_repo_created ON impact_analyses(repository_id, created_at);
CREATE INDEX ix_impact_analyses_repository_id ON impact_analyses(repository_id);
```
