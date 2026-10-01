"""Architectural tier classification engine for F07 Upgrade Planner."""

from __future__ import annotations

from pathlib import Path
from trace.domain.plan import TaskCategory


class TierMapper:
    """Classifies code symbols, files, and endpoints into 7 architectural categories."""

    TIER_WEIGHTS: dict[TaskCategory, int] = {
        TaskCategory.CONTRACT_API: 1,
        TaskCategory.CORE_LOGIC: 2,
        TaskCategory.DATA_MAPPING: 3,
        TaskCategory.CONSUMER_HANDLER: 4,
        TaskCategory.CLIENT_UI: 5,
        TaskCategory.INTEGRATION_TEST: 6,
        TaskCategory.DOCUMENTATION_CONFIG: 7,
    }

    @classmethod
    def classify(
        cls,
        entity_name: str,
        entity_type: str = "function",
        file_path: str = "",
    ) -> TaskCategory:
        """Deterministically determine the architectural TaskCategory for an entity."""
        normalized_path = file_path.replace("\\", "/").lower()
        lowered_name = entity_name.lower()
        lowered_type = entity_type.lower()

        # 1. Tests (check first to avoid test API mocks being classified as contracts)
        if (
            lowered_type in ("test", "testunit", "testfunction")
            or normalized_path.startswith("tests/")
            or "/tests/" in normalized_path
            or normalized_path.endswith("_test.py")
            or Path(normalized_path).name.startswith("test_")
            or lowered_name.startswith("test_")
            or lowered_name.startswith("test")
        ):
            return TaskCategory.INTEGRATION_TEST

        # 2. Non-code Documentation & Config
        if (
            normalized_path.endswith(
                (".md", ".rst", ".txt", ".json", ".yaml", ".yml", ".toml", ".ini", ".env")
            )
            or "dockerfile" in normalized_path
            or "/docs/" in normalized_path
            or normalized_path.startswith("docs/")
            or "/.github/" in normalized_path
            or normalized_path.startswith(".github/")
        ):
            return TaskCategory.DOCUMENTATION_CONFIG

        # 3. Client & UI
        if (
            lowered_type in ("view", "page", "component", "ui")
            or normalized_path.startswith("frontend/")
            or "/frontend/" in normalized_path
            or "/components/" in normalized_path
            or "/pages/" in normalized_path
            or "/views/" in normalized_path
            or "/templates/" in normalized_path
            or normalized_path.endswith("app.py")
        ):
            return TaskCategory.CLIENT_UI

        # 4. Contracts & Public APIs
        if (
            lowered_type in ("endpoint", "route", "api")
            or "/api/" in normalized_path
            or normalized_path.startswith("api/")
            or "/routes/" in normalized_path
            or "/endpoints/" in normalized_path
            or "/v1/" in normalized_path
            or "/v2/" in normalized_path
            or "contract" in normalized_path
            or "openapi" in normalized_path
            or lowered_name.endswith(("api", "endpoint", "route"))
        ):
            return TaskCategory.CONTRACT_API

        # 5. Data & Schema Mapping
        if (
            lowered_type in ("table", "database", "model", "schema")
            or "/models/" in normalized_path
            or normalized_path.startswith("models/")
            or "/schemas/" in normalized_path
            or normalized_path.startswith("schemas/")
            or "/alembic/" in normalized_path
            or normalized_path.startswith("alembic/")
            or "/migrations/" in normalized_path
            or normalized_path.startswith("migrations/")
            or "/database/" in normalized_path
            or normalized_path.startswith("database/")
            or normalized_path.endswith(("models.py", "schema.py", "entities.py"))
            or lowered_name.endswith(("model", "orm", "table", "schema", "record"))
        ):
            return TaskCategory.DATA_MAPPING

        # 6. Consumer / Handler
        if (
            lowered_type in ("worker", "task", "handler", "consumer", "webhook", "listener")
            or "/handlers/" in normalized_path
            or normalized_path.startswith("handlers/")
            or "/workers/" in normalized_path
            or normalized_path.startswith("workers/")
            or "/webhooks/" in normalized_path
            or normalized_path.startswith("webhooks/")
            or "/celery/" in normalized_path
            or normalized_path.startswith("celery/")
            or "/tasks/" in normalized_path
            or normalized_path.startswith("tasks/")
            or "/events/" in normalized_path
            or normalized_path.startswith("events/")
            or lowered_name.endswith(
                ("handler", "worker", "webhook", "consumer", "listener", "job")
            )
        ):
            return TaskCategory.CONSUMER_HANDLER

        # 7. Default: Core Domain Logic
        return TaskCategory.CORE_LOGIC

    @classmethod
    def get_tier_weight(cls, category: TaskCategory) -> int:
        """Return numeric sort weight for a category (lower runs earlier)."""
        return cls.TIER_WEIGHTS.get(category, 99)
