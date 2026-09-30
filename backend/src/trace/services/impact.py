"""Service layer orchestrating F05 Impact Analysis and Risk Evaluation Engine."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import select

from trace.analysis.analyzer import AnalysisContext, CodeAnalyzer, PythonCodeAnalyzer
from trace.analysis.delta_inference import DeltaInferenceEngine
from trace.analysis.diff_parser import GitDiffParser
from trace.analysis.graph_traversal import MermaidGenerator, TransposedGraphEngine
from trace.analysis.interval_overlap import IntervalOverlapEngine
from trace.analysis.reasoner.base import DualTrackReasoner
from trace.analysis.reasoner.heuristic import HeuristicRuleEngine
from trace.analysis.reasoner.llm import OpenRouterLlmReasoner
from trace.analysis.text_discovery import TextDiscoveryEngine
from trace.domain.analysis import RepositoryAnalysis
from trace.domain.diff import FileChangeType
from trace.domain.exceptions import RepositoryNotFoundError
from trace.domain.impact import (
    AnalysisMetadataPayload,
    CallerAtRisk,
    DependencyGraphPayload,
    DetailedImpact,
    GraphEdgePayload,
    GraphNodePayload,
    ImpactAnalysisAggregate,
    ReasoningMode,
    RemediationStep,
    RiskAnalysisPayload,
    RiskFactor,
    RiskLevel,
)
from trace.infrastructure.database.gateway import DatabaseGateway
from trace.infrastructure.database.models import ImpactAnalysisOrm, RepositoryOrm
from trace.infrastructure.git.provider import GitProvider
from trace.infrastructure.graph.gateway import GraphGateway
from trace.infrastructure.storage.artifact_store import FileArtifactStore

logger = structlog.get_logger(__name__)


class ImpactAnalysisNotFoundError(Exception):
    """Raised when an impact analysis run cannot be found."""

    def __init__(self, analysis_id: uuid.UUID) -> None:
        super().__init__(f"Impact analysis {analysis_id} not found.")
        self.analysis_id = analysis_id


class ImpactAnalysisService:
    """Orchestrates diff slicing, AST intersection, transposed blast radius, and dual-track reasoning."""

    def __init__(
        self,
        db_gateway: DatabaseGateway,
        git_provider: GitProvider,
        artifact_store: FileArtifactStore,
        diff_parser: GitDiffParser | None = None,
        overlap_engine: IntervalOverlapEngine | None = None,
        graph_engine: TransposedGraphEngine | None = None,
        text_engine: TextDiscoveryEngine | None = None,
        delta_engine: DeltaInferenceEngine | None = None,
        mermaid_generator: MermaidGenerator | None = None,
        analyzer: CodeAnalyzer | None = None,
        graph_gateway: GraphGateway | None = None,
    ) -> None:
        self._db_gateway = db_gateway
        self._git_provider = git_provider
        self._artifact_store = artifact_store
        self._diff_parser = diff_parser or GitDiffParser()
        self._overlap_engine = overlap_engine or IntervalOverlapEngine()
        self._graph_engine = graph_engine or TransposedGraphEngine(max_depth=3)
        self._text_engine = text_engine or TextDiscoveryEngine()
        self._delta_engine = delta_engine or DeltaInferenceEngine()
        self._mermaid_gen = mermaid_generator or MermaidGenerator()
        self._analyzer = analyzer or PythonCodeAnalyzer()
        self._graph_gateway = graph_gateway

    async def evaluate_impact(
        self,
        repository_id: uuid.UUID,
        base_ref: str | None = None,
        target_ref: str | None = None,
        openrouter_api_key: str | None = None,
        openrouter_model: str | None = None,
    ) -> ImpactAnalysisAggregate:
        """Execute full impact analysis and risk evaluation pipeline."""
        logger.info(
            "Evaluating change impact",
            repository_id=str(repository_id),
            base_ref=base_ref,
            target_ref=target_ref,
            has_llm_key=bool(openrouter_api_key),
        )

        async with self._db_gateway.session() as session:
            repo_stmt = select(RepositoryOrm).where(RepositoryOrm.id == repository_id)
            repo_orm = (await session.execute(repo_stmt)).scalar_one_or_none()
            if not repo_orm:
                raise RepositoryNotFoundError(repository_id)

            repo_location = repo_orm.location
            repo_url = repo_orm.location
            default_branch = repo_orm.default_branch or "main"

        # 1. Resolve working directory
        is_remote = repo_orm.type == "REMOTE" or repo_location.startswith(
            ("http://", "https://", "git@", "ssh://")
        )
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
        target_commit = await self._git_provider.resolve_revision(
            working_tree_path, resolved_target
        )
        if not target_commit and resolved_target != "HEAD":
            target_commit = await self._git_provider.resolve_revision(working_tree_path, "HEAD")
        target_commit = target_commit or "0000000000000000000000000000000000000000"

        base_commit = await self._git_provider.resolve_revision(working_tree_path, resolved_base)
        if not base_commit:
            base_commit = await self._git_provider.resolve_revision(working_tree_path, "HEAD~1")
        base_commit = base_commit or "0000000000000000000000000000000000000000"

        # 3. Generate raw zero-context diff & parse hunks
        try:
            raw_diff = await self._git_provider.get_diff(
                working_tree_path, base_ref=resolved_base, target_ref=resolved_target
            )
        except Exception as exc:
            logger.warning("Git diff extraction failed, using empty diff", error=str(exc))
            raw_diff = ""

        file_diffs = self._diff_parser.parse(raw_diff)
        deleted_files = [
            fd.old_path or ""
            for fd in file_diffs
            if fd.change_type == FileChangeType.DELETED and fd.old_path
        ]

        # 4. Load or compute target repository AST analysis
        target_analysis = await self._load_or_analyze(
            repository_id=repository_id,
            working_tree_path=working_tree_path,
            commit_hash=target_commit,
        )

        # 5. Intersect diff hunks with AST symbols
        overlaps = self._overlap_engine.find_modified_entities(file_diffs, target_analysis)

        # 6. Build Inverted Call Graph G^T
        forward_graph: dict[str, set[str]] = {}
        transposed_graph: dict[str, set[str]] = {}
        symbol_files: dict[str, str] = {}
        if target_analysis:
            (
                forward_graph,
                transposed_graph,
                symbol_files,
            ) = self._graph_engine.build_call_graphs(target_analysis)

        # 7. Reasoner setup
        heuristic_engine = HeuristicRuleEngine(self._delta_engine)
        has_llm = bool(openrouter_api_key and openrouter_api_key.strip())
        reasoning_mode = ReasoningMode.LLM_ENRICHED if has_llm else ReasoningMode.HEURISTIC

        # 8. Process each modified entity
        detailed_impacts: list[DetailedImpact] = []
        graph_nodes: list[GraphNodePayload] = []
        graph_edges: list[GraphEdgePayload] = []
        all_callers_at_risk: set[str] = set()
        signature_changed_entities: list[str] = []
        all_downstream_files: set[str] = set()

        for ov in overlaps:
            # Traversal on G^T
            t_res = self._graph_engine.traverse_blast_radius(
                target_symbol=ov.qualified_name,
                transposed_graph=transposed_graph,
                symbol_files=symbol_files,
            )

            # Discover text references in non-code files
            downstream_refs = self._text_engine.find_text_references(
                working_tree_path=working_tree_path,
                entity_name=ov.entity_name,
                source_file_path=ov.file_path,
            )
            downstream_tuple = tuple(sorted(list(set(downstream_refs + [ov.file_path]))))
            all_downstream_files.update(downstream_tuple)

            # Reason on delta
            summary_dict = {
                "entity": ov.entity_name,
                "entity_type": ov.entity_type,
                "file": ov.file_path,
                "lines_affected": ov.lines_affected,
            }
            reasoning_res = await heuristic_engine.reason(
                entity_summary=summary_dict,
                diff_snippet=ov.diff_snippet,
                inbound_callers=t_res.direct_callers,
                downstream_files=downstream_tuple,
            )

            # Record if signature changed
            if "signature" in reasoning_res["change_summary"].lower():
                signature_changed_entities.append(ov.entity_name)

            detailed_impacts.append(
                DetailedImpact(
                    file=ov.file_path,
                    entity=ov.entity_name,
                    entity_type=ov.entity_type,
                    lines_affected=ov.lines_affected,
                    diff_snippet=ov.diff_snippet,
                    change_summary=reasoning_res["change_summary"],
                    remediation_guidance=reasoning_res["remediation_guidance"],
                    justification=reasoning_res["justification"],
                    outbound_calls=ov.outbound_calls,
                    inbound_callers=t_res.direct_callers,
                    callers_at_risk=t_res.callers_at_risk,
                    downstream_dependent_files=downstream_tuple,
                )
            )

            # Graph payload
            graph_nodes.append(
                GraphNodePayload(
                    changed_entity=ov.entity_name,
                    file=ov.file_path,
                    downstream_dependent_files=downstream_tuple,
                    inbound_callers=t_res.direct_callers,
                    outbound_calls=ov.outbound_calls,
                )
            )

            for caller in t_res.direct_callers:
                all_callers_at_risk.add(caller)
                graph_edges.append(
                    GraphEdgePayload(
                        caller=caller,
                        callee=ov.entity_name,
                        relationship="direct_call",
                    )
                )

        # 9. Synthesize Actionable Remediation Plan
        remediation_plan = self._delta_engine.synthesize_remediation_plan(
            signature_changed_entities=signature_changed_entities,
            deleted_files=deleted_files,
            inbound_callers=list(all_callers_at_risk),
            downstream_files=list(all_downstream_files),
        )

        # 10. Risk Evaluation & Factors
        total_entities = len(detailed_impacts)
        total_callers = len(all_callers_at_risk)
        risk_level, risk_factors = self._evaluate_risk(
            total_entities=total_entities,
            signature_changes=len(signature_changed_entities),
            total_callers=total_callers,
            deleted_files_count=len(deleted_files),
        )

        ci_cd_recommendations = self._generate_ci_cd_recommendations(
            risk_level=risk_level,
            total_callers=total_callers,
            signature_changes=len(signature_changed_entities),
        )

        # 11. Generate Mermaid Diagram
        mermaid_code = self._mermaid_gen.generate(graph_nodes, graph_edges)

        # 12. Build Aggregate Payload
        analysis_id = uuid.uuid4()
        now = datetime.now(UTC)

        metadata = AnalysisMetadataPayload(
            analysis_id=analysis_id,
            repository=repo_url,
            base_commit=base_commit,
            current_commit=target_commit,
            reasoning_mode=reasoning_mode,
            total_changed_entities=total_entities,
            total_deleted_files=len(deleted_files),
            total_impacted_downstream_files=len(all_downstream_files),
            total_callers_at_risk=total_callers,
        )

        summary_sentence = (
            f"Detected {total_entities} changed entities and {len(deleted_files)} deleted files "
            f"impacting {len(all_downstream_files)} downstream files."
        )
        ai_directive = None
        if has_llm and openrouter_api_key:
            try:
                llm_reasoner = OpenRouterLlmReasoner(
                    api_key=openrouter_api_key.strip(),
                    model=openrouter_model or "anthropic/claude-3.5-sonnet",
                    timeout_seconds=15.0,
                )
                raw_entities = [
                    {
                        "entity": d.entity,
                        "file": d.file,
                        "lines_affected": list(d.lines_affected),
                        "change_summary": d.change_summary,
                    }
                    for d in detailed_impacts
                ]
                raw_callers = [
                    {
                        "qualified_name": c.qualified_name,
                        "file_path": c.file_path,
                        "distance": c.distance,
                    }
                    for d in detailed_impacts
                    for c in d.callers_at_risk
                ]
                ai_directive = await llm_reasoner.synthesize_developer_directive(
                    changed_entities=raw_entities,
                    callers_at_risk=raw_callers,
                    deleted_files=deleted_files,
                    downstream_files=list(all_downstream_files),
                )
                if ai_directive and ai_directive.get("executive_summary"):
                    summary_sentence = ai_directive["executive_summary"]
            except Exception as exc:
                logger.warning("LLM developer directive synthesis failed, using default summary", error=str(exc))

        aggregate = ImpactAnalysisAggregate(
            metadata=metadata,
            summary=summary_sentence,
            detailed_impacts=tuple(detailed_impacts),
            dependency_graph=DependencyGraphPayload(
                nodes=tuple(graph_nodes),
                edges=tuple(graph_edges),
                mermaid=mermaid_code,
            ),
            risk_analysis=RiskAnalysisPayload(
                risk_level=risk_level,
                key_risk_factors=tuple(risk_factors),
                ci_cd_recommendations=tuple(ci_cd_recommendations),
                actionable_remediation_plan=tuple(remediation_plan),
            ),
            created_at=now,
            ai_directive=ai_directive,
        )

        # 13. Persist JSON Artifact
        artifact_path = self._write_impact_artifact(aggregate)

        # 14. Persist DB Record
        async with self._db_gateway.session() as session:
            orm_record = ImpactAnalysisOrm(
                id=analysis_id,
                repository_id=repository_id,
                base_commit=base_commit,
                current_commit=target_commit,
                risk_level=risk_level.value,
                reasoning_mode=reasoning_mode.value,
                total_changed_entities=total_entities,
                total_deleted_files=len(deleted_files),
                total_impacted_downstream_files=len(all_downstream_files),
                total_callers_at_risk=total_callers,
                artifact_path=str(artifact_path),
                created_at=now,
            )
            session.add(orm_record)
            await session.commit()

        logger.info(
            "Impact analysis completed successfully",
            analysis_id=str(analysis_id),
            risk_level=risk_level.value,
            entities_changed=total_entities,
            callers_at_risk=total_callers,
        )
        return aggregate

    async def get_analysis(self, analysis_id: uuid.UUID) -> dict[str, Any]:
        """Retrieve previously computed impact analysis JSON payload."""
        async with self._db_gateway.session() as session:
            stmt = select(ImpactAnalysisOrm).where(ImpactAnalysisOrm.id == analysis_id)
            record = (await session.execute(stmt)).scalar_one_or_none()
            if not record:
                raise ImpactAnalysisNotFoundError(analysis_id)

        if record.artifact_path and Path(record.artifact_path).exists():
            try:
                data = json.loads(Path(record.artifact_path).read_text(encoding="utf-8"))
                return data
            except Exception as exc:
                logger.warning("Failed to read impact artifact JSON", error=str(exc))

        return {
            "analysis_metadata": {
                "analysis_id": str(record.id),
                "repository_id": str(record.repository_id),
                "base_commit": record.base_commit,
                "current_commit": record.current_commit,
                "risk_level": record.risk_level,
                "reasoning_mode": record.reasoning_mode,
            }
        }

    async def _load_or_analyze(
        self,
        repository_id: uuid.UUID,
        working_tree_path: Path,
        commit_hash: str,
    ) -> RepositoryAnalysis | None:
        """Load cached RepositoryAnalysis or compute static AST on the fly."""
        context = AnalysisContext(
            run_id=uuid.uuid4(),
            repository_id=repository_id,
            working_tree_path=working_tree_path,
            resolved_revision=commit_hash,
        )
        try:
            return self._analyzer.analyze(context)
        except Exception as exc:
            logger.warning("Failed to analyze repository AST", error=str(exc))
            return None

    def _evaluate_risk(
        self,
        total_entities: int,
        signature_changes: int,
        total_callers: int,
        deleted_files_count: int,
    ) -> tuple[RiskLevel, list[RiskFactor]]:
        """Evaluate architectural risk tier and contributing risk factors."""
        factors: list[RiskFactor] = []

        if signature_changes > 0:
            factors.append(
                RiskFactor(
                    factor="Public Callable Signature Alteration",
                    severity="HIGH" if signature_changes > 1 else "MEDIUM",
                    justification=f"{signature_changes} function/method signature(s) modified, risking argument mismatch at call sites.",
                )
            )

        if total_callers >= 5:
            factors.append(
                RiskFactor(
                    factor="Broad Upstream Propagation",
                    severity="CRITICAL",
                    justification=f"{total_callers} upstream callers are directly or indirectly at risk from these modifications.",
                )
            )
        elif total_callers >= 2:
            factors.append(
                RiskFactor(
                    factor="Multi-Hop Caller Dependency",
                    severity="HIGH",
                    justification=f"{total_callers} callers depend on altered symbols across the call graph.",
                )
            )

        if deleted_files_count > 0:
            factors.append(
                RiskFactor(
                    factor="Module Deletion",
                    severity="HIGH",
                    justification=f"{deleted_files_count} file(s) removed; requires import and dependency verification.",
                )
            )

        if not factors:
            factors.append(
                RiskFactor(
                    factor="Isolated Component Modification",
                    severity="LOW",
                    justification="Changes are localized with minimal downstream callers or cross-module dependencies.",
                )
            )

        # Risk rating
        severities = {f.severity for f in factors}
        if "CRITICAL" in severities:
            level = RiskLevel.CRITICAL
        elif "HIGH" in severities:
            level = RiskLevel.HIGH
        elif "MEDIUM" in severities:
            level = RiskLevel.MEDIUM
        else:
            level = RiskLevel.LOW

        return level, factors

    def _generate_ci_cd_recommendations(
        self,
        risk_level: RiskLevel,
        total_callers: int,
        signature_changes: int,
    ) -> list[str]:
        """Synthesize CI/CD testing recommendations based on risk rating."""
        recs: list[str] = []
        if risk_level == RiskLevel.CRITICAL:
            recs.append("Full regression test suite and end-to-end integration tests MUST pass before merge.")
            recs.append("Mandatory manual code review by domain owner required.")
        elif risk_level == RiskLevel.HIGH:
            recs.append("Execute targeted integration tests across all affected caller modules.")
            recs.append("Run contract validation tests for modified callable interfaces.")
        elif risk_level == RiskLevel.MEDIUM:
            recs.append("Execute unit test suite for modified functions and direct upstream callers.")
        else:
            recs.append("Standard test suite execution is sufficient.")

        return recs

    def _write_impact_artifact(self, aggregate: ImpactAnalysisAggregate) -> Path:
        """Serialize complete aggregate to 4-key JSON schema in artifact storage."""
        base_dir = (
            Path(getattr(self._artifact_store, "_base_path", ".trace/artifacts"))
            / "impacts"
        )
        base_dir.mkdir(parents=True, exist_ok=True)
        file_path = base_dir / f"{aggregate.metadata.analysis_id}.json"

        payload = {
            "analysis_metadata": {
                "analysis_id": str(aggregate.metadata.analysis_id),
                "repository": aggregate.metadata.repository,
                "base_commit": aggregate.metadata.base_commit,
                "current_commit": aggregate.metadata.current_commit,
                "reasoning_mode": aggregate.metadata.reasoning_mode.value,
                "total_changed_entities": aggregate.metadata.total_changed_entities,
                "total_deleted_files": aggregate.metadata.total_deleted_files,
                "total_impacted_downstream_files": aggregate.metadata.total_impacted_downstream_files,
                "total_callers_at_risk": aggregate.metadata.total_callers_at_risk,
            },
            "impact_analysis": {
                "summary": aggregate.summary,
                "detailed_impacts": [
                    {
                        "file": d.file,
                        "entity": d.entity,
                        "entity_type": d.entity_type,
                        "lines_affected": list(d.lines_affected),
                        "diff_snippet": d.diff_snippet,
                        "change_summary": d.change_summary,
                        "remediation_guidance": d.remediation_guidance,
                        "justification": d.justification,
                        "outbound_calls": list(d.outbound_calls),
                        "inbound_callers": list(d.inbound_callers),
                        "callers_at_risk": [
                            {
                                "qualified_name": c.qualified_name,
                                "file_path": c.file_path,
                                "distance": c.distance,
                                "call_chain": list(c.call_chain),
                            }
                            for c in d.callers_at_risk
                        ],
                        "downstream_dependent_files": list(d.downstream_dependent_files),
                    }
                    for d in aggregate.detailed_impacts
                ],
            },
            "dependency_graph": {
                "nodes": [
                    {
                        "changed_entity": n.changed_entity,
                        "file": n.file,
                        "downstream_dependent_files": list(n.downstream_dependent_files),
                        "inbound_callers": list(n.inbound_callers),
                        "outbound_calls": list(n.outbound_calls),
                    }
                    for n in aggregate.dependency_graph.nodes
                ],
                "edges": [
                    {
                        "caller": e.caller,
                        "callee": e.callee,
                        "relationship": e.relationship,
                    }
                    for e in aggregate.dependency_graph.edges
                ],
                "mermaid": aggregate.dependency_graph.mermaid,
            },
            "risk_analysis": {
                "risk_level": aggregate.risk_analysis.risk_level.value,
                "key_risk_factors": [
                    {
                        "factor": f.factor,
                        "severity": f.severity,
                        "justification": f.justification,
                    }
                    for f in aggregate.risk_analysis.key_risk_factors
                ],
                "ci_cd_recommendations": list(aggregate.risk_analysis.ci_cd_recommendations),
                "actionable_remediation_plan": [
                    {
                        "step_number": s.step_number,
                        "category": s.category,
                        "action_description": s.action_description,
                        "affected_targets": list(s.affected_targets),
                    }
                    for s in aggregate.risk_analysis.actionable_remediation_plan
                ],
                "ai_directive": getattr(aggregate, "ai_directive", None),
            },
        }

        file_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return file_path
