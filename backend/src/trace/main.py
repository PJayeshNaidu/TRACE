"""FastAPI application factory and lifespan composition root for TRACE."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from trace.analysis.analyzer import PythonCodeAnalyzer
from trace.api.errors import register_exception_handlers
from trace.api.router import api_router
from trace.core.config import ApplicationConfig
from trace.core.logging import configure_logging
from trace.infrastructure.database.gateway import SQLAlchemyDatabaseGateway
from trace.infrastructure.git.adapters.subprocess import SubprocessGitProvider
from trace.infrastructure.graph.gateway import (
    Neo4jGraphGateway,
    UnconfiguredGraphGateway,
)
from trace.infrastructure.llm.adapters.openrouter import OpenRouterAdapter
from trace.infrastructure.storage.artifact_store import FileArtifactStore
from trace.services.analysis import AnalysisService
from trace.services.graph import GraphService

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

        # Git Provider Adapter
        app.state.git = SubprocessGitProvider(config=cfg)

        # Artifact Store & Code Analyzer
        app.state.artifact_store = FileArtifactStore(cfg.artifacts_dir)
        app.state.code_analyzer = PythonCodeAnalyzer()

        # Graph Service (F03) — wires graph_gateway + analysis_service together
        # AnalysisService must be constructed first as a local var so GraphService
        # can reference it; then AnalysisService is re-constructed with graph_service.
        _base_analysis_svc = AnalysisService(
            db_gateway=db_gateway,
            analyzer=app.state.code_analyzer,
            artifact_store=app.state.artifact_store,
            git_provider=app.state.git,
        )
        graph_service = GraphService(
            db_gateway=db_gateway,
            graph_gateway=app.state.graph,
            analysis_service=_base_analysis_svc,
        )
        app.state.graph_service = graph_service

        # Re-create AnalysisService with graph_service injected for auto-trigger
        app.state.analysis_service = AnalysisService(
            db_gateway=db_gateway,
            analyzer=app.state.code_analyzer,
            artifact_store=app.state.artifact_store,
            git_provider=app.state.git,
            graph_service=graph_service,
        )

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
    register_exception_handlers(app)
    return app


app = create_app()
