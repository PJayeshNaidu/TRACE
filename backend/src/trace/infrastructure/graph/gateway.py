"""Graph database gateway protocol and Neo4j implementations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

import structlog
from neo4j import AsyncDriver

from trace.domain.health import GraphConnectivityState

if TYPE_CHECKING:
    from trace.domain.analysis import RepositoryAnalysis

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class GraphGateway(Protocol):
    """Protocol defining the interface for graph database connectivity and writes."""

    async def health_check(self) -> GraphConnectivityState:
        """Probe the graph database to determine connectivity status.

        Returns:
            GraphConnectivityState indicating REACHABLE, UNREACHABLE, or NOT_CONFIGURED.
            Never raises exceptions to callers.
        """
        ...

    async def ensure_constraints(self) -> None:
        """Create Neo4j uniqueness constraints if they do not already exist.

        Safe to call multiple times (uses IF NOT EXISTS).
        No-op when Neo4j is not configured.
        """
        ...

    async def build_graph(self, analysis: RepositoryAnalysis) -> tuple[int, int]:
        """Project a RepositoryAnalysis aggregate into Neo4j as nodes and relationships.

        Args:
            analysis: Complete RepositoryAnalysis domain aggregate from F02.

        Returns:
            Tuple of (total_nodes_merged, total_relationships_merged).

        Raises:
            GraphNotConfiguredError: When Neo4j is not configured.
        """
        ...

    async def clear_graph(self, analysis_run_id: str) -> int:
        """Delete all nodes (and their relationships) scoped to an analysis run.

        Args:
            analysis_run_id: UUID string of the analysis run whose graph should be cleared.

        Returns:
            Number of nodes deleted.
        """
        ...

    async def close(self) -> None:
        """Close any active connections or drivers."""
        ...


# ---------------------------------------------------------------------------
# Production Implementation
# ---------------------------------------------------------------------------


class Neo4jGraphGateway:
    """Production graph database gateway using the official Neo4j async driver."""

    def __init__(self, driver: AsyncDriver) -> None:
        """Initialize gateway with an active AsyncDriver instance.

        Args:
            driver: Neo4j AsyncDriver instance.
        """
        from trace.infrastructure.graph.neo4j_builder import Neo4jGraphBuilder

        self._driver = driver
        self._builder = Neo4jGraphBuilder()

    @property
    def driver(self) -> AsyncDriver:
        """Return the underlying Neo4j AsyncDriver."""
        return self._driver

    async def health_check(self) -> GraphConnectivityState:
        """Probe Neo4j connectivity via verify_connectivity probe.

        Returns:
            REACHABLE if connection succeeds, UNREACHABLE if any exception is raised.
        """
        try:
            await self._driver.verify_connectivity()
            return GraphConnectivityState.REACHABLE
        except Exception as exc:
            logger.warning("Neo4j health check probe failed", error=str(exc))
            return GraphConnectivityState.UNREACHABLE

    async def ensure_constraints(self) -> None:
        """Delegate constraint creation to the Neo4jGraphBuilder."""
        await self._builder.ensure_constraints(self._driver)

    async def build_graph(self, analysis: RepositoryAnalysis) -> tuple[int, int]:
        """Project a RepositoryAnalysis into Neo4j via the Neo4jGraphBuilder.

        Returns:
            Tuple of (total_nodes_merged, total_relationships_merged).
        """
        return await self._builder.build_graph(self._driver, analysis)

    async def clear_graph(self, analysis_run_id: str) -> int:
        """Delete all nodes scoped to the given analysis_run_id.

        Returns:
            Number of nodes deleted.
        """
        return await self._builder.clear_graph(self._driver, analysis_run_id)

    async def close(self) -> None:
        """Close the underlying Neo4j driver connections."""
        await self._driver.close()


# ---------------------------------------------------------------------------
# Unconfigured Gateway (Neo4j absent)
# ---------------------------------------------------------------------------


class GraphNotConfiguredError(RuntimeError):
    """Raised when a graph write operation is attempted without Neo4j configured."""

    def __init__(self) -> None:
        super().__init__(
            "Neo4j is not configured. Set NEO4J_URI, NEO4J_USERNAME, and NEO4J_PASSWORD "
            "environment variables to enable the dependency graph."
        )


class UnconfiguredGraphGateway:
    """Gateway used when Neo4j is not configured (NEO4J_URI absent)."""

    async def health_check(self) -> GraphConnectivityState:
        """Return NOT_CONFIGURED immediately without network calls."""
        return GraphConnectivityState.NOT_CONFIGURED

    async def ensure_constraints(self) -> None:
        """No-op — Neo4j is not configured."""
        pass

    async def build_graph(self, analysis: RepositoryAnalysis) -> tuple[int, int]:
        """Raise GraphNotConfiguredError — Neo4j is not configured."""
        raise GraphNotConfiguredError()

    async def clear_graph(self, analysis_run_id: str) -> int:
        """Raise GraphNotConfiguredError — Neo4j is not configured."""
        raise GraphNotConfiguredError()

    async def close(self) -> None:
        """No-op close for unconfigured gateway."""
        pass


# ---------------------------------------------------------------------------
# Stub Gateway (tests)
# ---------------------------------------------------------------------------


class StubGraphGateway:
    """Configurable stub gateway for deterministic test execution."""

    def __init__(
        self,
        initial_state: GraphConnectivityState = GraphConnectivityState.NOT_CONFIGURED,
        build_graph_result: tuple[int, int] = (0, 0),
        raise_on_build: Exception | None = None,
    ) -> None:
        """Initialize stub with designated connectivity state and build results.

        Args:
            initial_state: GraphConnectivityState returned by health_check.
            build_graph_result: (nodes, rels) tuple returned by build_graph.
            raise_on_build: If set, build_graph raises this exception instead.
        """
        self.state = initial_state
        self._build_result = build_graph_result
        self._raise_on_build = raise_on_build
        self.constraints_ensured = False
        self.build_calls: list[str] = []   # analysis_run_ids
        self.clear_calls: list[str] = []   # analysis_run_ids

    def set_state(self, state: GraphConnectivityState) -> None:
        """Update the connectivity state returned by health_check."""
        self.state = state

    def set_build_result(self, nodes: int, rels: int) -> None:
        """Update the (nodes, rels) tuple returned by build_graph."""
        self._build_result = (nodes, rels)

    async def health_check(self) -> GraphConnectivityState:
        """Return configured stub state without making network calls."""
        return self.state

    async def ensure_constraints(self) -> None:
        """Record constraint ensure call."""
        self.constraints_ensured = True

    async def build_graph(self, analysis: RepositoryAnalysis) -> tuple[int, int]:
        """Return configured build result or raise configured exception."""
        if self._raise_on_build is not None:
            raise self._raise_on_build
        self.build_calls.append(str(analysis.run_id))
        return self._build_result

    async def clear_graph(self, analysis_run_id: str) -> int:
        """Record clear call and return 0."""
        self.clear_calls.append(analysis_run_id)
        return 0

    async def close(self) -> None:
        """No-op close for stub gateway."""
        pass
