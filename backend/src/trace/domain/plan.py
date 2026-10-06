"""Domain entities for F07: Upgrade Planner."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, TypedDict
from uuid import UUID


class TaskStatus(StrEnum):
    """Operational lifecycle state of an upgrade task."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"


class Actionability(StrEnum):
    """Classification of change impact requiring engineering action or review."""

    IGNORE = "IGNORE"  # Whitespace, formatting, comment typo with no behavioral impact
    INFORMATIONAL = (
        "INFORMATIONAL"  # Documentation, configuration changes not requiring code remediation
    )
    REVIEW = "REVIEW"  # Test-only or ambiguous changes requiring developer inspection
    UPGRADE = "UPGRADE"  # Behavioral, contract, schema, or logic changes requiring code remediation


class ChangeSignificance(StrEnum):
    """Semantic magnitude of the detected revision difference."""

    MAJOR_CHANGE = "MAJOR_CHANGE"
    MODERATE_CHANGE = "MODERATE_CHANGE"
    MINOR_CHANGE = "MINOR_CHANGE"
    NO_ACTION_REQUIRED = "NO_ACTION_REQUIRED"


class TaskActionType(StrEnum):
    """Specific type of engineering action required for an individual task."""

    REQUIRED_CHANGE = "REQUIRED_CHANGE"
    VALIDATION_ONLY = "VALIDATION_ONLY"
    LOW_PRIORITY_REVIEW = "LOW_PRIORITY_REVIEW"
    NO_ACTION = "NO_ACTION"


class TaskCategory(StrEnum):
    """Architectural classification determining default sequencing precedence."""

    CONTRACT_API = "CONTRACT_API"  # Tier 1: Public contracts, endpoints, schemas
    CORE_LOGIC = "CORE_LOGIC"  # Tier 2: Domain services, core classes, algorithms
    DATA_MAPPING = "DATA_MAPPING"  # Tier 3: Database entities, ORM models, migrations
    CONSUMER_HANDLER = "CONSUMER_HANDLER"  # Tier 4: Background tasks, event listeners, webhooks
    CLIENT_UI = "CLIENT_UI"  # Tier 5: Frontend views, client consumers
    INTEGRATION_TEST = "INTEGRATION_TEST"  # Tier 6: Unit tests, integration suites
    DOCUMENTATION_CONFIG = "DOCUMENTATION_CONFIG"  # Tier 7: Documentation, environment, configs

    @property
    def tier_number(self) -> int:
        return TIER_DEFINITIONS[self]["tier_number"]

    @property
    def tier_name(self) -> str:
        return TIER_DEFINITIONS[self]["name"]

    @property
    def tier_meaning(self) -> str:
        return TIER_DEFINITIONS[self]["meaning"]

    @property
    def tier_description(self) -> str:
        return TIER_DEFINITIONS[self]["short_desc"]


class TierDefinition(TypedDict):
    """Metadata describing architectural tier sequencing properties."""

    tier_number: int
    name: str
    meaning: str
    short_desc: str


TIER_DEFINITIONS: dict[TaskCategory, TierDefinition] = {
    TaskCategory.CONTRACT_API: {
        "tier_number": 1,
        "name": "API / Contract",
        "meaning": "Public APIs, interfaces, schemas, request/response contracts",
        "short_desc": (
            "Public interfaces and request/response contracts that define component boundaries."
        ),
    },
    TaskCategory.CORE_LOGIC: {
        "tier_number": 2,
        "name": "Core Logic",
        "meaning": "Business rules, services, domain/application logic",
        "short_desc": "Business rules and application/service behavior.",
    },
    TaskCategory.DATA_MAPPING: {
        "tier_number": 3,
        "name": "Data / Mapping",
        "meaning": (
            "Database models, repositories, ORM mappings, serialization/data transformations"
        ),
        "short_desc": "Database models, persistence layers, and data transformation structures.",
    },
    TaskCategory.CONSUMER_HANDLER: {
        "tier_number": 4,
        "name": "Handlers / Consumers",
        "meaning": "Event handlers, webhooks, message consumers, adapters",
        "short_desc": (
            "Event subscribers, asynchronous message consumers, and integration adapters."
        ),
    },
    TaskCategory.CLIENT_UI: {
        "tier_number": 5,
        "name": "Client / UI",
        "meaning": "Frontend, UI components, templates, client-facing behavior",
        "short_desc": "Frontend presentations, user interface components, and templates.",
    },
    TaskCategory.INTEGRATION_TEST: {
        "tier_number": 6,
        "name": "Tests / Integration",
        "meaning": "Unit, integration, end-to-end and regression tests",
        "short_desc": "Validation suites, integration checks, and regression tests.",
    },
    TaskCategory.DOCUMENTATION_CONFIG: {
        "tier_number": 7,
        "name": "Documentation / Config",
        "meaning": (
            "Documentation, comments, non-runtime configuration and supporting project files"
        ),
        "short_desc": (
            "Documentation, code comments, and non-runtime supporting project configurations."
        ),
    },
}


@dataclass(frozen=True)
class InformationalChange:
    """Non-behavioral change (e.g. documentation, comments, configuration) noticed in changeset."""

    component: str
    file_path: str
    category: TaskCategory
    reason: str
    diff_snippet: str = ""
    actionability: Actionability = Actionability.INFORMATIONAL


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
    actionability: Actionability = Actionability.UPGRADE
    action_type: TaskActionType = TaskActionType.REQUIRED_CHANGE
    tier_name: str = ""
    tier_meaning: str = ""
    change_significance: ChangeSignificance | None = None
    ai_confidence: str | None = None
    ai_review: dict[str, Any] | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.tier_name and self.category in TIER_DEFINITIONS:
            self.tier_name = TIER_DEFINITIONS[self.category]["name"]
        if not self.tier_meaning and self.category in TIER_DEFINITIONS:
            self.tier_meaning = TIER_DEFINITIONS[self.category]["meaning"]


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
    change_significance: ChangeSignificance = ChangeSignificance.MODERATE_CHANGE
    significance_reasoning: str = ""
    recommended_action: str = ""
    order_rationale: str = ""
    tasks: list[UpgradeTask] = field(default_factory=list)
    informational_changes: list[InformationalChange] = field(default_factory=list)
    optional_suggestions: list[str] = field(default_factory=list)
    ai_plan_review: dict[str, Any] | None = None
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
