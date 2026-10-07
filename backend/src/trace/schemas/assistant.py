"""Pydantic schemas and contracts for TRACE F10 AI Assistant."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    """Dialogue turn in the conversational context."""

    model_config = ConfigDict(extra="ignore")

    role: Literal["user", "assistant"] = Field(
        ...,
        description="Role of the message author.",
    )
    content: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="Text content of the message.",
    )


class EvidenceSource(BaseModel):
    """Verifiable repository evidence element grounding an assistant answer."""

    model_config = ConfigDict(extra="ignore")

    type: Literal["graph", "risk", "plan", "diff", "ast", "test"] = Field(
        ...,
        description="Evidence domain category: graph relationship, risk evaluation, upgrade plan step, syntax diff hunk, AST metadata, or test reference.",
    )
    identifier: str = Field(
        ...,
        description="Unique identifier for the evidence item (e.g. node qualified name, rule ID, task ID, or file line span).",
        examples=["trace.services.planner.UpgradePlanService", "TASK-004", "BREAKING_SIGNATURE"],
    )
    summary: str = Field(
        ...,
        description="Concise human-readable summary of the evidence finding.",
        examples=["Direct caller: api.routes.auth_handler -> auth_service.login (depth 1)"],
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured key-value payload containing raw metrics, line ranges, or relationship properties.",
    )


class AssistantQueryRequest(BaseModel):
    """Request payload to query the TRACE AI Code Intelligence Assistant."""

    model_config = ConfigDict(extra="forbid")

    project_id: UUID = Field(
        ...,
        description="Authoritative UUID of the active TRACE project.",
    )
    analysis_run_id: UUID | None = Field(
        default=None,
        description="Optional UUID of a specific repository analysis run for targeted contextual scoping.",
    )
    question: str = Field(
        ...,
        min_length=3,
        max_length=1000,
        description="Natural-language question regarding code dependencies, risk metrics, or upgrade plans.",
        examples=[
            "Why is api.routes.auth_handler affected by this change?",
            "What depends on payment_processor?",
            "Why is component checkout_service classified as High Risk?",
            "Why does task 1 come before task 4 in the upgrade plan?",
        ],
    )
    history: list[ChatMessage] = Field(
        default_factory=list,
        description="Recent dialogue history turns (at most 2 user/assistant pairs evaluated).",
    )


class AssistantQueryResponse(BaseModel):
    """Response payload containing synthesized answer, evidence sources, and model attribution."""

    model_config = ConfigDict(extra="ignore")

    answer: str = Field(
        ...,
        description="Synthesized natural-language response strictly grounded in repository evidence.",
    )
    intent: str = Field(
        default="GENERAL_OBSERVATORY",
        description="Identified primary query intent.",
    )
    sources: list[EvidenceSource] = Field(
        default_factory=list,
        description="Ordered list of verified evidence sources supporting the answer.",
    )
    grounding_status: Literal[
        "DETERMINISTIC_GROUNDED",
        "PARTIAL_EVIDENCE",
        "FALLBACK_DETERMINISTIC",
        "INSUFFICIENT_EVIDENCE",
    ] = Field(
        default="FALLBACK_DETERMINISTIC",
        description="Evidence grounding status indicating completeness of repository facts.",
    )
    model_used: str = Field(
        ...,
        description="Identifier of the LLM model used for synthesis, or 'offline-deterministic-fallback'.",
        examples=["meta-llama/llama-3.3-70b-instruct:free", "offline-deterministic-fallback"],
    )
    suggested_followups: list[str] = Field(
        default_factory=list,
        description="Context-aware follow-up question suggestions.",
    )
