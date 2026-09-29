"""Service layer for TRACE static code analysis runs and intelligence retrieval."""

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path
from trace.analysis.analyzer import AnalysisContext, CodeAnalyzer
from trace.analysis.summary import (
    build_repository_summary_payload,
    save_repository_summary_json,
)
from trace.domain.analysis import (
    AnalysisRun,
    AnalysisStatus,
    RepositoryAnalysis,
)
from trace.domain.exceptions import (
    AnalysisRunNotFoundError,
    DatabasePersistenceError,
    InvalidAnalysisStateError,
    ProjectArchivedError,
    RepositoryNotFoundError,
)
from trace.domain.project import ProjectStatus
from trace.infrastructure.database.gateway import DatabaseGateway
from trace.infrastructure.database.models import AnalysisRunOrm, ProjectOrm, RepositoryOrm
from trace.infrastructure.git.provider import GitProvider
from trace.infrastructure.storage.artifact_store import FileArtifactStore
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

import structlog
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

if TYPE_CHECKING:
    from trace.services.graph import GraphService

logger = structlog.get_logger(__name__)


@runtime_checkable
class AnalysisExecutor(Protocol):
    """Protocol for dispatching asynchronous analysis run execution."""

    def dispatch(
        self,
        analysis_run_id: uuid.UUID,
        target_ref: str | None,
        exclude_patterns: tuple[str, ...],
    ) -> None:
        """Dispatch execution of an analysis run."""
        ...


class AnalysisService:
    """Orchestrates code analysis lifecycle, artifact storage, and query retrieval."""

    def __init__(
        self,
        db_gateway: DatabaseGateway,
        analyzer: CodeAnalyzer,
        artifact_store: FileArtifactStore,
        git_provider: GitProvider,
        graph_service: "GraphService | None" = None,
        repo_analysis_dir: Path | str | None = None,
    ) -> None:
        self._db_gateway = db_gateway
        self._analyzer = analyzer
        self._artifact_store = artifact_store
        self._git_provider = git_provider
        self._graph_service = graph_service
        self._repo_analysis_dir = repo_analysis_dir

    async def trigger_analysis(
        self,
        repository_id: uuid.UUID,
        target_ref: str | None = None,
        exclude_patterns: list[str] | None = None,
        executor: AnalysisExecutor | None = None,
    ) -> AnalysisRun:
        """Create and queue a new repository analysis run.

        Args:
            repository_id: Identifier of the repository to analyze.
            target_ref: Optional target git ref or commit SHA hint.
            exclude_patterns: Optional directory/file glob patterns to exclude.
            executor: Optional asynchronous execution dispatcher.

        Returns:
            The created AnalysisRun domain record in PENDING state.

        Raises:
            RepositoryNotFoundError: If repository_id does not exist.
            ProjectArchivedError: If the parent project is ARCHIVED.
        """
        async with self._db_gateway.session() as session:
            try:
                repo_stmt = select(RepositoryOrm).where(RepositoryOrm.id == repository_id)
                repo_orm = (await session.execute(repo_stmt)).scalar_one_or_none()
                if not repo_orm:
                    raise RepositoryNotFoundError(repository_id)

                proj_stmt = select(ProjectOrm).where(ProjectOrm.id == repo_orm.project_id)
                proj_orm = (await session.execute(proj_stmt)).scalar_one_or_none()
                if proj_orm and proj_orm.status == ProjectStatus.ARCHIVED:
                    raise ProjectArchivedError(proj_orm.id)

                now = datetime.now(UTC)
                run_id = uuid.uuid4()
                run_orm = AnalysisRunOrm(
                    id=run_id,
                    repository_id=repository_id,
                    project_id=repo_orm.project_id,
                    status=AnalysisStatus.PENDING,
                    target_ref=target_ref,
                    resolved_revision="0000000000000000000000000000000000000000",
                    commit_hash=None,
                    created_at=now,
                    updated_at=now,
                )
                session.add(run_orm)
                await session.commit()
                await session.refresh(run_orm)
                created_run = run_orm.to_domain()

            except (RepositoryNotFoundError, ProjectArchivedError):
                raise
            except SQLAlchemyError as exc:
                logger.exception("Database error while creating analysis run", error=str(exc))
                raise DatabasePersistenceError(f"Failed to create analysis run: {exc}") from exc

        patterns_tuple = tuple(exclude_patterns or [])
        if executor is not None:
            executor.dispatch(run_id, target_ref, patterns_tuple)
        else:
            # If no executor provided, dispatch task via asyncio background task
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(
                    self.execute_analysis_task(
                        analysis_run_id=run_id,
                        target_ref=target_ref,
                        exclude_patterns=patterns_tuple,
                    )
                )
            except RuntimeError:
                # No running event loop
                pass

        return created_run

    async def execute_analysis_task(
        self,
        analysis_run_id: uuid.UUID,
        target_ref: str | None = None,
        exclude_patterns: tuple[str, ...] = (),
    ) -> None:
        """Execute the static analysis pipeline and persist results.

        This method is invoked asynchronously by the execution dispatcher.

        Args:
            analysis_run_id: Target analysis run UUID.
            target_ref: Optional target git ref or commit SHA hint.
            exclude_patterns: Directory/file glob patterns to exclude.
        """
        logger.info("Starting analysis execution task", run_id=str(analysis_run_id))
        started_at = datetime.now(UTC)

        # 1. Update run status to IN_PROGRESS
        async with self._db_gateway.session() as session:
            try:
                stmt = select(AnalysisRunOrm).where(AnalysisRunOrm.id == analysis_run_id)
                run_orm = (await session.execute(stmt)).scalar_one_or_none()
                if not run_orm:
                    logger.error("Analysis run record missing", run_id=str(analysis_run_id))
                    return

                run_orm.status = AnalysisStatus.IN_PROGRESS
                run_orm.started_at = started_at
                run_orm.updated_at = started_at
                await session.commit()

                repo_stmt = select(RepositoryOrm).where(RepositoryOrm.id == run_orm.repository_id)
                repo_orm = (await session.execute(repo_stmt)).scalar_one_or_none()
                if not repo_orm:
                    run_orm.status = AnalysisStatus.FAILED
                    run_orm.error_message = f"Repository {run_orm.repository_id} not found."
                    run_orm.completed_at = datetime.now(UTC)
                    run_orm.updated_at = datetime.now(UTC)
                    await session.commit()
                    return

                repo_location = repo_orm.location
                repository_id = repo_orm.id

            except SQLAlchemyError as exc:
                logger.exception(
                    "Failed to mark run as IN_PROGRESS", run_id=str(analysis_run_id), error=str(exc)
                )
                return

        try:
            resolved_ref = target_ref if (target_ref and target_ref != "string") else "HEAD"

            # 2. Resolve working directory and commit SHA (auto-clone for REMOTE repos)
            is_remote = repo_orm.type == "REMOTE" or repo_location.startswith(("http://", "https://", "git@", "ssh://"))
            if is_remote:
                storage_repos_dir = Path("storage/repos") / str(repository_id)
                working_tree_path = await self._git_provider.clone_or_checkout(
                    url=repo_location,
                    destination=storage_repos_dir,
                    target_ref=target_ref,
                )
            else:
                working_tree_path = Path(repo_location).resolve()

            commit_hash = await self._git_provider.resolve_revision(
                working_tree_path, resolved_ref
            )
            if not commit_hash and resolved_ref != "HEAD":
                commit_hash = await self._git_provider.resolve_revision(
                    working_tree_path, "HEAD"
                )
            if not commit_hash:
                commit_hash = "0000000000000000000000000000000000000000"

            # 3. Execute deterministic CodeAnalyzer
            context = AnalysisContext(
                run_id=analysis_run_id,
                repository_id=repository_id,
                working_tree_path=working_tree_path,
                resolved_revision=commit_hash,
                exclude_patterns=tuple(exclude_patterns),
            )
            result = self._analyzer.analyze(context)

            # 4. Write full JSON intelligence artifact
            artifact_path = self._artifact_store.write_artifact(analysis_run_id, result.to_dict())

            # 5. Update run record to COMPLETED and update repository last_analysis_run_id
            completed_at = datetime.now(UTC)
            duration_ms = max(0.0, (completed_at - started_at).total_seconds() * 1000)

            async with self._db_gateway.session() as session:
                stmt = select(AnalysisRunOrm).where(AnalysisRunOrm.id == analysis_run_id)
                run_orm = (await session.execute(stmt)).scalar_one()

                run_orm.status = AnalysisStatus.COMPLETED
                run_orm.completed_at = completed_at
                run_orm.duration_ms = round(duration_ms, 2)
                run_orm.resolved_revision = commit_hash
                run_orm.commit_hash = commit_hash
                run_orm.total_files = int(result.summary.get("total_files", len(result.files)))
                run_orm.python_files = int(result.summary.get("python_files", 0))
                run_orm.total_modules = int(
                    result.summary.get("total_modules", len(result.modules))
                )
                run_orm.total_classes = int(
                    result.summary.get("total_classes", len(result.classes))
                )
                run_orm.total_functions = int(
                    result.summary.get("total_functions", len(result.functions))
                )
                run_orm.total_relationships = int(
                    result.summary.get("total_relationships", len(result.relationships))
                )
                run_orm.total_diagnostics = int(
                    result.summary.get("total_diagnostics", len(result.diagnostics))
                )
                run_orm.artifact_path = str(artifact_path)
                run_orm.updated_at = completed_at

                repo_stmt = select(RepositoryOrm).where(RepositoryOrm.id == repository_id)
                repo_orm = (await session.execute(repo_stmt)).scalar_one_or_none()
                if repo_orm:
                    repo_orm.last_analysis_run_id = analysis_run_id
                    repo_orm.updated_at = completed_at

                await session.commit()
                logger.info(
                    "Analysis execution completed successfully",
                    run_id=str(analysis_run_id),
                    duration_ms=round(duration_ms, 2),
                    total_files=run_orm.total_files,
                )

            # 6. Generate and save repository summary JSON strictly adhering to test.json schema
            repo_name = (
                getattr(repo_orm, "name", None) or Path(repo_location).name or "repository"
            )
            repo_url = repo_location
            is_remote_loc = (
                repo_location.startswith("http://")
                or repo_location.startswith("https://")
                or repo_location.startswith("git@")
            )
            if not is_remote_loc:
                try:
                    if hasattr(self._git_provider, "_run_command"):
                        rc, out, _ = await self._git_provider._run_command(
                            ["-C", str(working_tree_path), "config", "--get", "remote.origin.url"],
                            timeout_seconds=getattr(self._git_provider, "timeout_seconds", 10.0),
                        )
                        if rc == 0 and out.strip():
                            repo_url = out.strip()
                except Exception:
                    pass

            branch = (
                target_ref
                if (target_ref and target_ref not in ("HEAD", "string"))
                else (repo_orm.default_branch if repo_orm else None)
            )
            if not branch:
                try:
                    if hasattr(self._git_provider, "_run_command"):
                        rc, out, _ = await self._git_provider._run_command(
                            ["-C", str(working_tree_path), "branch", "--show-current"],
                            timeout_seconds=getattr(self._git_provider, "timeout_seconds", 10.0),
                        )
                        if rc == 0 and out.strip():
                            branch = out.strip()
                except Exception:
                    pass
            branch = branch or "main"

            default_branch = (repo_orm.default_branch if repo_orm else None) or branch
            summary_payload = build_repository_summary_payload(
                analysis_run_id=analysis_run_id,
                repository_id=repository_id,
                status=AnalysisStatus.COMPLETED.value,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
                repo_name=repo_name,
                repo_url=repo_url,
                branch=branch,
                commit_hash=commit_hash,
                working_tree_path=working_tree_path,
                artifact=result,
                default_branch=default_branch,
            )
            saved_summary_path = save_repository_summary_json(
                summary_payload=summary_payload,
                repo_name=repo_name,
                output_dir=self._repo_analysis_dir,
                run_id=analysis_run_id,
                branch_name=branch,
            )
            logger.info(
                "Repository summary JSON stored successfully per test.json schema",
                run_id=str(analysis_run_id),
                repo_name=repo_name,
                summary_path=str(saved_summary_path),
            )

            # Auto-trigger F03 dependency graph build after successful analysis
            if self._graph_service is not None:
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(
                        self._graph_service.build_dependency_graph(analysis_run_id),
                        name=f"graph_build:{analysis_run_id}",
                    )
                    logger.info(
                        "Dependency graph build dispatched",
                        run_id=str(analysis_run_id),
                    )
                except RuntimeError:
                    pass  # No running event loop (e.g. during sync tests)

        except Exception as exc:
            logger.exception(
                "Analysis execution failed fatally", run_id=str(analysis_run_id), error=str(exc)
            )
            completed_at = datetime.now(UTC)
            duration_ms = max(0.0, (completed_at - started_at).total_seconds() * 1000)
            async with self._db_gateway.session() as session:
                try:
                    stmt = select(AnalysisRunOrm).where(AnalysisRunOrm.id == analysis_run_id)
                    run_orm = (await session.execute(stmt)).scalar_one_or_none()
                    if run_orm:
                        run_orm.status = AnalysisStatus.FAILED
                        run_orm.error_message = str(exc)
                        run_orm.completed_at = completed_at
                        run_orm.duration_ms = round(duration_ms, 2)
                        run_orm.updated_at = completed_at
                        await session.commit()
                except SQLAlchemyError as db_exc:
                    logger.exception("Failed to record analysis failure status", error=str(db_exc))

    async def get_analysis_run(self, analysis_run_id: uuid.UUID) -> AnalysisRun:
        """Fetch metadata, status, and metrics for an analysis run.

        Args:
            analysis_run_id: Analysis run UUID.

        Returns:
            The AnalysisRun domain entity.

        Raises:
            AnalysisRunNotFoundError: If run does not exist.
        """
        async with self._db_gateway.session() as session:
            stmt = select(AnalysisRunOrm).where(AnalysisRunOrm.id == analysis_run_id)
            run_orm = (await session.execute(stmt)).scalar_one_or_none()
            if not run_orm:
                raise AnalysisRunNotFoundError(analysis_run_id)
            return run_orm.to_domain()

    async def list_analysis_runs(
        self,
        repository_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
        status: AnalysisStatus | None = None,
    ) -> tuple[list[AnalysisRun], int]:
        """List analysis runs for a repository with pagination and optional status filter.

        Args:
            repository_id: Repository UUID.
            limit: Maximum items to return (1-500).
            offset: Zero-based query offset.
            status: Optional status filter.

        Returns:
            Tuple of (list of AnalysisRun domain entities, total matching count).

        Raises:
            RepositoryNotFoundError: If repository_id does not exist.
        """
        async with self._db_gateway.session() as session:
            repo_stmt = select(RepositoryOrm).where(RepositoryOrm.id == repository_id)
            repo_orm = (await session.execute(repo_stmt)).scalar_one_or_none()
            if not repo_orm:
                raise RepositoryNotFoundError(repository_id)

            base_query = select(AnalysisRunOrm).where(AnalysisRunOrm.repository_id == repository_id)
            count_query = select(func.count(AnalysisRunOrm.id)).where(
                AnalysisRunOrm.repository_id == repository_id
            )

            if status is not None:
                base_query = base_query.where(AnalysisRunOrm.status == status)
                count_query = count_query.where(AnalysisRunOrm.status == status)

            total_count = (await session.execute(count_query)).scalar_one()

            runs_query = (
                base_query.order_by(AnalysisRunOrm.created_at.desc()).limit(limit).offset(offset)
            )
            rows = (await session.execute(runs_query)).scalars().all()
            return [row.to_domain() for row in rows], total_count

    async def get_analysis_artifact(self, analysis_run_id: uuid.UUID) -> RepositoryAnalysis:
        """Load and reconstruct the RepositoryAnalysis domain aggregate from artifact storage.

        Args:
            analysis_run_id: Analysis run UUID.

        Returns:
            The complete RepositoryAnalysis domain model.

        Raises:
            AnalysisRunNotFoundError: If run does not exist.
            InvalidAnalysisStateError: If run has not completed.
        """
        run = await self.get_analysis_run(analysis_run_id)
        if run.status != AnalysisStatus.COMPLETED:
            raise InvalidAnalysisStateError(
                run_id=analysis_run_id,
                current_status=run.status.value,
                operation="retrieve artifact for",
            )

        try:
            data = self._artifact_store.read_artifact(analysis_run_id)
            return RepositoryAnalysis.from_dict(data)
        except FileNotFoundError as exc:
            logger.error("Artifact file missing for completed run", run_id=str(analysis_run_id))
            raise AnalysisRunNotFoundError(analysis_run_id) from exc

    async def get_repository_summary(self, analysis_run_id: uuid.UUID) -> dict[str, Any]:
        """Fetch or reconstruct the complete repository summary conforming strictly to test.json."""
        run = await self.get_analysis_run(analysis_run_id)
        if run.status != AnalysisStatus.COMPLETED:
            raise InvalidAnalysisStateError(
                run_id=analysis_run_id,
                current_status=run.status.value,
                operation="retrieve summary for",
            )

        artifact = await self.get_analysis_artifact(analysis_run_id)

        async with self._db_gateway.session() as session:
            repo_stmt = select(RepositoryOrm).where(RepositoryOrm.id == run.repository_id)
            repo_orm = (await session.execute(repo_stmt)).scalar_one_or_none()

        repo_location = repo_orm.location if repo_orm else ""
        repo_name = getattr(repo_orm, "name", None) or Path(repo_location).name or "repository"
        repo_url = repo_location
        branch = run.target_ref or (repo_orm.default_branch if repo_orm else None) or "main"
        working_tree_path = Path(repo_location).resolve() if repo_location else Path.cwd()

        default_branch = (repo_orm.default_branch if repo_orm else None) or branch
        return build_repository_summary_payload(
            analysis_run_id=analysis_run_id,
            repository_id=run.repository_id,
            status=run.status.value,
            started_at=run.started_at,
            completed_at=run.completed_at,
            duration_ms=run.duration_ms,
            repo_name=repo_name,
            repo_url=repo_url,
            branch=branch,
            commit_hash=(
                run.commit_hash
                or run.resolved_revision
                or "0000000000000000000000000000000000000000"
            ),
            working_tree_path=working_tree_path,
            artifact=artifact,
            default_branch=default_branch,
        )

