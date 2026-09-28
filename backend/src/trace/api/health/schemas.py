"""Pydantic schemas for health endpoint responses."""

from typing import Literal

from pydantic import BaseModel, Field


class ServiceStatus(BaseModel):
    """Connectivity status for an individual infrastructure service."""

    status: Literal["reachable", "unreachable", "not_configured"] = Field(
        description="Current connectivity status of the service",
    )


class HealthStatus(BaseModel):
    """Aggregate health status of the TRACE application and dependencies."""

    status: Literal["healthy", "degraded"] = Field(
        description="Overall health status of the TRACE system",
    )
    version: str = Field(
        description="Installed package version or unknown if unresolvable",
    )
    services: dict[str, ServiceStatus] = Field(
        description="Map of service names to their respective connectivity statuses",
    )
