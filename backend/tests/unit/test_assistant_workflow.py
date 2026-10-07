"""Unit tests for TRACE Assistant LangGraph Workflow Engine.

Tests:
- Question understanding and composite intent classification
- Multi-turn history reference resolution (e.g., "Why?" following a component)
- Tool selection and concurrent dispatch
- Evidence sufficiency evaluation and hard 2-hop iteration bounds
- Synthesis routing (offline deterministic fallback, missing entity guard)
- Response assembly with relevant suggested follow-ups
- Full LangGraph compilation and deterministic termination
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
from trace.services.assistant.workflow import (
    build_assistant_graph,
    create_assemble_node,
    create_execute_tools_node,
    create_select_tools_node,
    create_sufficiency_node,
    create_synthesize_node,
    create_understand_node,
    route_after_sufficiency,
)


@pytest.fixture
def mock_tools():
    """Mock AssistantTools suite for workflow state transitions."""
    tools = MagicMock(spec=AssistantTools)
    tools.resolve_target_run = AsyncMock(return_value=(uuid.uuid4(), uuid.uuid4()))
    tools.get_repository_overview = AsyncMock(return_value={
        "status": "COMPLETED",
        "metrics": {"total_files": 15, "total_classes": 4},
        "entry_points": ["GET /api/v1/orders"],
        "test_counts": 12,
    })
    tools.search_code_symbols = AsyncMock(return_value=[
        {
            "type": "ast",
            "kind": "class",
            "name": "OrderService",
            "qualified_name": "app.services.OrderService",
            "file_path": "order_service.py",
            "start_line": 10,
        }
    ])
    tools.get_symbol_details = AsyncMock(return_value={
        "type": "ast",
        "name": "OrderService",
        "qualified_name": "app.services.OrderService",
        "parameters": ["self"],
        "docstring": "Core order processor.",
        "file_path": "order_service.py",
        "start_line": 10,
        "source_snippet": "class OrderService:\n    pass",
    })
    tools.get_graph_neighborhood = AsyncMock(return_value=[
        {
            "type": "graph",
            "direction": "incoming",
            "source": "app.routes.checkout",
            "target": "app.services.OrderService",
            "relationship": "CALLS",
            "depth": 1,
            "file_path": "checkout.py",
            "line": 42,
        }
    ])
    tools.get_impact_and_risk = AsyncMock(return_value={
        "risk_level": "HIGH",
        "risk_score": 85.0,
        "factors": ["Critical transaction flow", "Direct database write"],
        "callers_at_risk": ["app.routes.checkout"],
        "remediations": ["Add circuit breaker"],
    })
    tools.get_upgrade_plan_tasks = AsyncMock(return_value=[
        {
            "type": "plan",
            "task_id": "TASK-001",
            "step_number": 1,
            "component": "PaymentGateway",
            "tier": "CORE_LOGIC",
            "dependencies": [],
            "status": "PENDING",
            "reason": "Foundational migration",
        }
    ])
    tools.get_change_diffs = AsyncMock(return_value=[
        {
            "type": "diff",
            "symbol_name": "OrderService.process_order",
            "file_path": "order_service.py",
            "change_type": "MODIFIED",
            "is_breaking": True,
            "summary": "Added required parameter",
        }
    ])
    return tools


@pytest.fixture
def synthesis_service():
    """Offline AssistantSynthesisService for deterministic testing."""
    return AssistantSynthesisService(
        config=ApplicationConfig(llm_enable_external_calls=False)
    )


@pytest.mark.asyncio
async def test_understand_question_node(mock_tools):
    """T033: Verify understand_question extracts symbols and identifies composite intents."""
    understand_node = create_understand_node(mock_tools)

    state = AssistantState(
        project_id=uuid.uuid4(),
        question="Why is app.services.OrderService classified as high risk?",
    )
    result = await understand_node(state)

    assert "app.services.OrderService" in result["target_symbols"]
    assert "RISK_EVALUATION" in result["intents"]


@pytest.mark.asyncio
async def test_followup_disambiguation(mock_tools):
    """T039: Verify follow-up questions like 'Why?' resolve target symbol from conversation history."""
    understand_node = create_understand_node(mock_tools)

    history = [
        ChatMessage(role="user", content="Show callers of OrderService"),
        ChatMessage(role="assistant", content="OrderService is called by CheckoutHandler."),
    ]
    state = AssistantState(
        project_id=uuid.uuid4(),
        question="Why is it affected?",
        history=history,
    )
    result = await understand_node(state)

    # Disambiguates 'it' to OrderService from prior turn
    assert any("orderservice" in s.lower() for s in result["target_symbols"])
    assert "IMPACT_DEPENDENCY" in result["intents"]


@pytest.mark.asyncio
async def test_tool_selection_and_execution_nodes(mock_tools):
    """T034: Verify select_tools schedules correct tools and execute_tools executes concurrently."""
    select_tools = create_select_tools_node()
    execute_tools = create_execute_tools_node(mock_tools)

    run_id = uuid.uuid4()
    repo_id = uuid.uuid4()

    state = AssistantState(
        project_id=uuid.uuid4(),
        repository_id=repo_id,
        analysis_run_id=run_id,
        question="Why is OrderService affected?",
        intents=["IMPACT_DEPENDENCY"],
        target_symbols=["OrderService"],
    )

    selection_res = await select_tools(state)
    pending = selection_res["pending_tool_calls"]
    assert len(pending) <= 3
    tool_names = [p["tool"] for p in pending]
    assert "get_impact_and_risk" in tool_names or "get_graph_neighborhood" in tool_names

    # Update state with pending calls and execute
    state.pending_tool_calls = pending
    exec_res = await execute_tools(state)

    assert "raw_evidence" in exec_res
    assert len(exec_res["raw_evidence"]) >= 1
    assert "sources" in exec_res
    assert len(exec_res["sources"]) >= 1
    assert exec_res["iteration_count"] == 1


@pytest.mark.asyncio
async def test_sufficiency_and_hop_limits():
    """T035: Verify sufficiency evaluation and bounded loop routing edge."""
    evaluate_sufficiency = create_sufficiency_node()

    # Case 1: Insufficient evidence, iteration 0 -> Loop back
    state_iter0 = AssistantState(
        project_id=uuid.uuid4(),
        question="Why is OrderService affected?",
        target_symbols=["OrderService"],
        raw_evidence=[],  # No evidence yet
        iteration_count=0,
    )
    res_iter0 = await evaluate_sufficiency(state_iter0)
    assert res_iter0["is_sufficient"] is False
    state_iter0.is_sufficient = False
    assert route_after_sufficiency(state_iter0) == "loop_retrieval"

    # Case 2: Iteration 1 with both graph and diff -> Sufficient, proceed to synthesis
    state_iter1 = AssistantState(
        project_id=uuid.uuid4(),
        question="Why is OrderService affected?",
        target_symbols=["OrderService"],
        raw_evidence=[
            {"type": "graph", "source": "checkout", "target": "OrderService"},
            {"type": "diff", "symbol_name": "OrderService", "change_type": "MODIFIED"},
        ],
        iteration_count=1,
    )
    res_iter1 = await evaluate_sufficiency(state_iter1)
    assert res_iter1["is_sufficient"] is True
    state_iter1.is_sufficient = True
    assert route_after_sufficiency(state_iter1) == "proceed_to_synthesis"

    # Case 3: Insufficient but budget exhausted (iteration 2) -> Hard stop to synthesis
    state_iter2 = AssistantState(
        project_id=uuid.uuid4(),
        question="Why is OrderService affected?",
        target_symbols=["OrderService"],
        raw_evidence=[],
        iteration_count=2,
    )
    res_iter2 = await evaluate_sufficiency(state_iter2)
    assert res_iter2["is_sufficient"] is True  # Budget capped
    assert route_after_sufficiency(state_iter2) == "proceed_to_synthesis"



@pytest.mark.asyncio
async def test_synthesize_node_offline_deterministic(synthesis_service):
    """T042: Verify synthesize_node in offline mode outputs structured markdown and correct model."""
    synthesize_node = create_synthesize_node(synthesis_service)

    state = AssistantState(
        project_id=uuid.uuid4(),
        analysis_run_id=uuid.uuid4(),
        question="Show dependency graph for OrderService",
        target_symbols=["OrderService"],
        raw_evidence=[
            {
                "type": "graph",
                "source": "app.routes.checkout",
                "target": "OrderService",
                "relationship": "CALLS",
                "depth": 1,
                "file_path": "checkout.py",
                "line": 42,
            }
        ],
    )

    res = await synthesize_node(state)
    assert "Dependency Graph Paths" in res["final_answer"]
    assert "app.routes.checkout" in res["final_answer"]
    assert res["grounding_status"] == "FALLBACK_DETERMINISTIC"
    assert res["model_used"] == "offline-deterministic-fallback"


@pytest.mark.asyncio
async def test_missing_entity_guard(synthesis_service):
    """T052: Verify missing entity triggers explicit INSUFFICIENT_EVIDENCE reporting."""
    synthesize_node = create_synthesize_node(synthesis_service)

    state = AssistantState(
        project_id=uuid.uuid4(),
        analysis_run_id=uuid.uuid4(),
        question="Why is NonExistentModule affected?",
        target_symbols=["NonExistentModule"],
        raw_evidence=[],  # Zero evidence found
    )

    res = await synthesize_node(state)
    assert "No verified code symbols, dependency graph edges, or risk records were found" in res["final_answer"]
    assert "`NonExistentModule`" in res["final_answer"]
    assert res["grounding_status"] == "INSUFFICIENT_EVIDENCE"


@pytest.mark.asyncio
async def test_assemble_node():
    """Verify assemble_node generates relevant suggested follow-ups."""
    assemble_node = create_assemble_node()

    state = AssistantState(
        project_id=uuid.uuid4(),
        question="Why is OrderService affected?",
        target_symbols=["OrderService"],
    )

    res = await assemble_node(state)
    followups = res["suggested_followups"]
    assert len(followups) >= 2
    assert any("OrderService" in f for f in followups)


@pytest.mark.asyncio
async def test_full_langgraph_workflow_execution(mock_tools, synthesis_service):
    """T036: Test end-to-end execution of compiled StateGraph."""
    graph = build_assistant_graph(mock_tools, synthesis_service)

    initial_state = AssistantState(
        project_id=uuid.uuid4(),
        analysis_run_id=uuid.uuid4(),
        question="Why is OrderService affected by this change?",
    )

    final_state = await graph.ainvoke(initial_state)

    assert "final_answer" in final_state
    assert len(final_state["final_answer"]) > 0
    assert final_state["grounding_status"] in ("FALLBACK_DETERMINISTIC", "DETERMINISTIC_GROUNDED")
    assert len(final_state["sources"]) >= 1
    assert len(final_state["suggested_followups"]) >= 1
    assert final_state["iteration_count"] <= 2  # Proves bounded iteration


@pytest.mark.asyncio
async def test_diagnostic_routing_plan_task_sequence(mock_tools, synthesis_service):
    """Diagnostic 1: 'Why does Task 1 precede Task 4 in the upgrade plan?' routes to PLAN_TASK and retrieves upgrade plan."""
    mock_tools.get_upgrade_plan_tasks = AsyncMock(return_value=[
        {
            "type": "plan",
            "task_id": "TASK-001",
            "step_number": 1,
            "component": "BaseDatabaseSchema",
            "tier": "FOUNDATION",
            "dependencies": [],
            "status": "COMPLETED",
            "reason": "Root database migration",
        },
        {
            "type": "plan",
            "task_id": "TASK-004",
            "step_number": 4,
            "component": "ApiGateway",
            "tier": "ROUTING",
            "dependencies": ["TASK-001", "task_1", 1],
            "status": "PENDING",
            "reason": "Route handling depends on schema",
        },
    ])

    graph = build_assistant_graph(mock_tools, synthesis_service)
    initial_state = AssistantState(
        project_id=uuid.uuid4(),
        analysis_run_id=uuid.uuid4(),
        repository_id=uuid.uuid4(),
        question="Why does Task 1 precede Task 4 in the upgrade plan?",
    )

    final_state = await graph.ainvoke(initial_state)

    # 1. State/Intent verification
    assert final_state["target_type"] == "PLAN_TASK"
    assert "task_1" in final_state["target_task_ids"]
    assert "task_4" in final_state["target_task_ids"]
    assert "PLAN_SEQUENCE" in final_state["intents"]
    assert final_state["target_symbols"] == []  # Must NOT extract task_1 or task_4 as code symbols

    # 2. Tool invocation verification
    mock_tools.get_upgrade_plan_tasks.assert_awaited()
    # search_code_symbols should not be called with task_1/task_4
    for call in mock_tools.search_code_symbols.await_args_list:
        query_arg = call.args[0] if call.args else call.kwargs.get("query", "")
        assert "task" not in query_arg.lower()

    # 3. Grounding and answer verification
    assert final_state["grounding_status"] in ("FALLBACK_DETERMINISTIC", "DETERMINISTIC_GROUNDED")
    assert final_state["grounding_status"] != "INSUFFICIENT_EVIDENCE"
    assert "Step 1 vs Step 4" in final_state["final_answer"] or "TASK-001" in final_state["final_answer"]
    assert "BaseDatabaseSchema" in final_state["final_answer"]


@pytest.mark.asyncio
async def test_diagnostic_routing_project_run_risk(mock_tools, synthesis_service):
    """Diagnostic 2: 'Why is python-proj-HEAD classified as high risk?' routes to PROJECT_RUN risk evaluation."""
    mock_tools.get_impact_and_risk = AsyncMock(return_value={
        "type": "risk",
        "risk_level": "HIGH",
        "risk_score": 55.0,
        "factors": ["Changed entities: 3", "Downstream files impacted: 1"],
        "target_component": None,
        "remediations": ["Add integration regression tests"],
    })

    graph = build_assistant_graph(mock_tools, synthesis_service)
    initial_state = AssistantState(
        project_id=uuid.uuid4(),
        analysis_run_id=uuid.uuid4(),
        repository_id=uuid.uuid4(),
        question="Why is python-proj-HEAD classified as high risk?",
    )

    final_state = await graph.ainvoke(initial_state)

    # 1. Target type and intent verification
    assert final_state["target_type"] == "PROJECT_RUN"
    assert "RISK_EVALUATION" in final_state["intents"]
    assert final_state["target_symbols"] == []  # Must not invent HEAD or python-proj-HEAD as code symbol targets

    # 2. Tool invocation verification
    mock_tools.get_impact_and_risk.assert_awaited()

    # 3. Evidence not rejected
    assert final_state["grounding_status"] in ("FALLBACK_DETERMINISTIC", "DETERMINISTIC_GROUNDED")
    assert final_state["grounding_status"] != "INSUFFICIENT_EVIDENCE"
    assert "HIGH" in final_state["final_answer"]
    assert "55.0" in final_state["final_answer"]
    assert "Changed entities" in final_state["final_answer"]


@pytest.mark.asyncio
async def test_diagnostic_routing_dependencies_present(mock_tools, synthesis_service):
    """Diagnostic 3: 'what dependencies are present?' routes to general graph/overview without symbol hallucinations."""
    mock_tools.get_graph_neighborhood = AsyncMock(return_value=[
        {
            "type": "graph",
            "direction": "outgoing",
            "source": "PaymentGateway",
            "target": "BankConnector",
            "relationship": "CALLS",
            "depth": 1,
            "file_path": "gateway.py",
            "line": 40,
        }
    ])

    graph = build_assistant_graph(mock_tools, synthesis_service)
    # Include history with prior symbol to ensure history doesn't contaminate standalone general question
    history = [
        ChatMessage(role="user", content="Tell me about OrderService"),
        ChatMessage(role="assistant", content="OrderService processes customer orders."),
    ]
    initial_state = AssistantState(
        project_id=uuid.uuid4(),
        analysis_run_id=uuid.uuid4(),
        repository_id=uuid.uuid4(),
        question="what dependencies are present?",
        history=history,
    )

    final_state = await graph.ainvoke(initial_state)

    # 1. Target type and symbols verification
    assert final_state["target_type"] == "PROJECT_RUN"
    assert "IMPACT_DEPENDENCY" in final_state["intents"]
    assert final_state["target_symbols"] == []  # Did not latch onto OrderService or HEAD

    # 2. Tool invocation verification
    mock_tools.get_graph_neighborhood.assert_awaited()
    # Confirm symbol passed to get_graph_neighborhood was None (repository scope)
    graph_call = mock_tools.get_graph_neighborhood.await_args
    assert graph_call.kwargs.get("symbol") is None

    # 3. Grounding verification
    assert final_state["grounding_status"] in ("FALLBACK_DETERMINISTIC", "DETERMINISTIC_GROUNDED")
    assert "PaymentGateway" in final_state["final_answer"]
    assert "BankConnector" in final_state["final_answer"]


@pytest.mark.asyncio
async def test_regression_cases_a_through_m_and_followup(mock_tools, synthesis_service):
    """Verify routing and entity extraction for regression benchmark queries A through M."""
    understand_node = create_understand_node(mock_tools)
    proj_id = uuid.uuid4()

    # Case A: Repository/revision context, HEAD not treated as a Python symbol
    res_a = await understand_node(AssistantState(project_id=proj_id, question="What functions and components depend on python-proj-HEAD?"))
    assert res_a["target_type"] == "PROJECT_RUN"
    assert "IMPACT_DEPENDENCY" in res_a["intents"]
    assert res_a["target_symbols"] == []
    assert "HEAD" not in res_a["target_symbols"]

    # Case B: Symbol/component resolution
    res_b = await understand_node(AssistantState(project_id=proj_id, question="Show all callers of OrderService"))
    assert res_b["target_type"] == "CODE_SYMBOL"
    assert "OrderService" in res_b["target_symbols"]
    assert "IMPACT_DEPENDENCY" in res_b["intents"]

    # Case C: Impact/dependency retrieval for symbol
    res_c = await understand_node(AssistantState(project_id=proj_id, question="Why is OrderService affected?"))
    assert res_c["target_type"] == "CODE_SYMBOL"
    assert "OrderService" in res_c["target_symbols"]
    assert "IMPACT_DEPENDENCY" in res_c["intents"]

    # Case D: Version comparison / change exploration
    res_d = await understand_node(AssistantState(project_id=proj_id, question="What changed between v1.0 and v2.0?"))
    assert res_d["target_type"] == "VERSION_CHANGE"
    assert "CHANGE_EXPLORATION" in res_d["intents"]
    assert "v1.0" not in res_d["target_symbols"]
    assert "v2.0" not in res_d["target_symbols"]

    # Case E: Dependency / impact for PaymentAPI
    res_e = await understand_node(AssistantState(project_id=proj_id, question="Show me everything affected by PaymentAPI."))
    assert res_e["target_type"] == "CODE_SYMBOL"
    assert "PaymentAPI" in res_e["target_symbols"]
    assert "IMPACT_DEPENDENCY" in res_e["intents"]

    # Case F: Affected components with low test coverage
    res_f = await understand_node(AssistantState(project_id=proj_id, question="Which affected components have low test coverage?"))
    assert res_f["target_type"] == "PROJECT_RUN"
    assert "RISK_EVALUATION" in res_f["intents"]
    assert res_f["target_symbols"] == []

    # Case G: Risk analysis
    res_g = await understand_node(AssistantState(project_id=proj_id, question="Why was this component classified as high risk?"))
    assert res_g["target_type"] == "PROJECT_RUN"
    assert "RISK_EVALUATION" in res_g["intents"]

    # Case H: Upgrade plan sequencing
    res_h = await understand_node(AssistantState(project_id=proj_id, question="Which changes should be implemented first?"))
    assert res_h["target_type"] == "PLAN_TASK"
    assert "PLAN_SEQUENCE" in res_h["intents"]

    # Case I: Expected dependencies missed
    res_i = await understand_node(AssistantState(project_id=proj_id, question="Which expected dependencies appear to have been missed?"))
    assert res_i["target_type"] == "PROJECT_RUN"
    assert "IMPACT_DEPENDENCY" in res_i["intents"]

    # Case J: Project language
    res_j = await understand_node(AssistantState(project_id=proj_id, question="What language is the code written in?"))
    assert res_j["target_type"] == "PROJECT_RUN"
    assert "PROJECT_OVERVIEW" in res_j["intents"]

    # Case K: Project overview
    res_k = await understand_node(AssistantState(project_id=proj_id, question="What is this project?"))
    assert res_k["target_type"] == "PROJECT_RUN"
    assert "PROJECT_OVERVIEW" in res_k["intents"]

    # Case L: Codebase feasibility search (not failing on missing payment symbol)
    res_l = await understand_node(AssistantState(project_id=proj_id, question="Can I add payment-related functions to this codebase?"))
    assert res_l["target_type"] == "PROJECT_RUN"
    assert "CODE_SEARCH" in res_l["intents"]

    # Case M: General knowledge bypass
    res_m = await understand_node(AssistantState(project_id=proj_id, question="Why is the sky blue?"))
    assert res_m["target_type"] == "NONE"
    assert "GENERAL_KNOWLEDGE" in res_m["intents"]

    # Follow-up preservation test
    history = [
        ChatMessage(role="user", content="What functions and components depend on python-proj-HEAD?"),
        ChatMessage(role="assistant", content="python-proj-HEAD is the active repository context."),
    ]
    res_followup = await understand_node(AssistantState(project_id=proj_id, question="Show all callers", history=history))
    assert res_followup["target_type"] == "PROJECT_RUN"
    assert "IMPACT_DEPENDENCY" in res_followup["intents"]
    assert res_followup["target_symbols"] == []
    assert "HEAD" not in res_followup["target_symbols"]

