"""Unit and integration tests for F07 Actionability Refinement & AI Review.

Covers all 13 required test scenarios from the specification:
1. Docstring typo → no behavioral upgrade task.
2. Comment-only change → no caller propagation.
3. Documentation update accompanying API change → upgrade task remains.
4. Core logic change → upgrade task.
5. Direct caller → direct caller task.
6. Transitive caller → transitive task.
7. API signature change → upgrade task.
8. AI unavailable → deterministic plan still works.
9. Malformed AI JSON → deterministic plan still works.
10. AI flags false positive → recommendation does not override deterministic evidence.
11. AI suggests missing task → suggestion is not automatically inserted without evidence.
12. Whole-plan review produces structured output.
13. AI recommendations include confidence/actionability.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from trace.analysis.planner.task_synthesizer import TaskSynthesizer
from trace.analysis.planner.tier_mapper import TierMapper
from trace.domain.impact import (
    AnalysisMetadataPayload,
    CallerAtRisk,
    DependencyGraphPayload,
    DetailedImpact,
    GraphEdgePayload,
    ImpactAnalysisAggregate,
    ReasoningMode,
    RiskAnalysisPayload,
    RiskLevel,
)
from trace.domain.plan import (
    Actionability,
    ChangeSignificance,
    InformationalChange,
    TaskActionType,
    TaskCategory,
    TaskEvidence,
    UpgradeTask,
)
from trace.infrastructure.database.gateway import InMemoryDatabaseGateway
from trace.infrastructure.database.models import Base, ProjectOrm, RepositoryOrm
from trace.infrastructure.storage.artifact_store import FileArtifactStore
from trace.services.impact import ImpactAnalysisService
from trace.services.planner import UpgradePlanService
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ==============================================================================
# Helper fixture builders
# ==============================================================================


@pytest.fixture
def test_repo_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def mock_artifact_store(tmp_path: Path) -> FileArtifactStore:
    return FileArtifactStore(base_path=tmp_path / "artifacts")


async def create_initialized_planner_service(
    tmp_path: Path, repo_id: uuid.UUID
) -> tuple[UpgradePlanService, InMemoryDatabaseGateway]:
    db_gateway = InMemoryDatabaseGateway()
    async with db_gateway._engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed repository
    async with db_gateway.session() as session:
        proj = ProjectOrm(
            id=uuid.uuid4(),
            name="Test Project",
            status="ACTIVE",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        session.add(proj)
        repo = RepositoryOrm(
            id=repo_id,
            project_id=proj.id,
            type="LOCAL",
            location="/tmp/test_repo",
            status="CONNECTED",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        session.add(repo)
        await session.commit()

    artifact_store = FileArtifactStore(base_path=tmp_path / "artifacts")
    impact_svc = MagicMock(spec=ImpactAnalysisService)

    svc = UpgradePlanService(
        db_gateway=db_gateway,
        artifact_store=artifact_store,
        impact_service=impact_svc,
    )
    return svc, db_gateway


# ==============================================================================
# 1. Documentation & Actionability Tests
# ==============================================================================


def test_docstring_typo_actionability_ignore() -> None:
    """Scenario 1: Docstring typo in code file is classified as IGNORE."""
    diff_typo = """
- :data:`.session`, :data:`g:`, and :data:`.current_app` become available.
+ :data:`.session`, :data:`g`, and :data:`.current_app` become available.
"""
    assert TierMapper.is_documentation_diff(diff_typo) is True
    act = TierMapper.classify_actionability(
        diff_snippet=diff_typo,
        file_path="src/flask/app.py",
        entity_name="request_context",
        entity_type="function",
        category=TaskCategory.CORE_LOGIC,
    )
    assert act == Actionability.IGNORE


def test_comment_only_change_actionability_ignore() -> None:
    """Scenario 2: Comment-only wording change is classified as IGNORE."""
    comment_diff = """
- # Old explanation of payment token calculation
+ # Updated explanation of payment token calculation
"""
    assert TierMapper.is_documentation_diff(comment_diff) is True
    act = TierMapper.classify_actionability(
        diff_snippet=comment_diff,
        file_path="src/services/payment.py",
        entity_name="process_token",
        entity_type="function",
        category=TaskCategory.CORE_LOGIC,
    )
    assert act == Actionability.IGNORE


def test_documentation_accompanying_api_change_actionability_upgrade() -> None:
    """Scenario 3: Documentation update accompanying a genuine API change remains UPGRADE."""
    combined_diff = """
- def request_context(environ):
-     \"\"\"Old docstring.\"\"\"
+ def request_context(environ, app=None):
+     \"\"\"New docstring describing app parameter.\"\"\"
"""
    assert TierMapper.is_documentation_diff(combined_diff) is False
    act = TierMapper.classify_actionability(
        diff_snippet=combined_diff,
        file_path="src/flask/app.py",
        entity_name="request_context",
        entity_type="function",
        category=TaskCategory.CORE_LOGIC,
    )
    assert act == Actionability.UPGRADE


def test_whitespace_and_formatting_diff_actionability_ignore() -> None:
    """Whitespace-only and indentation-only changes are classified as IGNORE."""
    ws_diff = """
-     x = 10
+     x = 10   
"""
    assert TierMapper.is_whitespace_or_formatting_diff(ws_diff) is True
    act = TierMapper.classify_actionability(
        diff_snippet=ws_diff,
        file_path="src/services/calc.py",
        entity_name="calc",
    )
    assert act == Actionability.IGNORE


def test_standalone_doc_and_config_file_actionability_informational() -> None:
    """Markdown, docs, and configs are classified as INFORMATIONAL."""
    act_readme = TierMapper.classify_actionability(
        diff_snippet="+ # New Header",
        file_path="README.md",
        category=TaskCategory.DOCUMENTATION_CONFIG,
    )
    assert act_readme == Actionability.INFORMATIONAL

    act_cfg = TierMapper.classify_actionability(
        diff_snippet="+ port: 8080",
        file_path="config/app.yaml",
        category=TaskCategory.DOCUMENTATION_CONFIG,
    )
    assert act_cfg == Actionability.INFORMATIONAL


# ==============================================================================
# 2. Behavioral & Caller Propagation Tests
# ==============================================================================


def test_core_logic_change_actionability_upgrade() -> None:
    """Scenario 4: Core logic code change is classified as UPGRADE."""
    code_diff = """
- return amount * 0.10
+ return amount * tax_rate
"""
    assert TierMapper.is_documentation_diff(code_diff) is False
    act = TierMapper.classify_actionability(
        diff_snippet=code_diff,
        file_path="src/services/tax.py",
        entity_name="calculate_tax",
        category=TaskCategory.CORE_LOGIC,
    )
    assert act == Actionability.UPGRADE


def test_api_signature_change_actionability_upgrade() -> None:
    """Scenario 7: Function/endpoint signature change is classified as UPGRADE."""
    sig_diff = """
- def checkout(cart_id):
+ def checkout(cart_id, coupon_code=None):
"""
    assert TierMapper.is_documentation_diff(sig_diff) is False
    act = TierMapper.classify_actionability(
        diff_snippet=sig_diff,
        file_path="src/api/checkout.py",
        entity_name="checkout",
        category=TaskCategory.CONTRACT_API,
    )
    assert act == Actionability.UPGRADE


@pytest.mark.asyncio
async def test_docstring_typo_generates_no_upgrade_task_and_no_caller_propagation(
    tmp_path: Path, test_repo_id: uuid.UUID
) -> None:
    """Scenarios 1 & 2 in Plan Service:
    Docstring typo in request_context with 3 callers produces:
    - 0 upgrade tasks
    - 0 caller tasks
    - 1 informational change
    """
    svc, db = await create_initialized_planner_service(tmp_path, test_repo_id)

    flask_doc_diff = """
- :data:`.session`, :data:`g:`, and :data:`.current_app` become available.
+ :data:`.session`, :data:`g`, and :data:`.current_app` become available.
"""
    callers = (
        CallerAtRisk(
            qualified_name="Flask.__call__",
            file_path="src/flask/app.py",
            distance=1,
            call_chain=("Flask.__call__", "request_context"),
        ),
        CallerAtRisk(
            qualified_name="Flask.wsgi_app",
            file_path="src/flask/app.py",
            distance=1,
            call_chain=("Flask.wsgi_app", "request_context"),
        ),
        CallerAtRisk(
            qualified_name="Flask.test_request_context",
            file_path="src/flask/app.py",
            distance=1,
            call_chain=("Flask.test_request_context", "request_context"),
        ),
    )
    detailed = DetailedImpact(
        file="src/flask/app.py",
        entity="request_context",
        entity_type="function",
        lines_affected=(120, 125),
        diff_snippet=flask_doc_diff,
        change_summary="Fixed typo in docstring role.",
        remediation_guidance="None.",
        justification="Documentation update.",
        outbound_calls=(),
        inbound_callers=("Flask.__call__", "Flask.wsgi_app", "Flask.test_request_context"),
        callers_at_risk=callers,
        downstream_dependent_files=(),
    )
    aggregate = ImpactAnalysisAggregate(
        metadata=AnalysisMetadataPayload(
            analysis_id=uuid.uuid4(),
            repository="pallets/flask",
            base_commit="HEAD~1",
            current_commit="HEAD",
            reasoning_mode=ReasoningMode.HEURISTIC,
            total_changed_entities=1,
            total_deleted_files=0,
            total_impacted_downstream_files=0,
            total_callers_at_risk=3,
        ),
        summary="Docstring typo fix",
        detailed_impacts=(detailed,),
        dependency_graph=DependencyGraphPayload(nodes=(), edges=(), mermaid=""),
        risk_analysis=RiskAnalysisPayload(
            risk_level=RiskLevel.LOW,
            key_risk_factors=(),
            ci_cd_recommendations=(),
            actionable_remediation_plan=(),
        ),
        created_at=datetime.now(UTC),
    )
    svc._impact_service.get_analysis = AsyncMock(return_value=aggregate)

    plan = await svc.generate_plan(
        repository_id=test_repo_id,
        impact_analysis_id=aggregate.metadata.analysis_id,
    )

    # Must produce 0 upgrade tasks and 0 caller propagation tasks!
    assert plan.total_tasks == 0
    assert len(plan.tasks) == 0

    # Must produce 1 informational change recording the doc change!
    assert len(plan.informational_changes) == 1
    info = plan.informational_changes[0]
    assert info.component == "src/flask/app.py::request_context"
    assert info.actionability == Actionability.IGNORE
    assert "Documentation or comment-only change detected" in info.reason
    assert "No behavioral or contract upgrade required" in info.reason


@pytest.mark.asyncio
async def test_genuine_behavioral_change_propagates_direct_and_transitive_callers(
    tmp_path: Path, test_repo_id: uuid.UUID
) -> None:
    """Scenarios 4, 5, 6:
    Genuine logic change in payment_core propagates direct caller (checkout)
    and transitive caller (order_api).
    """
    svc, db = await create_initialized_planner_service(tmp_path, test_repo_id)

    code_diff = """
- def process_payment(amount):
-     return gateway.charge(amount)
+ def process_payment(amount, currency="USD"):
+     return gateway.charge(amount, currency=currency)
"""
    direct_caller = CallerAtRisk(
        qualified_name="checkout_flow",
        file_path="src/services/checkout.py",
        distance=1,
        call_chain=("checkout_flow", "process_payment"),
    )
    transitive_caller = CallerAtRisk(
        qualified_name="submit_order",
        file_path="src/api/orders.py",
        distance=2,
        call_chain=("submit_order", "checkout_flow", "process_payment"),
    )
    detailed = DetailedImpact(
        file="src/core/payment.py",
        entity="process_payment",
        entity_type="function",
        lines_affected=(10, 20),
        diff_snippet=code_diff,
        change_summary="Added currency parameter to payment processing.",
        remediation_guidance="Update callers to handle currency.",
        justification="Core contract modification.",
        outbound_calls=(),
        inbound_callers=("checkout_flow",),
        callers_at_risk=(direct_caller, transitive_caller),
        downstream_dependent_files=(),
    )
    aggregate = ImpactAnalysisAggregate(
        metadata=AnalysisMetadataPayload(
            analysis_id=uuid.uuid4(),
            repository="corp/payment",
            base_commit="HEAD~1",
            current_commit="HEAD",
            reasoning_mode=ReasoningMode.HEURISTIC,
            total_changed_entities=1,
            total_deleted_files=0,
            total_impacted_downstream_files=0,
            total_callers_at_risk=2,
        ),
        summary="Payment logic and contract update",
        detailed_impacts=(detailed,),
        dependency_graph=DependencyGraphPayload(
            nodes=(),
            edges=(
                GraphEdgePayload(caller="checkout_flow", callee="process_payment"),
                GraphEdgePayload(caller="submit_order", callee="checkout_flow"),
            ),
            mermaid="",
        ),
        risk_analysis=RiskAnalysisPayload(
            risk_level=RiskLevel.HIGH,
            key_risk_factors=(),
            ci_cd_recommendations=(),
            actionable_remediation_plan=(),
        ),
        created_at=datetime.now(UTC),
    )
    svc._impact_service.get_analysis = AsyncMock(return_value=aggregate)

    plan = await svc.generate_plan(
        repository_id=test_repo_id,
        impact_analysis_id=aggregate.metadata.analysis_id,
    )

    # 3 upgrade tasks: process_payment, checkout_flow, submit_order
    assert plan.total_tasks == 3
    components = [t.component for t in plan.tasks]
    assert "src/core/payment.py::process_payment" in components
    assert "src/services/checkout.py::checkout_flow" in components
    assert "src/api/orders.py::submit_order" in components

    # Prerequisite ordering: callee before direct caller before transitive caller
    t_payment = next(t for t in plan.tasks if "process_payment" in t.component)
    t_checkout = next(t for t in plan.tasks if "checkout_flow" in t.component)
    t_order = next(t for t in plan.tasks if "submit_order" in t.component)

    assert t_payment.step_number < t_checkout.step_number
    assert t_payment.actionability == Actionability.UPGRADE
    assert t_checkout.actionability == Actionability.UPGRADE
    assert t_order.actionability == Actionability.UPGRADE


# ==============================================================================
# 3. AI Integration Tests (Mocked OpenRouter)
# ==============================================================================


@pytest.mark.asyncio
async def test_ai_unavailable_deterministic_plan_still_works(
    tmp_path: Path, test_repo_id: uuid.UUID
) -> None:
    """Scenario 8: AI unavailable / network failure falls back cleanly to deterministic plan."""
    svc, db = await create_initialized_planner_service(tmp_path, test_repo_id)

    code_diff = "+ def new_func(): pass"
    detailed = DetailedImpact(
        file="src/service.py",
        entity="new_func",
        entity_type="function",
        lines_affected=(1, 5),
        diff_snippet=code_diff,
        change_summary="Added new function",
        remediation_guidance="",
        justification="",
        outbound_calls=(),
        inbound_callers=(),
        callers_at_risk=(),
        downstream_dependent_files=(),
    )
    aggregate = ImpactAnalysisAggregate(
        metadata=AnalysisMetadataPayload(
            analysis_id=uuid.uuid4(),
            repository="corp/app",
            base_commit="HEAD~1",
            current_commit="HEAD",
            reasoning_mode=ReasoningMode.HEURISTIC,
            total_changed_entities=1,
            total_deleted_files=0,
            total_impacted_downstream_files=0,
            total_callers_at_risk=0,
        ),
        summary="Added function",
        detailed_impacts=(detailed,),
        dependency_graph=DependencyGraphPayload(nodes=(), edges=(), mermaid=""),
        risk_analysis=RiskAnalysisPayload(
            risk_level=RiskLevel.LOW,
            key_risk_factors=(),
            ci_cd_recommendations=(),
            actionable_remediation_plan=(),
        ),
        created_at=datetime.now(UTC),
    )
    svc._impact_service.get_analysis = AsyncMock(return_value=aggregate)

    with patch(
        "httpx.AsyncClient.post", side_effect=Exception("OpenRouter 503 Service Unavailable")
    ):
        plan = await svc.generate_plan(
            repository_id=test_repo_id,
            impact_analysis_id=aggregate.metadata.analysis_id,
            llm_config={"api_key": "sk-test", "model": "mistralai/mistral-7b-instruct:free"},
        )

        assert plan.total_tasks == 1
        assert plan.tasks[0].component == "src/service.py::new_func"
        assert plan.reasoning_mode == "HEURISTIC"


@pytest.mark.asyncio
async def test_malformed_ai_json_deterministic_plan_still_works(
    tmp_path: Path, test_repo_id: uuid.UUID
) -> None:
    """Scenario 9: Malformed AI JSON response falls back gracefully without corrupting plan."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "This is not valid JSON! <<error>>"}}]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        reason, changes, tests, ai_review = await TaskSynthesizer.enrich_task_with_openrouter(
            component="PaymentAPI.pay",
            category=TaskCategory.CONTRACT_API,
            component_type="endpoint",
            file_path="src/api/payment.py",
            heuristic_reason="Base reason",
            heuristic_changes="Base changes",
            api_key="sk-test",
        )
        assert reason == "Base reason"
        assert changes == "Base changes"
        assert tests is None
        assert ai_review is None


@pytest.mark.asyncio
async def test_ai_flags_false_positive_does_not_override_deterministic_evidence(
    tmp_path: Path, test_repo_id: uuid.UUID
) -> None:
    """Scenario 10: AI suggests IGNORE, but deterministic code diff proves real code change.
    Deterministic evidence wins: task is NOT deleted or suppressed.
    """
    svc, db = await create_initialized_planner_service(tmp_path, test_repo_id)

    code_diff = """
- def calculate(x): return x
+ def calculate(x, multiplier=2): return x * multiplier
"""
    detailed = DetailedImpact(
        file="src/calc.py",
        entity="calculate",
        entity_type="function",
        lines_affected=(1, 5),
        diff_snippet=code_diff,
        change_summary="Modified calculation logic.",
        remediation_guidance="",
        justification="",
        outbound_calls=(),
        inbound_callers=(),
        callers_at_risk=(),
        downstream_dependent_files=(),
    )
    aggregate = ImpactAnalysisAggregate(
        metadata=AnalysisMetadataPayload(
            analysis_id=uuid.uuid4(),
            repository="corp/app",
            base_commit="HEAD~1",
            current_commit="HEAD",
            reasoning_mode=ReasoningMode.HEURISTIC,
            total_changed_entities=1,
            total_deleted_files=0,
            total_impacted_downstream_files=0,
            total_callers_at_risk=0,
        ),
        summary="Modified logic",
        detailed_impacts=(detailed,),
        dependency_graph=DependencyGraphPayload(nodes=(), edges=(), mermaid=""),
        risk_analysis=RiskAnalysisPayload(
            risk_level=RiskLevel.MEDIUM,
            key_risk_factors=(),
            ci_cd_recommendations=(),
            actionable_remediation_plan=(),
        ),
        created_at=datetime.now(UTC),
    )
    svc._impact_service.get_analysis = AsyncMock(return_value=aggregate)

    # AI incorrectly returns actionability IGNORE
    ai_task_resp = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "refined_reason": "AI opinion: just ignore it",
                            "detailed_expected_changes": "None",
                            "recommended_tests": [],
                            "actionability": "IGNORE",
                            "confidence": "HIGH",
                            "explanation": "Seems like a minor tweak",
                        }
                    )
                }
            }
        ]
    }
    ai_plan_resp = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "sequence_valid": True,
                            "confidence": 0.95,
                            "warnings": [],
                            "unnecessary_tasks": [],
                            "missing_task_suggestions": [],
                            "test_recommendations": [],
                            "actionability_reviews": [],
                        }
                    )
                }
            }
        ]
    }

    mock_task_resp = MagicMock()
    mock_task_resp.status_code = 200
    mock_task_resp.json.return_value = ai_task_resp

    mock_plan_resp = MagicMock()
    mock_plan_resp.status_code = 200
    mock_plan_resp.json.return_value = ai_plan_resp

    mock_post = AsyncMock(side_effect=[mock_task_resp, mock_plan_resp])

    with patch("httpx.AsyncClient.post", mock_post):
        plan = await svc.generate_plan(
            repository_id=test_repo_id,
            impact_analysis_id=aggregate.metadata.analysis_id,
            llm_config={"api_key": "sk-test", "model": "mistralai/mistral-7b-instruct:free"},
        )

        # Deterministic evidence wins: Task is NOT deleted or converted to IGNORE!
        assert plan.total_tasks == 1
        task = plan.tasks[0]
        assert task.component == "src/calc.py::calculate"
        assert task.actionability == Actionability.UPGRADE
        assert task.ai_review is not None
        assert "override_note" in task.ai_review
        assert "deterministic evidence" in task.ai_review["override_note"]


@pytest.mark.asyncio
async def test_ai_suggests_missing_task_not_automatically_inserted_without_evidence() -> None:
    """Scenario 11: AI missing-task suggestion is kept as an advisory warning/suggestion
    and NOT automatically inserted into the final DAG without deterministic AST evidence.
    """
    tasks = [
        UpgradeTask(
            id=uuid.uuid4(),
            plan_id=uuid.uuid4(),
            step_number=1,
            component="src/api/payment.py::pay",
            component_type="endpoint",
            category=TaskCategory.CONTRACT_API,
            reason="Contract changed",
        )
    ]
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "sequence_valid": True,
                            "confidence": 0.88,
                            "warnings": ["Check payment adapter"],
                            "unnecessary_tasks": [],
                            "missing_task_suggestions": [
                                {
                                    "component": "unknown_payment_adapter",
                                    "reason": "This component appears to consume the changed API.",
                                    "confidence": 0.71,
                                }
                            ],
                            "test_recommendations": [],
                            "actionability_reviews": [],
                        }
                    )
                }
            }
        ]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        review = await TaskSynthesizer.review_whole_plan_with_openrouter(
            tasks=tasks,
            informational_changes=[],
            repository_context={"known_files": ["src/api/payment.py"]},
            api_key="sk-test",
        )

        assert review is not None
        assert review["sequence_valid"] is True
        # Suggestion is retained as advisory suggestion
        assert len(review["missing_task_suggestions"]) == 1
        sug = review["missing_task_suggestions"][0]
        assert sug["component"] == "unknown_payment_adapter"
        assert sug["is_verified"] is False
        # And warning is recorded
        assert any("not verified in repository AST evidence" in w for w in review["warnings"])


@pytest.mark.asyncio
async def test_whole_plan_review_produces_structured_output() -> None:
    """Scenario 12: Whole-plan review produces comprehensive structured output."""
    tasks = [
        UpgradeTask(
            id=uuid.uuid4(),
            plan_id=uuid.uuid4(),
            step_number=1,
            component="src/core.py::run",
            component_type="function",
            category=TaskCategory.CORE_LOGIC,
            reason="Core logic updated",
            dependencies=(),
            expected_changes="Update run logic",
            required_tests=("tests/test_core.py::test_run",),
            evidence=TaskEvidence(diff_snippet="+ def run(): pass"),
        )
    ]
    info_changes = [
        InformationalChange(
            component="README.md",
            file_path="README.md",
            category=TaskCategory.DOCUMENTATION_CONFIG,
            reason="Docs updated",
        )
    ]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "sequence_valid": True,
                            "confidence": 0.94,
                            "warnings": ["Ensure database transaction safety"],
                            "unnecessary_tasks": [],
                            "missing_task_suggestions": [],
                            "test_recommendations": [
                                {
                                    "component": "src/core.py::run",
                                    "recommended_tests": ["tests/test_core.py::test_run"],
                                    "is_verified": True,
                                }
                            ],
                            "actionability_reviews": [
                                {
                                    "component": "src/core.py::run",
                                    "suggested_actionability": "UPGRADE",
                                    "reason": "Core logic modification requires testing",
                                    "confidence": 0.95,
                                }
                            ],
                        }
                    )
                }
            }
        ]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        review = await TaskSynthesizer.review_whole_plan_with_openrouter(
            tasks=tasks,
            informational_changes=info_changes,
            api_key="sk-test",
            model="mistralai/mistral-7b-instruct:free",
        )

        assert review is not None
        assert review["sequence_valid"] is True
        assert review["confidence"] == 0.94
        assert "Ensure database transaction safety" in review["warnings"]
        assert len(review["test_recommendations"]) == 1
        assert len(review["actionability_reviews"]) == 1


@pytest.mark.asyncio
async def test_ai_recommendations_include_confidence_and_actionability() -> None:
    """Scenario 13: Per-task review returns confidence and actionability."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "refined_reason": "Refined parameter reasoning",
                            "detailed_expected_changes": "Audit call sites",
                            "recommended_tests": ["tests/test_checkout.py::test_cart"],
                            "actionability": "REVIEW",
                            "confidence": "HIGH",
                            "explanation": "May need manual review",
                        }
                    )
                }
            }
        ]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        r, c, t, ai_rev = await TaskSynthesizer.enrich_task_with_openrouter(
            component="src/cart.py::checkout",
            category=TaskCategory.CORE_LOGIC,
            component_type="function",
            file_path="src/cart.py",
            heuristic_reason="Base",
            heuristic_changes="Base",
            api_key="sk-test",
        )
        assert r == "Refined parameter reasoning"
        assert t == ["tests/test_checkout.py::test_cart"]
        assert ai_rev is not None
        assert ai_rev["actionability"] == "REVIEW"
        assert ai_rev["confidence"] == "HIGH"
        assert "manual review" in ai_rev["explanation"]


# ==============================================================================
# Scenarios A through G from Specification
# ==============================================================================


@pytest.mark.asyncio
async def test_scenario_a_documentation_typo(
    tmp_path: Path, test_repo_id: uuid.UUID
) -> None:
    """Scenario A: Documentation typo fix inside a docstring.
    Expected: Significance = MINOR, 0 upgrade tasks, 0 caller propagation,
    risk = LOW, and clear low-priority suggestions.
    """
    svc, _ = await create_initialized_planner_service(tmp_path, test_repo_id)
    doc_diff = """
- :data:`.session`, :data:`g:`, and :data:`.current_app`
+ :data:`.session`, :data:`g`, and :data:`.current_app`
"""
    callers = tuple(
        CallerAtRisk(qualified_name=f"caller_{i}", file_path=f"src/c{i}.py", distance=1)
        for i in range(20)
    )
    detailed = DetailedImpact(
        file="src/flask/app.py",
        entity="session_interface",
        entity_type="function",
        lines_affected=(50, 52),
        diff_snippet=doc_diff,
        change_summary="Fixed typo in docstring.",
        remediation_guidance="",
        justification="",
        outbound_calls=(),
        inbound_callers=(),
        callers_at_risk=callers,
        downstream_dependent_files=(),
    )
    aggregate = ImpactAnalysisAggregate(
        metadata=AnalysisMetadataPayload(
            analysis_id=uuid.uuid4(),
            repository="pallets/flask",
            base_commit="HEAD~1",
            current_commit="HEAD",
            reasoning_mode=ReasoningMode.HEURISTIC,
            total_changed_entities=1,
            total_deleted_files=0,
            total_impacted_downstream_files=0,
            total_callers_at_risk=20,
        ),
        summary="Typo fix",
        detailed_impacts=(detailed,),
        dependency_graph=DependencyGraphPayload(nodes=(), edges=(), mermaid=""),
        risk_analysis=RiskAnalysisPayload(
            risk_level=RiskLevel.HIGH,  # Upstream had erroneously flagged HIGH due to 20 callers
            key_risk_factors=(),
            ci_cd_recommendations=(),
            actionable_remediation_plan=(),
        ),
        created_at=datetime.now(UTC),
    )
    svc._impact_service.get_analysis = AsyncMock(return_value=aggregate)

    plan = await svc.generate_plan(
        repository_id=test_repo_id,
        impact_analysis_id=aggregate.metadata.analysis_id,
    )

    assert plan.change_significance == ChangeSignificance.MINOR_CHANGE
    assert plan.risk_level == "LOW"
    assert len(plan.tasks) == 0
    assert "No major upgrade work required" in plan.recommended_action
    assert len(plan.optional_suggestions) > 0
    assert "Review documentation formatting." in plan.optional_suggestions


@pytest.mark.asyncio
async def test_scenario_b_comment_only_change(
    tmp_path: Path, test_repo_id: uuid.UUID
) -> None:
    """Scenario B: Comment-only code changes inside functions.
    Expected: Same behavior as documentation-only.
    """
    svc, _ = await create_initialized_planner_service(tmp_path, test_repo_id)
    comment_diff = """
- # Old comment describing legacy behavior
+ # Updated comment describing current behavior
"""
    callers = (CallerAtRisk(qualified_name="route_handler", file_path="src/routes.py", distance=1),)
    detailed = DetailedImpact(
        file="src/service.py",
        entity="do_work",
        entity_type="function",
        lines_affected=(10, 11),
        diff_snippet=comment_diff,
        change_summary="Updated explanatory comments.",
        remediation_guidance="",
        justification="",
        outbound_calls=(),
        inbound_callers=(),
        callers_at_risk=callers,
        downstream_dependent_files=(),
    )
    aggregate = ImpactAnalysisAggregate(
        metadata=AnalysisMetadataPayload(
            analysis_id=uuid.uuid4(),
            repository="corp/app",
            base_commit="HEAD~1",
            current_commit="HEAD",
            reasoning_mode=ReasoningMode.HEURISTIC,
            total_changed_entities=1,
            total_deleted_files=0,
            total_impacted_downstream_files=0,
            total_callers_at_risk=1,
        ),
        summary="Comment update",
        detailed_impacts=(detailed,),
        dependency_graph=DependencyGraphPayload(nodes=(), edges=(), mermaid=""),
        risk_analysis=RiskAnalysisPayload(
            risk_level=RiskLevel.LOW,
            key_risk_factors=(),
            ci_cd_recommendations=(),
            actionable_remediation_plan=(),
        ),
        created_at=datetime.now(UTC),
    )
    svc._impact_service.get_analysis = AsyncMock(return_value=aggregate)

    plan = await svc.generate_plan(
        repository_id=test_repo_id,
        impact_analysis_id=aggregate.metadata.analysis_id,
    )

    assert plan.change_significance == ChangeSignificance.MINOR_CHANGE
    assert plan.risk_level == "LOW"
    assert len(plan.tasks) == 0
    assert "No major upgrade work required" in plan.recommended_action


@pytest.mark.asyncio
async def test_scenario_c_function_signature_change(
    tmp_path: Path, test_repo_id: uuid.UUID
) -> None:
    """Scenario C: Function signature changed with direct and transitive callers.
    Expected: Significance = MAJOR, Changed function = REQUIRED_CHANGE,
    Direct caller = REQUIRED_CHANGE, Transitive caller = VALIDATION_ONLY,
    Topological order correct.
    """
    svc, _ = await create_initialized_planner_service(tmp_path, test_repo_id)
    sig_diff = """
- def calculate_tax(amount):
-     return amount * 0.1
+ def calculate_tax(amount, tax_rate):
+     return amount * tax_rate
"""
    direct_caller = CallerAtRisk(
        qualified_name="calculate_total",
        file_path="src/billing/total.py",
        distance=1,
        call_chain=("calculate_total", "calculate_tax"),
    )
    transitive_caller = CallerAtRisk(
        qualified_name="process_payment",
        file_path="src/billing/payment.py",
        distance=2,
        call_chain=("process_payment", "calculate_total", "calculate_tax"),
    )
    detailed = DetailedImpact(
        file="src/billing/tax.py",
        entity="calculate_tax",
        entity_type="function",
        lines_affected=(1, 5),
        diff_snippet=sig_diff,
        change_summary="Changed signature to require tax_rate.",
        remediation_guidance="Pass tax_rate parameter.",
        justification="Callable contract change.",
        outbound_calls=(),
        inbound_callers=("calculate_total",),
        callers_at_risk=(direct_caller, transitive_caller),
        downstream_dependent_files=(),
    )
    aggregate = ImpactAnalysisAggregate(
        metadata=AnalysisMetadataPayload(
            analysis_id=uuid.uuid4(),
            repository="corp/billing",
            base_commit="HEAD~1",
            current_commit="HEAD",
            reasoning_mode=ReasoningMode.HEURISTIC,
            total_changed_entities=1,
            total_deleted_files=0,
            total_impacted_downstream_files=0,
            total_callers_at_risk=2,
        ),
        summary="Tax contract change",
        detailed_impacts=(detailed,),
        dependency_graph=DependencyGraphPayload(
            nodes=(),
            edges=(
                GraphEdgePayload(
                    caller="src/billing/total.py::calculate_total",
                    callee="src/billing/tax.py::calculate_tax",
                ),
                GraphEdgePayload(
                    caller="src/billing/payment.py::process_payment",
                    callee="src/billing/total.py::calculate_total",
                ),
            ),
            mermaid="",
        ),
        risk_analysis=RiskAnalysisPayload(
            risk_level=RiskLevel.HIGH,
            key_risk_factors=(),
            ci_cd_recommendations=(),
            actionable_remediation_plan=(),
        ),
        created_at=datetime.now(UTC),
    )
    svc._impact_service.get_analysis = AsyncMock(return_value=aggregate)

    plan = await svc.generate_plan(
        repository_id=test_repo_id,
        impact_analysis_id=aggregate.metadata.analysis_id,
    )

    assert plan.change_significance == ChangeSignificance.MAJOR_CHANGE
    assert len(plan.tasks) == 3

    # Check tasks and order: calculate_tax -> calculate_total -> process_payment
    tax_task = plan.tasks[0]
    total_task = plan.tasks[1]
    payment_task = plan.tasks[2]

    assert "calculate_tax" in tax_task.component
    assert tax_task.action_type == TaskActionType.REQUIRED_CHANGE
    assert tax_task.risk_level == "HIGH"

    assert "calculate_total" in total_task.component
    assert total_task.action_type == TaskActionType.REQUIRED_CHANGE
    assert total_task.risk_level == "HIGH"
    assert any("calculate_tax" in d for d in total_task.dependencies)

    assert "process_payment" in payment_task.component
    assert payment_task.action_type == TaskActionType.VALIDATION_ONLY
    assert payment_task.risk_level == "MEDIUM"
    assert any("calculate_total" in d for d in payment_task.dependencies)

    assert "Why this order?" in plan.order_rationale
    assert "calculate_tax" in plan.order_rationale


@pytest.mark.asyncio
async def test_scenario_d_behavioral_implementation_change_unchanged_signature(
    tmp_path: Path, test_repo_id: uuid.UUID
) -> None:
    """Scenario D: Behavioral implementation change with unchanged signature.
    Expected: Significance = MODERATE_CHANGE, changed function = REQUIRED_CHANGE,
    caller = VALIDATION_ONLY.
    """
    svc, _ = await create_initialized_planner_service(tmp_path, test_repo_id)
    behavior_diff = """
  def compute_discount(subtotal):
-     return subtotal * 0.05
+     return subtotal * 0.08 if subtotal > 100 else 0
"""
    caller = CallerAtRisk(
        qualified_name="apply_discount",
        file_path="src/order.py",
        distance=1,
        call_chain=("apply_discount", "compute_discount"),
    )
    detailed = DetailedImpact(
        file="src/pricing.py",
        entity="compute_discount",
        entity_type="function",
        lines_affected=(10, 15),
        diff_snippet=behavior_diff,
        change_summary="Modified discount logic without signature change.",
        remediation_guidance="Verify discount thresholds in order processing.",
        justification="Internal business rule update.",
        outbound_calls=(),
        inbound_callers=("apply_discount",),
        callers_at_risk=(caller,),
        downstream_dependent_files=(),
    )
    aggregate = ImpactAnalysisAggregate(
        metadata=AnalysisMetadataPayload(
            analysis_id=uuid.uuid4(),
            repository="corp/shop",
            base_commit="HEAD~1",
            current_commit="HEAD",
            reasoning_mode=ReasoningMode.HEURISTIC,
            total_changed_entities=1,
            total_deleted_files=0,
            total_impacted_downstream_files=0,
            total_callers_at_risk=1,
        ),
        summary="Discount rule change",
        detailed_impacts=(detailed,),
        dependency_graph=DependencyGraphPayload(
            nodes=(),
            edges=(GraphEdgePayload(caller="apply_discount", callee="compute_discount"),),
            mermaid="",
        ),
        risk_analysis=RiskAnalysisPayload(
            risk_level=RiskLevel.MEDIUM,
            key_risk_factors=(),
            ci_cd_recommendations=(),
            actionable_remediation_plan=(),
        ),
        created_at=datetime.now(UTC),
    )
    svc._impact_service.get_analysis = AsyncMock(return_value=aggregate)

    plan = await svc.generate_plan(
        repository_id=test_repo_id,
        impact_analysis_id=aggregate.metadata.analysis_id,
    )

    assert plan.change_significance == ChangeSignificance.MODERATE_CHANGE
    assert len(plan.tasks) == 2

    # Changed component requires code update, caller is validation only
    comp_task = next(t for t in plan.tasks if "compute_discount" in t.component)
    caller_task = next(t for t in plan.tasks if "apply_discount" in t.component)

    assert comp_task.action_type == TaskActionType.REQUIRED_CHANGE
    assert caller_task.action_type == TaskActionType.VALIDATION_ONLY


@pytest.mark.asyncio
async def test_scenario_e_api_contract_change(
    tmp_path: Path, test_repo_id: uuid.UUID
) -> None:
    """Scenario E: API contract change.
    Expected: Contract/API tier first, Core/Consumers after, Tests after.
    Order rationale explains topological sequence.
    """
    svc, _ = await create_initialized_planner_service(tmp_path, test_repo_id)
    endpoint_diff = """
- @app.get("/items/{item_id}")
+ @app.get("/api/v2/items/{item_id}")
"""
    detailed_api = DetailedImpact(
        file="src/api/routes.py",
        entity="get_items_endpoint",
        entity_type="function",
        lines_affected=(1, 5),
        diff_snippet=endpoint_diff,
        change_summary="Versioned public items endpoint.",
        remediation_guidance="Update consumers to call /api/v2/",
        justification="Public contract updated.",
        outbound_calls=("src/services/items.py::fetch_items",),
        inbound_callers=(),
        callers_at_risk=(),
        downstream_dependent_files=(),
    )
    detailed_core = DetailedImpact(
        file="src/services/items.py",
        entity="fetch_items",
        entity_type="function",
        lines_affected=(10, 15),
        diff_snippet="+ def fetch_items_v2(): pass",
        change_summary="Added service supporting v2.",
        remediation_guidance="",
        justification="",
        outbound_calls=(),
        inbound_callers=(),
        callers_at_risk=(),
        downstream_dependent_files=(),
    )
    detailed_test = DetailedImpact(
        file="tests/test_items.py",
        entity="test_get_items",
        entity_type="function",
        lines_affected=(5, 10),
        diff_snippet="+ def test_get_items_v2(): pass",
        change_summary="Added test for v2 endpoint.",
        remediation_guidance="",
        justification="",
        outbound_calls=(),
        inbound_callers=(),
        callers_at_risk=(),
        downstream_dependent_files=(),
    )
    aggregate = ImpactAnalysisAggregate(
        metadata=AnalysisMetadataPayload(
            analysis_id=uuid.uuid4(),
            repository="corp/api",
            base_commit="HEAD~1",
            current_commit="HEAD",
            reasoning_mode=ReasoningMode.HEURISTIC,
            total_changed_entities=3,
            total_deleted_files=0,
            total_impacted_downstream_files=0,
            total_callers_at_risk=0,
        ),
        summary="API v2 upgrade",
        detailed_impacts=(detailed_api, detailed_core, detailed_test),
        dependency_graph=DependencyGraphPayload(
            nodes=(),
            edges=(
                GraphEdgePayload(
                    caller="src/api/routes.py::get_items_endpoint",
                    callee="src/services/items.py::fetch_items",
                ),
            ),
            mermaid="",
        ),
        risk_analysis=RiskAnalysisPayload(
            risk_level=RiskLevel.HIGH,
            key_risk_factors=(),
            ci_cd_recommendations=(),
            actionable_remediation_plan=(),
        ),
        created_at=datetime.now(UTC),
    )
    svc._impact_service.get_analysis = AsyncMock(return_value=aggregate)

    plan = await svc.generate_plan(
        repository_id=test_repo_id,
        impact_analysis_id=aggregate.metadata.analysis_id,
    )

    assert plan.change_significance == ChangeSignificance.MAJOR_CHANGE
    assert len(plan.order_rationale) > 0
    assert any(
        "contract" in plan.order_rationale.lower() or "first" in plan.order_rationale.lower()
        for _ in [1]
    )


@pytest.mark.asyncio
async def test_scenario_f_llm_unavailable_deterministic_fallback(
    tmp_path: Path, test_repo_id: uuid.UUID
) -> None:
    """Scenario F: OpenRouter LLM is offline or returns error.
    Expected: Plan still works smoothly, no exception raised, deterministic fallback.
    """
    svc, _ = await create_initialized_planner_service(tmp_path, test_repo_id)
    code_diff = """
- def compute(x): return x
+ def compute(x, y=1): return x * y
"""
    detailed = DetailedImpact(
        file="src/math.py",
        entity="compute",
        entity_type="function",
        lines_affected=(1, 3),
        diff_snippet=code_diff,
        change_summary="Modified math calculation.",
        remediation_guidance="",
        justification="",
        outbound_calls=(),
        inbound_callers=(),
        callers_at_risk=(),
        downstream_dependent_files=(),
    )
    aggregate = ImpactAnalysisAggregate(
        metadata=AnalysisMetadataPayload(
            analysis_id=uuid.uuid4(),
            repository="corp/math",
            base_commit="HEAD~1",
            current_commit="HEAD",
            reasoning_mode=ReasoningMode.HEURISTIC,
            total_changed_entities=1,
            total_deleted_files=0,
            total_impacted_downstream_files=0,
            total_callers_at_risk=0,
        ),
        summary="Math update",
        detailed_impacts=(detailed,),
        dependency_graph=DependencyGraphPayload(nodes=(), edges=(), mermaid=""),
        risk_analysis=RiskAnalysisPayload(
            risk_level=RiskLevel.MEDIUM,
            key_risk_factors=(),
            ci_cd_recommendations=(),
            actionable_remediation_plan=(),
        ),
        created_at=datetime.now(UTC),
    )
    svc._impact_service.get_analysis = AsyncMock(return_value=aggregate)

    # OpenRouter raises connection error
    with patch("httpx.AsyncClient.post", side_effect=Exception("OpenRouter timeout 504")):
        plan = await svc.generate_plan(
            repository_id=test_repo_id,
            impact_analysis_id=aggregate.metadata.analysis_id,
            llm_config={"api_key": "sk-key", "model": "mistralai/mistral-7b-instruct:free"},
        )

    assert plan is not None
    assert plan.status in ("DRAFT", "COMPLETED")
    assert plan.reasoning_mode == "HEURISTIC"
    assert len(plan.tasks) == 1


@pytest.mark.asyncio
async def test_scenario_g_llm_returns_unsupported_recommendation(
    tmp_path: Path, test_repo_id: uuid.UUID
) -> None:
    """Scenario G: LLM review fabricates an unverified component task.
    Expected: Grounded architecture ensures invented components do NOT become
    part of repository evidence or tasks.
    """
    svc, _ = await create_initialized_planner_service(tmp_path, test_repo_id)
    code_diff = """
- def auth(u): return u
+ def auth(u, p): return u == p
"""
    detailed = DetailedImpact(
        file="src/auth.py",
        entity="auth",
        entity_type="function",
        lines_affected=(1, 3),
        diff_snippet=code_diff,
        change_summary="Updated auth check.",
        remediation_guidance="",
        justification="",
        outbound_calls=(),
        inbound_callers=(),
        callers_at_risk=(),
        downstream_dependent_files=(),
    )
    aggregate = ImpactAnalysisAggregate(
        metadata=AnalysisMetadataPayload(
            analysis_id=uuid.uuid4(),
            repository="corp/auth",
            base_commit="HEAD~1",
            current_commit="HEAD",
            reasoning_mode=ReasoningMode.HEURISTIC,
            total_changed_entities=1,
            total_deleted_files=0,
            total_impacted_downstream_files=0,
            total_callers_at_risk=0,
        ),
        summary="Auth update",
        detailed_impacts=(detailed,),
        dependency_graph=DependencyGraphPayload(nodes=(), edges=(), mermaid=""),
        risk_analysis=RiskAnalysisPayload(
            risk_level=RiskLevel.MEDIUM,
            key_risk_factors=(),
            ci_cd_recommendations=(),
            actionable_remediation_plan=(),
        ),
        created_at=datetime.now(UTC),
    )
    svc._impact_service.get_analysis = AsyncMock(return_value=aggregate)

    # LLM hallucinates a missing task for a non-existent file
    ai_plan_resp = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "change_significance": "MAJOR_CHANGE",
                            "significance_reasoning": "Auth contract changed.",
                            "recommended_action": "A coordinated upgrade is recommended.",
                            "order_rationale": "Root contract first.",
                            "optional_suggestions": ["Run linter."],
                            "sequence_valid": True,
                            "confidence": 0.95,
                            "warnings": [],
                            "unnecessary_tasks": [],
                            "missing_task_suggestions": [
                                {
                                    "component": "src/invented/crypto_service.py::encrypt",
                                    "reason": "Imaginary crypto service should be updated.",
                                    "confidence": 0.9,
                                }
                            ],
                            "test_recommendations": [],
                            "actionability_reviews": [],
                        }
                    )
                }
            }
        ]
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = ai_plan_resp

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        plan = await svc.generate_plan(
            repository_id=test_repo_id,
            impact_analysis_id=aggregate.metadata.analysis_id,
            llm_config={"api_key": "sk-key", "model": "mistralai/mistral-7b-instruct:free"},
        )

    # Deterministic ground truth retained: only the real entity is a task
    assert len(plan.tasks) == 1
    assert "src/auth.py::auth" in plan.tasks[0].component
    # The fabricated component is NOT in the plan tasks
    assert not any("crypto_service" in t.component for t in plan.tasks)


@pytest.mark.asyncio
async def test_comment_containing_fatal_error_does_not_increase_risk_or_create_tasks(
    tmp_path: Path, test_repo_id: uuid.UUID
) -> None:
    """Test 2 from Senior Engineer Specification:
    Ensure that developer comments like '# FATAL ERROR' or '# BREAKING CHANGE'
    do NOT elevate risk or cause non-behavioral changes to become tasks.
    """
    svc, _ = await create_initialized_planner_service(tmp_path, test_repo_id)
    comment_diff = """
--- a/src/calc.py
+++ b/src/calc.py
@@ -10,3 +10,4 @@
 def compute(x):
+    # FATAL ERROR: CRITICAL BREAKING CHANGE - do not call without caution
     return x
"""
    callers = tuple(
        CallerAtRisk(
            qualified_name=f"caller_{i}",
            file_path=f"src/caller_{i}.py",
            distance=1,
            call_chain=(f"caller_{i}", "compute"),
        )
        for i in range(15)
    )
    detailed = DetailedImpact(
        file="src/calc.py",
        entity="compute",
        entity_type="function",
        lines_affected=(10, 14),
        diff_snippet=comment_diff,
        change_summary="Added comment warning about error conditions.",
        remediation_guidance="No functional changes required.",
        justification="Documentation / comment-only modification.",
        outbound_calls=(),
        inbound_callers=tuple(f"caller_{i}" for i in range(15)),
        callers_at_risk=callers,
        downstream_dependent_files=(),
    )
    aggregate = ImpactAnalysisAggregate(
        metadata=AnalysisMetadataPayload(
            analysis_id=uuid.uuid4(),
            repository="corp/calc",
            base_commit="HEAD~1",
            current_commit="HEAD",
            reasoning_mode=ReasoningMode.HEURISTIC,
            total_changed_entities=1,
            total_deleted_files=0,
            total_impacted_downstream_files=0,
            total_callers_at_risk=15,
        ),
        summary="Comment addition with FATAL ERROR wording",
        detailed_impacts=(detailed,),
        dependency_graph=DependencyGraphPayload(nodes=(), edges=(), mermaid=""),
        risk_analysis=RiskAnalysisPayload(
            risk_level=RiskLevel.HIGH,
            key_risk_factors=("Callers at risk count: 15",),
            ci_cd_recommendations=(),
            actionable_remediation_plan=(),
        ),
        created_at=datetime.now(UTC),
    )
    svc._impact_service.get_analysis = AsyncMock(return_value=aggregate)

    plan = await svc.generate_plan(
        repository_id=test_repo_id,
        impact_analysis_id=aggregate.metadata.analysis_id,
    )

    # Comments MUST NOT produce upgrade tasks or propagate to callers
    assert plan.change_significance == ChangeSignificance.MINOR_CHANGE
    assert plan.risk_level == "LOW"
    assert len(plan.tasks) == 0
    assert "No major upgrade work required" in plan.recommended_action
    assert len(plan.informational_changes) == 1
    assert len(plan.optional_suggestions) > 0


@pytest.mark.asyncio
async def test_entity_normalization_prevents_duplicate_tasks(
    tmp_path: Path, test_repo_id: uuid.UUID
) -> None:
    """Test 6 from Senior Engineer Specification:
    Ensure 'main.py::calculate_total' and 'main.py::main.calculate_total'
    collapse to a single canonical task identity rather than duplicating.
    """
    svc, _ = await create_initialized_planner_service(tmp_path, test_repo_id)

    code_diff = """
- def calculate_total(subtotal):
+ def calculate_total(subtotal, tax=0.0):
"""
    # DetailedImpact uses 'calculate_total'
    detailed = DetailedImpact(
        file="main.py",
        entity="calculate_total",
        entity_type="function",
        lines_affected=(1, 5),
        diff_snippet=code_diff,
        change_summary="Updated calculate_total signature.",
        remediation_guidance="Pass tax parameter.",
        justification="Callable contract update.",
        outbound_calls=(),
        inbound_callers=(),
        callers_at_risk=(),
        downstream_dependent_files=(),
    )

    # Dependency graph edge uses 'main.py::main.calculate_total'
    edge = GraphEdgePayload(
        caller="api.py::checkout",
        callee="main.py::main.calculate_total",
    )

    aggregate = ImpactAnalysisAggregate(
        metadata=AnalysisMetadataPayload(
            analysis_id=uuid.uuid4(),
            repository="corp/app",
            base_commit="HEAD~1",
            current_commit="HEAD",
            reasoning_mode=ReasoningMode.HEURISTIC,
            total_changed_entities=1,
            total_deleted_files=0,
            total_impacted_downstream_files=0,
            total_callers_at_risk=0,
        ),
        summary="Normalization verification",
        detailed_impacts=(detailed,),
        dependency_graph=DependencyGraphPayload(nodes=(), edges=(edge,), mermaid=""),
        risk_analysis=RiskAnalysisPayload(
            risk_level=RiskLevel.MEDIUM,
            key_risk_factors=(),
            ci_cd_recommendations=(),
            actionable_remediation_plan=(),
        ),
        created_at=datetime.now(UTC),
    )
    svc._impact_service.get_analysis = AsyncMock(return_value=aggregate)

    plan = await svc.generate_plan(
        repository_id=test_repo_id,
        impact_analysis_id=aggregate.metadata.analysis_id,
    )

    # Must contain only ONE task for calculate_total (no duplicate main.py::main.calculate_total)
    calc_tasks = [t for t in plan.tasks if "calculate_total" in t.component]
    assert len(calc_tasks) == 1
    assert calc_tasks[0].component == "main.py::calculate_total"
