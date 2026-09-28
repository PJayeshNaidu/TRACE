"""FastAPI application factory and lifespan composition root for TRACE."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from trace.api.router import api_router
from trace.core.config import ApplicationConfig
from trace.core.logging import configure_logging
from trace.infrastructure.database.gateway import SQLAlchemyDatabaseGateway
from trace.infrastructure.graph.gateway import (
    Neo4jGraphGateway,
    UnconfiguredGraphGateway,
)
from trace.infrastructure.llm.adapters.openrouter import OpenRouterAdapter

import httpx
import structlog
from fastapi import FastAPI
from neo4j import AsyncGraphDatabase

logger = structlog.get_logger(__name__)


def create_app(config: ApplicationConfig | None = None) -> FastAPI:
    """Create and configure a FastAPI application instance.

    Args:
        config: Optional pre-constructed ApplicationConfig for test environments.

    Returns:
        Configured FastAPI application with lifecycle management.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Manage startup and shutdown lifecycle of application resources."""
        nonlocal config
        cfg = config if config is not None else ApplicationConfig()
        app.state.config = cfg

        configure_logging(app_env=cfg.app_env, log_level=cfg.log_level)
        logger.info(
            "Starting TRACE application",
            app_env=cfg.app_env,
            log_level=cfg.log_level,
        )

        # Relational Database Gateway
        db_gateway = SQLAlchemyDatabaseGateway(cfg.database_url.get_secret_value())
        app.state.db = db_gateway

        # Graph Database Gateway
        if cfg.neo4j_uri:
            auth = (
                cfg.neo4j_username or "neo4j",
                cfg.neo4j_password.get_secret_value() if cfg.neo4j_password else "",
            )
            neo4j_driver = AsyncGraphDatabase.driver(cfg.neo4j_uri, auth=auth)
            app.state.graph = Neo4jGraphGateway(neo4j_driver)
        else:
            app.state.graph = UnconfiguredGraphGateway()

        # LLM Provider Adapter (composition root: OpenRouterAdapter instantiated here only)
        http_client = httpx.AsyncClient()
        app.state.llm = OpenRouterAdapter(config=cfg, http_client=http_client)

        try:
            yield
        finally:
            logger.info("Shutting down TRACE application resources")
            await app.state.db.dispose()
            await app.state.graph.close()
            await http_client.aclose()

    app = FastAPI(
        title="TRACE API",
        description="Transformation Risk Analysis & Change Evaluation API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.include_router(api_router)
    return app


app = create_app()
