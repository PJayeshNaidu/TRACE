"""FastAPI router for F04: Version & Change Analyzer endpoints."""

import uuid
from trace.api.analyses.router import get_artifact_store, get_code_analyzer
from trace.api.diff.schemas import (
    BlastRadiusItemSchema,
    BranchListResponse,
    CommitItemSchema,
    CommitListResponse,
    CompareTriggerRequest,
    CompareTriggerResponse,
    ComparisonDetailResponse,
    ComparisonSummarySchema,
    DiffHunkSchema,
    FileDiffSchema,
    SymbolDiffSchema,
)
from trace.api.health.router import get_db_gateway
from trace.api.repositories.router import get_git_provider
from trace.domain.diff import VersionComparison
from trace.infrastructure.database.gateway import DatabaseGateway
from trace.infrastructure.git.provider import GitProvider
from trace.infrastructure.storage.artifact_store import FileArtifactStore
from trace.services.diff import ComparisonNotFoundError, VersionChangeService
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

diff_router = APIRouter(tags=["version-change-analyzer"])


def get_diff_service(
    request: Request,
    db: Annotated[DatabaseGateway, Depends(get_db_gateway)],
    git: Annotated[GitProvider, Depends(get_git_provider)],
    artifact_store: Annotated[FileArtifactStore, Depends(get_artifact_store)],
) -> VersionChangeService:
    """Dependency provider for VersionChangeService."""
    state_svc = getattr(request.app.state, "diff_service", None)
    if state_svc is not None:
        return state_svc  # type: ignore[return-value]

    analyzer = getattr(request.app.state, "code_analyzer", None)
    graph_gateway = getattr(request.app.state, "graph_gateway", None)
    return VersionChangeService(
        db_gateway=db,
        git_provider=git,
        artifact_store=artifact_store,
        analyzer=analyzer,
        graph_gateway=graph_gateway,
    )


def _to_comparison_detail_response(comparison: VersionComparison) -> ComparisonDetailResponse:
    return ComparisonDetailResponse(
        comparison_id=comparison.id,
        repository_id=comparison.repository_id,
        base_ref=comparison.base_ref,
        target_ref=comparison.target_ref,
        base_commit_hash=comparison.base_commit_hash,
        target_commit_hash=comparison.target_commit_hash,
        risk_level=comparison.risk_level.value,
        created_at=comparison.created_at,
        summary=ComparisonSummarySchema(
            total_files_changed=comparison.total_files_changed,
            total_insertions=comparison.total_insertions,
            total_deletions=comparison.total_deletions,
            total_symbols_changed=comparison.total_symbols_changed,
            total_breaking_changes=comparison.total_breaking_changes,
        ),
        file_diffs=[
            FileDiffSchema(
                old_path=f.old_path,
                new_path=f.new_path,
                change_type=f.change_type.value,
                insertions=f.insertions,
                deletions=f.deletions,
                hunks=[
                    DiffHunkSchema(
                        old_start=h.old_start,
                        old_lines=h.old_lines,
                        new_start=h.new_start,
                        new_lines=h.new_lines,
                        header=h.header,
                    )
                    for h in f.hunks
                ],
            )
            for f in comparison.file_diffs
        ],
        symbol_diffs=[
            SymbolDiffSchema(
                symbol_id=s.symbol_id,
                qualified_name=s.qualified_name,
                kind=s.kind,
                file_path=s.file_path,
                change_kind=s.change_kind.value,
                is_breaking=s.is_breaking,
                breaking_reason=s.breaking_reason,
                old_signature=s.old_signature,
                new_signature=s.new_signature,
            )
            for s in comparison.symbol_diffs
        ],
        blast_radius=[
            BlastRadiusItemSchema(
                target_symbol_id=b.target_symbol_id,
                affected_symbol_id=b.affected_symbol_id,
                affected_qualified_name=b.affected_qualified_name,
                affected_kind=b.affected_kind,
                affected_file_path=b.affected_file_path or "",
                relationship_kind=b.relationship_kind,
                depth=b.depth,
            )
            for b in comparison.blast_radius
        ],
        commit_messages=list(comparison.commit_messages),
    )


@diff_router.post(
    "/analyses/compare",
    response_model=CompareTriggerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Trigger a version, branch, or commit comparison",
)
async def trigger_comparison(
    payload: CompareTriggerRequest,
    diff_service: Annotated[VersionChangeService, Depends(get_diff_service)],
) -> CompareTriggerResponse:
    """Compare two Git revisions (branches, tags, or commits) and compute semantic changes & risk."""
    try:
        comparison = await diff_service.trigger_comparison(
            repository_id=payload.repository_id,
            base_ref=payload.base_ref,
            target_ref=payload.target_ref,
        )
        return CompareTriggerResponse(
            comparison_id=comparison.id,
            repository_id=comparison.repository_id,
            base_ref=comparison.base_ref,
            target_ref=comparison.target_ref,
            base_commit_hash=comparison.base_commit_hash,
            target_commit_hash=comparison.target_commit_hash,
            risk_level=comparison.risk_level.value,
            created_at=comparison.created_at,
            summary=ComparisonSummarySchema(
                total_files_changed=comparison.total_files_changed,
                total_insertions=comparison.total_insertions,
                total_deletions=comparison.total_deletions,
                total_symbols_changed=comparison.total_symbols_changed,
                total_breaking_changes=comparison.total_breaking_changes,
            ),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to execute comparison: {str(exc)}",
        ) from exc


@diff_router.get(
    "/analyses/compare/{comparison_id}",
    response_model=ComparisonDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get full version comparison details",
)
async def get_comparison(
    comparison_id: uuid.UUID,
    diff_service: Annotated[VersionChangeService, Depends(get_diff_service)],
) -> ComparisonDetailResponse:
    """Retrieve complete comparison results, symbol deltas, breaking changes, and blast radius."""
    try:
        comparison = await diff_service.get_comparison(comparison_id)
        return _to_comparison_detail_response(comparison)
    except ComparisonNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@diff_router.get(
    "/repositories/{repository_id}/branches",
    response_model=BranchListResponse,
    status_code=status.HTTP_200_OK,
    summary="List available branches in a repository",
)
async def list_branches(
    repository_id: uuid.UUID,
    diff_service: Annotated[VersionChangeService, Depends(get_diff_service)],
) -> BranchListResponse:
    """List all active branches in the repository for comparison selection."""
    try:
        branches = await diff_service.list_branches(repository_id)
        default_branch = branches[0] if branches else "main"
        return BranchListResponse(
            repository_id=repository_id,
            default_branch=default_branch,
            branches=branches,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to list branches: {str(exc)}",
        ) from exc


@diff_router.get(
    "/repositories/{repository_id}/commits",
    response_model=CommitListResponse,
    status_code=status.HTTP_200_OK,
    summary="List recent commit history in a repository branch",
)
async def list_commits(
    repository_id: uuid.UUID,
    diff_service: Annotated[VersionChangeService, Depends(get_diff_service)],
    branch: Annotated[str | None, Query(description="Target branch name")] = None,
    limit: Annotated[int, Query(ge=1, le=100, description="Max commits to return")] = 30,
) -> CommitListResponse:
    """Retrieve recent commits for quick commit-to-commit selection."""
    try:
        commits = await diff_service.list_commits(
            repository_id=repository_id,
            branch=branch,
            limit=limit,
        )
        return CommitListResponse(
            repository_id=repository_id,
            branch=branch,
            commits=[
                CommitItemSchema(
                    commit_hash=c.commit_hash,
                    short_hash=c.short_hash,
                    message=c.message,
                    author=c.author,
                    timestamp=c.timestamp if isinstance(c.timestamp, str) else c.timestamp.isoformat(),
                )
                for c in commits
            ],
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to list commits: {str(exc)}",
        ) from exc
