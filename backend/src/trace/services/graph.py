"""Service layer for F03 Dependency Graph build orchestration.

GraphService coordinates:
  1. Validating that the target analysis run exists and is COMPLETED.
  2. Creating and updating a GraphBuildRun lifecycle record in PostgreSQL.
  3. Delegating actual Neo4j writes to the GraphGateway.
  4. Exposing query methods for build run status.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from trace.domain.analysis import AnalysisStatus
from trace.domain.exceptions import (
    AnalysisRunNotFoundError,
    InvalidAnalysisStateError,
)
from trace.domain.graph import GraphBuildRun, GraphBuildStatus
from trace.infrastructure.database.gateway import DatabaseGateway
from trace.infrastructure.database.models import AnalysisRunOrm, GraphBuildRunOrm
from trace.infrastructure.graph.gateway import GraphGateway, GraphNotConfiguredError

if TYPE_CHECKING:
    from trace.services.analysis import AnalysisService

logger = structlog.get_logger(__name__)


class GraphBuildRunNotFoundError(Exception):
    """Raised when a GraphBuildRun cannot be located by its ID."""

    def __init__(self, build_run_id: uuid.UUID) -> None:
        super().__init__(f"Graph build run {build_run_id} not found.")
        self.build_run_id = build_run_id


class GraphService:
    """Orchestrates the Neo4j dependency graph build lifecycle for F03.

    Responsibilities:
    - Create and persist ``GraphBuildRun`` records in PostgreSQL.
    - Coordinate with ``AnalysisService`` to load the F02 artifact.
    - Delegate Cypher writes to ``GraphGateway``.
    - Expose status queries for build runs.
    """

    def __init__(
        self,
        db_gateway: DatabaseGateway,
        graph_gateway: GraphGateway,
        analysis_service: AnalysisService,
    ) -> None:
        self._db = db_gateway
        self._graph = graph_gateway
        self._analysis = analysis_service

    # ------------------------------------------------------------------
    # Build lifecycle
    # ------------------------------------------------------------------

    async def build_dependency_graph(self, analysis_run_id: uuid.UUID) -> GraphBuildRun:
        """Orchestrate a full Neo4j graph build for a completed analysis run.

        Steps:
        1. Validate analysis run exists and is COMPLETED.
        2. Create a GraphBuildRun record in PENDING state.
        3. Mark IN_PROGRESS.
        4. Load RepositoryAnalysis artifact from the artifact store.
        5. Delegate to GraphGateway.build_graph().
        6. Persist COMPLETED (or FAILED) status with stats.

        Args:
            analysis_run_id: UUID of the COMPLETED analysis run to graph.

        Returns:
            The final GraphBuildRun domain record.

        Raises:
            AnalysisRunNotFoundError: If the analysis run does not exist.
            InvalidAnalysisStateError: If the analysis run is not COMPLETED.
        """
        log = logger.bind(analysis_run_id=str(analysis_run_id))
        log.info("Initiating dependency graph build")

        # 1. Validate analysis run
        repository_id = await self._validate_analysis_run(analysis_run_id)

        # 2. Create PENDING build run record
        build_run_id = uuid.uuid4()
        now = datetime.now(UTC)
        await self._create_build_run(
            build_run_id=build_run_id,
            analysis_run_id=analysis_run_id,
            repository_id=repository_id,
            now=now,
        )

        # 3. Mark IN_PROGRESS
        started_at = datetime.now(UTC)
        await self._update_build_run_status(
            build_run_id=build_run_id,
            status=GraphBuildStatus.IN_PROGRESS,
            started_at=started_at,
        )

        # 4. Load artifact & 5. Build graph
        try:
            analysis = await self._analysis.get_analysis_artifact(analysis_run_id)
            nodes_created, rels_created = await self._graph.build_graph(analysis)

        except GraphNotConfiguredError as exc:
            log.warning("Neo4j not configured — graph build skipped", error=str(exc))
            return await self._fail_build_run(
                build_run_id=build_run_id,
                started_at=started_at,
                error_message=str(exc),
            )

        except Exception as exc:
            log.exception("Graph build failed", error=str(exc))
            return await self._fail_build_run(
                build_run_id=build_run_id,
                started_at=started_at,
                error_message=str(exc),
            )

        # 6. Mark COMPLETED
        completed_at = datetime.now(UTC)
        duration_ms = round((completed_at - started_at).total_seconds() * 1000, 2)

        log.info(
            "Graph build completed",
            nodes=nodes_created,
            rels=rels_created,
            duration_ms=duration_ms,
        )
        return await self._complete_build_run(
            build_run_id=build_run_id,
            nodes_created=nodes_created,
            relationships_created=rels_created,
            completed_at=completed_at,
            duration_ms=duration_ms,
        )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def get_build_run(self, build_run_id: uuid.UUID) -> GraphBuildRun:
        """Fetch a GraphBuildRun by its own ID.

        Raises:
            GraphBuildRunNotFoundError: If no record exists with that ID.
        """
        async with self._db.session() as session:
            stmt = select(GraphBuildRunOrm).where(GraphBuildRunOrm.id == build_run_id)
            orm = (await session.execute(stmt)).scalar_one_or_none()
            if orm is None:
                raise GraphBuildRunNotFoundError(build_run_id)
            return orm.to_domain()

    async def get_latest_build_run(
        self, analysis_run_id: uuid.UUID
    ) -> GraphBuildRun | None:
        """Return the most recent GraphBuildRun for an analysis run, or None.

        Ordered by created_at descending so the latest attempt is returned first.
        """
        async with self._db.session() as session:
            stmt = (
                select(GraphBuildRunOrm)
                .where(GraphBuildRunOrm.analysis_run_id == analysis_run_id)
                .order_by(GraphBuildRunOrm.created_at.desc())
                .limit(1)
            )
            orm = (await session.execute(stmt)).scalar_one_or_none()
            return orm.to_domain() if orm is not None else None

    async def list_build_runs(
        self,
        analysis_run_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[GraphBuildRun], int]:
        """List all graph build runs for an analysis run with pagination.

        Returns:
            Tuple of (list of GraphBuildRun, total count).
        """
        async with self._db.session() as session:
            base_q = select(GraphBuildRunOrm).where(
                GraphBuildRunOrm.analysis_run_id == analysis_run_id
            )
            count_q = select(func.count(GraphBuildRunOrm.id)).where(
                GraphBuildRunOrm.analysis_run_id == analysis_run_id
            )
            total = (await session.execute(count_q)).scalar_one()
            rows = (
                await session.execute(
                    base_q.order_by(GraphBuildRunOrm.created_at.desc())
                    .limit(limit)
                    .offset(offset)
                )
            ).scalars().all()
            return [r.to_domain() for r in rows], total

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _validate_analysis_run(self, analysis_run_id: uuid.UUID) -> uuid.UUID:
        """Confirm the analysis run exists, is COMPLETED, and return its repository_id."""
        async with self._db.session() as session:
            stmt = select(AnalysisRunOrm).where(AnalysisRunOrm.id == analysis_run_id)
            run_orm = (await session.execute(stmt)).scalar_one_or_none()

        if run_orm is None:
            raise AnalysisRunNotFoundError(analysis_run_id)

        if run_orm.status != AnalysisStatus.COMPLETED:
            raise InvalidAnalysisStateError(
                run_id=analysis_run_id,
                current_status=run_orm.status,
                operation="build dependency graph for",
            )

        return run_orm.repository_id

    async def _create_build_run(
        self,
        build_run_id: uuid.UUID,
        analysis_run_id: uuid.UUID,
        repository_id: uuid.UUID,
        now: datetime,
    ) -> None:
        async with self._db.session() as session:
            try:
                orm = GraphBuildRunOrm(
                    id=build_run_id,
                    analysis_run_id=analysis_run_id,
                    repository_id=repository_id,
                    status=GraphBuildStatus.PENDING,
                    nodes_created=0,
                    relationships_created=0,
                    created_at=now,
                    updated_at=now,
                )
                session.add(orm)
                await session.commit()
            except SQLAlchemyError as exc:
                logger.exception(
                    "Failed to create GraphBuildRun record", error=str(exc)
                )
                raise

    async def _update_build_run_status(
        self,
        build_run_id: uuid.UUID,
        status: GraphBuildStatus,
        started_at: datetime | None = None,
    ) -> None:
        async with self._db.session() as session:
            stmt = select(GraphBuildRunOrm).where(GraphBuildRunOrm.id == build_run_id)
            orm = (await session.execute(stmt)).scalar_one_or_none()
            if orm is None:
                return
            orm.status = status
            orm.updated_at = datetime.now(UTC)
            if started_at is not None:
                orm.started_at = started_at
            await session.commit()

    async def _complete_build_run(
        self,
        build_run_id: uuid.UUID,
        nodes_created: int,
        relationships_created: int,
        completed_at: datetime,
        duration_ms: float,
    ) -> GraphBuildRun:
        async with self._db.session() as session:
            stmt = select(GraphBuildRunOrm).where(GraphBuildRunOrm.id == build_run_id)
            orm = (await session.execute(stmt)).scalar_one()
            orm.status = GraphBuildStatus.COMPLETED
            orm.nodes_created = nodes_created
            orm.relationships_created = relationships_created
            orm.completed_at = completed_at
            orm.duration_ms = duration_ms
            orm.updated_at = completed_at
            await session.commit()
            await session.refresh(orm)
            return orm.to_domain()

    async def _fail_build_run(
        self,
        build_run_id: uuid.UUID,
        started_at: datetime,
        error_message: str,
    ) -> GraphBuildRun:
        completed_at = datetime.now(UTC)
        duration_ms = round((completed_at - started_at).total_seconds() * 1000, 2)
        async with self._db.session() as session:
            stmt = select(GraphBuildRunOrm).where(GraphBuildRunOrm.id == build_run_id)
            orm = (await session.execute(stmt)).scalar_one_or_none()
            if orm is None:
                # Fallback — return a synthetic domain record
                return GraphBuildRun(
                    id=build_run_id,
                    analysis_run_id=uuid.uuid4(),
                    repository_id=uuid.uuid4(),
                    status=GraphBuildStatus.FAILED,
                    error_message=error_message,
                    duration_ms=duration_ms,
                )
            orm.status = GraphBuildStatus.FAILED
            orm.error_message = error_message[:2000] if error_message else None
            orm.completed_at = completed_at
            orm.duration_ms = duration_ms
            orm.updated_at = completed_at
            await session.commit()
            await session.refresh(orm)
            return orm.to_domain()
