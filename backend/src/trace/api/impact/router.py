"""FastAPI router for F05: Impact Analysis and Risk Evaluation Engine."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from trace.api.analyses.router import get_artifact_store
from trace.api.health.router import get_db_gateway
from trace.api.impact.schemas import EvaluateImpactRequest, ImpactAnalysisResponse
from trace.api.repositories.router import get_git_provider
from trace.domain.exceptions import RepositoryNotFoundError
from trace.infrastructure.database.gateway import DatabaseGateway
from trace.infrastructure.git.provider import GitProvider
from trace.infrastructure.storage.artifact_store import FileArtifactStore
from trace.services.impact import ImpactAnalysisNotFoundError, ImpactAnalysisService

impact_router = APIRouter(tags=["impact-analysis"])


def get_impact_service(
    request: Request,
    db: Annotated[DatabaseGateway, Depends(get_db_gateway)],
    git: Annotated[GitProvider, Depends(get_git_provider)],
    artifact_store: Annotated[FileArtifactStore, Depends(get_artifact_store)],
) -> ImpactAnalysisService:
    """Dependency provider for ImpactAnalysisService."""
    state_svc = getattr(request.app.state, "impact_service", None)
    if state_svc is not None:
        return state_svc  # type: ignore[return-value]

    analyzer = getattr(request.app.state, "code_analyzer", None)
    graph_gateway = getattr(request.app.state, "graph_gateway", None)
    return ImpactAnalysisService(
        db_gateway=db,
        git_provider=git,
        artifact_store=artifact_store,
        analyzer=analyzer,
        graph_gateway=graph_gateway,
    )


@impact_router.post(
    "/impact/evaluate",
    response_model=dict[str, Any],
    status_code=status.HTTP_201_CREATED,
    summary="Evaluate code change impact and risk",
)
async def evaluate_impact(
    body: EvaluateImpactRequest,
    service: Annotated[ImpactAnalysisService, Depends(get_impact_service)],
) -> dict[str, Any]:
    """Trigger full impact analysis returning the unified 4-key JSON schema."""
    try:
        api_key = body.llm_config.api_key if body.llm_config and body.llm_config.enabled else None
        model = body.llm_config.model if body.llm_config and body.llm_config.enabled else None

        aggregate = await service.evaluate_impact(
            repository_id=body.repository_id,
            base_ref=body.base_ref,
            target_ref=body.target_ref,
            openrouter_api_key=api_key,
            openrouter_model=model,
        )
        return await service.get_analysis(aggregate.metadata.analysis_id)
    except RepositoryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Impact evaluation failed: {exc}",
        )


@impact_router.get(
    "/impact/{analysis_id}",
    response_model=dict[str, Any],
    summary="Retrieve computed impact analysis JSON payload",
)
async def get_impact_analysis(
    analysis_id: uuid.UUID,
    service: Annotated[ImpactAnalysisService, Depends(get_impact_service)],
) -> dict[str, Any]:
    """Retrieve existing impact analysis artifact by ID."""
    try:
        return await service.get_analysis(analysis_id)
    except ImpactAnalysisNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
