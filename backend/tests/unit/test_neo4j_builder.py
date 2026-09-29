"""Unit tests for Neo4jGraphBuilder — F03 Dependency Graph."""

from __future__ import annotations

import uuid

import pytest

from tests.fixtures import make_minimal_repository_analysis
from trace.infrastructure.graph.neo4j_builder import (
    Neo4jGraphBuilder,
    _build_node_rows,
    _build_rel_rows,
    _node_id,
)


class TestNodeIdGeneration:
    """Tests for the node ID generation helper."""

    def test_node_id_is_deterministic(self):
        """Same inputs always produce the same ID."""
        run_id = "run-abc"
        assert _node_id("Module", "trace.services.payment", run_id) == \
               _node_id("Module", "trace.services.payment", run_id)

    def test_node_id_is_unique_across_labels(self):
        """Same key with different labels produces different IDs."""
        run_id = "run-abc"
        m_id = _node_id("Module", "trace.payment", run_id)
        c_id = _node_id("Class", "trace.payment", run_id)
        assert m_id != c_id

    def test_node_id_is_unique_across_runs(self):
        """Same key + label with different run_ids produces different IDs."""
        m1 = _node_id("Module", "trace.payment", "run-1")
        m2 = _node_id("Module", "trace.payment", "run-2")
        assert m1 != m2


class TestBuildNodeRows:
    """Tests for the node row builder function."""

    def test_produces_correct_label_keys(self):
        """All expected labels appear as keys in the output dict."""
        analysis = make_minimal_repository_analysis()
        rows = _build_node_rows(analysis)
        assert "AnalysisRoot" in rows
        assert "Module" in rows
        assert "Class" in rows
        assert "Function" in rows

    def test_analysis_root_always_present(self):
        """AnalysisRoot always has exactly one row."""
        analysis = make_minimal_repository_analysis()
        rows = _build_node_rows(analysis)
        assert len(rows["AnalysisRoot"]) == 1

    def test_module_count_matches_analysis(self):
        """Module rows count equals analysis.modules count."""
        analysis = make_minimal_repository_analysis()
        rows = _build_node_rows(analysis)
        assert len(rows["Module"]) == len(analysis.modules)

    def test_class_count_matches_analysis(self):
        analysis = make_minimal_repository_analysis()
        rows = _build_node_rows(analysis)
        assert len(rows["Class"]) == len(analysis.classes)

    def test_function_count_matches_analysis(self):
        analysis = make_minimal_repository_analysis()
        rows = _build_node_rows(analysis)
        assert len(rows["Function"]) == len(analysis.functions)

    def test_all_node_rows_have_id_and_analysis_run_id(self):
        """Every node row must have 'id' and 'analysis_run_id' keys."""
        analysis = make_minimal_repository_analysis()
        rows = _build_node_rows(analysis)
        for label, label_rows in rows.items():
            for row in label_rows:
                assert "id" in row, f"Missing 'id' in {label} row: {row}"
                assert "analysis_run_id" in row, f"Missing 'analysis_run_id' in {label} row"

    def test_node_ids_are_unique_within_label(self):
        """All node IDs within a single label are unique."""
        analysis = make_minimal_repository_analysis()
        rows = _build_node_rows(analysis)
        for label, label_rows in rows.items():
            ids = [r["id"] for r in label_rows]
            assert len(ids) == len(set(ids)), f"Duplicate IDs in {label} rows"

    def test_analysis_run_id_matches(self):
        """All node rows carry the correct analysis_run_id string."""
        analysis = make_minimal_repository_analysis()
        expected = str(analysis.run_id)
        rows = _build_node_rows(analysis)
        for label, label_rows in rows.items():
            for row in label_rows:
                assert row["analysis_run_id"] == expected, \
                    f"Wrong analysis_run_id in {label} row"


class TestBuildRelRows:
    """Tests for the relationship row builder function."""

    def test_rel_count_matches_analysis(self):
        """Relationship rows include all static relationships plus structural containment edges."""
        analysis = make_minimal_repository_analysis()
        rows = _build_rel_rows(analysis)
        assert len(rows) >= len(analysis.relationships)
        rel_types = {r["rel_type"] for r in rows}
        assert "CALLS" in rel_types
        assert "DEFINES" in rel_types

    def test_all_rel_rows_have_required_keys(self):
        """Every relationship row must have source_id, target_id, rel_type, analysis_run_id."""
        analysis = make_minimal_repository_analysis()
        rows = _build_rel_rows(analysis)
        for row in rows:
            assert "source_id" in row
            assert "target_id" in row
            assert "rel_type" in row
            assert "analysis_run_id" in row

    def test_rel_type_is_string(self):
        """Relationship type must be a plain string (enum value, not the enum itself)."""
        analysis = make_minimal_repository_analysis()
        rows = _build_rel_rows(analysis)
        for row in rows:
            assert isinstance(row["rel_type"], str)

    def test_empty_analysis_produces_no_rels(self):
        """An analysis with no relationships produces no rows."""
        import uuid as _uuid
        from datetime import datetime, UTC as _UTC
        from trace.domain.analysis import RepositoryAnalysis

        analysis = RepositoryAnalysis(
            run_id=_uuid.uuid4(),
            repository_id=_uuid.uuid4(),
            analyzed_at=datetime.now(_UTC),
            files=(),
            modules=(),
            classes=(),
            functions=(),
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
        )
        rows = _build_rel_rows(analysis)
        assert rows == []


class TestNeo4jGraphBuilderPublicInterface:
    """Tests for Neo4jGraphBuilder public helper methods."""

    def test_node_id_static_method(self):
        builder = Neo4jGraphBuilder()
        nid = builder.node_id("Function", "trace.foo.bar", "run-1")
        assert "Function" in nid
        assert "trace.foo.bar" in nid
        assert "run-1" in nid

    def test_build_node_rows_via_instance(self):
        builder = Neo4jGraphBuilder()
        analysis = make_minimal_repository_analysis()
        rows = builder.build_node_rows(analysis)
        assert isinstance(rows, dict)
        assert "Module" in rows

    def test_build_rel_rows_via_instance(self):
        builder = Neo4jGraphBuilder()
        analysis = make_minimal_repository_analysis()
        rows = builder.build_rel_rows(analysis)
        assert isinstance(rows, list)


class TestStubGraphGateway:
    """Tests for StubGraphGateway determinism."""

    async def test_build_graph_records_call(self):
        from trace.infrastructure.graph.gateway import StubGraphGateway
        from trace.domain.health import GraphConnectivityState

        stub = StubGraphGateway(
            initial_state=GraphConnectivityState.REACHABLE,
            build_graph_result=(10, 20),
        )
        analysis = make_minimal_repository_analysis()
        nodes, rels = await stub.build_graph(analysis)

        assert nodes == 10
        assert rels == 20
        assert str(analysis.run_id) in stub.build_calls

    async def test_build_graph_raises_when_configured(self):
        from trace.infrastructure.graph.gateway import StubGraphGateway, GraphNotConfiguredError
        from trace.domain.health import GraphConnectivityState

        stub = StubGraphGateway(
            initial_state=GraphConnectivityState.NOT_CONFIGURED,
            raise_on_build=GraphNotConfiguredError(),
        )
        analysis = make_minimal_repository_analysis()

        with pytest.raises(GraphNotConfiguredError):
            await stub.build_graph(analysis)

    async def test_clear_graph_records_call(self):
        from trace.infrastructure.graph.gateway import StubGraphGateway
        from trace.domain.health import GraphConnectivityState

        stub = StubGraphGateway(initial_state=GraphConnectivityState.REACHABLE)
        deleted = await stub.clear_graph("some-run-id")
        assert deleted == 0
        assert "some-run-id" in stub.clear_calls
