"""Graph database gateway protocol and Neo4j implementations."""

from trace.domain.health import GraphConnectivityState
from typing import Protocol, runtime_checkable

import structlog
from neo4j import AsyncDriver

logger = structlog.get_logger(__name__)


@runtime_checkable
class GraphGateway(Protocol):
    """Protocol defining the interface for graph database connectivity."""

    async def health_check(self) -> GraphConnectivityState:
        """Probe the graph database to determine connectivity status.

        Returns:
            GraphConnectivityState indicating REACHABLE, UNREACHABLE, or NOT_CONFIGURED.
            Never raises exceptions to callers.
        """
        ...

    async def close(self) -> None:
        """Close any active connections or drivers."""
        ...


class Neo4jGraphGateway:
    """Production graph database gateway using the official Neo4j async driver."""

    def __init__(self, driver: AsyncDriver) -> None:
        """Initialize gateway with an active AsyncDriver instance.

        Args:
            driver: Neo4j AsyncDriver instance.
        """
        self._driver = driver

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

    async def close(self) -> None:
        """Close the underlying Neo4j driver connections."""
        await self._driver.close()


class UnconfiguredGraphGateway:
    """Gateway used when Neo4j is not configured (NEO4J_URI absent)."""

    async def health_check(self) -> GraphConnectivityState:
        """Return NOT_CONFIGURED immediately without network calls.

        Returns:
            GraphConnectivityState.NOT_CONFIGURED.
        """
        return GraphConnectivityState.NOT_CONFIGURED

    async def close(self) -> None:
        """No-op close for unconfigured gateway."""
        pass


class StubGraphGateway:
    """Configurable stub gateway for deterministic test execution."""

    def __init__(
        self,
        initial_state: GraphConnectivityState = GraphConnectivityState.NOT_CONFIGURED,
    ) -> None:
        """Initialize stub with designated connectivity state.

        Args:
            initial_state: GraphConnectivityState to return from health_check.
        """
        self.state = initial_state

    def set_state(self, state: GraphConnectivityState) -> None:
        """Update the connectivity state returned by health_check.

        Args:
            state: New GraphConnectivityState to return.
        """
        self.state = state

    async def health_check(self) -> GraphConnectivityState:
        """Return configured stub state without making network calls.

        Returns:
            The configured GraphConnectivityState.
        """
        return self.state

    async def close(self) -> None:
        """No-op close for stub gateway."""
        pass
