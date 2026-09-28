"""Unit tests for health endpoint Pydantic schemas."""

from trace.api.health.schemas import HealthStatus, ServiceStatus

import pytest
from pydantic import ValidationError


def test_service_status_valid_literals() -> None:
    """Verify ServiceStatus accepts the three defined valid literals."""
    for valid in ("reachable", "unreachable", "not_configured"):
        status = ServiceStatus(status=valid)
        assert status.status == valid


def test_service_status_rejects_invalid_values() -> None:
    """Verify ServiceStatus rejects values outside the three valid literals."""
    with pytest.raises(ValidationError):
        ServiceStatus(status="online")

    with pytest.raises(ValidationError):
        ServiceStatus(status="offline")

    with pytest.raises(ValidationError):
        ServiceStatus(status="")


def test_health_status_serialisation_healthy() -> None:
    """Verify HealthStatus serialises to the expected JSON-compatible dictionary."""
    model = HealthStatus(
        status="healthy",
        version="0.1.0",
        services={
            "postgres": ServiceStatus(status="reachable"),
            "neo4j": ServiceStatus(status="not_configured"),
        },
    )
    dumped = model.model_dump()
    assert dumped == {
        "status": "healthy",
        "version": "0.1.0",
        "services": {
            "postgres": {"status": "reachable"},
            "neo4j": {"status": "not_configured"},
        },
    }


def test_health_status_serialisation_degraded() -> None:
    """Verify HealthStatus with degraded status serialises correctly."""
    model = HealthStatus(
        status="degraded",
        version="0.1.0",
        services={
            "postgres": ServiceStatus(status="unreachable"),
            "neo4j": ServiceStatus(status="not_configured"),
        },
    )
    dumped = model.model_dump()
    assert dumped["status"] == "degraded"
    assert dumped["services"]["postgres"]["status"] == "unreachable"


def test_health_status_accepts_unknown_version() -> None:
    """Verify version field accepts 'unknown' as a valid fallback value."""
    model = HealthStatus(
        status="healthy",
        version="unknown",
        services={
            "postgres": ServiceStatus(status="reachable"),
        },
    )
    assert model.version == "unknown"
    assert model.model_dump()["version"] == "unknown"
