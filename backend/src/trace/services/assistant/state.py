"""Typed execution state and reducers for TRACE LangGraph AI Assistant workflow."""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from trace.schemas.assistant import ChatMessage, EvidenceSource


def merge_evidence(
    current: list[dict[str, Any]], new_items: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Reducer combining evidence dictionaries without duplicates, capped at 25 items."""
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []

    for item in current:
        unique_id = (
            item.get("identifier")
            or item.get("qualified_name")
            or item.get("symbol_name")
            or item.get("source")
            or item.get("task_id")
            or (f"step_{item.get('step_number')}" if "step_number" in item else None)
            or item.get("name")
        )
        key = f"{item.get('type')}:{unique_id}"
        if key not in seen:
            seen.add(key)
            merged.append(item)

    for item in new_items:
        unique_id = (
            item.get("identifier")
            or item.get("qualified_name")
            or item.get("symbol_name")
            or item.get("source")
            or item.get("task_id")
            or (f"step_{item.get('step_number')}" if "step_number" in item else None)
            or item.get("name")
        )
        key = f"{item.get('type')}:{unique_id}"
        if key not in seen:
            seen.add(key)
            merged.append(item)

    return merged[:25]


class AssistantState(BaseModel):
    """Typed execution state for the LangGraph assistant workflow."""

    # Request Scope
    project_id: UUID
    analysis_run_id: UUID | None = None
    repository_id: UUID | None = None
    question: str
    history: list[ChatMessage] = Field(default_factory=list)

    # Workflow Reasoning
    intents: list[str] = Field(default_factory=list)
    target_type: Literal["CODE_SYMBOL", "PLAN_TASK", "PROJECT_RUN", "VERSION_CHANGE", "NONE"] = "NONE"
    target_symbols: list[str] = Field(default_factory=list)
    target_task_ids: list[str] = Field(default_factory=list)
    target_project_id: UUID | None = None
    target_analysis_run_id: UUID | None = None
    pending_tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    iteration_count: int = 0
    is_sufficient: bool = False

    # Evidence Store
    raw_evidence: Annotated[list[dict[str, Any]], merge_evidence] = Field(default_factory=list)
    sources: list[EvidenceSource] = Field(default_factory=list)

    # Output
    final_answer: str = ""
    grounding_status: Literal[
        "DETERMINISTIC_GROUNDED",
        "PARTIAL_EVIDENCE",
        "FALLBACK_DETERMINISTIC",
        "INSUFFICIENT_EVIDENCE",
    ] = "INSUFFICIENT_EVIDENCE"
    model_used: str = ""
    suggested_followups: list[str] = Field(default_factory=list)
    error_message: str | None = None
