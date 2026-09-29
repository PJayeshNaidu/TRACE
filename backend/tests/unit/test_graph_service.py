"""Unit tests for GraphService — F03 Dependency Graph."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from trace.domain.analysis import AnalysisRun, AnalysisStatus
from trace.domain.graph import GraphBuildStatus
from trace.infrastructure.graph.gateway import GraphNotConfiguredError, StubGraphGateway
from trace.domain.health import GraphConnectivityState


# ---------------------------------------------------------------------------
# Minimal RepositoryAnalysis factory
# ---------------------------------------------------------------------------


def _make_analysis_run(
    run_id: uuid.UUID,
    repo_id: uuid.UUID,
    status: AnalysisStatus = AnalysisStatus.COMPLETED,
) -> AnalysisRun:
    now = datetime.now(UTC)
    return AnalysisRun(
        id=run_id,
        repository_id=repo_id,
        project_id=uuid.uuid4(),
        status=status,
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_and_graph_service(in_memory_db_gateway):
    """Return (db_gateway, GraphService) using in-memory SQLite + StubGraphGateway."""
    from trace.services.graph import GraphService
    from unittest.mock import AsyncMock

    stub_graph = StubGraphGateway(
        initial_state=GraphConnectivityState.REACHABLE,
        build_graph_result=(42, 87),
    )

    # Mock AnalysisService so we don't need a full repo + artifact store
    analysis_svc = AsyncMock()

    graph_svc = GraphService(
        db_gateway=in_memory_db_gateway,
        graph_gateway=stub_graph,
        analysis_service=analysis_svc,
    )
    return in_memory_db_gateway, stub_graph, analysis_svc, graph_svc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGraphServiceBuildDependencyGraph:
    """Tests for GraphService.build_dependency_graph()."""

    async def test_happy_path_creates_completed_build_run(
        self, db_and_graph_service, in_memory_db_gateway
    ):
        """A completed analysis run triggers a successful graph build."""
        from trace.domain.analysis import RepositoryAnalysis
        from trace.infrastructure.database.models import AnalysisRunOrm, RepositoryOrm, ProjectOrm
        from sqlalchemy.ext.asyncio import AsyncSession
        from trace.services.graph import GraphService
        from trace.infrastructure.graph.gateway import StubGraphGateway
        from trace.domain.health import GraphConnectivityState

        db, stub_graph, analysis_svc, graph_svc = db_and_graph_service

        run_id = uuid.uuid4()
        repo_id = uuid.uuid4()
        project_id = uuid.uuid4()
        now = datetime.now(UTC)

        # Insert prerequisite rows directly
        async with in_memory_db_gateway.session() as session:
            session.add(ProjectOrm(
                id=project_id,
                name="TestProject",
                status="ACTIVE",
                created_at=now,
                updated_at=now,
            ))
            session.add(RepositoryOrm(
                id=repo_id,
                project_id=project_id,
                type="LOCAL",
                location="/tmp/repo",
                status="REGISTERED",
                created_at=now,
                updated_at=now,
            ))
            session.add(AnalysisRunOrm(
                id=run_id,
                repository_id=repo_id,
                project_id=project_id,
                status=AnalysisStatus.COMPLETED,
                resolved_revision="abc123",
                created_at=now,
                updated_at=now,
            ))
            await session.commit()

        # Mock the artifact returned by AnalysisService
        from tests.fixtures import make_minimal_repository_analysis  # type: ignore[import]
        analysis_svc.get_analysis_artifact = AsyncMock(
            return_value=make_minimal_repository_analysis(run_id, repo_id)
        )

        result = await graph_svc.build_dependency_graph(run_id)

        assert result.status == GraphBuildStatus.COMPLETED
        assert result.analysis_run_id == run_id
        assert result.nodes_created == 42
        assert result.relationships_created == 87
        assert result.duration_ms is not None and result.duration_ms >= 0
        assert str(run_id) in stub_graph.build_calls

    async def test_analysis_not_found_raises(self, db_and_graph_service):
        """Missing analysis run raises AnalysisRunNotFoundError."""
        from trace.domain.exceptions import AnalysisRunNotFoundError

        _, _, _, graph_svc = db_and_graph_service
        with pytest.raises(AnalysisRunNotFoundError):
            await graph_svc.build_dependency_graph(uuid.uuid4())

    async def test_analysis_not_completed_raises(
        self, db_and_graph_service, in_memory_db_gateway
    ):
        """Analysis run in PENDING state raises InvalidAnalysisStateError."""
        from trace.domain.exceptions import InvalidAnalysisStateError
        from trace.infrastructure.database.models import AnalysisRunOrm, RepositoryOrm, ProjectOrm

        _, _, _, graph_svc = db_and_graph_service
        run_id = uuid.uuid4()
        repo_id = uuid.uuid4()
        project_id = uuid.uuid4()
        now = datetime.now(UTC)

        async with in_memory_db_gateway.session() as session:
            session.add(ProjectOrm(id=project_id, name="P", status="ACTIVE",
                                   created_at=now, updated_at=now))
            session.add(RepositoryOrm(id=repo_id, project_id=project_id,
                                      type="LOCAL",
                                      location="/x", status="REGISTERED",
                                      created_at=now, updated_at=now))
            session.add(AnalysisRunOrm(
                id=run_id, repository_id=repo_id, project_id=project_id,
                status=AnalysisStatus.PENDING,
                resolved_revision="abc",
                created_at=now, updated_at=now,
            ))
            await session.commit()

        with pytest.raises(InvalidAnalysisStateError):
            await graph_svc.build_dependency_graph(run_id)

    async def test_graph_not_configured_results_in_failed_run(
        self, in_memory_db_gateway
    ):
        """GraphNotConfiguredError is caught and stored as a FAILED build run."""
        from trace.services.graph import GraphService
        from trace.infrastructure.graph.gateway import StubGraphGateway, GraphNotConfiguredError
        from trace.infrastructure.database.models import AnalysisRunOrm, RepositoryOrm, ProjectOrm

        stub_graph = StubGraphGateway(
            initial_state=GraphConnectivityState.NOT_CONFIGURED,
            raise_on_build=GraphNotConfiguredError(),
        )
        analysis_svc = AsyncMock()

        graph_svc = GraphService(
            db_gateway=in_memory_db_gateway,
            graph_gateway=stub_graph,
            analysis_service=analysis_svc,
        )

        run_id = uuid.uuid4()
        repo_id = uuid.uuid4()
        project_id = uuid.uuid4()
        now = datetime.now(UTC)

        async with in_memory_db_gateway.session() as session:
            session.add(ProjectOrm(id=project_id, name="P", status="ACTIVE",
                                   created_at=now, updated_at=now))
            session.add(RepositoryOrm(id=repo_id, project_id=project_id,
                                      type="LOCAL",
                                      location="/x", status="REGISTERED",
                                      created_at=now, updated_at=now))
            session.add(AnalysisRunOrm(
                id=run_id, repository_id=repo_id, project_id=project_id,
                status=AnalysisStatus.COMPLETED,
                resolved_revision="abc",
                created_at=now, updated_at=now,
            ))
            await session.commit()

        from tests.fixtures import make_minimal_repository_analysis  # type: ignore[import]
        analysis_svc.get_analysis_artifact = AsyncMock(
            return_value=make_minimal_repository_analysis(run_id, repo_id)
        )

        result = await graph_svc.build_dependency_graph(run_id)

        assert result.status == GraphBuildStatus.FAILED
        assert result.error_message is not None
        assert "Neo4j" in result.error_message


class TestGraphServiceGetLatestBuildRun:
    """Tests for GraphService.get_latest_build_run()."""

    async def test_returns_none_when_no_builds_exist(self, db_and_graph_service):
        """No build run record → returns None."""
        _, _, _, graph_svc = db_and_graph_service
        result = await graph_svc.get_latest_build_run(uuid.uuid4())
        assert result is None
