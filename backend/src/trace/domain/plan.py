"""Domain entities for F07: Upgrade Planner."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID


class TaskStatus(StrEnum):
    """Operational lifecycle state of an upgrade task."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"


class TaskCategory(StrEnum):
    """Architectural classification determining default sequencing precedence."""

    CONTRACT_API = "CONTRACT_API"  # Tier 1: Public contracts, endpoints, schemas
    CORE_LOGIC = "CORE_LOGIC"  # Tier 2: Domain services, core classes, algorithms
    DATA_MAPPING = "DATA_MAPPING"  # Tier 3: Database entities, ORM models, migrations
    CONSUMER_HANDLER = "CONSUMER_HANDLER"  # Tier 4: Background tasks, event listeners, webhooks
    CLIENT_UI = "CLIENT_UI"  # Tier 5: Frontend views, client consumers
    INTEGRATION_TEST = "INTEGRATION_TEST"  # Tier 6: Unit tests, integration suites
    DOCUMENTATION_CONFIG = "DOCUMENTATION_CONFIG"  # Tier 7: Documentation, environment, configs


@dataclass(frozen=True)
class TaskEvidence:
    """Underlying deterministic proof backing the generation of the task."""

    diff_snippet: str = ""
    lines_affected: tuple[int, int] = (0, 0)
    call_chain: tuple[str, ...] = ()
    file_path: str = ""
    target_symbol: str = ""


@dataclass(frozen=True)
class TaskDependency:
    """Directed dependency between two tasks."""

    source_task_id: UUID
    target_task_id: UUID
    dependency_type: str = "CALLS"


@dataclass
class UpgradeTask:
    """An actionable, single-responsibility engineering task within an upgrade plan."""

    id: UUID
    plan_id: UUID
    step_number: int
    component: str
    component_type: str
    category: TaskCategory
    reason: str
    dependencies: tuple[str, ...] = ()
    expected_changes: str = ""
    required_tests: tuple[str, ...] = ()
    risk_level: str = "LOW"
    status: TaskStatus = TaskStatus.PENDING
    is_circular: bool = False
    parallel_group_id: int = 1
    notes: str | None = None
    evidence: TaskEvidence | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class UpgradePlan:
    """Root aggregate governing an upgrade plan."""

    id: UUID
    repository_id: UUID
    impact_analysis_id: UUID
    title: str
    base_commit: str
    target_commit: str
    risk_level: str = "LOW"
    status: str = "DRAFT"  # DRAFT, IN_PROGRESS, COMPLETED, CANCELLED
    tasks: list[UpgradeTask] = field(default_factory=list)
    reasoning_mode: str = "HEURISTIC"  # HEURISTIC or LLM_ENRICHED
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def total_tasks(self) -> int:
        return len(self.tasks)

    @property
    def completed_tasks(self) -> int:
        return sum(1 for t in self.tasks if t.status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED))

    @property
    def in_progress_tasks(self) -> int:
        return sum(1 for t in self.tasks if t.status == TaskStatus.IN_PROGRESS)

    @property
    def pending_tasks(self) -> int:
        return sum(1 for t in self.tasks if t.status == TaskStatus.PENDING)

    @property
    def blocked_tasks(self) -> int:
        return sum(1 for t in self.tasks if t.status == TaskStatus.BLOCKED)

    @property
    def skipped_tasks(self) -> int:
        return sum(1 for t in self.tasks if t.status == TaskStatus.SKIPPED)

    @property
    def progress_percentage(self) -> float:
        if not self.tasks:
            return 100.0
        return round((self.completed_tasks / self.total_tasks) * 100.0, 1)
