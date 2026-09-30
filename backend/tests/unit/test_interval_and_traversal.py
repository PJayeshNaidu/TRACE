"""Unit tests for AST interval overlap, decorator expansion, and transposed graph BFS."""

from datetime import UTC, datetime
import pytest
from trace.analysis.graph_traversal import MermaidGenerator, TransposedGraphEngine
from trace.analysis.interval_overlap import (
    IntervalOverlapEngine,
    extract_diff_patch_snippet,
    hunk_to_interval,
    intervals_overlap,
)
from trace.domain.analysis import (
    Call,
    CallResolutionStatus,
    DecoratorDescriptor,
    EntityKind,
    Function,
    FunctionKind,
    RepositoryAnalysis,
    SourceLocation,
)
from trace.domain.diff import DiffHunk, FileChangeType, FileDiff


def test_hunk_to_interval():
    """Verify hunk conversion to inclusive 1-indexed line interval."""
    hunk1 = DiffHunk(old_start=10, old_lines=5, new_start=15, new_lines=10, header="", content="")
    assert hunk_to_interval(hunk1) == (15, 24)

    hunk_zero = DiffHunk(old_start=10, old_lines=5, new_start=15, new_lines=0, header="", content="")
    assert hunk_to_interval(hunk_zero) == (15, 15)


def test_intervals_overlap():
    """Verify mathematical overlap condition max(F_s, H_s) <= min(F_e, H_e)."""
    # Overlapping intervals
    assert intervals_overlap(10, 20, 15, 25) is True
    assert intervals_overlap(10, 20, 20, 30) is True
    assert intervals_overlap(10, 20, 5, 12) is True
    assert intervals_overlap(10, 20, 12, 18) is True

    # Disjoint intervals
    assert intervals_overlap(10, 20, 21, 30) is False
    assert intervals_overlap(10, 20, 1, 9) is False


def test_extract_diff_patch_snippet():
    """Verify only patch lines (+ and -) are extracted and capped."""
    content = "@@ -1,3 +1,3 @@\n def hello():\n-    return 1\n+    return 2"
    snippet = extract_diff_patch_snippet(content, max_chars=100)
    assert "-    return 1" in snippet
    assert "+    return 2" in snippet
    assert "def hello():" not in snippet  # Context line skipped


def test_interval_overlap_engine_with_decorator_expansion():
    """Verify function interval expands to include preceding decorators."""
    engine = IntervalOverlapEngine()

    func = Function(
        name="secure_endpoint",
        qualified_name="api.secure_endpoint",
        module_name="api",
        enclosing_class=None,
        location=SourceLocation(file_path="api.py", start_line=15, end_line=25),
        kind=FunctionKind.FUNCTION,
        parameters=(),
        return_type="dict",
        decorators=(
            DecoratorDescriptor(name="app.get", raw_expression='@app.get("/secure")', line_number=12),
        ),
        docstring=None,
    )

    analysis = RepositoryAnalysis(
        run_id=None,
        repository_id=None,
        analyzed_at=datetime.now(UTC),
        files=(),
        modules=(),
        classes=(),
        functions=(func,),
        services=(),
        imports=(),
        calls=(),
        endpoints=(),
        configurations=(),
        database_references=(),
        tests=(),
        documentation=(),
        dependencies=(),
        relationships=(),
        diagnostics=(),
        summary={},
    )

    # Hunk modifying lines 12-13 (the decorator)
    hunk = DiffHunk(
        old_start=12,
        old_lines=2,
        new_start=12,
        new_lines=2,
        header="",
        content='-@app.get("/secure")\n+@app.get("/v2/secure")',
    )
    file_diff = FileDiff(
        old_path="api.py",
        new_path="api.py",
        change_type=FileChangeType.MODIFIED,
        insertions=1,
        deletions=1,
        hunks=(hunk,),
    )

    overlaps = engine.find_modified_entities([file_diff], analysis)
    assert len(overlaps) == 1
    assert overlaps[0].entity_name == "secure_endpoint"
    assert "+@app.get" in overlaps[0].diff_snippet


def test_transposed_graph_multi_hop_bfs():
    """Verify G^T inversion and multi-hop BFS caller reachability."""
    engine = TransposedGraphEngine(max_depth=3)

    # Chain: A calls B calls C (modified)
    call_bc = Call(
        caller_qualified_name="pkg.b",
        callee_expression="pkg.c",
        resolved_target="pkg.c",
        resolution_status=CallResolutionStatus.RESOLVED_INTERNAL,
        location=SourceLocation("b.py", 10, 10),
    )
    call_ab = Call(
        caller_qualified_name="pkg.a",
        callee_expression="pkg.b",
        resolved_target="pkg.b",
        resolution_status=CallResolutionStatus.RESOLVED_INTERNAL,
        location=SourceLocation("a.py", 5, 5),
    )

    analysis = RepositoryAnalysis(
        run_id=None,
        repository_id=None,
        analyzed_at=datetime.now(UTC),
        files=(),
        modules=(),
        classes=(),
        functions=(),
        services=(),
        imports=(),
        calls=(call_bc, call_ab),
        endpoints=(),
        configurations=(),
        database_references=(),
        tests=(),
        documentation=(),
        dependencies=(),
        relationships=(),
        diagnostics=(),
        summary={},
    )

    _, transposed, symbol_files = engine.build_call_graphs(analysis)
    assert "pkg.b" in transposed.get("pkg.c", set())
    assert "pkg.a" in transposed.get("pkg.b", set())

    # Traverse from pkg.c
    res = engine.traverse_blast_radius("pkg.c", transposed, symbol_files)
    assert "pkg.b" in res.direct_callers

    # Callers at risk should have B at depth 1 and A at depth 2
    distances = {c.qualified_name: c.distance for c in res.callers_at_risk}
    assert distances.get("pkg.b") == 1
    assert distances.get("pkg.a") == 2


def test_mermaid_generator():
    """Verify styled Mermaid diagram generation."""
    generator = MermaidGenerator()
    from trace.domain.impact import GraphEdgePayload, GraphNodePayload

    nodes = [GraphNodePayload(changed_entity="calculate_tax", file="tax.py")]
    edges = [GraphEdgePayload(caller="checkout", callee="calculate_tax")]

    mermaid = generator.generate(nodes, edges)
    assert "graph TD" in mermaid
    assert "calculate_tax" in mermaid
    assert "checkout" in mermaid
    assert "modifiedNode" in mermaid
    assert "riskNode" in mermaid
