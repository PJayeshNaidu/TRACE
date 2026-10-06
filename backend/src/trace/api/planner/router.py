"""FastAPI router for F07 Upgrade Planner endpoints."""

from __future__ import annotations

import uuid
from trace.api.analyses.router import get_artifact_store
from trace.api.health.router import get_db_gateway
from trace.api.impact.router import get_impact_service
from trace.api.planner.schemas import (
    GenerateUpgradePlanRequest,
    InformationalChangeSchema,
    SummaryMetricsSchema,
    TaskEvidenceSchema,
    UpdateTaskStatusRequest,
    UpgradePlanListResponse,
    UpgradePlanResponse,
    UpgradePlanSummaryItem,
    UpgradeTaskListResponse,
    UpgradeTaskResponse,
)
from trace.api.repositories.router import get_git_provider
from trace.domain.exceptions import RepositoryNotFoundError
from trace.domain.plan import TaskStatus, UpgradePlan, UpgradeTask
from trace.infrastructure.database.gateway import DatabaseGateway
from trace.infrastructure.git.provider import GitProvider
from trace.infrastructure.storage.artifact_store import FileArtifactStore
from trace.services.impact import ImpactAnalysisNotFoundError, ImpactAnalysisService
from trace.services.planner import (
    UpgradePlanNotFoundError,
    UpgradePlanService,
    UpgradeTaskNotFoundError,
)
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

planner_router = APIRouter(tags=["upgrade-planner"])


def get_planner_service(
    request: Request,
    db: Annotated[DatabaseGateway, Depends(get_db_gateway)],
    git: Annotated[GitProvider, Depends(get_git_provider)],
    artifact_store: Annotated[FileArtifactStore, Depends(get_artifact_store)],
    impact_service: Annotated[ImpactAnalysisService, Depends(get_impact_service)],
) -> UpgradePlanService:
    """Dependency provider for UpgradePlanService."""
    state_svc = getattr(request.app.state, "planner_service", None)
    if state_svc is not None:
        return state_svc  # type: ignore[return-value]

    return UpgradePlanService(
        db_gateway=db,
        git_provider=git,
        artifact_store=artifact_store,
        impact_service=impact_service,
    )


def _serialize_task(task: UpgradeTask) -> UpgradeTaskResponse:
    return UpgradeTaskResponse(
        id=task.id,
        plan_id=task.plan_id,
        step_number=task.step_number,
        component=task.component,
        component_type=task.component_type,
        category=str(task.category),
        reason=task.reason,
        dependencies=list(task.dependencies),
        expected_changes=task.expected_changes,
        required_tests=list(task.required_tests),
        risk_level=task.risk_level,
        status=str(task.status),
        is_circular=task.is_circular,
        parallel_group_id=task.parallel_group_id,
        notes=task.notes,
        evidence=TaskEvidenceSchema(
            diff_snippet=task.evidence.diff_snippet if task.evidence else "",
            lines_affected=list(task.evidence.lines_affected) if task.evidence else [],
            call_chain=list(task.evidence.call_chain) if task.evidence else [],
            file_path=task.evidence.file_path if task.evidence else "",
            target_symbol=task.evidence.target_symbol if task.evidence else "",
        )
        if task.evidence
        else None,
        actionability=str(
            task.actionability.value if hasattr(task.actionability, "value") else task.actionability
        ),
        action_type=str(
            task.action_type.value if hasattr(task.action_type, "value") else task.action_type
        ),
        tier_name=task.tier_name,
        tier_meaning=task.tier_meaning,
        change_significance=(
            str(
                task.change_significance.value
                if hasattr(task.change_significance, "value")
                else task.change_significance
            )
            if task.change_significance
            else None
        ),
        ai_confidence=task.ai_confidence,
        ai_review=task.ai_review,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def _serialize_plan(plan: UpgradePlan) -> UpgradePlanResponse:
    return UpgradePlanResponse(
        id=plan.id,
        repository_id=plan.repository_id,
        impact_analysis_id=plan.impact_analysis_id,
        title=plan.title,
        base_commit=plan.base_commit,
        target_commit=plan.target_commit,
        risk_level=plan.risk_level,
        status=plan.status,
        reasoning_mode=plan.reasoning_mode,
        change_significance=str(
            plan.change_significance.value
            if hasattr(plan.change_significance, "value")
            else plan.change_significance
        ),
        significance_reasoning=plan.significance_reasoning,
        recommended_action=plan.recommended_action,
        order_rationale=plan.order_rationale,
        optional_suggestions=list(plan.optional_suggestions),
        created_at=plan.created_at,
        updated_at=plan.updated_at,
        summary_metrics=SummaryMetricsSchema(
            total_tasks=plan.total_tasks,
            completed_tasks=plan.completed_tasks,
            in_progress_tasks=plan.in_progress_tasks,
            pending_tasks=plan.pending_tasks,
            blocked_tasks=plan.blocked_tasks,
            skipped_tasks=plan.skipped_tasks,
            progress_percentage=plan.progress_percentage,
        ),
        informational_changes=[
            InformationalChangeSchema(
                component=ic.component,
                file_path=ic.file_path,
                category=str(ic.category),
                reason=ic.reason,
                diff_snippet=ic.diff_snippet,
                actionability=str(
                    ic.actionability.value
                    if hasattr(ic.actionability, "value")
                    else ic.actionability
                ),
            )
            for ic in plan.informational_changes
        ],
        ai_plan_review=plan.ai_plan_review,
        tasks=[_serialize_task(t) for t in plan.tasks],
    )


@planner_router.post(
    "/upgrade-plans/generate",
    response_model=UpgradePlanResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate an upgrade plan from impact analysis",
)
async def generate_upgrade_plan(
    body: GenerateUpgradePlanRequest,
    service: Annotated[UpgradePlanService, Depends(get_planner_service)],
) -> UpgradePlanResponse:
    """Construct an actionable, dependency-ordered upgrade plan."""
    try:
        llm_cfg = body.llm_config.model_dump() if body.llm_config else None
        plan = await service.generate_plan(
            repository_id=body.repository_id,
            impact_analysis_id=body.impact_analysis_id,
            base_ref=body.base_ref,
            target_ref=body.target_ref,
            title=body.title,
            llm_config=llm_cfg,
        )
        return _serialize_plan(plan)
    except RepositoryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ImpactAnalysisNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Plan generation failed: {exc}",
        ) from exc


@planner_router.get(
    "/upgrade-plans/{plan_id}",
    response_model=UpgradePlanResponse,
    summary="Retrieve an upgrade plan by ID",
)
async def get_upgrade_plan(
    plan_id: uuid.UUID,
    service: Annotated[UpgradePlanService, Depends(get_planner_service)],
) -> UpgradePlanResponse:
    """Retrieve complete upgrade plan with task DAG and summary metrics."""
    try:
        plan = await service.get_plan(plan_id)
        return _serialize_plan(plan)
    except UpgradePlanNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@planner_router.get(
    "/upgrade-plans/{plan_id}/tasks",
    response_model=UpgradeTaskListResponse,
    summary="Retrieve filtered/paginated tasks for an upgrade plan",
)
async def list_upgrade_tasks(
    plan_id: uuid.UUID,
    service: Annotated[UpgradePlanService, Depends(get_planner_service)],
    task_status: str | None = Query(default=None, alias="status"),
    category: str | None = Query(default=None),
    risk_level: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> UpgradeTaskListResponse:
    """Query upgrade tasks with status, category, and risk filtering."""
    try:
        # Check plan exists
        await service.get_plan(plan_id)
        total, tasks = await service.list_tasks(
            plan_id=plan_id,
            status=task_status,
            category=category,
            risk_level=risk_level,
            limit=limit,
            offset=offset,
        )
        return UpgradeTaskListResponse(
            plan_id=plan_id,
            total=total,
            limit=limit,
            offset=offset,
            items=[_serialize_task(t) for t in tasks],
        )
    except UpgradePlanNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@planner_router.patch(
    "/upgrade-plans/{plan_id}/tasks/{task_id}",
    response_model=UpgradeTaskResponse,
    summary="Update task lifecycle status and notes",
)
async def update_task_status(
    plan_id: uuid.UUID,
    task_id: uuid.UUID,
    body: UpdateTaskStatusRequest,
    service: Annotated[UpgradePlanService, Depends(get_planner_service)],
) -> UpgradeTaskResponse:
    """Transition an upgrade task's status and trigger plan progress recalculation."""
    try:
        target_status = TaskStatus(body.status.upper())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid task status '{body.status}'. Valid: {[s.value for s in TaskStatus]}",
        ) from exc

    try:
        task = await service.update_task_status(
            plan_id=plan_id,
            task_id=task_id,
            new_status=target_status,
            notes=body.notes,
        )
        return _serialize_task(task)
    except UpgradeTaskNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except UpgradePlanNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@planner_router.get(
    "/repositories/{repository_id}/upgrade-plans",
    response_model=UpgradePlanListResponse,
    summary="List upgrade plans for a repository",
)
async def list_repository_upgrade_plans(
    repository_id: uuid.UUID,
    service: Annotated[UpgradePlanService, Depends(get_planner_service)],
) -> UpgradePlanListResponse:
    """Retrieve historical upgrade plans for a specific repository."""
    plans = await service.list_plans_for_repository(repository_id)
    items = [
        UpgradePlanSummaryItem(
            id=p.id,
            title=p.title,
            base_commit=p.base_commit,
            target_commit=p.target_commit,
            risk_level=p.risk_level,
            status=p.status,
            total_tasks=p.total_tasks,
            completed_tasks=p.completed_tasks,
            progress_percentage=p.progress_percentage,
            created_at=p.created_at,
        )
        for p in plans
    ]
    return UpgradePlanListResponse(
        repository_id=repository_id,
        total=len(items),
        items=items,
    )
