"""Database gateway protocol and SQLAlchemy implementations."""

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Protocol, runtime_checkable

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = structlog.get_logger(__name__)


@runtime_checkable
class DatabaseGateway(Protocol):
    """Protocol defining the interface for relational database interactions."""

    def session(self) -> AbstractAsyncContextManager[AsyncSession]:
        """Provide an asynchronous database session context manager.

        Returns:
            An async context manager yielding an AsyncSession.
        """
        ...

    async def health_check(self) -> bool:
        """Probe the database connection to determine reachability.

        Returns:
            True if the database responds to a probe query, False otherwise.
            Never raises exceptions to callers.
        """
        ...


class SQLAlchemyDatabaseGateway:
    """Production database gateway using SQLAlchemy 2.x async engine."""

    def __init__(self, engine_or_url: AsyncEngine | str) -> None:
        """Initialize gateway with an AsyncEngine or connection URL.

        Args:
            engine_or_url: SQLAlchemy AsyncEngine instance or database connection URL string.
        """
        if isinstance(engine_or_url, str):
            self._engine = create_async_engine(engine_or_url)
        else:
            self._engine = engine_or_url
        self._session_maker = async_sessionmaker(self._engine, expire_on_commit=False)

    @property
    def engine(self) -> AsyncEngine:
        """Return the underlying AsyncEngine instance."""
        return self._engine

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Provide an asynchronous database session context manager.

        Yields:
            An active AsyncSession instance managed within a context.
        """
        async with self._session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def health_check(self) -> bool:
        """Probe the database connection by executing a lightweight SELECT 1 query.

        Returns:
            True if the query succeeds, False if any exception occurs.
        """
        try:
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception as exc:
            logger.warning("Database health check probe failed", error=str(exc))
            return False

    async def dispose(self) -> None:
        """Dispose of the underlying SQLAlchemy engine connection pool."""
        await self._engine.dispose()


class InMemoryDatabaseGateway(SQLAlchemyDatabaseGateway):
    """In-memory SQLite database gateway for deterministic test execution."""

    def __init__(self) -> None:
        """Initialize with an in-memory SQLite async engine."""
        super().__init__("sqlite+aiosqlite:///:memory:")
