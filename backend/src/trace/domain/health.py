"""Domain models and states for health evaluation."""

from enum import StrEnum


class HealthState(StrEnum):
    """Aggregate health state of the TRACE system."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"


class GraphConnectivityState(StrEnum):
    """Connectivity state of the graph storage backend."""

    NOT_CONFIGURED = "not_configured"
    REACHABLE = "reachable"
    UNREACHABLE = "unreachable"
