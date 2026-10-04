# Data Model: TRACE Phase 6 — F07: Upgrade Planner

**Feature**: [spec.md](spec.md) | [plan.md](plan.md)  
**Date**: 2026-10-01  

---

## 1. Domain Entities (`trace.domain.plan`)

### `TaskStatus` (Enum)
Represents the operational lifecycle state of an individual upgrade task:
```python
class TaskStatus(StrEnum):
    PENDING = "PENDING"          # Not yet started
    IN_PROGRESS = "IN_PROGRESS"  # Actively being addressed
    COMPLETED = "COMPLETED"      # Verified and finished
    BLOCKED = "BLOCKED"          # Waiting on external/prerequisite factors
    SKIPPED = "SKIPPED"          # Intentionally bypassed with rationale
```

### `TaskCategory` (Enum)
Architectural classification determining default sequencing precedence:
```python
class TaskCategory(StrEnum):
    CONTRACT_API = "CONTRACT_API"                  # Tier 1: Public contracts, endpoints, schemas
    CORE_LOGIC = "CORE_LOGIC"                      # Tier 2: Domain services, core classes, algorithms
    DATA_MAPPING = "DATA_MAPPING"                  # Tier 3: Database entities, ORM models, migrations
    CONSUMER_HANDLER = "CONSUMER_HANDLER"          # Tier 4: Background tasks, event listeners, webhooks
    CLIENT_UI = "CLIENT_UI"                        # Tier 5: Frontend views, client consumers
    INTEGRATION_TEST = "INTEGRATION_TEST"          # Tier 6: Unit tests, integration suites
    DOCUMENTATION_CONFIG = "DOCUMENTATION_CONFIG"  # Tier 7: Documentation, environment, configs
```

### `TaskEvidence` (Value Object)
Underlying deterministic proof backing the generation of the task:
```python
@dataclass(frozen=True)
class TaskEvidence:
    diff_snippet: str = ""
    lines_affected: tuple[int, int] = (0, 0)
    call_chain: tuple[str, ...] = ()
    file_path: str = ""
    target_symbol: str = ""
```

### `UpgradeTask` (Entity)
An actionable, single-responsibility engineering task within an upgrade plan:
```python
@dataclass
class UpgradeTask:
    id: UUID
    plan_id: UUID
    step_number: int
    component: str
    component_type: str
    category: TaskCategory
    reason: str
    dependencies: tuple[str, ...]  # Component names or task IDs that must precede this
    expected_changes: str
    required_tests: tuple[str, ...]
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    status: TaskStatus = TaskStatus.PENDING
    is_circular: bool = False
    parallel_group_id: int = 1
    notes: str | None = None
    evidence: TaskEvidence | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
```

### `UpgradePlan` (Aggregate Root)
The complete root aggregate governing an upgrade plan:
```python
@dataclass
class UpgradePlan:
    id: UUID
    repository_id: UUID
    impact_analysis_id: UUID
    title: str
    base_commit: str
    target_commit: str
    risk_level: str  # Inherited from F06
    status: str      # DRAFT, IN_PROGRESS, COMPLETED, CANCELLED
    tasks: list[UpgradeTask]
    reasoning_mode: str  # HEURISTIC or LLM_ENRICHED
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def total_tasks(self) -> int:
        return len(self.tasks)

    @property
    def completed_tasks(self) -> int:
        return sum(1 for t in self.tasks if t.status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED))

    @property
    def progress_percentage(self) -> float:
        if not self.tasks:
            return 100.0
        return round((self.completed_tasks / self.total_tasks) * 100.0, 1)
```

---

## 2. State Machine & Transitions

```text
       ┌──────────┐
       │ PENDING  │◄───────────────────┐
       └────┬─────┘                    │
            │                          │
            ▼                          │ (Reset)
     ┌─────────────┐                   │
     │ IN_PROGRESS │───────────────────┤
     └──────┬──────┘                   │
            │                          │
       ┌────┴────┬─────────────┐       │
       │         │             │       │
       ▼         ▼             ▼       │
 ┌──────────┐ ┌─────────┐ ┌─────────┐  │
 │COMPLETED │ │ BLOCKED │ │ SKIPPED │──┘
 └──────────┘ └─────────┘ └─────────┘
```

- **Plan Lifecycle**:
  - `DRAFT`: Newly generated plan, all tasks `PENDING`.
  - `IN_PROGRESS`: At least one task is `IN_PROGRESS` or `COMPLETED`.
  - `COMPLETED`: All tasks have reached `COMPLETED` or `SKIPPED`.
  - `CANCELLED`: Plan abandoned by user.

---

## 3. Relational Database Schema (`upgrade_plans` & `upgrade_tasks`)

```sql
CREATE TABLE upgrade_plans (
    id UUID PRIMARY KEY,
    repository_id UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    impact_analysis_id UUID NOT NULL REFERENCES impact_analyses(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    base_commit VARCHAR(64) NOT NULL,
    target_commit VARCHAR(64) NOT NULL,
    risk_level VARCHAR(20) NOT NULL DEFAULT 'LOW',
    status VARCHAR(30) NOT NULL DEFAULT 'DRAFT',
    reasoning_mode VARCHAR(20) NOT NULL DEFAULT 'HEURISTIC',
    artifact_path TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX ix_upgrade_plans_repo_id ON upgrade_plans(repository_id);
CREATE INDEX ix_upgrade_plans_impact_id ON upgrade_plans(impact_analysis_id);
CREATE INDEX ix_upgrade_plans_created ON upgrade_plans(created_at);

CREATE TABLE upgrade_tasks (
    id UUID PRIMARY KEY,
    plan_id UUID NOT NULL REFERENCES upgrade_plans(id) ON DELETE CASCADE,
    step_number INTEGER NOT NULL,
    component VARCHAR(255) NOT NULL,
    component_type VARCHAR(50) NOT NULL,
    category VARCHAR(50) NOT NULL,
    reason TEXT NOT NULL,
    dependencies JSONB NOT NULL DEFAULT '[]'::jsonb,
    expected_changes TEXT NOT NULL,
    required_tests JSONB NOT NULL DEFAULT '[]'::jsonb,
    risk_level VARCHAR(20) NOT NULL DEFAULT 'LOW',
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    is_circular BOOLEAN NOT NULL DEFAULT FALSE,
    parallel_group_id INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    evidence JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX ix_upgrade_tasks_plan_step ON upgrade_tasks(plan_id, step_number);
CREATE INDEX ix_upgrade_tasks_status ON upgrade_tasks(status);

CREATE TABLE task_dependencies (
    source_task_id UUID NOT NULL REFERENCES upgrade_tasks(id) ON DELETE CASCADE,
    target_task_id UUID NOT NULL REFERENCES upgrade_tasks(id) ON DELETE CASCADE,
    dependency_type VARCHAR(50) NOT NULL DEFAULT 'CALLS',
    PRIMARY KEY (source_task_id, target_task_id)
);
```

---

## 4. File Artifact Storage

In addition to PostgreSQL persistence, full plan payloads are stored as JSON artifacts in `.trace/artifacts/plans/{plan_id}.json` to enable rapid zero-query retrieval, caching, and offline portability:
```json
{
  "plan_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "repository_id": "...",
  "impact_analysis_id": "...",
  "title": "Upgrade Plan: v1.0 -> v2.0",
  "base_commit": "abc1234",
  "target_commit": "def5678",
  "risk_level": "HIGH",
  "status": "IN_PROGRESS",
  "summary_metrics": {
    "total_tasks": 7,
    "completed_tasks": 3,
    "in_progress_tasks": 1,
    "pending_tasks": 3,
    "progress_percentage": 42.9
  },
  "tasks": [
    {
      "id": "...",
      "step_number": 1,
      "component": "src/api/payment.py::PaymentAPI",
      "component_type": "endpoint",
      "category": "CONTRACT_API",
      "reason": "Public payment endpoint modified; parameter payment_id renamed to transaction_id",
      "dependencies": [],
      "expected_changes": "Update route definition and request body schema to accept transaction_id",
      "required_tests": ["tests/test_api.py::test_payment_endpoint"],
      "risk_level": "HIGH",
      "status": "COMPLETED",
      "is_circular": false,
      "parallel_group_id": 1,
      "notes": "Verified against OpenAPI schema",
      "evidence": {
        "diff_snippet": "- def pay(payment_id):\n+ def pay(transaction_id):",
        "lines_affected": [14, 18],
        "file_path": "src/api/payment.py"
      }
    }
  ]
}
```
