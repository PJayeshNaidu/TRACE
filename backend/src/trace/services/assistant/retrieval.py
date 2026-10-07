"""Deterministic retrieval service for TRACE F10 AI Assistant.

Extracts candidate symbols from user questions, queries Neo4j for 1-hop and 2-hop
upstream/downstream graph paths, retrieves F05 risk metrics and F07 upgrade plan steps,
and prunes evidence into a compact bundle (< 1,500 tokens).
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import desc, select

from trace.infrastructure.database.gateway import DatabaseGateway
from trace.infrastructure.database.models import (
    AnalysisRunOrm,
    ImpactAnalysisOrm,
    RepositoryOrm,
    UpgradePlanOrm,
    UpgradeTaskOrm,
    VersionComparisonOrm,
)
from trace.infrastructure.graph.gateway import GraphGateway, Neo4jGraphGateway
from trace.infrastructure.storage.artifact_store import FileArtifactStore
from trace.schemas.assistant import EvidenceSource

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal Evidence Data Structures
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class GraphNeighborEvidence:
    """Graph adjacency relationship extracted from Neo4j or memory."""

    source_symbol: str
    target_symbol: str
    relationship_kind: str
    depth: int
    file_path: str | None = None


@dataclass(slots=True)
class RiskItemEvidence:
    """Risk evaluation entry extracted from F05/F06."""

    symbol_name: str
    risk_level: str
    risk_score: float
    factors: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PlanStepEvidence:
    """Upgrade plan task step extracted from F07."""

    task_id: str
    title: str
    step_number: int
    tier: str
    component: str
    dependencies: list[str] = field(default_factory=list)
    status: str = "PENDING"
    reason: str = ""


@dataclass(slots=True)
class DiffHunkEvidence:
    """AST syntax delta entry extracted from F04."""

    symbol_name: str
    file_path: str
    change_type: str
    is_breaking: bool
    summary: str


@dataclass(slots=True)
class CompactEvidenceBundle:
    """Unified compact evidence container strictly budget-limited (< 1,500 tokens)."""

    project_id: UUID
    analysis_run_id: UUID | None
    matched_symbols: list[str] = field(default_factory=list)
    graph_paths: list[GraphNeighborEvidence] = field(default_factory=list)
    total_graph_paths_count: int = 0
    risk_items: list[RiskItemEvidence] = field(default_factory=list)
    plan_steps: list[PlanStepEvidence] = field(default_factory=list)
    diff_hunks: list[DiffHunkEvidence] = field(default_factory=list)
    sources: list[EvidenceSource] = field(default_factory=list)

    def to_compact_json(self) -> dict[str, Any]:
        """Serialize into a concise JSON payload (< 1,500 tokens / 6,000 characters)."""
        return {
            "matched_symbols": self.matched_symbols[:5],
            "graph_paths": [
                {
                    "from": g.source_symbol,
                    "to": g.target_symbol,
                    "rel": g.relationship_kind,
                    "depth": g.depth,
                    "file": g.file_path,
                }
                for g in self.graph_paths[:8]
            ],
            "total_graph_paths": self.total_graph_paths_count,
            "risk_items": [
                {
                    "symbol": r.symbol_name,
                    "level": r.risk_level,
                    "score": r.risk_score,
                    "factors": r.factors[:3],
                    "recommendations": r.recommendations[:2],
                }
                for r in self.risk_items[:5]
            ],
            "plan_steps": [
                {
                    "id": p.task_id,
                    "step": p.step_number,
                    "task": p.title,
                    "component": p.component,
                    "tier": p.tier,
                    "deps": p.dependencies,
                    "status": p.status,
                    "reason": p.reason,
                }
                for p in self.plan_steps[:5]
            ],
            "diff_hunks": [
                {
                    "symbol": d.symbol_name,
                    "file": d.file_path,
                    "change": d.change_type,
                    "breaking": d.is_breaking,
                    "summary": d.summary,
                }
                for d in self.diff_hunks[:5]
            ],
        }


# ---------------------------------------------------------------------------
# Deterministic Symbol Extractor
# ---------------------------------------------------------------------------


class CandidateSymbolExtractor:
    """Extracts candidate code symbols and task references from natural-language queries."""

    _TASK_PATTERN = re.compile(r"(?i)\b(?:task[_\-\s]*(\d+))\b")
    _BACKTICK_PATTERN = re.compile(r"`([^`\s]+)`")
    _SYMBOL_PATTERN = re.compile(
        r"\b(?:[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)+|[A-Z][a-zA-Z0-9]+|[a-z0-9]+_[a-z0-9_]+)\b"
    )

    _STOPWORDS = {
        "what", "whats", "what's", "why", "how", "is", "are", "the", "a", "an",
        "dependency", "dependencies", "component", "components", "risk", "high",
        "plan", "task", "show", "tell", "explain", "classified", "affected",
        "change", "core", "structural", "entry", "points", "and", "in", "of", "to",
        "evidence", "supports", "support", "everything", "anything", "something",
        "all", "each", "every", "other", "first", "next", "last", "between", "two",
        "versions", "version", "about", "with", "from", "for", "by", "this", "that",
        "these", "those", "have", "has", "had", "low", "which", "where", "code",
        "head", "main", "master", "origin", "trunk", "branch", "commit", "repo",
        "project", "repository", "snapshot", "upgrade", "call", "calls", "caller",
        "callers", "callee", "callees", "dependent", "dependents", "called",
        "language", "languages", "framework", "frameworks", "file", "files",
        "install", "installed", "present", "v1", "v2", "v3", "v1.0", "v2.0",
        "v1.0.0", "difference", "differences", "comparison", "codebase", "sky", "blue",
        "can", "could", "should", "would", "may", "might", "will", "shall", "do",
        "does", "did", "give", "find", "search", "locate", "check", "see", "list", "get",
    }

    _REVISION_OR_GIT_PATTERN = re.compile(
        r"(?i)^(?:head(?:~\d+)?|main|master|origin|trunk|branch|commit|snapshot|"
        r"v\d+(?:\.\d+)*(?:-[a-z0-9]+)?|[0-9a-f]{7,40})$"
    )
    _REPO_OR_PROJECT_PATTERN = re.compile(
        r"(?i)^(?:[a-zA-Z0-9_\-]+-(?:head|main|master|v\d+.*)|python-proj|repo|repository|project|codebase)$"
    )

    @classmethod
    def sanitize_non_symbol_tokens(cls, text: str) -> str:
        """Strip repository identifiers, revisions, and UUIDs to avoid splitting them into false symbols."""
        # 1. UUIDs
        text = re.sub(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", " ", text, flags=re.I)
        # 2. Repo-revision compound identifiers like python-proj-HEAD or sample-repo-main
        text = re.sub(r"\b[a-zA-Z0-9_\-]+-(?:HEAD|main|master|origin|trunk|branch|v\d+[\.\d]*)\b", " ", text, flags=re.I)
        # 3. Git refs like HEAD~1
        text = re.sub(r"\bHEAD~\d+\b", " ", text, flags=re.I)
        # 4. Version numbers like v1.0, v2.0
        text = re.sub(r"\bv\d+(?:\.\d+)+\b", " ", text, flags=re.I)
        # 5. Project names like python-proj
        text = re.sub(r"\bpython-proj\b", " ", text, flags=re.I)
        return text

    @classmethod
    def extract_candidates(
        cls,
        question: str,
        known_symbols: set[str] | None = None,
    ) -> list[str]:
        """Extract candidate symbols from question text, filtering strictly against known symbols.

        Args:
            question: The user's input query.
            known_symbols: Optional set of known symbols from AST/registry for exact/fuzzy matches.

        Returns:
            List of candidate symbol strings ordered by specificity.
        """
        candidates: list[str] = []
        seen: set[str] = set()

        # 1. First extract task references (e.g. Task 1 -> task_1)
        for tm in cls._TASK_PATTERN.finditer(question):
            t_num = tm.group(1)
            t_name = f"task_{t_num}"
            if t_name not in seen:
                seen.add(t_name)
                candidates.append(t_name)

        # 2. Extract backtick-quoted symbols
        for bm in cls._BACKTICK_PATTERN.finditer(question):
            quoted = bm.group(1).strip()
            q_lower = quoted.lower()
            if (
                quoted
                and quoted not in seen
                and q_lower not in cls._STOPWORDS
                and not cls._REVISION_OR_GIT_PATTERN.match(quoted)
                and not cls._REPO_OR_PROJECT_PATTERN.match(quoted)
            ):
                seen.add(quoted)
                candidates.append(quoted)

        # 3. Extract code symbols and qualified names from sanitized text
        sanitized_question = cls.sanitize_non_symbol_tokens(question)
        raw_matches = cls._SYMBOL_PATTERN.findall(sanitized_question)
        extracted: list[str] = []
        for m in raw_matches:
            cleaned = m.strip()
            lower_val = cleaned.lower().replace("'", "")
            if (
                lower_val in cls._STOPWORDS
                or lower_val.rstrip("s") in cls._STOPWORDS
                or cls._REVISION_OR_GIT_PATTERN.match(cleaned)
                or cls._REPO_OR_PROJECT_PATTERN.match(cleaned)
            ):
                continue

            if cleaned not in seen:
                seen.add(cleaned)
                extracted.append(cleaned)

        def _specificity_score(token: str) -> int:
            if "." in token:
                return 4
            if any(c.isupper() for c in token[1:]):  # CamelCase / PascalCase
                return 3
            if token.isupper() and len(token) > 1:  # Acronym like API
                return 3
            if "_" in token:
                return 2
            return 1

        extracted.sort(key=_specificity_score, reverse=True)
        candidates.extend(extracted)

        # If known_symbols is provided, strictly prioritize and filter against known symbols
        if known_symbols:
            scored_candidates: list[tuple[int, str]] = []
            for c in candidates:
                if c.startswith("task_"):
                    scored_candidates.append((4, c))
                    continue
                c_lower = c.lower()
                matched = False
                for ks in known_symbols:
                    ks_lower = ks.lower()
                    if ks_lower == c_lower:
                        scored_candidates.append((3, ks))
                        matched = True
                        break
                    elif ks_lower.endswith(f".{c_lower}") or ks_lower.endswith(f":{c_lower}"):
                        scored_candidates.append((2, ks))
                        matched = True
                    elif c_lower in ks_lower and len(c) >= 4:
                        scored_candidates.append((1, ks))
                        matched = True
                # Note: Unmatched words are dropped when known_symbols are supplied

            scored_candidates.sort(key=lambda x: x[0], reverse=True)
            res = []
            for _, s in scored_candidates:
                if s not in res:
                    res.append(s)
            return res[:5]

        return candidates[:5]


# ---------------------------------------------------------------------------
# Retrieval Service
# ---------------------------------------------------------------------------


class AssistantRetrievalService:
    """Orchestrates deterministic retrieval of graph paths, risk factors, and upgrade plans."""

    def __init__(
        self,
        db_gateway: DatabaseGateway,
        graph_gateway: GraphGateway,
        artifact_store: FileArtifactStore | None = None,
    ) -> None:
        self._db = db_gateway
        self._graph = graph_gateway
        self._artifact_store = artifact_store

    async def retrieve(
        self,
        question: str,
        project_id: UUID,
        analysis_run_id: UUID | None = None,
    ) -> CompactEvidenceBundle:
        """Convenience alias for retrieve_evidence accepting (question, project_id, analysis_run_id)."""
        return await self.retrieve_evidence(
            project_id=project_id,
            question=question,
            analysis_run_id=analysis_run_id,
        )

    async def retrieve_evidence(
        self,
        project_id: UUID,
        question: str,
        analysis_run_id: UUID | None = None,
    ) -> CompactEvidenceBundle:
        """Execute end-to-end deterministic retrieval for a given question.

        Args:
            project_id: Target project UUID.
            question: Natural-language query.
            analysis_run_id: Optional analysis run ID filter.

        Returns:
            CompactEvidenceBundle with graph paths, risk items, plan steps, and sources.
        """
        # 1. Resolve active repository and analysis run
        resolved_repo_id, resolved_run_id = await self._resolve_target_context(
            project_id, analysis_run_id
        )

        # 2. Extract candidate symbols from question
        known_symbols = await self._get_known_symbols(resolved_run_id)
        candidates = CandidateSymbolExtractor.extract_candidates(question, known_symbols)

        bundle = CompactEvidenceBundle(
            project_id=project_id,
            analysis_run_id=resolved_run_id,
            matched_symbols=candidates,
        )

        if not candidates and not resolved_run_id:
            logger.info("No candidate symbols or analysis run resolved", question=question)
            return bundle

        # 3. Retrieve Graph Traversal Evidence (1-hop & 2-hop)
        graph_paths, total_paths = await self._retrieve_graph_paths(candidates, resolved_run_id)
        bundle.graph_paths = graph_paths
        bundle.total_graph_paths_count = total_paths

        # 4. Retrieve F05/F06 Risk Assessment Items
        risk_items = await self._retrieve_risk_items(candidates, resolved_repo_id)
        bundle.risk_items = risk_items

        # 5. Retrieve F07 Upgrade Plan Steps
        plan_steps = await self._retrieve_plan_steps(candidates, resolved_repo_id)
        bundle.plan_steps = plan_steps

        # 6. Retrieve F04 Syntax Delta / Diff Hunks
        diff_hunks = await self._retrieve_diff_hunks(candidates, resolved_repo_id)
        bundle.diff_hunks = diff_hunks

        # 7. Assemble Typed EvidenceSource records
        bundle.sources = self.assemble_evidence_sources(bundle)

        return bundle

    async def _resolve_target_context(
        self,
        project_id: UUID,
        analysis_run_id: UUID | None,
    ) -> tuple[UUID | None, UUID | None]:
        """Resolve repository ID and active analysis run ID."""
        try:
            async with self._db.session() as session:
                if analysis_run_id:
                    stmt = select(AnalysisRunOrm).where(AnalysisRunOrm.id == analysis_run_id)
                    res = (await session.execute(stmt)).scalar_one_or_none()
                    if res:
                        return res.repository_id, res.id

                # Fallback: get the latest analysis run for the project
                stmt_repo = (
                    select(RepositoryOrm)
                    .where(RepositoryOrm.project_id == project_id)
                    .order_by(desc(RepositoryOrm.updated_at))
                )
                repos = (await session.execute(stmt_repo)).scalars().all()
                if not repos:
                    return None, None

                repo_ids = [r.id for r in repos]
                stmt_run = (
                    select(AnalysisRunOrm)
                    .where(AnalysisRunOrm.repository_id.in_(repo_ids))
                    .order_by(desc(AnalysisRunOrm.created_at))
                )
                latest_run = (await session.execute(stmt_run)).scalars().first()
                if latest_run:
                    return latest_run.repository_id, latest_run.id

                return repos[0].id, None
        except Exception as exc:
            logger.debug("Database lookup skipped or failed during context resolution", error=str(exc))
            return None, analysis_run_id

    async def _get_known_symbols(self, analysis_run_id: UUID | None) -> set[str]:
        """Retrieve known symbol names for candidate extraction."""
        if not analysis_run_id or not self._artifact_store:
            return set()
        try:
            if hasattr(self._artifact_store, "get_artifact"):
                artifact = await self._artifact_store.get_artifact(analysis_run_id)
                if artifact:
                    symbols: set[str] = set()
                    for c in getattr(artifact, "classes", []):
                        symbols.add(getattr(c, "qualified_name", getattr(c, "name", "")))
                        symbols.add(getattr(c, "name", ""))
                    for f in getattr(artifact, "functions", []):
                        symbols.add(getattr(f, "qualified_name", getattr(f, "name", "")))
                        symbols.add(getattr(f, "name", ""))
                    for m in getattr(artifact, "modules", []):
                        symbols.add(getattr(m, "qualified_name", getattr(m, "name", "")))
                    return {s for s in symbols if s}
        except Exception as exc:
            logger.debug("Could not extract symbols from artifact store", error=str(exc))
        return set()

    async def _retrieve_graph_paths(
        self,
        candidates: list[str],
        analysis_run_id: UUID | None,
    ) -> tuple[list[GraphNeighborEvidence], int]:
        """Query Neo4j for 1-hop and 2-hop callers/callees."""
        if not candidates:
            return [], 0

        paths: list[GraphNeighborEvidence] = []
        seen_edges: set[tuple[str, str, str]] = set()

        # Check if live Neo4j driver is available
        if isinstance(self._graph, Neo4jGraphGateway) and hasattr(self._graph, "driver"):
            driver = self._graph.driver
            try:
                async with driver.session() as session:
                    for sym in candidates:
                        # 1-hop callers
                        q1 = (
                            "MATCH (caller)-[r:CALLS|IMPORTS|DEPENDS_ON]->(target) "
                            "WHERE target.qualified_name = $sym OR target.name = $sym "
                            "RETURN caller.qualified_name AS src, target.qualified_name AS tgt, "
                            "type(r) AS rel, 1 AS depth, caller.file_path AS file LIMIT 10"
                        )
                        res1 = await session.run(q1, {"sym": sym})
                        for rec in await res1.data():
                            edge_key = (rec["src"] or "", rec["tgt"] or "", rec["rel"] or "")
                            if edge_key not in seen_edges:
                                seen_edges.add(edge_key)
                                paths.append(
                                    GraphNeighborEvidence(
                                        source_symbol=rec["src"] or "unknown",
                                        target_symbol=rec["tgt"] or sym,
                                        relationship_kind=rec["rel"] or "CALLS",
                                        depth=1,
                                        file_path=rec.get("file"),
                                    )
                                )

                        # 1-hop callees
                        q2 = (
                            "MATCH (target)-[r:CALLS|IMPORTS|DEPENDS_ON]->(callee) "
                            "WHERE target.qualified_name = $sym OR target.name = $sym "
                            "RETURN target.qualified_name AS src, callee.qualified_name AS tgt, "
                            "type(r) AS rel, 1 AS depth, callee.file_path AS file LIMIT 10"
                        )
                        res2 = await session.run(q2, {"sym": sym})
                        for rec in await res2.data():
                            edge_key = (rec["src"] or "", rec["tgt"] or "", rec["rel"] or "")
                            if edge_key not in seen_edges:
                                seen_edges.add(edge_key)
                                paths.append(
                                    GraphNeighborEvidence(
                                        source_symbol=rec["src"] or sym,
                                        target_symbol=rec["tgt"] or "unknown",
                                        relationship_kind=rec["rel"] or "CALLS",
                                        depth=1,
                                        file_path=rec.get("file"),
                                    )
                                )

                        # 2-hop callers
                        q3 = (
                            "MATCH (c2)-[r1:CALLS|IMPORTS|DEPENDS_ON]->(c1)-[r2:CALLS|IMPORTS|DEPENDS_ON]->(target) "
                            "WHERE (target.qualified_name = $sym OR target.name = $sym) AND c2 <> target "
                            "RETURN c2.qualified_name AS src, target.qualified_name AS tgt, "
                            "type(r1) AS rel, 2 AS depth, c2.file_path AS file LIMIT 10"
                        )
                        res3 = await session.run(q3, {"sym": sym})
                        for rec in await res3.data():
                            edge_key = (rec["src"] or "", rec["tgt"] or "", rec["rel"] or "")
                            if edge_key not in seen_edges:
                                seen_edges.add(edge_key)
                                paths.append(
                                    GraphNeighborEvidence(
                                        source_symbol=rec["src"] or "unknown",
                                        target_symbol=rec["tgt"] or sym,
                                        relationship_kind=rec["rel"] or "CALLS",
                                        depth=2,
                                        file_path=rec.get("file"),
                                    )
                                )
            except Exception as exc:
                logger.warning("Neo4j Cypher query execution failed", error=str(exc))

        # In-memory artifact fallback if Neo4j returned zero paths or was unconfigured
        if not paths and analysis_run_id and self._artifact_store:
            try:
                if hasattr(self._artifact_store, "get_artifact"):
                    artifact = await self._artifact_store.get_artifact(analysis_run_id)
                    if artifact:
                        for rel in getattr(artifact, "relationships", []):
                            src_name = getattr(rel, "source", "")
                            tgt_name = getattr(rel, "target", "")
                            kind = getattr(rel, "kind", "CALLS")
                            for sym in candidates:
                                sym_l = sym.lower()
                                if (sym_l in src_name.lower() or sym_l in tgt_name.lower()) and len(sym) >= 3:
                                    edge_key = (src_name, tgt_name, kind)
                                    if edge_key not in seen_edges:
                                        seen_edges.add(edge_key)
                                        paths.append(
                                            GraphNeighborEvidence(
                                                source_symbol=src_name,
                                                target_symbol=tgt_name,
                                                relationship_kind=kind,
                                                depth=1,
                                            )
                                        )
            except Exception as exc:
                logger.debug("Artifact relationship fallback error", error=str(exc))

        total_count = len(paths)
        # Localized pruning: hard cap at 8 items
        pruned_paths = paths[:8]
        return pruned_paths, total_count

    async def _retrieve_risk_items(
        self,
        candidates: list[str],
        repository_id: UUID | None,
    ) -> list[RiskItemEvidence]:
        """Fetch F05/F06 risk assessment metrics for candidate symbols."""
        if not repository_id:
            return []

        risk_items: list[RiskItemEvidence] = []
        try:
            async with self._db.session() as session:
                stmt = (
                    select(ImpactAnalysisOrm)
                    .where(ImpactAnalysisOrm.repository_id == repository_id)
                    .order_by(desc(ImpactAnalysisOrm.created_at))
                    .limit(5)
                )
                impact_runs = (await session.execute(stmt)).scalars().all()

                for imp in impact_runs:
                    # If symbol candidate matches or general repository risk query
                    if not candidates or any(
                        c.lower() in (imp.risk_level.lower() or "risk") for c in candidates
                    ):
                        factors = [
                            f"Changed entities: {imp.total_changed_entities}",
                            f"Downstream files impacted: {imp.total_impacted_downstream_files}",
                            f"Callers at risk: {imp.total_callers_at_risk}",
                        ]
                        risk_items.append(
                            RiskItemEvidence(
                                symbol_name=f"Commit {imp.current_commit[:8]}",
                                risk_level=imp.risk_level,
                                risk_score=float(imp.total_callers_at_risk * 10 + (25 if imp.risk_level == 'HIGH' else 10)),
                                factors=factors,
                                recommendations=["Run integration tests for impacted callers"],
                            )
                        )

                    # Attempt to read detailed impact artifact if path exists
                    if imp.artifact_path and Path(imp.artifact_path).exists():
                        try:
                            raw_data = json.loads(Path(imp.artifact_path).read_text(encoding="utf-8"))
                            for item in raw_data.get("affected_components", raw_data.get("affected_symbols", [])):
                                sym_name = item.get("symbol_id") or item.get("qualified_name") or item.get("name", "")
                                for c in candidates:
                                    if c.lower() in sym_name.lower():
                                        risk_items.append(
                                            RiskItemEvidence(
                                                symbol_name=sym_name,
                                                risk_level=item.get("risk_level", imp.risk_level),
                                                risk_score=float(item.get("risk_score", 50.0)),
                                                factors=item.get("risk_factors", ["Downstream caller dependency"]),
                                                recommendations=item.get("recommendations", []),
                                            )
                                        )
                        except Exception as exc:
                            logger.debug("Could not read impact analysis JSON file", error=str(exc))
        except Exception as exc:
            logger.debug("Risk item retrieval skipped or failed", error=str(exc))

        # Deduplicate by symbol_name
        unique_risks: list[RiskItemEvidence] = []
        seen_syms: set[str] = set()
        for r in risk_items:
            if r.symbol_name not in seen_syms:
                seen_syms.add(r.symbol_name)
                unique_risks.append(r)

        return unique_risks[:5]

    async def _retrieve_plan_steps(
        self,
        candidates: list[str],
        repository_id: UUID | None,
    ) -> list[PlanStepEvidence]:
        """Fetch F07 upgrade plan steps for candidate symbols."""
        if not repository_id:
            return []

        plan_steps: list[PlanStepEvidence] = []
        try:
            async with self._db.session() as session:
                stmt = (
                    select(UpgradePlanOrm)
                    .where(UpgradePlanOrm.repository_id == repository_id)
                    .order_by(desc(UpgradePlanOrm.created_at))
                    .limit(1)
                )
                plan = (await session.execute(stmt)).scalar_one_or_none()

                if plan:
                    stmt_tasks = (
                        select(UpgradeTaskOrm)
                        .where(UpgradeTaskOrm.plan_id == plan.id)
                        .order_by(UpgradeTaskOrm.step_number)
                    )
                    tasks = (await session.execute(stmt_tasks)).scalars().all()

                    for t in tasks:
                        matched = False
                        if not candidates:
                            matched = True
                        else:
                            for c in candidates:
                                c_l = c.lower()
                                if (
                                    c_l in t.component.lower()
                                    or c_l in t.category.lower()
                                    or c_l in f"task_{t.step_number}"
                                    or c_l in f"task_{t.id}"
                                    or c_l in t.reason.lower()
                                ):
                                    matched = True
                                    break

                        if matched:
                            plan_steps.append(
                                PlanStepEvidence(
                                    task_id=f"TASK-{t.step_number:03d}",
                                    title=f"Step {t.step_number}: {t.component}",
                                    step_number=t.step_number,
                                    tier=t.category,
                                    component=t.component,
                                    dependencies=[str(d) for d in t.dependencies],
                                    status=t.status,
                                    reason=t.reason,
                                )
                            )
        except Exception as exc:
            logger.debug("Plan step retrieval skipped or failed", error=str(exc))

        return plan_steps[:5]

    async def _retrieve_diff_hunks(
        self,
        candidates: list[str],
        repository_id: UUID | None,
    ) -> list[DiffHunkEvidence]:
        """Fetch real F04 diff hunks for candidate symbols (never generates dummy mock paths)."""
        if not repository_id:
            return []

        diff_hunks: list[DiffHunkEvidence] = []
        try:
            async with self._db.session() as session:
                stmt = (
                    select(VersionComparisonOrm)
                    .where(VersionComparisonOrm.repository_id == repository_id)
                    .order_by(desc(VersionComparisonOrm.created_at))
                    .limit(1)
                )
                comp = (await session.execute(stmt)).scalar_one_or_none()
                if comp and comp.artifact_path and Path(comp.artifact_path).exists():
                    raw_data = json.loads(Path(comp.artifact_path).read_text(encoding="utf-8"))
                    for sym_diff in raw_data.get("symbol_diffs", []):
                        s_name = sym_diff.get("symbol_name") or sym_diff.get("name", "")
                        file_path = sym_diff.get("file_path", "")
                        matched = False
                        if not candidates:
                            matched = True
                        else:
                            for c in candidates:
                                if c.lower() in s_name.lower() or c.lower() in file_path.lower():
                                    matched = True
                                    break
                        if matched and s_name:
                            diff_hunks.append(
                                DiffHunkEvidence(
                                    symbol_name=s_name,
                                    file_path=file_path,
                                    change_type=sym_diff.get("change_type", "MODIFIED"),
                                    is_breaking=bool(sym_diff.get("is_breaking", False)),
                                    summary=sym_diff.get("summary", f"Symbol {s_name} changed in revision"),
                                )
                            )
        except Exception as exc:
            logger.debug("Diff hunk retrieval skipped or failed", error=str(exc))

        return diff_hunks[:5]

    def _assemble_sources(self, bundle: CompactEvidenceBundle) -> list[EvidenceSource]:
        """Convert extracted evidence items into typed EvidenceSource objects."""
        return self.assemble_evidence_sources(bundle)

    @staticmethod
    def assemble_evidence_sources(bundle: CompactEvidenceBundle) -> list[EvidenceSource]:
        """Convert extracted evidence items into typed EvidenceSource objects."""
        sources: list[EvidenceSource] = []

        # Graph sources
        for g in bundle.graph_paths:
            sources.append(
                EvidenceSource(
                    type="graph",
                    identifier=f"{g.source_symbol} -> {g.target_symbol}",
                    summary=f"{g.depth}-hop call edge ({g.relationship_kind}): {g.source_symbol} -> {g.target_symbol}",
                    metadata={
                        "from": g.source_symbol,
                        "to": g.target_symbol,
                        "depth": g.depth,
                        "relationship": g.relationship_kind,
                        "file": g.file_path,
                    },
                )
            )

        # Risk sources
        for r in bundle.risk_items:
            sources.append(
                EvidenceSource(
                    type="risk",
                    identifier=r.symbol_name,
                    summary=f"Assessed Risk: {r.risk_level} (Score: {r.risk_score:.1f}, Factors: {', '.join(r.factors[:2])})",
                    metadata={
                        "risk_level": r.risk_level,
                        "risk_score": r.risk_score,
                        "factors": r.factors,
                    },
                )
            )

        # Plan sources
        for p in bundle.plan_steps:
            sources.append(
                EvidenceSource(
                    type="plan",
                    identifier=p.task_id,
                    summary=f"Upgrade Step {p.step_number} [{p.tier}]: {p.component} (Status: {p.status})",
                    metadata={
                        "step_number": p.step_number,
                        "tier": p.tier,
                        "component": p.component,
                        "dependencies": p.dependencies,
                        "status": p.status,
                    },
                )
            )

        # Diff sources
        for d in bundle.diff_hunks:
            sources.append(
                EvidenceSource(
                    type="diff",
                    identifier=d.symbol_name,
                    summary=f"Diff: {d.change_type} {d.symbol_name} (Breaking: {d.is_breaking}) in {d.file_path}",
                    metadata={
                        "file": d.file_path,
                        "change_type": d.change_type,
                        "is_breaking": d.is_breaking,
                    },
                )
            )

        return sources
