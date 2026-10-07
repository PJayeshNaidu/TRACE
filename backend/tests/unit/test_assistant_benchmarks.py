"""Benchmark Evaluation Suite for TRACE AI Assistant (F10 Evolution).

Implements and verifies the 9 concrete benchmark acceptance scenarios defined in
Section 2.2 of specs/008-ai-assistant/spec.md:

1. Blast Radius & Impact Drilldown ("Why is OrderService affected?")
2. Cross-Version Change Summary ("What changed between two versions?")
3. Transitive Blast Radius Exploration ("Show everything affected by PaymentAPI.")
4. Deficit & Test Coverage Analysis ("Which affected components have low test coverage?")
5. Transparent Risk Rationale ("Why was this classified as high risk?")
6. Upgrade Plan Task Sequencing ("Which changes should be implemented first?")
7. Verifiable Call Edge Evidence ("What evidence supports this dependency?")
8. Bounded Multi-Turn Follow-Up ("Why?")
9. Explicit Insufficient Evidence Reporting ("Why is InventoryReconciliationService affected?")
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from trace.core.config import ApplicationConfig
from trace.schemas.assistant import ChatMessage
from trace.services.assistant.state import AssistantState
from trace.services.assistant.synthesis import AssistantSynthesisService
from trace.services.assistant.tools import AssistantTools
from trace.services.assistant.workflow import build_assistant_graph


@pytest.fixture
def benchmark_harness():
    """Build in-memory fixtures and mock AssistantTools suite modeling TRACE services."""
    project_id = uuid.uuid4()
    analysis_run_id = uuid.uuid4()
    repository_id = uuid.uuid4()

    mock_tools = MagicMock(spec=AssistantTools)
    mock_tools.resolve_target_run = AsyncMock(return_value=(repository_id, analysis_run_id))

    # 1. Overview fixture
    mock_tools.get_repository_overview = AsyncMock(return_value={
        "status": "COMPLETED",
        "metrics": {"total_files": 24, "total_classes": 18, "total_functions": 92},
        "entry_points": ["GET /api/v1/orders", "POST /api/v1/checkout"],
        "test_counts": 3,  # Low overall test count
    })

    # 2. Symbol Registry fixture
    async def mock_search_symbols(query, analysis_run_id, kind=None):
        query_l = query.lower()
        if "order" in query_l:
            return [{
                "type": "ast",
                "kind": "class",
                "name": "OrderService",
                "qualified_name": "app.services.order.OrderService",
                "file_path": "src/services/order_service.py",
                "start_line": 25,
            }]
        elif "payment" in query_l:
            return [{
                "type": "ast",
                "kind": "class",
                "name": "PaymentAPI",
                "qualified_name": "app.api.payment.PaymentAPI",
                "file_path": "src/api/payment_gateway.py",
                "start_line": 15,
            }]
        elif "worker" in query_l:
            return [{
                "type": "ast",
                "kind": "module",
                "name": "worker.py",
                "qualified_name": "src.worker",
                "file_path": "src/worker.py",
                "start_line": 1,
            }]
        elif "billing" in query_l:
            return [{
                "type": "ast",
                "kind": "class",
                "name": "BillingWorker",
                "qualified_name": "app.workers.BillingWorker",
                "file_path": "src/workers/billing.py",
                "start_line": 10,
            }]
        return []

    mock_tools.search_code_symbols = AsyncMock(side_effect=mock_search_symbols)

    # 3. AST Details fixture
    async def mock_symbol_details(qualified_name, analysis_run_id):
        if "inventory" in (qualified_name or "").lower():
            return None
        if "payment" in (qualified_name or "").lower():
            return {
                "type": "ast",
                "name": "process_charge",
                "qualified_name": "app.api.payment.PaymentAPI.process_charge",
                "parameters": ["self", "amount", "currency", "idempotency_key"],
                "docstring": "Execute payment transaction with required idempotency_key.",
                "file_path": "src/api/payment_gateway.py",
                "start_line": 45,
                "complexity": 4,
                "source_snippet": "def process_charge(self, amount: int, currency: str, idempotency_key: str):\n    ...",
            }
        elif any(k in (qualified_name or "").lower() for k in ("order", "billing", "worker", "checkout")):
            return {
                "type": "ast",
                "name": qualified_name.split(".")[-1],
                "qualified_name": qualified_name,
                "parameters": ["self"],
                "file_path": "src/service.py",
                "start_line": 1,
                "complexity": 1,
                "source_snippet": f"# Code for {qualified_name}\npass",
            }
        return None

    mock_tools.get_symbol_details = AsyncMock(side_effect=mock_symbol_details)

    # 4. Graph Neighborhood fixture
    async def mock_graph_neighborhood(symbol, direction="both", depth=2, analysis_run_id=None):
        sym_l = (symbol or "").lower()
        if "order" in sym_l:
            return [
                {
                    "type": "graph",
                    "direction": "outgoing",
                    "source": "OrderService",
                    "target": "payment_gateway.process_charge",
                    "relationship": "CALLS",
                    "depth": 1,
                    "file_path": "src/services/order_service.py",
                    "line": 52,
                }
            ]
        elif "paymentapi" in sym_l or "payment" in sym_l:
            return [
                {
                    "type": "graph",
                    "direction": "incoming",
                    "source": "CheckoutService",
                    "target": "PaymentAPI",
                    "relationship": "CALLS",
                    "depth": 1,
                    "file_path": "src/services/checkout.py",
                    "line": 88,
                },
                {
                    "type": "graph",
                    "direction": "incoming",
                    "source": "BillingWorker",
                    "target": "PaymentAPI",
                    "relationship": "CALLS",
                    "depth": 1,
                    "file_path": "src/workers/billing.py",
                    "line": 34,
                },
                {
                    "type": "graph",
                    "direction": "incoming",
                    "source": "WebUI",
                    "target": "CheckoutService",
                    "relationship": "CALLS",
                    "depth": 2,
                    "file_path": "src/web/routes.py",
                    "line": 112,
                },
            ]
        elif "worker" in sym_l or "queue" in sym_l:
            return [
                {
                    "type": "graph",
                    "direction": "outgoing",
                    "source": "worker.py",
                    "target": "queue_manager.py",
                    "relationship": "CALLS",
                    "depth": 1,
                    "file_path": "src/worker.py",
                    "line": 42,
                }
            ]
        elif "billing" in sym_l:
            return [
                {
                    "type": "graph",
                    "direction": "outgoing",
                    "source": "BillingWorker",
                    "target": "payment_gateway",
                    "relationship": "CALLS",
                    "depth": 1,
                    "file_path": "src/workers/billing.py",
                    "line": 34,
                }
            ]
        return []

    mock_tools.get_graph_neighborhood = AsyncMock(side_effect=mock_graph_neighborhood)

    # 5. Impact and Risk fixture
    async def mock_impact_and_risk(symbol_or_component=None, analysis_run_id=None):
        sym_l = (symbol_or_component or "").lower()
        if "auth" in sym_l:
            return {
                "risk_level": "HIGH",
                "risk_score": 75.0,
                "factors": ["Missing unit test coverage (0 tests found)", "Direct authentication gateway"],
                "callers_at_risk": ["LoginController", "TokenValidator"],
                "remediations": ["Author unit regression tests for auth_service.py"],
            }
        # Default high-risk component fixture
        return {
            "target_component": "CorePaymentEngine",
            "risk_level": "HIGH",
            "risk_score": 78.5,
            "factors": ["High fan-in (14 callers)", "Breaking parameter changes in process_charge"],
            "callers_at_risk": ["OrderService", "BillingWorker", "CheckoutService"],
            "remediations": ["Pin legacy signature and roll out staged upgrade"],
        }

    mock_tools.get_impact_and_risk = AsyncMock(side_effect=mock_impact_and_risk)

    # 6. Upgrade Plan fixture
    async def mock_plan_tasks(task_or_component=None, repository_id=None):
        return [
            {
                "type": "plan",
                "task_id": "TASK-001",
                "step_number": 1,
                "tier": "FOUNDATION",
                "component": "Update Base Schema",
                "dependencies": [],
                "status": "PENDING",
                "reason": "Root database migration prerequisite",
            },
            {
                "type": "plan",
                "task_id": "TASK-002",
                "step_number": 2,
                "tier": "CORE_DOMAIN",
                "component": "Update Payment Gateway",
                "dependencies": ["TASK-001"],
                "status": "PENDING",
                "reason": "Adapts core domain to updated schema",
            },
            {
                "type": "plan",
                "task_id": "TASK-004",
                "step_number": 3,
                "tier": "API_SURFACE",
                "component": "Refactor API Handler",
                "dependencies": ["TASK-001", "TASK-002"],
                "status": "PENDING",
                "reason": "Exposes new idempotency key parameter",
            },
        ]

    mock_tools.get_upgrade_plan_tasks = AsyncMock(side_effect=mock_plan_tasks)

    # 7. Change Diffs fixture
    async def mock_change_diffs(symbol_or_file=None, repository_id=None):
        return [
            {
                "type": "diff",
                "symbol_name": "payment_gateway.process_charge",
                "file_path": "src/api/payment_gateway.py",
                "change_type": "MODIFIED",
                "is_breaking": True,
                "summary": "Added required parameter 'idempotency_key' to process_charge",
            },
            {
                "type": "diff",
                "symbol_name": "models.order",
                "file_path": "src/models/order.py",
                "change_type": "MODIFIED",
                "is_breaking": False,
                "summary": "Added optional timestamp field",
            },
            {
                "type": "diff",
                "symbol_name": "config.settings",
                "file_path": "src/config/settings.py",
                "change_type": "MODIFIED",
                "is_breaking": False,
                "summary": "Updated retry timeout default",
            },
        ]

    mock_tools.get_change_diffs = AsyncMock(side_effect=mock_change_diffs)

    synthesis_service = AssistantSynthesisService(
        config=ApplicationConfig(llm_enable_external_calls=False)
    )

    return {
        "project_id": project_id,
        "analysis_run_id": analysis_run_id,
        "repository_id": repository_id,
        "tools": mock_tools,
        "synthesis": synthesis_service,
    }


# ===========================================================================
# T047: Benchmark Test Harness Setup
# ===========================================================================


@pytest.mark.asyncio
async def test_benchmark_harness_setup(benchmark_harness):
    """T047: Verify benchmark harness initializes mock tools and data fixtures properly."""
    tools = benchmark_harness["tools"]
    run_id = benchmark_harness["analysis_run_id"]
    repo_id = benchmark_harness["repository_id"]

    overview = await tools.get_repository_overview(run_id)
    assert overview["metrics"]["total_files"] == 24
    assert overview["test_counts"] == 3

    symbols = await tools.search_code_symbols("OrderService", run_id)
    assert len(symbols) == 1
    assert symbols[0]["name"] == "OrderService"

    diffs = await tools.get_change_diffs(repository_id=repo_id)
    assert len(diffs) == 3
    assert any(d["is_breaking"] for d in diffs)

    graph = await tools.get_graph_neighborhood("OrderService", analysis_run_id=run_id)
    assert len(graph) == 1
    assert graph[0]["target"] == "payment_gateway.process_charge"


# ===========================================================================
# T048: Benchmarks 1, 2, and 3
# ===========================================================================


@pytest.mark.asyncio
async def test_benchmark_1_blast_radius_multi_hop(benchmark_harness):
    """T048 [Benchmark 1]: 'Why is OrderService affected?' multi-hop causal resolution."""
    tools = benchmark_harness["tools"]
    synthesis = benchmark_harness["synthesis"]
    graph = build_assistant_graph(tools, synthesis)

    initial_state = AssistantState(
        project_id=benchmark_harness["project_id"],
        analysis_run_id=benchmark_harness["analysis_run_id"],
        repository_id=benchmark_harness["repository_id"],
        question="Why is OrderService affected?",
    )

    final_state = await graph.ainvoke(initial_state)

    # 1. State machine completed within bounded iterations
    assert final_state["iteration_count"] <= 2
    assert final_state["grounding_status"] in ("FALLBACK_DETERMINISTIC", "DETERMINISTIC_GROUNDED")

    # 2. Graph citations detected
    sources = final_state["sources"]
    assert any(s.type == "graph" for s in sources), "Must include graph edge source"

    # 3. Multi-hop triggered retrieval of diff or AST details for payment_gateway
    assert any(
        "payment_gateway" in str(e).lower() for e in final_state["raw_evidence"]
    ), "Multi-hop must inspect connected dependency payment_gateway"

    # 4. Final answer explains the call relationship
    ans = final_state["final_answer"]
    assert "OrderService" in ans
    assert "payment_gateway" in ans


@pytest.mark.asyncio
async def test_benchmark_2_cross_version_change_summary(benchmark_harness):
    """T048 [Benchmark 2]: 'What changed between two versions?' syntax diff and breaking flag."""
    tools = benchmark_harness["tools"]
    synthesis = benchmark_harness["synthesis"]
    graph = build_assistant_graph(tools, synthesis)

    initial_state = AssistantState(
        project_id=benchmark_harness["project_id"],
        analysis_run_id=benchmark_harness["analysis_run_id"],
        repository_id=benchmark_harness["repository_id"],
        question="What changed between two versions?",
    )

    final_state = await graph.ainvoke(initial_state)

    # 1. Intent recognized as CHANGE_EXPLORATION
    assert "CHANGE_EXPLORATION" in final_state["intents"]

    # 2. Diff sources present
    sources = final_state["sources"]
    assert any(s.type == "diff" for s in sources), "Must cite diff evidence"

    # 3. Distinguishes breaking from non-breaking changes
    ans = final_state["final_answer"]
    assert "BREAKING" in ans or any(s.metadata.get("is_breaking") for s in sources)
    assert "payment_gateway" in ans


@pytest.mark.asyncio
async def test_benchmark_3_transitive_blast_radius(benchmark_harness):
    """T048 [Benchmark 3]: 'Show everything affected by PaymentAPI.' partitioned by depth."""
    tools = benchmark_harness["tools"]
    synthesis = benchmark_harness["synthesis"]
    graph = build_assistant_graph(tools, synthesis)

    initial_state = AssistantState(
        project_id=benchmark_harness["project_id"],
        analysis_run_id=benchmark_harness["analysis_run_id"],
        repository_id=benchmark_harness["repository_id"],
        question="Show everything affected by PaymentAPI.",
    )

    final_state = await graph.ainvoke(initial_state)

    # 1. Intent is IMPACT_DEPENDENCY
    assert "IMPACT_DEPENDENCY" in final_state["intents"]

    # 2. Both direct callers (1-hop) and transitive callers (2-hop) captured in evidence
    evidence_str = str(final_state["raw_evidence"])
    assert "CheckoutService" in evidence_str
    assert "BillingWorker" in evidence_str
    assert "WebUI" in evidence_str

    # 3. Sources include graph citations
    sources = final_state["sources"]
    graph_sources = [s for s in sources if s.type == "graph"]
    assert len(graph_sources) >= 2


# ===========================================================================
# T049: Benchmarks 4, 5, and 6
# ===========================================================================


@pytest.mark.asyncio
async def test_benchmark_4_low_test_coverage(benchmark_harness):
    """T049 [Benchmark 4]: 'Which affected components have low test coverage?'."""
    tools = benchmark_harness["tools"]
    synthesis = benchmark_harness["synthesis"]
    graph = build_assistant_graph(tools, synthesis)

    initial_state = AssistantState(
        project_id=benchmark_harness["project_id"],
        analysis_run_id=benchmark_harness["analysis_run_id"],
        repository_id=benchmark_harness["repository_id"],
        question="Which affected components have low test coverage?",
    )

    final_state = await graph.ainvoke(initial_state)

    # 1. Intent recognized as RISK_EVALUATION
    assert "RISK_EVALUATION" in final_state["intents"]

    # 2. Invokes get_impact_and_risk and overview
    assert any(s.type == "risk" for s in final_state["sources"])
    ans = final_state["final_answer"]
    assert "Risk" in ans or "test" in ans.lower()


@pytest.mark.asyncio
async def test_benchmark_5_transparent_risk_rationale(benchmark_harness):
    """T049 [Benchmark 5]: 'Why was this classified as high risk?' cites score and factors."""
    tools = benchmark_harness["tools"]
    synthesis = benchmark_harness["synthesis"]
    graph = build_assistant_graph(tools, synthesis)

    initial_state = AssistantState(
        project_id=benchmark_harness["project_id"],
        analysis_run_id=benchmark_harness["analysis_run_id"],
        repository_id=benchmark_harness["repository_id"],
        question="Why was this classified as high risk?",
    )

    final_state = await graph.ainvoke(initial_state)

    # 1. Intent recognized
    assert "RISK_EVALUATION" in final_state["intents"]

    # 2. Risk score and factors cited
    ans = final_state["final_answer"]
    assert "78.5" in ans or any(s.metadata.get("risk_score") == 78.5 for s in final_state["sources"])
    assert "HIGH" in ans or any(s.metadata.get("risk_level") == "HIGH" for s in final_state["sources"])


@pytest.mark.asyncio
async def test_benchmark_6_upgrade_plan_task_sequencing(benchmark_harness):
    """T049 [Benchmark 6]: 'Which changes should be implemented first?' identifies Foundation tasks."""
    tools = benchmark_harness["tools"]
    synthesis = benchmark_harness["synthesis"]
    graph = build_assistant_graph(tools, synthesis)

    initial_state = AssistantState(
        project_id=benchmark_harness["project_id"],
        analysis_run_id=benchmark_harness["analysis_run_id"],
        repository_id=benchmark_harness["repository_id"],
        question="Which changes should be implemented first?",
    )

    final_state = await graph.ainvoke(initial_state)

    # 1. Intent recognized
    assert "PLAN_SEQUENCE" in final_state["intents"]

    # 2. Foundation task (TASK-001) cited in sources and answer
    plan_sources = [s for s in final_state["sources"] if s.type == "plan"]
    assert len(plan_sources) >= 1
    assert any(s.metadata.get("tier") == "FOUNDATION" for s in plan_sources)
    assert "TASK-001" in final_state["final_answer"]


# ===========================================================================
# T050: Benchmark 7
# ===========================================================================


@pytest.mark.asyncio
async def test_benchmark_7_evidence_citation(benchmark_harness):
    """T050 [Benchmark 7]: 'What evidence supports this dependency?' asserts exact file and line."""
    tools = benchmark_harness["tools"]
    synthesis = benchmark_harness["synthesis"]
    graph = build_assistant_graph(tools, synthesis)

    initial_state = AssistantState(
        project_id=benchmark_harness["project_id"],
        analysis_run_id=benchmark_harness["analysis_run_id"],
        repository_id=benchmark_harness["repository_id"],
        question="What evidence supports this dependency for worker.py?",
    )

    final_state = await graph.ainvoke(initial_state)

    # 1. Edge cited with file_path and line number
    ans = final_state["final_answer"]
    sources = final_state["sources"]
    graph_sources = [s for s in sources if s.type == "graph"]

    assert len(graph_sources) >= 1
    edge = graph_sources[0]
    assert edge.metadata.get("file_path") == "src/worker.py"
    assert edge.metadata.get("line") == 42
    assert "src/worker.py:42" in ans or "src/worker.py" in ans


# ===========================================================================
# T051: Benchmark 8
# ===========================================================================


@pytest.mark.asyncio
async def test_benchmark_8_followup_why(benchmark_harness):
    """T051 [Benchmark 8]: Multi-Turn Follow-Up ('Why?') resolving causal entity from history."""
    tools = benchmark_harness["tools"]
    synthesis = benchmark_harness["synthesis"]
    graph = build_assistant_graph(tools, synthesis)

    history = [
        ChatMessage(role="user", content="What is the impact of payment_gateway?"),
        ChatMessage(role="assistant", content="BillingWorker is impacted by a change in payment_gateway."),
    ]

    initial_state = AssistantState(
        project_id=benchmark_harness["project_id"],
        analysis_run_id=benchmark_harness["analysis_run_id"],
        repository_id=benchmark_harness["repository_id"],
        question="Why?",
        history=history,
    )

    final_state = await graph.ainvoke(initial_state)

    # 1. Disambiguation extracted BillingWorker from prior turn
    assert any("billingworker" in s.lower() for s in final_state["target_symbols"])

    # 2. Causality verified via graph / diff linking BillingWorker to payment_gateway
    ans = final_state["final_answer"]
    assert "BillingWorker" in ans or any("billing" in s.identifier.lower() for s in final_state["sources"])


# ===========================================================================
# T052: Benchmark 9
# ===========================================================================


@pytest.mark.asyncio
async def test_benchmark_9_missing_entity(benchmark_harness):
    """T052 [Benchmark 9]: Missing Entity Guard asserting INSUFFICIENT_EVIDENCE status."""
    tools = benchmark_harness["tools"]
    synthesis = benchmark_harness["synthesis"]
    graph = build_assistant_graph(tools, synthesis)

    initial_state = AssistantState(
        project_id=benchmark_harness["project_id"],
        analysis_run_id=benchmark_harness["analysis_run_id"],
        repository_id=benchmark_harness["repository_id"],
        question="Why is InventoryReconciliationService affected?",
    )

    final_state = await graph.ainvoke(initial_state)

    # 1. Strict anti-hallucination guard triggered
    assert final_state["grounding_status"] == "INSUFFICIENT_EVIDENCE"

    # 2. Answer explicitly states symbol not found in analysis run
    ans = final_state["final_answer"]
    assert "No verified code symbols, dependency graph edges, or risk records were found" in ans
    assert "`InventoryReconciliationService`" in ans

    # 3. Zero hallucinated sources
    assert len(final_state["sources"]) == 0
