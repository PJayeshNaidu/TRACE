"""Unit tests for SQLAlchemyDatabaseGateway and InMemoryDatabaseGateway."""

from trace.infrastructure.database.gateway import (
    InMemoryDatabaseGateway,
    SQLAlchemyDatabaseGateway,
)

import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_in_memory_database_gateway_lifecycle() -> None:
    """Verify InMemoryDatabaseGateway initializes, executes queries, and disposes."""
    gw = InMemoryDatabaseGateway()
    assert gw.engine is not None

    # Test health check succeeds
    is_healthy = await gw.health_check()
    assert is_healthy is True

    # Test session context manager commit path
    async with gw.session() as session:
        result = await session.execute(text("SELECT 42"))
        val = result.scalar()
        assert val == 42

    # Test session context manager rollback on exception
    async def _failing_operation() -> None:
        async with gw.session() as session:
            await session.execute(text("SELECT 1"))
            raise RuntimeError("Forced error to test rollback")

    with pytest.raises(RuntimeError):
        await _failing_operation()

    await gw.dispose()


@pytest.mark.asyncio
async def test_sqlalchemy_gateway_from_url_string() -> None:
    """Verify gateway accepts a connection URL string directly in constructor."""
    gw = SQLAlchemyDatabaseGateway("sqlite+aiosqlite:///:memory:")
    assert await gw.health_check() is True
    await gw.dispose()


@pytest.mark.asyncio
async def test_sqlalchemy_gateway_health_check_failure() -> None:
    """Verify health_check returns False when connection cannot be established."""
    # Invalid host and port with short timeout simulation
    gw = SQLAlchemyDatabaseGateway(
        "postgresql+asyncpg://invalid_user:invalid_pass@127.0.0.1:1/invalid_db"
    )
    is_healthy = await gw.health_check()
    assert is_healthy is False
    await gw.dispose()
