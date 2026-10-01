"""Integration tests for F07 Upgrade Planner API endpoints and lifecycle."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from trace.api.analyses.router import get_artifact_store
from trace.api.health.router import get_db_gateway
from trace.api.impact.router import get_impact_service
from trace.api.repositories.router import get_git_provider
from trace.domain.impact import (
    AnalysisMetadataPayload,
    CallerAtRisk,
    DependencyGraphPayload,
    DetailedImpact,
    GraphEdgePayload,
    GraphNodePayload,
    ImpactAnalysisAggregate,
    ReasoningMode,
    RiskAnalysisPayload,
    RiskFactor,
    RiskLevel,
)
from trace.infrastructure.database.gateway import InMemoryDatabaseGateway
from trace.infrastructure.database.models import Base, ProjectOrm, RepositoryOrm
from trace.infrastructure.git.provider import GitProvider
from trace.infrastructure.storage.artifact_store import FileArtifactStore
from trace.main import create_app
from trace.services.impact import ImpactAnalysisService
from trace.services.planner import UpgradePlanService
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def mock_impact_aggregate() -> ImpactAnalysisAggregate:
    """Fixture providing a multi-hop impact analysis aggregate for plan testing."""
    analysis_id = uuid.uuid4()
    caller_at_risk = CallerAtRisk(
        qualified_name="services.auth_login",
        file_path="src/services/auth.py",
        distance=1,
        call_chain=("services.auth_login", "models.User"),
    )
    detailed_1 = DetailedImpact(
        file="src/models/user.py",
        entity="models.User",
        entity_type="class",
        lines_affected=(10, 25),
        diff_snippet="+ def verify_token(self): pass",
        change_summary="Added verify_token method",
        remediation_guidance="Update call sites",
        justification="Core model changed",
        outbound_calls=(),
        inbound_callers=("services.auth_login",),
        callers_at_risk=(caller_at_risk,),
        downstream_dependent_files=(),
    )
    detailed_2 = DetailedImpact(
        file="src/services/auth.py",
        entity="services.auth_login",
        entity_type="function",
        lines_affected=(45, 60),
        diff_snippet="user.verify_token()",
        change_summary="Calls verify_token",
        remediation_guidance="Adopt new signature",
        justification="Caller impacted",
        outbound_calls=("models.User",),
        inbound_callers=(),
        callers_at_risk=(),
        downstream_dependent_files=(),
    )
    nodes = (
        GraphNodePayload(
            changed_entity="models.User",
            file="src/models/user.py",
            inbound_callers=("services.auth_login",),
            outbound_calls=(),
        ),
        GraphNodePayload(
            changed_entity="services.auth_login",
            file="src/services/auth.py",
            inbound_callers=(),
            outbound_calls=("models.User",),
        ),
    )
    edges = (GraphEdgePayload(caller="services.auth_login", callee="models.User"),)
    graph = DependencyGraphPayload(nodes=nodes, edges=edges, mermaid="graph TD;")
    risk = RiskAnalysisPayload(
        risk_level=RiskLevel.MEDIUM,
        key_risk_factors=(
            RiskFactor(
                factor="Contract modified",
                severity="MEDIUM",
                justification="Signature change",
            ),
        ),
        ci_cd_recommendations=("Run test suite",),
        actionable_remediation_plan=(),
    )
    meta = AnalysisMetadataPayload(
        analysis_id=analysis_id,
        repository="test/repo",
        base_commit="HEAD~1",
        current_commit="HEAD",
        reasoning_mode=ReasoningMode.HEURISTIC,
        total_changed_entities=2,
        total_deleted_files=0,
        total_impacted_downstream_files=1,
        total_callers_at_risk=1,
    )
    return ImpactAnalysisAggregate(
        metadata=meta,
        summary="Test impact summary",
        detailed_impacts=(detailed_1, detailed_2),
        dependency_graph=graph,
        risk_analysis=risk,
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def mock_impact_dict(mock_impact_aggregate: ImpactAnalysisAggregate) -> dict[str, Any]:
    """Fixture providing a 4-key JSON schema dictionary as produced by F06 get_analysis()."""
    meta = mock_impact_aggregate.metadata
    return {
        "analysis_metadata": {
            "analysis_id": str(meta.analysis_id),
            "repository": meta.repository,
            "base_commit": meta.base_commit,
            "current_commit": meta.current_commit,
            "reasoning_mode": meta.reasoning_mode.value,
            "total_changed_entities": meta.total_changed_entities,
            "total_deleted_files": meta.total_deleted_files,
            "total_impacted_downstream_files": meta.total_impacted_downstream_files,
            "total_callers_at_risk": meta.total_callers_at_risk,
        },
        "impact_analysis": {
            "summary": mock_impact_aggregate.summary,
            "detailed_impacts": [
                {
                    "file": d.file,
                    "entity": d.entity,
                    "entity_type": d.entity_type,
                    "lines_affected": list(d.lines_affected),
                    "diff_snippet": d.diff_snippet,
                    "change_summary": d.change_summary,
                    "remediation_guidance": d.remediation_guidance,
                    "justification": d.justification,
                    "outbound_calls": list(d.outbound_calls),
                    "inbound_callers": list(d.inbound_callers),
                    "callers_at_risk": [
                        {
                            "qualified_name": c.qualified_name,
                            "file_path": c.file_path,
                            "distance": c.distance,
                            "call_chain": list(c.call_chain),
                        }
                        for c in d.callers_at_risk
                    ],
                    "downstream_dependent_files": list(d.downstream_dependent_files),
                }
                for d in mock_impact_aggregate.detailed_impacts
            ],
        },
        "dependency_graph": {
            "nodes": [
                {
                    "changed_entity": n.changed_entity,
                    "file": n.file,
                    "downstream_dependent_files": list(n.downstream_dependent_files),
                    "inbound_callers": list(n.inbound_callers),
                    "outbound_calls": list(n.outbound_calls),
                }
                for n in mock_impact_aggregate.dependency_graph.nodes
            ],
            "edges": [
                {
                    "caller": e.caller,
                    "callee": e.callee,
                    "relationship": e.relationship,
                }
                for e in mock_impact_aggregate.dependency_graph.edges
            ],
            "mermaid": mock_impact_aggregate.dependency_graph.mermaid,
        },
        "risk_analysis": {
            "risk_level": mock_impact_aggregate.risk_analysis.risk_level.value,
            "key_risk_factors": [
                {
                    "factor": f.factor,
                    "severity": f.severity,
                    "justification": f.justification,
                }
                for f in mock_impact_aggregate.risk_analysis.key_risk_factors
            ],
            "ci_cd_recommendations": list(
                mock_impact_aggregate.risk_analysis.ci_cd_recommendations
            ),
            "actionable_remediation_plan": [],
        },
    }


@pytest.fixture
async def test_env(tmp_path: Path):
    """Setup in-memory DB and test app client."""
    db_gateway = InMemoryDatabaseGateway()
    async with db_gateway._engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Insert test project and repo
    project_id = uuid.uuid4()
    repo_id = uuid.uuid4()
    async with db_gateway.session() as session:
        proj = ProjectOrm(
            id=project_id,
            name="Test Project",
            status="ACTIVE",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        session.add(proj)
        repo = RepositoryOrm(
            id=repo_id,
            project_id=project_id,
            type="LOCAL",
            location="/tmp/test_repo",
            status="CONNECTED",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        session.add(repo)
        await session.commit()

    artifact_store = FileArtifactStore(base_path=tmp_path / "artifacts")
    mock_impact_service = MagicMock(spec=ImpactAnalysisService)
    mock_git = MagicMock(spec=GitProvider)

    planner_svc = UpgradePlanService(
        db_gateway=db_gateway,
        artifact_store=artifact_store,
        impact_service=mock_impact_service,
        git_provider=mock_git,
    )

    app: FastAPI = create_app()
    app.dependency_overrides[get_db_gateway] = lambda: db_gateway
    app.dependency_overrides[get_artifact_store] = lambda: artifact_store
    app.dependency_overrides[get_git_provider] = lambda: mock_git
    app.dependency_overrides[get_impact_service] = lambda: mock_impact_service

    # Attach singleton planner service to app.state
    app.state.planner_service = planner_svc

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield {
            "client": client,
            "repo_id": repo_id,
            "db_gateway": db_gateway,
            "impact_service": mock_impact_service,
            "planner_service": planner_svc,
        }

    await db_gateway.dispose()


@pytest.mark.asyncio
async def test_generate_and_retrieve_upgrade_plan(test_env, mock_impact_dict):
    """US1: Verify plan generation from F06 dictionary artifact and retrieval."""
    client: AsyncClient = test_env["client"]
    repo_id = test_env["repo_id"]
    impact_svc = test_env["impact_service"]
    # F06 get_analysis() returns dict
    impact_svc.get_analysis = AsyncMock(return_value=mock_impact_dict)

    # 1. Generate plan
    resp = await client.post(
        "/api/v1/upgrade-plans/generate",
        json={
            "repository_id": str(repo_id),
            "impact_analysis_id": mock_impact_dict["analysis_metadata"]["analysis_id"],
            "title": "Authentication Refactor Plan",
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()

    plan_id = data["id"]
    assert data["title"] == "Authentication Refactor Plan"
    assert data["status"] == "DRAFT"
    assert data["risk_level"] == "MEDIUM"
    assert data["summary_metrics"]["total_tasks"] == 2
    assert data["summary_metrics"]["progress_percentage"] == 0.0

    tasks = data["tasks"]
    assert len(tasks) == 2

    # Prerequisite models.User must have step_number 1, services.auth_login step_number 2
    user_task = next(t for t in tasks if "User" in t["component"])
    auth_task = next(t for t in tasks if "auth_login" in t["component"])
    assert user_task["step_number"] < auth_task["step_number"]
    assert user_task["step_number"] == 1
    assert auth_task["step_number"] == 2

    # Verify task metadata (US2)
    assert user_task["reason"] != ""
    assert user_task["expected_changes"] != ""
    assert len(user_task["required_tests"]) > 0
    assert user_task["evidence"] is not None
    assert user_task["evidence"]["diff_snippet"] != ""

    # 2. Retrieve plan via GET
    get_resp = await client.get(f"/api/v1/upgrade-plans/{plan_id}")
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["id"] == plan_id
    assert len(get_data["tasks"]) == 2


@pytest.mark.asyncio
async def test_generate_plan_via_evaluate_impact_on_the_fly(test_env, mock_impact_aggregate):
    """Verify plan generation without impact_analysis_id calls evaluate_impact with correct args."""
    client: AsyncClient = test_env["client"]
    repo_id = test_env["repo_id"]
    impact_svc = test_env["impact_service"]
    impact_svc.evaluate_impact = AsyncMock(return_value=mock_impact_aggregate)

    resp = await client.post(
        "/api/v1/upgrade-plans/generate",
        json={
            "repository_id": str(repo_id),
            "base_ref": "v1.0.0",
            "target_ref": "v2.0.0",
            "title": "On-The-Fly Plan",
            "llm_config": {
                "enabled": True,
                "api_key": "sk-openrouter-key",
                "model": "anthropic/claude-3.5-sonnet",
            },
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["title"] == "On-The-Fly Plan"

    # Verify evaluate_impact was called with openrouter_api_key, NOT unexpected kwargs
    impact_svc.evaluate_impact.assert_awaited_once_with(
        repository_id=repo_id,
        base_ref="v1.0.0",
        target_ref="v2.0.0",
        openrouter_api_key="sk-openrouter-key",
        openrouter_model="anthropic/claude-3.5-sonnet",
    )


@pytest.mark.asyncio
async def test_task_lifecycle_and_progress_recalculation(test_env, mock_impact_dict):
    """US3: Verify status transitions, progress updates, and automatic completion."""
    client: AsyncClient = test_env["client"]
    repo_id = test_env["repo_id"]
    impact_svc = test_env["impact_service"]
    impact_svc.get_analysis = AsyncMock(return_value=mock_impact_dict)

    # Generate plan
    gen_resp = await client.post(
        "/api/v1/upgrade-plans/generate",
        json={
            "repository_id": str(repo_id),
            "impact_analysis_id": mock_impact_dict["analysis_metadata"]["analysis_id"],
        },
    )
    plan_id = gen_resp.json()["id"]
    tasks = gen_resp.json()["tasks"]
    task1_id = tasks[0]["id"]
    task2_id = tasks[1]["id"]

    # 1. Update task 1 to IN_PROGRESS
    p1 = await client.patch(
        f"/api/v1/upgrade-plans/{plan_id}/tasks/{task1_id}",
        json={"status": "IN_PROGRESS", "notes": "Working on user model"},
    )
    assert p1.status_code == 200
    assert p1.json()["status"] == "IN_PROGRESS"
    assert p1.json()["notes"] == "Working on user model"

    # Plan should be IN_PROGRESS
    plan_resp = await client.get(f"/api/v1/upgrade-plans/{plan_id}")
    assert plan_resp.json()["status"] == "IN_PROGRESS"
    assert plan_resp.json()["summary_metrics"]["in_progress_tasks"] == 1

    # 2. Complete task 1
    p2 = await client.patch(
        f"/api/v1/upgrade-plans/{plan_id}/tasks/{task1_id}",
        json={"status": "COMPLETED"},
    )
    assert p2.status_code == 200
    plan_resp2 = await client.get(f"/api/v1/upgrade-plans/{plan_id}")
    assert plan_resp2.json()["summary_metrics"]["completed_tasks"] == 1
    assert plan_resp2.json()["summary_metrics"]["progress_percentage"] == 50.0

    # 3. Complete task 2 -> Plan should transition to COMPLETED (100%)
    p3 = await client.patch(
        f"/api/v1/upgrade-plans/{plan_id}/tasks/{task2_id}",
        json={"status": "COMPLETED"},
    )
    assert p3.status_code == 200
    plan_resp3 = await client.get(f"/api/v1/upgrade-plans/{plan_id}")
    assert plan_resp3.json()["status"] == "COMPLETED"
    assert plan_resp3.json()["summary_metrics"]["completed_tasks"] == 2
    assert plan_resp3.json()["summary_metrics"]["progress_percentage"] == 100.0


@pytest.mark.asyncio
async def test_list_tasks_filtering_and_pagination(test_env, mock_impact_aggregate):
    """US3: Verify querying tasks with status, category, and pagination."""
    client: AsyncClient = test_env["client"]
    repo_id = test_env["repo_id"]
    impact_svc = test_env["impact_service"]
    impact_svc.get_analysis = AsyncMock(return_value=mock_impact_aggregate)

    gen_resp = await client.post(
        "/api/v1/upgrade-plans/generate",
        json={
            "repository_id": str(repo_id),
            "impact_analysis_id": str(mock_impact_aggregate.metadata.analysis_id),
        },
    )
    plan_id = gen_resp.json()["id"]

    # Filter by PENDING
    resp_pending = await client.get(f"/api/v1/upgrade-plans/{plan_id}/tasks?status=PENDING")
    assert resp_pending.status_code == 200
    assert resp_pending.json()["total"] == 2

    # Filter with non-matching status
    resp_done = await client.get(f"/api/v1/upgrade-plans/{plan_id}/tasks?status=COMPLETED")
    assert resp_done.status_code == 200
    assert resp_done.json()["total"] == 0

    # Pagination limit=1
    resp_paged = await client.get(f"/api/v1/upgrade-plans/{plan_id}/tasks?limit=1&offset=0")
    assert resp_paged.status_code == 200
    assert len(resp_paged.json()["items"]) == 1
    assert resp_paged.json()["total"] == 2


@pytest.mark.asyncio
async def test_list_repository_plans(test_env, mock_impact_dict):
    """Verify listing all upgrade plans for a repository."""
    client: AsyncClient = test_env["client"]
    repo_id = test_env["repo_id"]
    impact_svc = test_env["impact_service"]
    impact_svc.get_analysis = AsyncMock(return_value=mock_impact_dict)

    # Generate plan 1
    await client.post(
        "/api/v1/upgrade-plans/generate",
        json={
            "repository_id": str(repo_id),
            "impact_analysis_id": mock_impact_dict["analysis_metadata"]["analysis_id"],
            "title": "Plan 1",
        },
    )

    list_resp = await client.get(f"/api/v1/repositories/{repo_id}/upgrade-plans")
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert data["total"] >= 1
    assert data["items"][0]["title"] == "Plan 1"


@pytest.mark.asyncio
async def test_empty_impact_plan_generation(test_env):
    """US1 edge case: Zero-impact analysis produces clean empty plan."""
    client: AsyncClient = test_env["client"]
    repo_id = test_env["repo_id"]
    impact_svc = test_env["impact_service"]

    empty_analysis_id = uuid.uuid4()
    empty_aggregate = ImpactAnalysisAggregate(
        metadata=AnalysisMetadataPayload(
            analysis_id=empty_analysis_id,
            repository="test/repo",
            base_commit="HEAD~1",
            current_commit="HEAD",
            reasoning_mode=ReasoningMode.HEURISTIC,
            total_changed_entities=0,
            total_deleted_files=0,
            total_impacted_downstream_files=0,
            total_callers_at_risk=0,
        ),
        summary="No impacts detected",
        detailed_impacts=(),
        dependency_graph=DependencyGraphPayload(nodes=(), edges=(), mermaid=""),
        risk_analysis=RiskAnalysisPayload(
            risk_level=RiskLevel.LOW,
            key_risk_factors=(),
            ci_cd_recommendations=(),
            actionable_remediation_plan=(),
        ),
        created_at=datetime.now(UTC),
    )
    impact_svc.get_analysis = AsyncMock(return_value=empty_aggregate)

    resp = await client.post(
        "/api/v1/upgrade-plans/generate",
        json={
            "repository_id": str(repo_id),
            "impact_analysis_id": str(empty_analysis_id),
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "COMPLETED"
    assert data["summary_metrics"]["total_tasks"] == 0
    assert len(data["tasks"]) == 0
