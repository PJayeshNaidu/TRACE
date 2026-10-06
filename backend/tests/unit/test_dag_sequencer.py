"""Unit tests for DagSequencer."""

from trace.analysis.planner.dag_sequencer import DagSequencer
from trace.domain.plan import TaskCategory


def test_empty_nodes_returns_empty_list() -> None:
    assert DagSequencer.sequence_tasks([]) == []


def test_linear_caller_callee_ordering() -> None:
    # A calls B, B calls C.
    # Therefore C must be updated before B, and B before A.
    nodes = [
        {"component": "A", "category": TaskCategory.CORE_LOGIC},
        {"component": "B", "category": TaskCategory.CORE_LOGIC},
        {"component": "C", "category": TaskCategory.CORE_LOGIC},
    ]
    call_edges = [
        ("A", "B"),
        ("B", "C"),
    ]

    seq = DagSequencer.sequence_tasks(nodes, call_edges)
    ordered_components = [s.component for s in seq]

    assert ordered_components == ["C", "B", "A"]
    assert seq[0].step_number == 1
    assert seq[1].step_number == 2
    assert seq[2].step_number == 3
    assert "B" in seq[2].dependencies
    assert "C" in seq[1].dependencies


def test_architectural_tier_precedence_as_tie_breaker() -> None:
    # Multiple independent components; should be sorted by architectural tier:
    # Contract (tier 1) -> Service (tier 2) -> Mapping (tier 3) -> Test (tier 6) -> Docs (tier 7)
    nodes = [
        {"component": "README.md", "category": TaskCategory.DOCUMENTATION_CONFIG},
        {"component": "test_pay", "category": TaskCategory.INTEGRATION_TEST},
        {"component": "PaymentService", "category": TaskCategory.CORE_LOGIC},
        {"component": "PaymentAPI", "category": TaskCategory.CONTRACT_API},
        {"component": "PaymentModel", "category": TaskCategory.DATA_MAPPING},
    ]

    seq = DagSequencer.sequence_tasks(nodes)
    ordered_categories = [s.category for s in seq]

    assert ordered_categories == [
        TaskCategory.CONTRACT_API,
        TaskCategory.CORE_LOGIC,
        TaskCategory.DATA_MAPPING,
        TaskCategory.INTEGRATION_TEST,
        TaskCategory.DOCUMENTATION_CONFIG,
    ]


def test_circular_dependency_handling_via_tarjan_scc() -> None:
    # Mutual cycle: A calls B and B calls A. Plus C calls A.
    nodes = [
        {"component": "A", "category": TaskCategory.CORE_LOGIC},
        {"component": "B", "category": TaskCategory.CORE_LOGIC},
        {"component": "C", "category": TaskCategory.CORE_LOGIC},
    ]
    call_edges = [
        ("A", "B"),
        ("B", "A"),
        ("C", "A"),
    ]

    seq = DagSequencer.sequence_tasks(nodes, call_edges)
    assert len(seq) == 3

    # Both A and B must be tagged as circular
    comp_map = {s.component: s for s in seq}
    assert comp_map["A"].is_circular is True
    assert comp_map["B"].is_circular is True
    assert comp_map["C"].is_circular is False

    # C depends on the cycle, so C must come after A and B
    step_a = comp_map["A"].step_number
    step_b = comp_map["B"].step_number
    step_c = comp_map["C"].step_number
    assert step_c > step_a
    assert step_c > step_b


def test_parallel_execution_streams_for_disconnected_components() -> None:
    # Disconnected subgraphs: (X -> Y) and (P -> Q)
    nodes = [
        {"component": "X", "category": TaskCategory.CORE_LOGIC},
        {"component": "Y", "category": TaskCategory.CORE_LOGIC},
        {"component": "P", "category": TaskCategory.CORE_LOGIC},
        {"component": "Q", "category": TaskCategory.CORE_LOGIC},
    ]
    call_edges = [
        ("X", "Y"),  # Y before X
        ("P", "Q"),  # Q before P
    ]

    seq = DagSequencer.sequence_tasks(nodes, call_edges)
    assert len(seq) == 4

    comp_map = {s.component: s for s in seq}
    # Nodes in the same connected component have the same group id
    assert comp_map["X"].parallel_group_id == comp_map["Y"].parallel_group_id
    assert comp_map["P"].parallel_group_id == comp_map["Q"].parallel_group_id
    # Disconnected components have distinct group ids
    assert comp_map["X"].parallel_group_id != comp_map["P"].parallel_group_id
