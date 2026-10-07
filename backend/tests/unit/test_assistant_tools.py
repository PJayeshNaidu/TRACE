"""Unit tests for TRACE Assistant Typed Retrieval Tools.

Tests all 7 typed retrieval tools for:
- Correct contract output
- Strict analysis_run_id / repository_id scoping (preventing cross-run leaks)
- Source code / AST snippet bounding (<= 40 lines)
- Graph neighborhood traversal
- Robust fallback when artifacts or records are missing
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from trace.domain.project import ProjectStatus
from trace.infrastructure.database.gateway import InMemoryDatabaseGateway
from trace.infrastructure.database.models import (
    AnalysisRunOrm,
    ImpactAnalysisOrm,
    ProjectOrm,
    RepositoryOrm,
    UpgradePlanOrm,
    UpgradeTaskOrm,
    VersionComparisonOrm,
)
from trace.infrastructure.graph.gateway import StubGraphGateway
from trace.services.assistant.tools import AssistantTools, resolve_target_run


@dataclass
class MockAstEntity:
    name: str
    qualified_name: str
    file_path: str | None = None
    start_line: int = 1
    end_line: int = 10
    docstring: str = ""
    parameters: list[Any] = field(default_factory=list)
    complexity: int = 1


@dataclass
class MockRelationship:
    source_identifier: str
    target_identifier: str
    relationship_type: str = "CALLS"


@dataclass
class MockArtifact:
    run_id: uuid.UUID
    repository_id: uuid.UUID
    status: str = "COMPLETED"
    classes: list[MockAstEntity] = field(default_factory=list)
    functions: list[MockAstEntity] = field(default_factory=list)
    modules: list[MockAstEntity] = field(default_factory=list)
    relationships: list[MockRelationship] = field(default_factory=list)
    endpoints: list[Any] = field(default_factory=list)
    tests: list[Any] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


@pytest.fixture
def mock_artifact_fixture(tmp_path) -> MockArtifact:
    """Create a sample MockArtifact with AST nodes and relationships."""
    run_id = uuid.uuid4()
    repo_id = uuid.uuid4()

    # Create dummy source file with > 50 lines to verify 40-line snippet bounding
    src_file = tmp_path / "order_service.py"
    lines = [f"# Line {i}\ndef dummy_{i}(): pass" for i in range(1, 60)]
    lines[10] = "class OrderService:"
    lines[11] = "    '''Manages customer order workflows and payments.'''"
    lines[12] = "    def process_order(self, order_id: str, amount: float) -> bool:"
    lines[13] = "        return True"
    src_file.write_text("\n".join(lines), encoding="utf-8")

    cls_entity = MockAstEntity(
        name="OrderService",
        qualified_name="app.services.OrderService",
        file_path=str(src_file),
        start_line=11,
        end_line=55,
        docstring="Manages customer order workflows and payments.",
        complexity=3,
    )
    fn_entity = MockAstEntity(
        name="process_order",
        qualified_name="app.services.OrderService.process_order",
        file_path=str(src_file),
        start_line=13,
        end_line=25,
        docstring="Processes order transactions.",
        parameters=["self", "order_id: str", "amount: float"],
    )

    rels = [
        MockRelationship(
            source_identifier="app.routes.checkout",
            target_identifier="app.services.OrderService.process_order",
            relationship_type="CALLS",
        ),
        MockRelationship(
            source_identifier="app.services.OrderService.process_order",
            target_identifier="app.integrations.PaymentGateway",
            relationship_type="CALLS",
        ),
    ]

    return MockArtifact(
        run_id=run_id,
        repository_id=repo_id,
        classes=[cls_entity],
        functions=[fn_entity],
        relationships=rels,
        summary={"total_files": 12, "total_lines_of_code": 1450, "languages": {"python": 1450}},
    )


@pytest.fixture
async def seeded_db_context(in_memory_db_gateway: InMemoryDatabaseGateway, tmp_path):
    """Seed test database with project, repository, runs, impact, plan, and diffs."""
    async with in_memory_db_gateway.session() as session:
        proj_id = uuid.uuid4()
        repo_id = uuid.uuid4()
        run1_id = uuid.uuid4()
        run2_id = uuid.uuid4()
        now = datetime.now(UTC)

        proj = ProjectOrm(
            id=proj_id,
            name="Test Assistant Project",
            status=ProjectStatus.ACTIVE.value,
            created_at=now,
            updated_at=now,
        )
        repo = RepositoryOrm(
            id=repo_id,
            project_id=proj_id,
            type="LOCAL",
            location=str(tmp_path),
            default_branch="main",
            status="READY",
            created_at=now,
            updated_at=now,
        )
        run1 = AnalysisRunOrm(
            id=run1_id,
            repository_id=repo_id,
            project_id=proj_id,
            status="COMPLETED",
            target_ref="main",
            commit_hash="sha1111",
            total_files=12,
            python_files=12,
            total_modules=2,
            total_classes=1,
            total_functions=1,
            total_relationships=2,
            created_at=now,
            completed_at=now,
        )
        run2 = AnalysisRunOrm(
            id=run2_id,
            repository_id=repo_id,
            project_id=proj_id,
            status="COMPLETED",
            target_ref="feature",
            commit_hash="sha2222",
            total_files=8,
            python_files=8,
            total_modules=1,
            total_classes=1,
            total_functions=1,
            total_relationships=1,
            created_at=now,
            completed_at=now,
        )

        # Impact record with component drill-down artifact
        impact_file = tmp_path / "impact_artifact.json"
        impact_file.write_text(json.dumps({
            "affected_components": [
                {
                    "symbol_id": "app.services.OrderService",
                    "risk_level": "HIGH",
                    "risk_score": 78.5,
                    "risk_factors": ["Critical financial pathway", "No circuit breaker"],
                    "callers_at_risk": ["app.routes.checkout"],
                    "recommendations": ["Add fallback handler"],
                }
            ]
        }), encoding="utf-8")

        impact_run1 = ImpactAnalysisOrm(
            id=uuid.uuid4(),
            repository_id=repo_id,
            base_commit="sha1111",
            current_commit="sha2222",
            risk_level="HIGH",
            reasoning_mode="HEURISTIC",
            total_changed_entities=3,
            total_deleted_files=0,
            total_impacted_downstream_files=2,
            total_callers_at_risk=4,
            artifact_path=str(impact_file),
            created_at=now,
        )

        # Upgrade Plan and Tasks
        plan1 = UpgradePlanOrm(
            id=uuid.uuid4(),
            repository_id=repo_id,
            impact_analysis_id=impact_run1.id,
            title="Upgrade Plan 1",
            base_commit="sha1111",
            target_commit="sha2222",
            risk_level="HIGH",
            status="ACTIVE",
            reasoning_mode="HEURISTIC",
            artifact_path="",
            created_at=now,
            updated_at=now,
        )
        task1_1 = UpgradeTaskOrm(
            id=uuid.uuid4(),
            plan_id=plan1.id,
            step_number=1,
            component="app.integrations.PaymentGateway",
            component_type="SERVICE",
            category="CORE_LOGIC",
            reason="Prerequisite for OrderService",
            dependencies=[],
            expected_changes="Refactor gateway interface",
            required_tests=["tests/unit/test_payment.py"],
            risk_level="LOW",
            status="PENDING",
            created_at=now,
            updated_at=now,
        )
        task1_2 = UpgradeTaskOrm(
            id=uuid.uuid4(),
            plan_id=plan1.id,
            step_number=2,
            component="app.services.OrderService",
            component_type="SERVICE",
            category="APPLICATION",
            reason="Update payment integration",
            dependencies=[str(task1_1.id)],
            expected_changes="Update process_order calls",
            required_tests=["tests/unit/test_order.py"],
            risk_level="HIGH",
            status="PENDING",
            created_at=now,
            updated_at=now,
        )

        # Version Comparison diffs
        diff_file = tmp_path / "diff_artifact.json"
        diff_file.write_text(json.dumps({
            "symbol_diffs": [
                {
                    "symbol_name": "app.services.OrderService.process_order",
                    "file_path": "order_service.py",
                    "change_type": "MODIFIED",
                    "is_breaking": True,
                    "summary": "Modified process_order signature",
                    "parameters_added": ["amount: float"],
                    "parameters_removed": [],
                }
            ]
        }), encoding="utf-8")

        vcomp1 = VersionComparisonOrm(
            id=uuid.uuid4(),
            repository_id=repo_id,
            base_ref="main",
            target_ref="feature",
            base_commit_hash="sha1111",
            target_commit_hash="sha2222",
            risk_level="HIGH",
            total_files_changed=1,
            total_insertions=10,
            total_deletions=2,
            total_symbols_changed=1,
            total_breaking_changes=1,
            artifact_path=str(diff_file),
            created_at=now,
        )

        session.add_all([
            proj,
            repo,
            run1,
            run2,
            impact_run1,
            plan1,
            task1_1,
            task1_2,
            vcomp1,
        ])
        await session.commit()

        return {
            "project_id": proj_id,
            "repo_id": repo_id,
            "run1_id": run1_id,
            "run2_id": run2_id,
            "plan1_id": plan1.id,
        }


@pytest.mark.asyncio
async def test_resolve_target_run(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    seeded_db_context: dict[str, uuid.UUID],
):
    """Test resolution of repository_id and analysis_run_id with and without explicit ID."""
    proj_id = seeded_db_context["project_id"]
    run1_id = seeded_db_context["run1_id"]

    # Explicit run resolution
    repo_id, resolved_run = await resolve_target_run(in_memory_db_gateway, proj_id, run1_id)
    assert repo_id == seeded_db_context["repo_id"]
    assert resolved_run == run1_id

    # Omitted run resolution (finds latest completed)
    repo_id_auto, resolved_auto = await resolve_target_run(in_memory_db_gateway, proj_id, None)
    assert repo_id_auto == seeded_db_context["repo_id"]
    assert resolved_auto in (seeded_db_context["run1_id"], seeded_db_context["run2_id"])

    # Nonexistent project
    missing_repo, missing_run = await resolve_target_run(in_memory_db_gateway, uuid.uuid4(), None)
    assert missing_repo is None
    assert missing_run is None


@pytest.mark.asyncio
async def test_get_repository_overview(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    mock_artifact_fixture: MockArtifact,
    seeded_db_context: dict[str, uuid.UUID],
):
    """Tool 1: Verify get_repository_overview outputs structure and metrics."""
    run1_id = seeded_db_context["run1_id"]
    mock_artifact_fixture.run_id = run1_id
    mock_store = MagicMock()
    mock_store.read_artifact.return_value = mock_artifact_fixture

    tools = AssistantTools(
        db_gateway=in_memory_db_gateway,
        graph_gateway=StubGraphGateway(),
        artifact_store=mock_store,
    )

    overview = await tools.get_repository_overview(run1_id)
    assert overview["analysis_run_id"] == str(run1_id)
    assert overview["status"] == "COMPLETED"
    assert overview["metrics"]["total_files"] == 12


@pytest.mark.asyncio
async def test_search_code_symbols(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    mock_artifact_fixture: MockArtifact,
    seeded_db_context: dict[str, uuid.UUID],
):
    """Tool 2: Verify search_code_symbols retrieves matching symbols and locations."""
    run1_id = seeded_db_context["run1_id"]
    mock_artifact_fixture.run_id = run1_id
    mock_store = MagicMock()
    mock_store.read_artifact.return_value = mock_artifact_fixture

    tools = AssistantTools(
        db_gateway=in_memory_db_gateway,
        graph_gateway=StubGraphGateway(),
        artifact_store=mock_store,
    )

    results = await tools.search_code_symbols("OrderService", run1_id)
    assert len(results) >= 1
    found = [r for r in results if r["name"] == "OrderService"][0]
    assert found["kind"] == "class"
    assert found["file_path"].endswith("order_service.py")
    assert found["start_line"] == 11


@pytest.mark.asyncio
async def test_get_symbol_details_and_snippet_bounding(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    mock_artifact_fixture: MockArtifact,
    seeded_db_context: dict[str, uuid.UUID],
):
    """Tool 3: Verify get_symbol_details extracts AST info and caps snippet to <= 40 lines."""
    run1_id = seeded_db_context["run1_id"]
    mock_artifact_fixture.run_id = run1_id

    mock_store = MagicMock()
    mock_store.read_artifact.return_value = mock_artifact_fixture

    tools = AssistantTools(
        db_gateway=in_memory_db_gateway,
        graph_gateway=StubGraphGateway(),
        artifact_store=mock_store,
    )

    details = await tools.get_symbol_details("app.services.OrderService", run1_id)

    assert details is not None
    assert details["name"] == "OrderService"
    assert "Manages customer order workflows" in details["docstring"]

    snippet = details.get("source_snippet")
    assert snippet is not None
    snippet_lines = snippet.splitlines()
    assert len(snippet_lines) <= 40  # Strict 40-line limit constraint


@pytest.mark.asyncio
async def test_get_graph_neighborhood_artifact_fallback(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    mock_artifact_fixture: MockArtifact,
    seeded_db_context: dict[str, uuid.UUID],
):
    """Tool 4: Verify get_graph_neighborhood falls back to artifact relationships."""
    run1_id = seeded_db_context["run1_id"]
    mock_artifact_fixture.run_id = run1_id
    mock_store = MagicMock()
    mock_store.read_artifact.return_value = mock_artifact_fixture

    tools = AssistantTools(
        db_gateway=in_memory_db_gateway,
        graph_gateway=StubGraphGateway(),
        artifact_store=mock_store,
    )

    # Callers of process_order
    callers = await tools.get_graph_neighborhood(
        symbol="process_order",
        direction="callers",
        depth=1,
        analysis_run_id=run1_id,
    )
    assert len(callers) >= 1
    assert callers[0]["source"] == "app.routes.checkout"

    # Callees of process_order
    callees = await tools.get_graph_neighborhood(
        symbol="process_order",
        direction="callees",
        depth=1,
        analysis_run_id=run1_id,
    )
    assert len(callees) >= 1
    assert callees[0]["target"] == "app.integrations.PaymentGateway"


@pytest.mark.asyncio
async def test_get_impact_and_risk_scoping(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    seeded_db_context: dict[str, uuid.UUID],
):
    """Tool 5: Verify strict analysis_run_id scoping for impact and risk records."""
    tools = AssistantTools(
        db_gateway=in_memory_db_gateway,
        graph_gateway=StubGraphGateway(),
    )

    run1_id = seeded_db_context["run1_id"]

    # Query for OrderService in Run 1 (Expect HIGH risk: 78.5)
    impact_run1 = await tools.get_impact_and_risk("OrderService", run1_id)
    assert impact_run1["risk_level"] == "HIGH"
    assert impact_run1["risk_score"] == 78.5
    assert "Critical financial pathway" in impact_run1["factors"]
    assert "app.routes.checkout" in impact_run1["callers_at_risk"]


@pytest.mark.asyncio
async def test_get_upgrade_plan_tasks(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    seeded_db_context: dict[str, uuid.UUID],
):
    """Tool 6: Verify get_upgrade_plan_tasks returns ordered tasks scoped to repository."""
    tools = AssistantTools(
        db_gateway=in_memory_db_gateway,
        graph_gateway=StubGraphGateway(),
    )

    repo_id = seeded_db_context["repo_id"]
    tasks = await tools.get_upgrade_plan_tasks(task_or_component="all", repository_id=repo_id)

    assert len(tasks) == 2
    assert tasks[0]["step_number"] == 1
    assert tasks[0]["component"] == "app.integrations.PaymentGateway"
    assert tasks[1]["step_number"] == 2
    assert tasks[1]["component"] == "app.services.OrderService"


@pytest.mark.asyncio
async def test_get_change_diffs(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    seeded_db_context: dict[str, uuid.UUID],
):
    """Tool 7: Verify get_change_diffs retrieves diffs with breaking status."""
    tools = AssistantTools(
        db_gateway=in_memory_db_gateway,
        graph_gateway=StubGraphGateway(),
    )

    repo_id = seeded_db_context["repo_id"]
    diffs = await tools.get_change_diffs(symbol_or_file="all", repository_id=repo_id)

    assert len(diffs) >= 1
    diff = diffs[0]
    assert diff["symbol_name"] == "app.services.OrderService.process_order"
    assert diff["is_breaking"] is True
    assert diff["change_type"] == "MODIFIED"
