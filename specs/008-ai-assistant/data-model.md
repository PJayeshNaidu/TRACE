# Data Model & Schema Contracts: Feature 008 — AI Assistant (TRACE F10)

**Feature Branch**: `008-ai-assistant` | **Date**: 2026-10-05 | **Spec Reference**: [spec.md](spec.md)

This document specifies the data contracts, Pydantic validation schemas, intermediate evidence structures, and relationship models for the **TRACE F10 AI Assistant**.

---

## 1. Schema Definitions (`backend/src/trace/schemas/assistant.py`)

All schemas inherit from Pydantic `BaseModel` (v2) with strict typing.

### 1.1 `EvidenceSource`
Represents an individual verifiable evidence element backing an assistant answer.

```python
from typing import Any, Literal
from pydantic import BaseModel, Field


class EvidenceSource(BaseModel):
    """Verifiable repository evidence element grounding an assistant answer."""

    type: Literal["graph", "risk", "plan", "diff"] = Field(
        ...,
        description="Evidence domain category: graph relationship, risk evaluation, upgrade plan step, or syntax diff hunk.",
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
```

### 1.2 `AssistantQueryRequest`
Represents the incoming question payload submitted by the Observatory UI or API client.

```python
from uuid import UUID
from pydantic import BaseModel, Field


class AssistantQueryRequest(BaseModel):
    """Request payload to query the TRACE AI Code Intelligence Assistant."""

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
```

### 1.3 `AssistantQueryResponse`
Represents the complete answer returned to the client.

```python
from pydantic import BaseModel, Field


class AssistantQueryResponse(BaseModel):
    """Response payload containing synthesized answer, evidence sources, and model attribution."""

    answer: str = Field(
        ...,
        description="Synthesized natural-language response strictly grounded in repository evidence.",
    )
    sources: list[EvidenceSource] = Field(
        default_factory=list,
        description="Ordered list of verified evidence sources supporting the answer.",
    )
    model_used: str = Field(
        ...,
        description="Identifier of the LLM model used for synthesis, or 'deterministic-fallback' if synthesized offline.",
        examples=["mistralai/mistral-7b-instruct:free", "deterministic-fallback"],
    )
```

---

## 2. Intermediate Retrieval Data Structures (`backend/src/trace/services/assistant/retrieval.py`)

These internal dataclasses encapsulate data extracted across TRACE subsystem boundaries before token budgeting and synthesis.

```python
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass(slots=True)
class GraphNeighborEvidence:
    """Graph adjacency entry extracted from Neo4j."""
    source_symbol: str
    target_symbol: str
    relationship_kind: str
    depth: int
    file_path: str | None = None


@dataclass(slots=True)
class RiskItemEvidence:
    """Risk evaluation entry extracted from F05/F06."""
    symbol_name: str
    risk_level: str
    risk_score: float
    factors: list[str]
    recommendations: list[str]


@dataclass(slots=True)
class PlanStepEvidence:
    """Upgrade plan step extracted from F07."""
    task_id: str
    title: str
    step_number: int
    tier: str
    component: str
    dependencies: list[str]
    status: str


@dataclass(slots=True)
class DiffHunkEvidence:
    """AST syntax delta entry extracted from F04."""
    symbol_name: str
    file_path: str
    change_type: str
    is_breaking: bool
    summary: str


@dataclass(slots=True)
class CompactEvidenceBundle:
    """Unified compact evidence container submitted to the prompt synthesizer."""
    project_id: UUID
    analysis_run_id: UUID | None
    matched_symbols: list[str] = field(default_factory=list)
    graph_paths: list[GraphNeighborEvidence] = field(default_factory=list)
    risk_items: list[RiskItemEvidence] = field(default_factory=list)
    plan_steps: list[PlanStepEvidence] = field(default_factory=list)
    diff_hunks: list[DiffHunkEvidence] = field(default_factory=list)
    sources: list[EvidenceSource] = field(default_factory=list)

    def to_compact_json(self) -> dict[str, Any]:
        """Convert to a pruned JSON dictionary guaranteed to be < 1,500 tokens."""
        return {
            "matched_symbols": self.matched_symbols[:5],
            "graph_paths": [
                {
                    "from": g.source_symbol,
                    "to": g.target_symbol,
                    "rel": g.relationship_kind,
                    "depth": g.depth,
                }
                for g in self.graph_paths[:10]
            ],
            "risk_items": [
                {
                    "symbol": r.symbol_name,
                    "level": r.risk_level,
                    "score": r.risk_score,
                    "factors": r.factors[:3],
                }
                for r in self.risk_items[:5]
            ],
            "plan_steps": [
                {
                    "step": p.step_number,
                    "task": p.title,
                    "tier": p.tier,
                    "deps": p.dependencies,
                    "status": p.status,
                }
                for p in self.plan_steps[:5]
            ],
            "diff_hunks": [
                {
                    "symbol": d.symbol_name,
                    "change": d.change_type,
                    "breaking": d.is_breaking,
                }
                for d in self.diff_hunks[:5]
            ],
        }
```

---

## 3. End-to-End Information Flow Diagram

```text
User Question: "Why is checkout_service high risk?"
                       │
                       ▼
   ┌────────────────────────────────────────────────────────┐
   │ Deterministic Symbol Extraction (Regex & Index Match)  │
   │ Target: "checkout_service"                             │
   └───────────────────────┬────────────────────────────────┘
                           │
             ┌─────────────┼─────────────┬─────────────┐
             ▼             ▼             ▼             ▼
        [Neo4j G^T]    [F05/F06 Risk] [F07 Tasks] [F04 Diffs]
        Callers (15)   Risk: HIGH     Task #4     Sig Changed
             │             │             │             │
             └─────────────┼─────────────┴─────────────┘
                           │
                           ▼
   ┌────────────────────────────────────────────────────────┐
   │ CompactEvidenceBundle (< 1,500 Tokens)                 │
   │ + Sources: [GraphNode, RiskFactor, TaskStep]           │
   └───────────────────────┬────────────────────────────────┘
                           │
                           ▼
   ┌────────────────────────────────────────────────────────┐
   │ LLM Synthesis (OpenRouter: Mistral 7B Instruct Free)   │
   │ (Fallback to deterministic markdown if offline)        │
   └───────────────────────┬────────────────────────────────┘
                           │
                           ▼
   ┌────────────────────────────────────────────────────────┐
   │ AssistantQueryResponse                                 │
   │ - answer: "checkout_service is classified as..."       │
   │ - sources: [EvidenceSource(...), ...]                  │
   │ - model_used: "mistralai/mistral-7b-instruct:free"     │
   └────────────────────────────────────────────────────────┘
```
