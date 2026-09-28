"""Integration test verifying live PostgreSQL connectivity via SQLAlchemyDatabaseGateway."""

import os
from trace.infrastructure.database.gateway import SQLAlchemyDatabaseGateway

import pytest


@pytest.mark.integration
async def test_postgres_live_connectivity() -> None:
    """Connect to a live PostgreSQL service defined by DATABASE_URL and assert reachability."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL environment variable is not set")

    gateway = SQLAlchemyDatabaseGateway(database_url)
    try:
        is_reachable = await gateway.health_check()
        assert is_reachable is True
    finally:
        await gateway.dispose()
