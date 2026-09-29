"""FastAPI router for static code analysis endpoints."""

import uuid
from trace.analysis.analyzer import CodeAnalyzer
from trace.analysis.summary import (
    format_summary_filename,
    resolve_repo_analysis_dir,
    save_repository_summary_json,
)
from trace.api.analyses.schemas import (
    AnalysisRunListResponse,
    AnalysisRunResponse,
    AnalysisSummaryResponse,
    AnalysisTriggerRequest,
    DiagnosticItem,
    DiagnosticListResponse,
    EntityItem,
    EntityListResponse,
    RelationshipItem,
    RelationshipListResponse,
    SourceLocationSchema,
)
from trace.api.health.router import get_db_gateway
from trace.api.repositories.router import get_git_provider
from trace.domain.analysis import (
    AnalysisStatus,
    DiagnosticSeverity,
    RelationshipKind,
)
from trace.domain.exceptions import InvalidAnalysisStateError
from trace.infrastructure.database.gateway import DatabaseGateway
from trace.infrastructure.git.provider import GitProvider
from trace.infrastructure.storage.artifact_store import FileArtifactStore
from trace.services.analysis import AnalysisService
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, status
from fastapi.responses import FileResponse

analyses_router = APIRouter(tags=["analyses"])


def get_artifact_store(request: Request) -> FileArtifactStore:
    """Dependency provider for FileArtifactStore from application state."""
    store = getattr(request.app.state, "artifact_store", None)
    if store is not None:
        return store  # type: ignore[no-any-return]
    config = getattr(request.app.state, "config", None)
    base_path = getattr(config, "artifacts_dir", ".trace/artifacts")
    return FileArtifactStore(base_path)


def get_code_analyzer(request: Request) -> CodeAnalyzer:
    """Dependency provider for CodeAnalyzer from application state."""
    analyzer = getattr(request.app.state, "code_analyzer", None)
    if analyzer is not None:
        return analyzer  # type: ignore[no-any-return]
    from trace.analysis.analyzer import PythonCodeAnalyzer

    return PythonCodeAnalyzer()


def get_analysis_service(
    request: Request,
    db: Annotated[DatabaseGateway, Depends(get_db_gateway)],
    analyzer: Annotated[CodeAnalyzer, Depends(get_code_analyzer)],
    artifact_store: Annotated[FileArtifactStore, Depends(get_artifact_store)],
    git: Annotated[GitProvider, Depends(get_git_provider)],
) -> AnalysisService:
    """Dependency provider for AnalysisService."""
    config = getattr(request.app.state, "config", None)
    repo_analysis_dir = getattr(config, "repo_analysis_dir", None)
    return AnalysisService(
        db_gateway=db,
        analyzer=analyzer,
        artifact_store=artifact_store,
        git_provider=git,
        repo_analysis_dir=repo_analysis_dir,
    )


class BackgroundTasksAnalysisExecutor:
    """Dispatches asynchronous analysis execution tasks via FastAPI BackgroundTasks."""

    def __init__(self, background_tasks: BackgroundTasks, service: AnalysisService) -> None:
        self._background_tasks = background_tasks
        self._service = service

    def dispatch(
        self,
        analysis_run_id: uuid.UUID,
        target_ref: str | None,
        exclude_patterns: tuple[str, ...],
    ) -> None:
        self._background_tasks.add_task(
            self._service.execute_analysis_task,
            analysis_run_id=analysis_run_id,
            target_ref=target_ref,
            exclude_patterns=exclude_patterns,
        )


@analyses_router.post(
    "/repositories/{repository_id}/analyze",
    response_model=AnalysisRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger an asynchronous repository analysis run",
)
async def trigger_repository_analysis(
    repository_id: uuid.UUID,
    payload: AnalysisTriggerRequest,
    background_tasks: BackgroundTasks,
    service: Annotated[AnalysisService, Depends(get_analysis_service)],
) -> AnalysisRunResponse:
    executor = BackgroundTasksAnalysisExecutor(background_tasks=background_tasks, service=service)
    sanitized_target_ref = (
        None
        if payload.target_ref in ("string", "", None)
        else payload.target_ref
    )
    run = await service.trigger_analysis(
        repository_id=repository_id,
        target_ref=sanitized_target_ref,
        exclude_patterns=payload.exclude_patterns,
        executor=executor,
    )
    return AnalysisRunResponse.from_domain(run)


@analyses_router.get(
    "/repositories/{repository_id}/analyses",
    response_model=AnalysisRunListResponse,
    status_code=status.HTTP_200_OK,
    summary="List analysis runs for a repository",
)
async def list_repository_analyses(
    repository_id: uuid.UUID,
    service: Annotated[AnalysisService, Depends(get_analysis_service)],
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    run_status: Annotated[AnalysisStatus | None, Query(alias="status")] = None,
) -> AnalysisRunListResponse:
    runs, total = await service.list_analysis_runs(
        repository_id=repository_id,
        limit=limit,
        offset=offset,
        status=run_status,
    )
    return AnalysisRunListResponse(
        items=[AnalysisRunResponse.from_domain(r) for r in runs],
        total=total,
        limit=limit,
        offset=offset,
    )


@analyses_router.get(
    "/analyses/{analysis_run_id}",
    response_model=AnalysisRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Get metadata, status, and metrics of an analysis run",
)
async def get_analysis_run(
    analysis_run_id: uuid.UUID,
    service: Annotated[AnalysisService, Depends(get_analysis_service)],
) -> AnalysisRunResponse:
    run = await service.get_analysis_run(analysis_run_id)
    return AnalysisRunResponse.from_domain(run)


@analyses_router.get(
    "/analyses/{analysis_run_id}/summary",
    response_model=AnalysisSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get high-level summary metrics and test.json payload of an analysis run",
)
async def get_analysis_summary(
    analysis_run_id: uuid.UUID,
    service: Annotated[AnalysisService, Depends(get_analysis_service)],
) -> AnalysisSummaryResponse:
    run = await service.get_analysis_run(analysis_run_id)
    if run.status == AnalysisStatus.COMPLETED:
        summary_payload = await service.get_repository_summary(analysis_run_id)
        repo_name = summary_payload["repository"]["name"]
        branch_name = (
            summary_payload.get("version_control", {}).get("current_version", {}).get("branch")
            or summary_payload["repository"].get("default_branch")
            or "main"
        )
        summary_dir = resolve_repo_analysis_dir(service._repo_analysis_dir)
        filename = format_summary_filename(repo_name, branch_name)
        summary_file = summary_dir / filename
        if not summary_file.exists():
            save_repository_summary_json(
                summary_payload=summary_payload,
                repo_name=repo_name,
                output_dir=service._repo_analysis_dir,
                run_id=analysis_run_id,
                branch_name=branch_name,
            )

        return AnalysisSummaryResponse(
            analysis_run_id=run.id,
            repository_id=run.repository_id,
            status=run.status,
            duration_ms=run.duration_ms,
            metrics=summary_payload["metrics"],
            schema_version=summary_payload.get("schema_version"),
            analysis_run=summary_payload["analysis_run"],
            repository=summary_payload["repository"],
            version_control=summary_payload.get("version_control"),
            files=summary_payload.get("files"),
            python_files=summary_payload["python_files"],
            external_dependencies=summary_payload.get("external_dependencies"),
            relationships=summary_payload.get("relationships"),
            dependency_graph=summary_payload.get("dependency_graph"),
            changes=summary_payload.get("changes"),
            architecture=summary_payload.get("architecture"),
            configuration=summary_payload.get("configuration"),
            diagnostics=summary_payload.get("diagnostics"),
            summary_file_path=str(summary_file) if summary_file.exists() else None,
        )
    else:
        metrics = {
            "total_files": run.total_files,
            "python_files": run.python_files,
            "modules": run.total_modules,
            "packages": 0,
            "classes": run.total_classes,
            "functions": run.total_functions,
            "methods": 0,
            "endpoints": 0,
            "database_models": 0,
            "test_functions": 0,
            "external_dependencies": 0,
            "total_relationships": run.total_relationships,
            "diagnostics_count": run.total_diagnostics,
        }
        return AnalysisSummaryResponse(
            analysis_run_id=run.id,
            repository_id=run.repository_id,
            status=run.status,
            duration_ms=run.duration_ms,
            metrics=metrics,
        )


@analyses_router.get(
    "/analyses/{analysis_run_id}/summary/file",
    status_code=status.HTTP_200_OK,
    summary="Download the repository summary JSON file strictly formatted per test.json",
)
async def get_analysis_summary_file(
    analysis_run_id: uuid.UUID,
    service: Annotated[AnalysisService, Depends(get_analysis_service)],
) -> FileResponse:
    run = await service.get_analysis_run(analysis_run_id)
    if run.status != AnalysisStatus.COMPLETED:
        raise InvalidAnalysisStateError(
            run_id=analysis_run_id,
            current_status=run.status.value,
            operation="download summary file for",
        )
    summary_payload = await service.get_repository_summary(analysis_run_id)
    repo_name = summary_payload["repository"]["name"]
    branch_name = (
        summary_payload.get("version_control", {}).get("current_version", {}).get("branch")
        or summary_payload["repository"].get("default_branch")
        or "main"
    )
    file_path = save_repository_summary_json(
        summary_payload=summary_payload,
        repo_name=repo_name,
        output_dir=service._repo_analysis_dir,
        run_id=analysis_run_id,
        branch_name=branch_name,
    )
    return FileResponse(
        path=str(file_path),
        media_type="application/json",
        filename=file_path.name,
    )


@analyses_router.get(
    "/analyses/{analysis_run_id}/entities",
    response_model=EntityListResponse,
    status_code=status.HTTP_200_OK,
    summary="List discovered code entities with pagination and filtering",
)
async def get_analysis_entities(
    analysis_run_id: uuid.UUID,
    service: Annotated[AnalysisService, Depends(get_analysis_service)],
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    kind: Annotated[str | None, Query()] = None,
) -> EntityListResponse:
    artifact = await service.get_analysis_artifact(analysis_run_id)
    all_entities: list[EntityItem] = []

    for m in artifact.modules:
        short_name = m.qualified_name.rsplit(".", 1)[-1]
        all_entities.append(
            EntityItem(
                kind="MODULE",
                name=short_name,
                qualified_name=m.qualified_name,
                module_name=m.qualified_name,
                location=SourceLocationSchema.from_domain(m.location),
                attributes={"is_package": m.is_package, "docstring": m.docstring},
            )
        )

    for c in artifact.classes:
        mod = c.qualified_name.rsplit(".", 1)[0] if "." in c.qualified_name else None
        all_entities.append(
            EntityItem(
                kind="CLASS",
                name=c.name,
                qualified_name=c.qualified_name,
                module_name=mod,
                location=SourceLocationSchema.from_domain(c.location),
                attributes={
                    "parent_classes": list(c.parent_classes),
                    "docstring": c.docstring,
                    "decorators": [d.name for d in c.decorators],
                },
            )
        )

    for fn in artifact.functions:
        mod = fn.qualified_name.rsplit(".", 1)[0] if "." in fn.qualified_name else None
        all_entities.append(
            EntityItem(
                kind="FUNCTION",
                name=fn.name,
                qualified_name=fn.qualified_name,
                module_name=mod,
                location=SourceLocationSchema.from_domain(fn.location),
                attributes={
                    "kind": fn.kind.value,
                    "enclosing_class": fn.enclosing_class,
                    "return_type": fn.return_type,
                    "parameters": [p.name for p in fn.parameters],
                },
            )
        )

    for s in artifact.services:
        all_entities.append(
            EntityItem(
                kind="SERVICE",
                name=s.name,
                qualified_name=s.qualified_name,
                module_name=s.module_name,
                location=SourceLocationSchema.from_domain(s.location),
                attributes={"service_kind": s.service_kind.value, "methods": list(s.methods)},
            )
        )

    for ep in artifact.endpoints:
        all_entities.append(
            EntityItem(
                kind="ENDPOINT",
                name=f"{ep.http_method} {ep.path}",
                qualified_name=ep.handler_qualified_name,
                module_name=None,
                location=SourceLocationSchema.from_domain(ep.location),
                attributes={
                    "http_method": ep.http_method,
                    "path": ep.path,
                    "framework": ep.framework,
                },
            )
        )

    for db in artifact.database_references:
        all_entities.append(
            EntityItem(
                kind="DATABASE",
                name=db.target_entity,
                qualified_name=f"{db.target_entity}:{db.operation.value}",
                module_name=None,
                location=SourceLocationSchema.from_domain(db.location),
                attributes={
                    "target_entity": db.target_entity,
                    "operation": db.operation.value,
                    "referencing_symbol": db.referencing_symbol,
                },
            )
        )

    for t in artifact.tests:
        all_entities.append(
            EntityItem(
                kind="TEST",
                name=t.test_name,
                qualified_name=t.test_qualified_name,
                module_name=None,
                location=SourceLocationSchema.from_domain(t.location),
                attributes={
                    "target_symbol": t.target_symbol,
                    "framework": t.framework,
                },
            )
        )

    for cfg in artifact.configurations:
        all_entities.append(
            EntityItem(
                kind="CONFIGURATION",
                name=cfg.key_name,
                qualified_name=f"{cfg.key_name}:{cfg.referencing_symbol}",
                module_name=None,
                location=SourceLocationSchema.from_domain(cfg.location),
                attributes={
                    "key_name": cfg.key_name,
                    "access_kind": cfg.access_kind.value,
                    "referencing_symbol": cfg.referencing_symbol,
                },
            )
        )

    for doc in artifact.documentation:
        all_entities.append(
            EntityItem(
                kind="DOCUMENTATION",
                name=doc.title,
                qualified_name=doc.file_path,
                module_name=None,
                location=SourceLocationSchema.from_domain(doc.location),
                attributes={
                    "title": doc.title,
                    "doc_type": doc.doc_type.value,
                    "associated_symbol": doc.associated_symbol,
                },
            )
        )

    for dep in artifact.dependencies:
        all_entities.append(
            EntityItem(
                kind="DEPENDENCY",
                name=dep.package_name,
                qualified_name=dep.package_name,
                module_name=None,
                location=SourceLocationSchema(
                    file_path=dep.manifest_path,
                    start_line=1,
                    end_line=1,
                    start_column=0,
                    end_column=0,
                ),
                attributes={
                    "version_spec": dep.version_spec,
                    "manifest_path": dep.manifest_path,
                },
            )
        )

    if kind:
        kind_clean = kind.strip().upper()
        all_entities = [e for e in all_entities if e.kind.upper() == kind_clean]

    total = len(all_entities)
    paginated = all_entities[offset : offset + limit]
    return EntityListResponse(items=paginated, total=total, limit=limit, offset=offset)


@analyses_router.get(
    "/analyses/{analysis_run_id}/relationships",
    response_model=RelationshipListResponse,
    status_code=status.HTTP_200_OK,
    summary="List structural relationships with pagination and type filtering",
)
async def get_analysis_relationships(
    analysis_run_id: uuid.UUID,
    service: Annotated[AnalysisService, Depends(get_analysis_service)],
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    relationship_type: Annotated[RelationshipKind | None, Query()] = None,
) -> RelationshipListResponse:
    artifact = await service.get_analysis_artifact(analysis_run_id)
    all_rels = [
        RelationshipItem(
            source_type=r.source_type,
            source_identifier=r.source_identifier,
            relationship_type=r.relationship_type,
            target_type=r.target_type,
            target_identifier=r.target_identifier,
            evidence_location=SourceLocationSchema.from_domain(r.evidence_location)
            if r.evidence_location
            else None,
        )
        for r in artifact.relationships
    ]

    if relationship_type:
        all_rels = [r for r in all_rels if r.relationship_type == relationship_type]

    total = len(all_rels)
    paginated = all_rels[offset : offset + limit]
    return RelationshipListResponse(items=paginated, total=total, limit=limit, offset=offset)


@analyses_router.get(
    "/analyses/{analysis_run_id}/diagnostics",
    response_model=DiagnosticListResponse,
    status_code=status.HTTP_200_OK,
    summary="List parser errors, warnings, and analysis diagnostics",
)
async def get_analysis_diagnostics(
    analysis_run_id: uuid.UUID,
    service: Annotated[AnalysisService, Depends(get_analysis_service)],
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    severity: Annotated[DiagnosticSeverity | None, Query()] = None,
) -> DiagnosticListResponse:
    artifact = await service.get_analysis_artifact(analysis_run_id)
    all_diags = [
        DiagnosticItem(
            file_path=d.file_path,
            severity=d.severity,
            code=d.code,
            message=d.message,
            line=d.line,
            column=d.column,
        )
        for d in artifact.diagnostics
    ]

    if severity:
        all_diags = [d for d in all_diags if d.severity == severity]

    total = len(all_diags)
    paginated = all_diags[offset : offset + limit]
    return DiagnosticListResponse(items=paginated, total=total, limit=limit, offset=offset)
