"""Unit tests for TRACE Assistant Retrieval Service and Candidate Symbol Extractor."""

import uuid
from unittest.mock import AsyncMock, MagicMock
import pytest

from trace.infrastructure.database.gateway import InMemoryDatabaseGateway
from trace.infrastructure.graph.gateway import StubGraphGateway
from trace.services.assistant.retrieval import (
    AssistantRetrievalService,
    CandidateSymbolExtractor,
    CompactEvidenceBundle,
    GraphNeighborEvidence,
    PlanStepEvidence,
    RiskItemEvidence,
)


def test_extract_candidate_symbols():
    """Verify regex and heuristic symbol extraction from natural-language questions."""
    q1 = "Why is api.routes.auth_handler affected by this change?"
    candidates1 = CandidateSymbolExtractor.extract_candidates(q1)
    assert "api.routes.auth_handler" in candidates1

    q2 = "What depends on payment_processor?"
    candidates2 = CandidateSymbolExtractor.extract_candidates(q2)
    assert "payment_processor" in candidates2

    q3 = "Why does Task 1 come before Task 4 in the upgrade plan?"
    candidates3 = CandidateSymbolExtractor.extract_candidates(q3)
    assert "task_1" in candidates3
    assert "task_4" in candidates3

    q4 = "Explain why OrderManager is classified as High Risk"
    candidates4 = CandidateSymbolExtractor.extract_candidates(q4)
    assert "OrderManager" in candidates4


def test_extract_candidate_symbols_with_known_symbols():
    """Verify known symbol prioritization and suffix matching."""
    known = {
        "trace.services.planner.UpgradePlanService",
        "trace.services.auth.login_handler",
    }
    q = "Show me details for login_handler and UpgradePlanService"
    candidates = CandidateSymbolExtractor.extract_candidates(q, known_symbols=known)
    assert "trace.services.auth.login_handler" in candidates
    assert "trace.services.planner.UpgradePlanService" in candidates


def test_compact_bundle_token_budget():
    """Verify CompactEvidenceBundle serialization stays strictly under 1,500 tokens (< 6,000 chars)."""
    bundle = CompactEvidenceBundle(
        project_id=uuid.uuid4(),
        analysis_run_id=uuid.uuid4(),
        matched_symbols=["service.auth", "service.payment"],
    )

    # Add 15 graph paths (exceeding 8 cap)
    for i in range(15):
        bundle.graph_paths.append(
            GraphNeighborEvidence(
                source_symbol=f"caller_{i}.handle_request",
                target_symbol="service.auth",
                relationship_kind="CALLS",
                depth=1 if i < 5 else 2,
                file_path=f"src/caller_{i}.py",
            )
        )
    bundle.total_graph_paths_count = len(bundle.graph_paths)

    # Add risk items
    bundle.risk_items.append(
        RiskItemEvidence(
            symbol_name="service.auth",
            risk_level="HIGH",
            risk_score=85.0,
            factors=["breaking_signature", "blast_radius_15", "missing_tests"],
            recommendations=["Add unit tests", "Add fallback route"],
        )
    )

    # Add plan steps
    for s in range(1, 10):
        bundle.plan_steps.append(
            PlanStepEvidence(
                task_id=f"TASK-{s:03d}",
                title=f"Step {s}: Refactor component {s}",
                step_number=s,
                tier="CORE_LOGIC",
                component=f"component_{s}",
                dependencies=[f"TASK-{s-1:03d}"] if s > 1 else [],
                status="PENDING",
                reason=f"Prerequisite for step {s+1}",
            )
        )

    compact = bundle.to_compact_json()
    import json
    json_str = json.dumps(compact)

    # Assert pruning capped items
    assert len(compact["graph_paths"]) <= 8
    assert len(compact["plan_steps"]) <= 5
    assert len(compact["risk_items"]) <= 5
    assert compact["total_graph_paths"] == 15

    # Budget assertion (< 6000 characters is ~1500 tokens)
    assert len(json_str) < 6000


@pytest.mark.asyncio
async def test_retrieval_service_empty_context():
    """Verify retrieval service gracefully handles nonexistent projects without raising exceptions."""
    db = InMemoryDatabaseGateway()
    graph = StubGraphGateway()
    service = AssistantRetrievalService(db_gateway=db, graph_gateway=graph)

    nonexistent_project_id = uuid.uuid4()
    bundle = await service.retrieve_evidence(
        project_id=nonexistent_project_id,
        question="Why is non_existent_symbol affected?",
    )

    assert bundle.project_id == nonexistent_project_id
    assert "non_existent_symbol" in bundle.matched_symbols
    assert len(bundle.graph_paths) == 0
    assert len(bundle.risk_items) == 0
    assert len(bundle.plan_steps) == 0
    assert len(bundle.sources) >= 0


@pytest.mark.asyncio
async def test_assemble_evidence_sources():
    """Verify evidence source assembly builds typed, valid EvidenceSource items."""
    db = InMemoryDatabaseGateway()
    graph = StubGraphGateway()
    service = AssistantRetrievalService(db_gateway=db, graph_gateway=graph)

    bundle = CompactEvidenceBundle(
        project_id=uuid.uuid4(),
        analysis_run_id=uuid.uuid4(),
        matched_symbols=["auth_service.login"],
    )
    bundle.graph_paths.append(
        GraphNeighborEvidence(
            source_symbol="api.routes.auth",
            target_symbol="auth_service.login",
            relationship_kind="CALLS",
            depth=1,
            file_path="src/api/routes.py",
        )
    )
    bundle.risk_items.append(
        RiskItemEvidence(
            symbol_name="auth_service.login",
            risk_level="HIGH",
            risk_score=80.0,
            factors=["breaking_signature"],
        )
    )
    bundle.plan_steps.append(
        PlanStepEvidence(
            task_id="TASK-001",
            title="Step 1: Update Auth Schema",
            step_number=1,
            tier="CONTRACT_API",
            component="auth_service.login",
            dependencies=[],
            status="PENDING",
            reason="Contract changed",
        )
    )

    sources = service._assemble_sources(bundle)
    assert len(sources) >= 3

    types = {s.type for s in sources}
    assert "graph" in types
    assert "risk" in types
    assert "plan" in types

    for s in sources:
        assert s.identifier
        assert s.summary
        assert isinstance(s.metadata, dict)
