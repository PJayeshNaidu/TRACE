"""FastAPI router for TRACE AI Assistant (F10) Q&A endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select

from trace.api.health.router import get_db_gateway
from trace.core.config import ApplicationConfig
from trace.domain.exceptions import ProjectNotFoundError
from trace.infrastructure.database.gateway import DatabaseGateway
from trace.infrastructure.database.models.project import ProjectOrm
from trace.infrastructure.graph.gateway import GraphGateway, UnconfiguredGraphGateway
from trace.infrastructure.storage.artifact_store import FileArtifactStore
from trace.schemas.assistant import AssistantQueryRequest, AssistantQueryResponse
from trace.services.assistant.retrieval import AssistantRetrievalService
from trace.services.assistant.synthesis import AssistantService, AssistantSynthesisService

logger = structlog.get_logger(__name__)

assistant_router = APIRouter(tags=["assistant"])


# ---------------------------------------------------------------------------
# Dependency Providers
# ---------------------------------------------------------------------------


def get_config(request: Request) -> ApplicationConfig:
    """Dependency provider for ApplicationConfig."""
    cfg = getattr(request.app.state, "config", None)
    if cfg is not None:
        return cfg  # type: ignore[return-value]
    return ApplicationConfig()


def get_graph_gateway_safe(request: Request) -> GraphGateway:
    """Dependency provider for GraphGateway with fallback for test harnesses."""
    gw = getattr(request.app.state, "graph", None)
    if gw is not None:
        return gw  # type: ignore[return-value]
    return UnconfiguredGraphGateway()


def get_artifact_store_safe(request: Request) -> FileArtifactStore:
    """Dependency provider for FileArtifactStore with fallback for test harnesses."""
    store = getattr(request.app.state, "artifact_store", None)
    if store is not None:
        return store  # type: ignore[return-value]
    cfg = getattr(request.app.state, "config", None)
    base_path = getattr(cfg, "artifacts_dir", ".trace/artifacts")
    return FileArtifactStore(base_path)


def get_assistant_service(
    request: Request,
    db: Annotated[DatabaseGateway, Depends(get_db_gateway)],
    graph: Annotated[GraphGateway, Depends(get_graph_gateway_safe)],
    artifact_store: Annotated[FileArtifactStore, Depends(get_artifact_store_safe)],
    config: Annotated[ApplicationConfig, Depends(get_config)],
) -> AssistantService:
    """Dependency provider for AssistantService."""
    state_svc = getattr(request.app.state, "assistant_service", None)
    if state_svc is not None:
        return state_svc  # type: ignore[return-value]

    retrieval_svc = AssistantRetrievalService(
        db_gateway=db,
        graph_gateway=graph,
        artifact_store=artifact_store,
    )
    http_client = getattr(request.app.state, "http_client", None)
    synthesis_svc = AssistantSynthesisService(
        config=config,
        http_client=http_client,
    )
    return AssistantService(
        retrieval_service=retrieval_svc,
        synthesis_service=synthesis_svc,
        config=config,
    )


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------


@assistant_router.post(
    "/assistant/ask",
    response_model=AssistantQueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Ask contextual Q&A question over code intelligence artifacts",
)
async def ask_assistant(
    body: AssistantQueryRequest,
    assistant_service: Annotated[AssistantService, Depends(get_assistant_service)],
    db: Annotated[DatabaseGateway, Depends(get_db_gateway)],
) -> AssistantQueryResponse:
    """Query the TRACE AI Assistant to obtain grounded answers with source citations."""
    # Verify project exists
    try:
        async with db.session() as session:
            stmt = select(ProjectOrm).where(ProjectOrm.id == body.project_id)
            project = (await session.execute(stmt)).scalar_one_or_none()
            if project is None:
                raise ProjectNotFoundError(body.project_id)
    except ProjectNotFoundError:
        raise
    except Exception as exc:
        logger.debug("Project lookup skipped during assistant request", error=str(exc))

    return await assistant_service.ask(body)


@assistant_router.get(
    "/assistant/status",
    status_code=status.HTTP_200_OK,
    summary="Get assistant service configuration and status",
)
async def get_assistant_status(
    config: Annotated[ApplicationConfig, Depends(get_config)],
) -> dict[str, Any]:
    """Return live assistant status, model configured, and whether online synthesis is active."""
    has_key = bool(config.openrouter_api_key and config.openrouter_api_key.get_secret_value().strip())
    model = config.openrouter_model or config.llm_default_model
    return {
        "status": "online" if has_key else "offline",
        "has_api_key": has_key,
        "model": model,
        "external_calls_enabled": config.llm_enable_external_calls,
    }

