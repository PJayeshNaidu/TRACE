"""Service layer for F04: Version & Change Analysis and Blast Radius Evaluation."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from trace.analysis.analyzer import AnalysisContext, CodeAnalyzer, PythonCodeAnalyzer
from trace.analysis.diff_parser import GitDiffParser
from trace.analysis.symbol_diff import SymbolDiffEngine
from trace.domain.analysis import AnalysisStatus, RepositoryAnalysis
from trace.domain.diff import (
    BlastRadiusItem,
    CommitInfo,
    DiffHunk,
    FileChangeType,
    FileDiff,
    RiskLevel,
    SymbolChangeKind,
    SymbolDiff,
    VersionComparison,
)
from trace.domain.exceptions import RepositoryNotFoundError
from trace.infrastructure.database.gateway import DatabaseGateway
from trace.infrastructure.database.models import (
    AnalysisRunOrm,
    RepositoryOrm,
    VersionComparisonOrm,
)
from trace.infrastructure.git.provider import GitProvider
from trace.infrastructure.graph.gateway import GraphGateway
from trace.infrastructure.storage.artifact_store import FileArtifactStore
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import desc, select
from sqlalchemy.exc import SQLAlchemyError

logger = structlog.get_logger(__name__)


class ComparisonNotFoundError(Exception):
    """Raised when a version comparison run cannot be found."""

    def __init__(self, comparison_id: uuid.UUID) -> None:
        super().__init__(f"Version comparison {comparison_id} not found.")
        self.comparison_id = comparison_id


class VersionChangeService:
    """Orchestrates git diff extraction, AST delta analysis, and graph blast radius calculation."""

    def __init__(
        self,
        db_gateway: DatabaseGateway,
        git_provider: GitProvider,
        artifact_store: FileArtifactStore,
        diff_parser: GitDiffParser | None = None,
        symbol_diff_engine: SymbolDiffEngine | None = None,
        analyzer: CodeAnalyzer | None = None,
        graph_gateway: GraphGateway | None = None,
    ) -> None:
        self._db_gateway = db_gateway
        self._git_provider = git_provider
        self._artifact_store = artifact_store
        self._diff_parser = diff_parser or GitDiffParser()
        self._symbol_diff_engine = symbol_diff_engine or SymbolDiffEngine()
        self._analyzer = analyzer or PythonCodeAnalyzer()
        self._graph_gateway = graph_gateway

    async def trigger_comparison(
        self,
        repository_id: uuid.UUID,
        base_ref: str | None = None,
        target_ref: str | None = None,
    ) -> VersionComparison:
        """Trigger a comparison between two branches, commits, or default HEAD~1 vs HEAD."""
        logger.info(
            "Triggering version comparison",
            repository_id=str(repository_id),
            base_ref=base_ref,
            target_ref=target_ref,
        )

        async with self._db_gateway.session() as session:
            repo_stmt = select(RepositoryOrm).where(RepositoryOrm.id == repository_id)
            repo_orm = (await session.execute(repo_stmt)).scalar_one_or_none()
            if not repo_orm:
                raise RepositoryNotFoundError(repository_id)

            repo_location = repo_orm.location
            default_branch = repo_orm.default_branch or "main"

        # 1. Resolve working directory
        is_remote = repo_orm.type == "REMOTE" or repo_location.startswith(("http://", "https://", "git@", "ssh://"))
        if is_remote:
            working_tree_path = Path("storage/repos") / str(repository_id)
            if not (working_tree_path / ".git").exists():
                working_tree_path = await self._git_provider.clone_or_checkout(
                    url=repo_location,
                    destination=working_tree_path,
                    target_ref=target_ref or default_branch,
                )
        else:
            working_tree_path = Path(repo_location).resolve()

        resolved_target = target_ref if (target_ref and target_ref != "string") else "HEAD"
        resolved_base = base_ref if (base_ref and base_ref != "string") else "HEAD~1"

        # 2. Resolve commit hashes
        target_commit = await self._git_provider.resolve_revision(working_tree_path, resolved_target)
        if not target_commit and resolved_target != "HEAD":
            target_commit = await self._git_provider.resolve_revision(working_tree_path, "HEAD")
        target_commit = target_commit or "0000000000000000000000000000000000000000"

        base_commit = await self._git_provider.resolve_revision(working_tree_path, resolved_base)
        if not base_commit:
            base_commit = await self._git_provider.resolve_revision(working_tree_path, "HEAD~1")
        base_commit = base_commit or "0000000000000000000000000000000000000000"

        # 3. Generate raw Git diff & parse
        try:
            raw_diff = await self._git_provider.get_diff(
                working_tree_path, base_ref=resolved_base, target_ref=resolved_target
            )
        except Exception as exc:
            logger.warning("Git diff execution failed, falling back to empty diff", error=str(exc))
            raw_diff = ""

        file_diffs = self._diff_parser.parse(raw_diff)

        # 4. Load or generate AST analyses for base and target
        base_analysis = await self._load_or_analyze(
            repository_id=repository_id,
            working_tree_path=working_tree_path,
            commit_hash=base_commit,
        )
        target_analysis = await self._load_or_analyze(
            repository_id=repository_id,
            working_tree_path=working_tree_path,
            commit_hash=target_commit,
        )

        # 5. Compute Symbol Diffs & Breaking changes
        symbol_diffs = self._symbol_diff_engine.compute_symbol_diffs(
            file_diffs=file_diffs,
            base_analysis=base_analysis,
            target_analysis=target_analysis,
        )

        # 6. Query Neo4j for Blast Radius on affected symbols
        blast_radius = await self._compute_blast_radius(
            symbol_diffs=symbol_diffs,
            target_analysis=target_analysis,
            base_analysis=base_analysis,
        )

        # 7. Evaluate overall Risk Level
        total_breaking = sum(1 for s in symbol_diffs if s.is_breaking)
        risk_level = self._evaluate_risk_level(
            total_breaking=total_breaking,
            blast_radius_count=len(blast_radius),
            symbol_diffs_count=len(symbol_diffs),
        )

        # 8. Retrieve commit messages
        try:
            commits = await self._git_provider.list_commits(
                working_tree_path, branch=resolved_target, limit=15
            )
            commit_messages = tuple(c.message for c in commits)
        except Exception:
            commit_messages = ()

        total_insertions = sum(f.insertions for f in file_diffs)
        total_deletions = sum(f.deletions for f in file_diffs)
        comparison_id = uuid.uuid4()
        now = datetime.now(UTC)

        comparison = VersionComparison(
            id=comparison_id,
            repository_id=repository_id,
            base_ref=resolved_base,
            target_ref=resolved_target,
            base_commit_hash=base_commit,
            target_commit_hash=target_commit,
            created_at=now,
            risk_level=risk_level,
            total_files_changed=len(file_diffs),
            total_insertions=total_insertions,
            total_deletions=total_deletions,
            total_symbols_changed=len(symbol_diffs),
            total_breaking_changes=total_breaking,
            file_diffs=tuple(file_diffs),
            symbol_diffs=tuple(symbol_diffs),
            blast_radius=tuple(blast_radius),
            commit_messages=commit_messages,
        )

        # 9. Persist artifact JSON
        artifact_path = self._write_comparison_artifact(comparison)

        # 10. Persist DB record
        async with self._db_gateway.session() as session:
            comp_orm = VersionComparisonOrm(
                id=comparison_id,
                repository_id=repository_id,
                base_ref=resolved_base,
                target_ref=resolved_target,
                base_commit_hash=base_commit,
                target_commit_hash=target_commit,
                risk_level=risk_level.value,
                total_files_changed=len(file_diffs),
                total_insertions=total_insertions,
                total_deletions=total_deletions,
                total_symbols_changed=len(symbol_diffs),
                total_breaking_changes=total_breaking,
                artifact_path=str(artifact_path),
                created_at=now,
            )
            session.add(comp_orm)
            await session.commit()

        logger.info(
            "Version comparison completed successfully",
            comparison_id=str(comparison_id),
            risk_level=risk_level.value,
            files_changed=len(file_diffs),
            symbols_changed=len(symbol_diffs),
            breaking_changes=total_breaking,
            blast_radius_count=len(blast_radius),
        )
        return comparison

    async def get_comparison(self, comparison_id: uuid.UUID) -> VersionComparison:
        """Retrieve complete version comparison by ID."""
        async with self._db_gateway.session() as session:
            stmt = select(VersionComparisonOrm).where(VersionComparisonOrm.id == comparison_id)
            comp_orm = (await session.execute(stmt)).scalar_one_or_none()
            if not comp_orm:
                raise ComparisonNotFoundError(comparison_id)

        # Read full JSON artifact if available
        if comp_orm.artifact_path and Path(comp_orm.artifact_path).exists():
            try:
                data = json.loads(Path(comp_orm.artifact_path).read_text(encoding="utf-8"))
                return self._deserialize_comparison(data)
            except Exception as exc:
                logger.warning("Failed to deserialize comparison artifact JSON", error=str(exc))

        return comp_orm.to_domain()

    async def list_branches(self, repository_id: uuid.UUID) -> list[str]:
        """List active branches in repository."""
        async with self._db_gateway.session() as session:
            repo_stmt = select(RepositoryOrm).where(RepositoryOrm.id == repository_id)
            repo_orm = (await session.execute(repo_stmt)).scalar_one_or_none()
            if not repo_orm:
                raise RepositoryNotFoundError(repository_id)
            repo_location = repo_orm.location

        path = Path("storage/repos") / str(repository_id) if repo_orm.type == "REMOTE" else Path(repo_location)
        if not path.exists():
            return [repo_orm.default_branch or "main"]

        branches = await self._git_provider.list_branches(path)
        if not branches:
            branches = [repo_orm.default_branch or "main"]
        return branches

    async def list_commits(
        self,
        repository_id: uuid.UUID,
        branch: str | None = None,
        limit: int = 30,
    ) -> list[CommitInfo]:
        """List recent commit history in repository."""
        async with self._db_gateway.session() as session:
            repo_stmt = select(RepositoryOrm).where(RepositoryOrm.id == repository_id)
            repo_orm = (await session.execute(repo_stmt)).scalar_one_or_none()
            if not repo_orm:
                raise RepositoryNotFoundError(repository_id)
            repo_location = repo_orm.location

        path = Path("storage/repos") / str(repository_id) if repo_orm.type == "REMOTE" else Path(repo_location)
        if not path.exists():
            return []

        return await self._git_provider.list_commits(path, branch=branch, limit=limit)

    async def _load_or_analyze(
        self,
        repository_id: uuid.UUID,
        working_tree_path: Path,
        commit_hash: str,
    ) -> RepositoryAnalysis | None:
        """Load cached RepositoryAnalysis from DB/ArtifactStore or compute on the fly."""
        async with self._db_gateway.session() as session:
            stmt = (
                select(AnalysisRunOrm)
                .where(
                    AnalysisRunOrm.repository_id == repository_id,
                    AnalysisRunOrm.status == AnalysisStatus.COMPLETED,
                    AnalysisRunOrm.resolved_revision == commit_hash,
                )
                .order_by(desc(AnalysisRunOrm.created_at))
            )
            run_orm = (await session.execute(stmt)).scalars().first()
            if run_orm and run_orm.artifact_path and Path(run_orm.artifact_path).exists():
                try:
                    data = json.loads(Path(run_orm.artifact_path).read_text(encoding="utf-8"))
                    return RepositoryAnalysis.from_dict(data)
                except Exception:
                    pass

        # Fallback: run deterministic analyzer on snapshot of specific commit
        try:
            current_head = await self._git_provider.resolve_revision(working_tree_path, "HEAD")
            if current_head != commit_hash and hasattr(self._git_provider, "_run_command"):
                import shutil
                import tempfile
                tmp_dir = Path(tempfile.mkdtemp(prefix="trace_rev_"))
                try:
                    rc, _, _ = await self._git_provider._run_command(
                        ["-C", str(working_tree_path), "worktree", "add", "--detach", str(tmp_dir), commit_hash],
                        timeout_seconds=15.0,
                    )
                    if rc == 0:
                        context = AnalysisContext(
                            run_id=uuid.uuid4(),
                            repository_id=repository_id,
                            working_tree_path=tmp_dir,
                            resolved_revision=commit_hash,
                        )
                        return self._analyzer.analyze(context)
                finally:
                    try:
                        await self._git_provider._run_command(
                            ["-C", str(working_tree_path), "worktree", "remove", "--force", str(tmp_dir)],
                            timeout_seconds=15.0,
                        )
                    except Exception:
                        pass
                    if tmp_dir.exists():
                        shutil.rmtree(tmp_dir, ignore_errors=True)

            context = AnalysisContext(
                run_id=uuid.uuid4(),
                repository_id=repository_id,
                working_tree_path=working_tree_path,
                resolved_revision=commit_hash,
            )
            return self._analyzer.analyze(context)
        except Exception as exc:
            logger.warning("Failed to analyze commit snapshot", commit=commit_hash, error=str(exc))
            return None

    async def _compute_blast_radius(
        self,
        symbol_diffs: list[SymbolDiff],
        target_analysis: RepositoryAnalysis | None,
        base_analysis: RepositoryAnalysis | None = None,
    ) -> list[BlastRadiusItem]:
        """Query Neo4j graph or AST relationships to find all dependent callers of modified symbols."""
        blast_items: list[BlastRadiusItem] = []
        if not symbol_diffs:
            return blast_items

        changed_syms = [
            s for s in symbol_diffs
            if s.change_kind in (SymbolChangeKind.MODIFIED, SymbolChangeKind.DELETED, SymbolChangeKind.ADDED)
        ]
        if not changed_syms:
            return blast_items

        qual_names = {s.qualified_name: s for s in changed_syms}
        short_names = {s.qualified_name.split(".")[-1]: s for s in changed_syms}
        seen_keys: set[tuple[str, str]] = set()

        # 1. Try Neo4j graph query if gateway with driver is available
        if self._graph_gateway is not None and hasattr(self._graph_gateway, "driver"):
            try:
                driver = getattr(self._graph_gateway, "driver")
                query = """
                MATCH (upstream)-[r:CALLS|IMPORTS|EXTENDS|DEPENDS_ON]->(target)
                WHERE target.qualified_name IN $qual_names OR target.name IN $short_names
                RETURN target.qualified_name AS target_name,
                       target.id AS target_id,
                       upstream.id AS upstream_id,
                       upstream.qualified_name AS upstream_name,
                       upstream.name AS upstream_short_name,
                       head(labels(upstream)) AS upstream_kind,
                       upstream.file_path AS upstream_file,
                       type(r) AS rel_type
                LIMIT 100
                """
                async with driver.session() as session:
                    result = await session.run(
                        query,
                        qual_names=list(qual_names.keys()),
                        short_names=list(short_names.keys()),
                    )
                    records = await result.data()
                    for rec in records:
                        t_name = rec.get("target_name") or rec.get("upstream_name")
                        matched_sym = qual_names.get(t_name) or short_names.get(t_name)
                        t_id = matched_sym.symbol_id if matched_sym else rec.get("target_id", "")
                        u_id = rec.get("upstream_id") or rec.get("upstream_name", "")
                        pair_key = (str(t_id), str(u_id))
                        if pair_key not in seen_keys:
                            seen_keys.add(pair_key)
                            blast_items.append(
                                BlastRadiusItem(
                                    target_symbol_id=t_id,
                                    affected_symbol_id=f"sym:{u_id}",
                                    affected_qualified_name=rec.get("upstream_name") or rec.get("upstream_short_name", "Unknown"),
                                    affected_kind=rec.get("upstream_kind", "Component"),
                                    affected_file_path=rec.get("upstream_file", ""),
                                    relationship_kind=rec.get("rel_type", "DEPENDS_ON"),
                                    depth=1,
                                )
                            )
            except Exception as exc:
                logger.debug("Neo4j blast radius query fell back to AST traversal", error=str(exc))

        # 2. Traverse AST relationships from both target and base analyses
        for analysis in (target_analysis, base_analysis):
            if not analysis:
                continue
            for rel in analysis.relationships:
                t_ident = rel.target_identifier
                matched_sym = qual_names.get(t_ident) or short_names.get(t_ident)
                if not matched_sym:
                    for sn, sym_obj in short_names.items():
                        if t_ident.endswith(f".{sn}") or t_ident == sn:
                            matched_sym = sym_obj
                            break

                if matched_sym:
                    pair_key = (matched_sym.symbol_id, rel.source_identifier)
                    if pair_key not in seen_keys:
                        seen_keys.add(pair_key)
                        blast_items.append(
                            BlastRadiusItem(
                                target_symbol_id=matched_sym.symbol_id,
                                affected_symbol_id=f"sym:{rel.source_identifier}",
                                affected_qualified_name=rel.source_identifier,
                                affected_kind=rel.source_type.value if hasattr(rel.source_type, "value") else str(rel.source_type),
                                affected_file_path=rel.evidence_location.file_path if rel.evidence_location else "",
                                relationship_kind=rel.relationship_type.value if hasattr(rel.relationship_type, "value") else str(rel.relationship_type),
                                depth=1,
                            )
                        )

        return blast_items

    def _evaluate_risk_level(
        self,
        total_breaking: int,
        blast_radius_count: int,
        symbol_diffs_count: int,
    ) -> RiskLevel:
        """Deterministic risk rating calculation."""
        if total_breaking >= 2 or blast_radius_count >= 5:
            return RiskLevel.CRITICAL
        elif total_breaking >= 1 or blast_radius_count >= 2:
            return RiskLevel.HIGH
        elif symbol_diffs_count > 0:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def _write_comparison_artifact(self, comparison: VersionComparison) -> Path:
        """Write JSON artifact representation of VersionComparison."""
        base_dir = Path(getattr(self._artifact_store, "_base_path", ".trace/artifacts")) / "diffs"
        base_dir.mkdir(parents=True, exist_ok=True)
        file_path = base_dir / f"{comparison.id}.json"

        payload = {
            "id": str(comparison.id),
            "repository_id": str(comparison.repository_id),
            "base_ref": comparison.base_ref,
            "target_ref": comparison.target_ref,
            "base_commit_hash": comparison.base_commit_hash,
            "target_commit_hash": comparison.target_commit_hash,
            "created_at": comparison.created_at.isoformat(),
            "risk_level": comparison.risk_level.value,
            "total_files_changed": comparison.total_files_changed,
            "total_insertions": comparison.total_insertions,
            "total_deletions": comparison.total_deletions,
            "total_symbols_changed": comparison.total_symbols_changed,
            "total_breaking_changes": comparison.total_breaking_changes,
            "file_diffs": [
                {
                    "old_path": f.old_path,
                    "new_path": f.new_path,
                    "change_type": f.change_type.value,
                    "insertions": f.insertions,
                    "deletions": f.deletions,
                    "hunks": [
                        {
                            "old_start": h.old_start,
                            "old_lines": h.old_lines,
                            "new_start": h.new_start,
                            "new_lines": h.new_lines,
                            "header": h.header,
                        }
                        for h in f.hunks
                    ],
                }
                for f in comparison.file_diffs
            ],
            "symbol_diffs": [
                {
                    "symbol_id": s.symbol_id,
                    "qualified_name": s.qualified_name,
                    "kind": s.kind,
                    "file_path": s.file_path,
                    "change_kind": s.change_kind.value,
                    "is_breaking": s.is_breaking,
                    "breaking_reason": s.breaking_reason,
                    "old_signature": s.old_signature,
                    "new_signature": s.new_signature,
                }
                for s in comparison.symbol_diffs
            ],
            "blast_radius": [
                {
                    "target_symbol_id": b.target_symbol_id,
                    "affected_symbol_id": b.affected_symbol_id,
                    "affected_qualified_name": b.affected_qualified_name,
                    "affected_kind": b.affected_kind,
                    "affected_file_path": b.affected_file_path,
                    "relationship_kind": b.relationship_kind,
                    "depth": b.depth,
                }
                for b in comparison.blast_radius
            ],
            "commit_messages": list(comparison.commit_messages),
        }
        file_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return file_path

    def _deserialize_comparison(self, data: dict[str, Any]) -> VersionComparison:
        """Deserialize dictionary back to VersionComparison."""
        file_diffs = [
            FileDiff(
                old_path=f.get("old_path"),
                new_path=f.get("new_path"),
                change_type=FileChangeType(f["change_type"]),
                insertions=f.get("insertions", 0),
                deletions=f.get("deletions", 0),
                hunks=tuple(
                    DiffHunk(
                        old_start=h["old_start"],
                        old_lines=h["old_lines"],
                        new_start=h["new_start"],
                        new_lines=h["new_lines"],
                        header=h.get("header", ""),
                    )
                    for h in f.get("hunks", [])
                ),
            )
            for f in data.get("file_diffs", [])
        ]

        symbol_diffs = [
            SymbolDiff(
                symbol_id=s["symbol_id"],
                qualified_name=s["qualified_name"],
                kind=s["kind"],
                file_path=s["file_path"],
                change_kind=SymbolChangeKind(s["change_kind"]),
                is_breaking=s.get("is_breaking", False),
                breaking_reason=s.get("breaking_reason"),
                old_signature=s.get("old_signature"),
                new_signature=s.get("new_signature"),
            )
            for s in data.get("symbol_diffs", [])
        ]

        blast_radius = [
            BlastRadiusItem(
                target_symbol_id=b["target_symbol_id"],
                affected_symbol_id=b["affected_symbol_id"],
                affected_qualified_name=b["affected_qualified_name"],
                affected_kind=b["affected_kind"],
                affected_file_path=b.get("affected_file_path") or "",
                relationship_kind=b["relationship_kind"],
                depth=b.get("depth", 1),
            )
            for b in data.get("blast_radius", [])
        ]

        return VersionComparison(
            id=uuid.UUID(data["id"]),
            repository_id=uuid.UUID(data["repository_id"]),
            base_ref=data["base_ref"],
            target_ref=data["target_ref"],
            base_commit_hash=data["base_commit_hash"],
            target_commit_hash=data["target_commit_hash"],
            created_at=datetime.fromisoformat(data["created_at"]),
            risk_level=RiskLevel(data["risk_level"]),
            total_files_changed=data["total_files_changed"],
            total_insertions=data["total_insertions"],
            total_deletions=data["total_deletions"],
            total_symbols_changed=data["total_symbols_changed"],
            total_breaking_changes=data["total_breaking_changes"],
            file_diffs=tuple(file_diffs),
            symbol_diffs=tuple(symbol_diffs),
            blast_radius=tuple(blast_radius),
            commit_messages=tuple(data.get("commit_messages", ())),
        )
