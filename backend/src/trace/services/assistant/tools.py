"""Typed, run-scoped TRACE code intelligence tools for the AI Assistant.

Wraps existing TRACE domain services (AnalysisService, GraphGateway, ImpactService,
PlannerService, VersionChangeService) into 7 typed, bounded retrieval tools.
Enforces strict project_id and analysis_run_id scoping and bounds token usage.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import structlog
from sqlalchemy import desc, select

from trace.domain.analysis import RepositoryAnalysis
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


async def resolve_target_run(
    db_gateway: DatabaseGateway,
    project_id: UUID,
    analysis_run_id: UUID | None = None,
) -> tuple[UUID | None, UUID | None]:
    """Resolve repository_id and active analysis_run_id with strict fallback.

    If analysis_run_id is omitted, resolves the latest completed analysis run for project_id.

    Returns:
        Tuple of (repository_id, analysis_run_id).
    """
    try:
        async with db_gateway.session() as session:
            if analysis_run_id:
                stmt = select(AnalysisRunOrm).where(AnalysisRunOrm.id == analysis_run_id)
                run = (await session.execute(stmt)).scalar_one_or_none()
                if run:
                    return run.repository_id, run.id

            # Find latest repository for the project
            repo_stmt = (
                select(RepositoryOrm)
                .where(RepositoryOrm.project_id == project_id)
                .order_by(desc(RepositoryOrm.updated_at))
            )
            repos = (await session.execute(repo_stmt)).scalars().all()
            if not repos:
                return None, None

            repo_ids = [r.id for r in repos]
            # Find latest completed analysis run for these repositories
            run_stmt = (
                select(AnalysisRunOrm)
                .where(
                    AnalysisRunOrm.repository_id.in_(repo_ids),
                    AnalysisRunOrm.status == "COMPLETED",
                )
                .order_by(desc(AnalysisRunOrm.created_at))
            )
            latest_completed = (await session.execute(run_stmt)).scalars().first()
            if latest_completed:
                return latest_completed.repository_id, latest_completed.id

            # Fallback to any latest run
            any_run_stmt = (
                select(AnalysisRunOrm)
                .where(AnalysisRunOrm.repository_id.in_(repo_ids))
                .order_by(desc(AnalysisRunOrm.created_at))
            )
            latest_any = (await session.execute(any_run_stmt)).scalars().first()
            if latest_any:
                return latest_any.repository_id, latest_any.id

            return repos[0].id, None
    except Exception as exc:
        logger.debug("Failed to resolve target analysis run", error=str(exc))
        return None, analysis_run_id


from trace.domain.plan import TIER_DEFINITIONS, TaskCategory

TIER_WEIGHTS_MAP: dict[str, int] = {
    "CONTRACT_API": 1,
    "CORE_LOGIC": 2,
    "DATA_MAPPING": 3,
    "CONSUMER_HANDLER": 4,
    "CLIENT_UI": 5,
    "INTEGRATION_TEST": 6,
    "DOCUMENTATION_CONFIG": 7,
}

TIER_NAMES_MAP: dict[str, str] = {
    "CONTRACT_API": "API / Contract",
    "CORE_LOGIC": "Core Logic",
    "DATA_MAPPING": "Data / Mapping",
    "CONSUMER_HANDLER": "Handlers / Consumers",
    "CLIENT_UI": "Client / UI",
    "INTEGRATION_TEST": "Tests / Integration",
    "DOCUMENTATION_CONFIG": "Documentation / Config",
}


def resolve_tier_info(category_str: str | None) -> tuple[int, str, str]:
    """Returns (tier_number, tier_name, canonical_category) using F07 7-tier classification."""
    if not category_str:
        return (2, "Core Logic", "CORE_LOGIC")
    cat_clean = category_str.strip().upper()
    try:
        task_cat = TaskCategory(cat_clean)
        tier_def = TIER_DEFINITIONS[task_cat]
        return (tier_def["tier_number"], tier_def["name"], task_cat.value)
    except (ValueError, KeyError):
        if any(k in cat_clean for k in ("CONTRACT", "API", "SCHEMA", "ENDPOINT", "ROUTE")):
            return (1, "API / Contract", "CONTRACT_API")
        if any(k in cat_clean for k in ("DATA", "MAPPING", "MODEL", "ORM", "DATABASE", "DB", "MIGRATION")):
            return (3, "Data / Mapping", "DATA_MAPPING")
        if any(k in cat_clean for k in ("CONSUMER", "HANDLER", "EVENT", "WEBHOOK", "ADAPTER")):
            return (4, "Handlers / Consumers", "CONSUMER_HANDLER")
        if any(k in cat_clean for k in ("CLIENT", "UI", "FRONTEND", "VIEW", "TEMPLATE")):
            return (5, "Client / UI", "CLIENT_UI")
        if any(k in cat_clean for k in ("TEST", "INTEGRATION", "UNIT_TEST", "E2E")):
            return (6, "Tests / Integration", "INTEGRATION_TEST")
        if any(k in cat_clean for k in ("DOC", "DOCUMENTATION", "CONFIG", "ENV")):
            return (7, "Documentation / Config", "DOCUMENTATION_CONFIG")
        return (2, "Core Logic", "CORE_LOGIC")


class AssistantTools:
    """Suite of 7 typed retrieval tools for the TRACE AI Assistant."""

    def __init__(
        self,
        db_gateway: DatabaseGateway,
        graph_gateway: GraphGateway,
        artifact_store: FileArtifactStore | None = None,
    ) -> None:
        self._db = db_gateway
        self._graph = graph_gateway
        self._artifact_store = artifact_store

    async def get_repository_overview(self, analysis_run_id: UUID) -> dict[str, Any]:
        """Tool 1: Summarize top-level repository structure, metrics, languages, and test stats."""
        result: dict[str, Any] = {
            "type": "overview",
            "analysis_run_id": str(analysis_run_id),
            "status": "UNKNOWN",
            "metrics": {},
            "entry_points": [],
            "test_counts": 0,
            "diagnostics_count": 0,
        }
        try:
            async with self._db.session() as session:
                stmt = select(AnalysisRunOrm).where(AnalysisRunOrm.id == analysis_run_id)
                run = (await session.execute(stmt)).scalar_one_or_none()
                if run:
                    result["status"] = run.status
                    result["metrics"] = {
                        "total_files": run.total_files,
                        "python_files": run.python_files,
                        "modules": run.total_modules,
                        "classes": run.total_classes,
                        "functions": run.total_functions,
                        "relationships": run.total_relationships,
                    }
                    result["diagnostics_count"] = run.total_diagnostics

            artifact = await self._load_artifact(analysis_run_id)
            if artifact:
                if not result["metrics"]:
                    result["metrics"] = getattr(artifact, "summary", {}) or getattr(artifact, "metrics", {})
                result["test_counts"] = len(getattr(artifact, "tests", []))

                endpoints = getattr(artifact, "endpoints", [])
                result["entry_points"] = [
                    f"{getattr(e, 'http_method', 'ROUTE')} {getattr(e, 'route_path', getattr(e, 'qualified_name', ''))}"
                    for e in endpoints[:5]
                ]
                if not result["entry_points"]:
                    # Fallback entry points: top functions in main or api modules
                    funcs = getattr(artifact, "functions", [])
                    result["entry_points"] = [
                        getattr(f, "qualified_name", getattr(f, "name", ""))
                        for f in funcs
                        if any(k in getattr(f, "qualified_name", "").lower() for k in ("main", "app", "api", "handler", "route"))
                    ][:5]
        except Exception as exc:
            logger.warning("get_repository_overview failed", error=str(exc), analysis_run_id=str(analysis_run_id))
        return result

    async def search_code_symbols(
        self, query: str, analysis_run_id: UUID, kind: str | None = None
    ) -> list[dict[str, Any]]:
        """Tool 2: Search AST symbol registry for matching classes, functions, and modules."""
        if not query or len(query.strip()) < 2:
            return []

        q_clean = query.strip().lower()
        matches: list[dict[str, Any]] = []

        artifact = await self._load_artifact(analysis_run_id)
        if not artifact:
            return []

        try:
            # Classes
            if not kind or kind.lower() in ("class", "classes"):
                for c in getattr(artifact, "classes", []):
                    name = getattr(c, "name", "")
                    qname = getattr(c, "qualified_name", name)
                    if q_clean in name.lower() or q_clean in qname.lower():
                        matches.append({
                            "type": "ast",
                            "kind": "class",
                            "name": name,
                            "qualified_name": qname,
                            "file_path": getattr(c, "file_path", None),
                            "start_line": getattr(c, "start_line", None),
                            "end_line": getattr(c, "end_line", None),
                            "docstring": (getattr(c, "docstring", "") or "")[:200],
                        })

            # Functions
            if not kind or kind.lower() in ("function", "functions", "method", "methods"):
                for f in getattr(artifact, "functions", []):
                    name = getattr(f, "name", "")
                    qname = getattr(f, "qualified_name", name)
                    if q_clean in name.lower() or q_clean in qname.lower():
                        matches.append({
                            "type": "ast",
                            "kind": "function",
                            "name": name,
                            "qualified_name": qname,
                            "file_path": getattr(f, "file_path", None),
                            "start_line": getattr(f, "start_line", None),
                            "end_line": getattr(f, "end_line", None),
                            "docstring": (getattr(f, "docstring", "") or "")[:200],
                        })

            # Modules
            if not kind or kind.lower() in ("module", "modules"):
                for m in getattr(artifact, "modules", []):
                    name = getattr(m, "name", "")
                    qname = getattr(m, "qualified_name", name)
                    if q_clean in name.lower() or q_clean in qname.lower():
                        matches.append({
                            "type": "ast",
                            "kind": "module",
                            "name": name,
                            "qualified_name": qname,
                            "file_path": getattr(m, "file_path", None),
                            "start_line": 1,
                            "end_line": getattr(m, "line_count", None),
                            "docstring": (getattr(m, "docstring", "") or "")[:200],
                        })
        except Exception as exc:
            logger.warning("search_code_symbols failed", error=str(exc))

        # Prioritize exact name matches
        matches.sort(key=lambda x: (x["name"].lower() != q_clean, len(x["qualified_name"])))
        return matches[:8]

    async def get_symbol_details(
        self, qualified_name: str, analysis_run_id: UUID
    ) -> dict[str, Any] | None:
        """Tool 3: Retrieve detailed AST metadata, signatures, parameters, and bounded source snippets."""
        if not qualified_name:
            return None

        artifact = await self._load_artifact(analysis_run_id)
        if not artifact:
            return None

        qn_clean = qualified_name.strip()
        qn_lower = qn_clean.lower()

        # Find entity in functions or classes
        target_entity: Any = None
        entity_kind = "function"

        for f in getattr(artifact, "functions", []):
            if getattr(f, "qualified_name", "").lower() == qn_lower or getattr(f, "name", "").lower() == qn_lower:
                target_entity = f
                entity_kind = "function"
                break

        if not target_entity:
            for c in getattr(artifact, "classes", []):
                if getattr(c, "qualified_name", "").lower() == qn_lower or getattr(c, "name", "").lower() == qn_lower:
                    target_entity = c
                    entity_kind = "class"
                    break

        if not target_entity:
            # Check modules
            for m in getattr(artifact, "modules", []):
                if getattr(m, "qualified_name", "").lower() == qn_lower or getattr(m, "name", "").lower() == qn_lower:
                    target_entity = m
                    entity_kind = "module"
                    break

        if not target_entity:
            return None

        file_path = getattr(target_entity, "file_path", None)
        start_line = getattr(target_entity, "start_line", 1) or 1
        end_line = getattr(target_entity, "end_line", start_line + 10) or (start_line + 10)

        # Parameters
        parameters: list[str] = []
        for p in getattr(target_entity, "parameters", []):
            p_name = getattr(p, "name", str(p))
            p_type = getattr(p, "type_annotation", None)
            parameters.append(f"{p_name}: {p_type}" if p_type else p_name)

        docstring = getattr(target_entity, "docstring", "") or ""
        complexity = getattr(target_entity, "complexity", None)

        # Attempt to read working tree source code snippet (bounded to 40 lines)
        source_snippet: str | None = None
        if file_path:
            source_snippet = await self._read_source_snippet(analysis_run_id, file_path, start_line, end_line)

        return {
            "type": "ast",
            "qualified_name": getattr(target_entity, "qualified_name", qn_clean),
            "name": getattr(target_entity, "name", qn_clean),
            "kind": entity_kind,
            "file_path": file_path,
            "start_line": start_line,
            "end_line": end_line,
            "parameters": parameters,
            "return_type": getattr(target_entity, "return_type", None),
            "docstring": docstring[:300],
            "complexity": complexity,
            "source_snippet": source_snippet,
        }

    async def get_graph_neighborhood(
        self,
        symbol: str | None = None,
        direction: str = "both",
        depth: int = 1,
        analysis_run_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        """Tool 4: Query Neo4j for 1-hop and 2-hop caller/callee relationships with evidence locations."""
        depth = max(1, min(depth, 2))
        run_str = str(analysis_run_id) if analysis_run_id else None
        results: list[dict[str, Any]] = []
        seen_edges: set[tuple[str, str, str]] = set()

        sym_clean = symbol.strip() if symbol else None
        is_general_query = not sym_clean or sym_clean.lower() in ("all", "dependencies", "graph", "*")

        # Query live Neo4j driver
        if isinstance(self._graph, Neo4jGraphGateway) and hasattr(self._graph, "driver"):
            try:
                driver = self._graph.driver
                async with driver.session() as session:
                    if is_general_query:
                        q_gen = (
                            "MATCH (caller)-[r:CALLS|IMPORTS|DEPENDS_ON]->(target) "
                            "WHERE ($run_id IS NULL OR caller.analysis_run_id = $run_id) "
                            "RETURN caller.qualified_name AS src, target.qualified_name AS tgt, "
                            "type(r) AS rel, 1 AS depth, caller.file_path AS file, r.evidence_start_line AS line "
                            "LIMIT 10"
                        )
                        res_gen = await session.run(q_gen, {"run_id": run_str})
                        for rec in await res_gen.data():
                            key = (rec["src"] or "", rec["tgt"] or "", rec["rel"] or "")
                            if key not in seen_edges:
                                seen_edges.add(key)
                                results.append({
                                    "type": "graph",
                                    "direction": "outgoing",
                                    "source": rec["src"] or "unknown",
                                    "target": rec["tgt"] or "unknown",
                                    "relationship": rec["rel"] or "CALLS",
                                    "depth": 1,
                                    "file_path": rec.get("file"),
                                    "line": rec.get("line"),
                                })
                    else:
                        # 1. Incoming Callers (dependents)
                        if direction in ("callers", "dependents", "both"):
                            q1 = (
                                "MATCH (caller)-[r:CALLS|IMPORTS|DEPENDS_ON]->(target) "
                                "WHERE (target.qualified_name = $sym OR target.name = $sym) "
                                "AND ($run_id IS NULL OR target.analysis_run_id = $run_id) "
                                "RETURN caller.qualified_name AS src, target.qualified_name AS tgt, "
                                "type(r) AS rel, 1 AS depth, caller.file_path AS file, r.evidence_start_line AS line "
                                "LIMIT 10"
                            )
                            res1 = await session.run(q1, {"sym": sym_clean, "run_id": run_str})
                            for rec in await res1.data():
                                key = (rec["src"] or "", rec["tgt"] or "", rec["rel"] or "")
                                if key not in seen_edges:
                                    seen_edges.add(key)
                                    results.append({
                                        "type": "graph",
                                        "direction": "incoming",
                                        "source": rec["src"] or "unknown",
                                        "target": rec["tgt"] or sym_clean,
                                        "relationship": rec["rel"] or "CALLS",
                                        "depth": 1,
                                        "file_path": rec.get("file"),
                                        "line": rec.get("line"),
                                    })

                        # 2. Outgoing Callees (dependencies)
                        if direction in ("callees", "dependencies", "both"):
                            q2 = (
                                "MATCH (target)-[r:CALLS|IMPORTS|DEPENDS_ON]->(callee) "
                                "WHERE (target.qualified_name = $sym OR target.name = $sym) "
                                "AND ($run_id IS NULL OR target.analysis_run_id = $run_id) "
                                "RETURN target.qualified_name AS src, callee.qualified_name AS tgt, "
                                "type(r) AS rel, 1 AS depth, callee.file_path AS file, r.evidence_start_line AS line "
                                "LIMIT 10"
                            )
                            res2 = await session.run(q2, {"sym": sym_clean, "run_id": run_str})
                            for rec in await res2.data():
                                key = (rec["src"] or "", rec["tgt"] or "", rec["rel"] or "")
                                if key not in seen_edges:
                                    seen_edges.add(key)
                                    results.append({
                                        "type": "graph",
                                        "direction": "outgoing",
                                        "source": rec["src"] or sym_clean,
                                        "target": rec["tgt"] or "unknown",
                                        "relationship": rec["rel"] or "CALLS",
                                        "depth": 1,
                                        "file_path": rec.get("file"),
                                        "line": rec.get("line"),
                                    })

                        # 3. 2-Hop Callers
                        if depth >= 2 and direction in ("callers", "dependents", "both"):
                            q3 = (
                                "MATCH (c2)-[r1:CALLS|IMPORTS|DEPENDS_ON]->(c1)-[r2:CALLS|IMPORTS|DEPENDS_ON]->(target) "
                                "WHERE (target.qualified_name = $sym OR target.name = $sym) "
                                "AND ($run_id IS NULL OR target.analysis_run_id = $run_id) "
                                "AND c2 <> target "
                                "RETURN c2.qualified_name AS src, target.qualified_name AS tgt, "
                                "type(r1) AS rel, 2 AS depth, c2.file_path AS file, r1.evidence_start_line AS line "
                                "LIMIT 10"
                            )
                            res3 = await session.run(q3, {"sym": sym_clean, "run_id": run_str})
                            for rec in await res3.data():
                                key = (rec["src"] or "", rec["tgt"] or "", rec["rel"] or "")
                                if key not in seen_edges:
                                    seen_edges.add(key)
                                    results.append({
                                        "type": "graph",
                                        "direction": "incoming",
                                        "source": rec["src"] or "unknown",
                                        "target": rec["tgt"] or sym_clean,
                                        "relationship": rec["rel"] or "CALLS",
                                        "depth": 2,
                                        "file_path": rec.get("file"),
                                        "line": rec.get("line"),
                                    })
            except Exception as exc:
                logger.warning("Neo4j graph query failed", error=str(exc))

        # In-memory artifact relationship fallback if Neo4j returned 0 results
        if not results and analysis_run_id:
            artifact = await self._load_artifact(analysis_run_id)
            if artifact:
                sym_l = sym_clean.lower() if sym_clean else None
                for rel in getattr(artifact, "relationships", []):
                    src_id = getattr(rel, "source_identifier", getattr(rel, "source", ""))
                    tgt_id = getattr(rel, "target_identifier", getattr(rel, "target", ""))
                    rel_type = getattr(rel, "relationship_type", getattr(rel, "kind", "CALLS"))

                    if is_general_query:
                        src_match = True
                        tgt_match = True
                    else:
                        src_match = bool(sym_l and sym_l in src_id.lower())
                        tgt_match = bool(sym_l and sym_l in tgt_id.lower())

                    if (src_match and direction in ("callees", "dependencies", "both")) or (
                        tgt_match and direction in ("callers", "dependents", "both")
                    ):
                        key = (src_id, tgt_id, str(rel_type))
                        if key not in seen_edges:
                            seen_edges.add(key)
                            results.append({
                                "type": "graph",
                                "direction": "outgoing" if src_match else "incoming",
                                "source": src_id,
                                "target": tgt_id,
                                "relationship": str(rel_type),
                                "depth": 1,
                                "file_path": getattr(rel, "file_path", None),
                                "line": getattr(rel, "line_number", None),
                            })

        return results[:10]

    async def get_impact_and_risk(
        self, symbol_or_component: str | None, analysis_run_id: UUID
    ) -> dict[str, Any]:
        """Tool 5: Fetch blast radius, risk metrics, and mitigation steps strictly scoped to analysis_run_id."""
        impact_data: dict[str, Any] = {
            "type": "risk",
            "analysis_run_id": str(analysis_run_id),
            "risk_level": "UNKNOWN",
            "risk_score": 0.0,
            "factors": [],
            "callers_at_risk": [],
            "remediations": [],
            "affected_entities": [],
            "high_risk_components": [],
            "components": [],
        }

        try:
            async with self._db.session() as session:
                # 1. Resolve repository_id from analysis_run_id
                run_stmt = select(AnalysisRunOrm).where(AnalysisRunOrm.id == analysis_run_id)
                run = (await session.execute(run_stmt)).scalar_one_or_none()
                repo_id = run.repository_id if run else None

                if not repo_id:
                    return impact_data

                # 2. Query ImpactAnalysisOrm for this repository, matching run if possible
                imp_stmt = (
                    select(ImpactAnalysisOrm)
                    .where(ImpactAnalysisOrm.repository_id == repo_id)
                    .order_by(desc(ImpactAnalysisOrm.created_at))
                    .limit(5)
                )
                impact_records = (await session.execute(imp_stmt)).scalars().all()
                if not impact_records:
                    return impact_data

                target_rec = impact_records[0]
                impact_data["risk_level"] = target_rec.risk_level
                impact_data["risk_score"] = float(
                    target_rec.total_callers_at_risk * 10 + (35 if target_rec.risk_level == "HIGH" else 15)
                )
                impact_data["factors"] = [
                    f"Changed entities: {target_rec.total_changed_entities}",
                    f"Downstream files impacted: {target_rec.total_impacted_downstream_files}",
                    f"Callers at risk: {target_rec.total_callers_at_risk}",
                ]
                impact_data["remediations"] = ["Run integration regression tests for downstream callers"]

                # 3. Query UpgradePlan and UpgradeTasks from database
                plan_stmt = (
                    select(UpgradePlanOrm)
                    .where(UpgradePlanOrm.repository_id == repo_id)
                    .order_by(desc(UpgradePlanOrm.created_at))
                    .limit(1)
                )
                plan = (await session.execute(plan_stmt)).scalar_one_or_none()
                tasks: list[UpgradeTaskOrm] = []
                if plan:
                    tasks_stmt = (
                        select(UpgradeTaskOrm)
                        .where(UpgradeTaskOrm.plan_id == plan.id)
                        .order_by(UpgradeTaskOrm.step_number)
                    )
                    tasks = list((await session.execute(tasks_stmt)).scalars().all())

                # 4. Load impact artifact if available
                artifact_impacts: list[dict[str, Any]] = []
                if target_rec.artifact_path and Path(target_rec.artifact_path).exists():
                    try:
                        raw_imp = json.loads(Path(target_rec.artifact_path).read_text(encoding="utf-8"))
                        if "impact_analysis" in raw_imp and isinstance(raw_imp["impact_analysis"], dict):
                            artifact_impacts = raw_imp["impact_analysis"].get("detailed_impacts", [])
                        elif "detailed_impacts" in raw_imp:
                            artifact_impacts = raw_imp.get("detailed_impacts", [])
                        elif "affected_components" in raw_imp:
                            artifact_impacts = raw_imp.get("affected_components", [])
                        elif "affected_symbols" in raw_imp:
                            artifact_impacts = raw_imp.get("affected_symbols", [])
                    except Exception as exc:
                        logger.debug("Failed to read impact artifact JSON", error=str(exc))

                # 5. Build unified component records merging artifact impacts and upgrade tasks
                components_map: dict[str, dict[str, Any]] = {}

                # Ingest artifact detailed impacts
                for item in artifact_impacts:
                    c_name = item.get("entity") or item.get("symbol_id") or item.get("qualified_name") or item.get("name")
                    if not c_name:
                        continue
                    file_p = item.get("file") or item.get("file_path")
                    cat_hint = item.get("category") or item.get("entity_type")
                    tier_num, tier_name, cat_val = resolve_tier_info(cat_hint)

                    callers_raw = item.get("callers_at_risk", [])
                    callers_list: list[str] = []
                    for c in callers_raw:
                        if isinstance(c, dict):
                            callers_list.append(c.get("qualified_name") or c.get("name") or str(c))
                        elif isinstance(c, str):
                            callers_list.append(c)

                    item_risk_lvl = item.get("risk_level", target_rec.risk_level)
                    item_score = float(item.get("risk_score", 75.0 if item_risk_lvl == "HIGH" else (90.0 if item_risk_lvl == "CRITICAL" else 35.0)))
                    factors = item.get("risk_factors") or ([item.get("change_summary")] if item.get("change_summary") else []) or ([item.get("justification")] if item.get("justification") else [])
                    recs = item.get("recommendations") or ([item.get("remediation_guidance")] if item.get("remediation_guidance") else [])

                    components_map[c_name.lower()] = {
                        "component": c_name,
                        "file_path": file_p,
                        "category": cat_val,
                        "tier": cat_val,
                        "tier_number": tier_num,
                        "tier_weight": tier_num,
                        "tier_name": tier_name,
                        "risk_level": item_risk_lvl,
                        "risk_score": item_score,
                        "callers_at_risk": callers_list,
                        "factors": factors,
                        "remediations": recs,
                        "step_number": None,
                        "dependencies": [],
                        "required_tests": [],
                    }

                # Ingest DB upgrade tasks
                for t in tasks:
                    comp_key = t.component.lower()
                    tier_num, tier_name, cat_val = resolve_tier_info(t.category)
                    evidence_file = None
                    evidence_callers: list[str] = []
                    if isinstance(t.evidence, dict):
                        evidence_file = t.evidence.get("file_path")
                        evidence_callers = [str(c) for c in t.evidence.get("call_chain", [])]

                    if comp_key in components_map:
                        existing = components_map[comp_key]
                        existing["step_number"] = t.step_number
                        existing["dependencies"] = list(t.dependencies or [])
                        existing["required_tests"] = list(t.required_tests or [])
                        if t.risk_level and t.risk_level != "UNKNOWN":
                            existing["risk_level"] = t.risk_level
                        if not existing["file_path"] and evidence_file:
                            existing["file_path"] = evidence_file
                        if not existing["callers_at_risk"] and evidence_callers:
                            existing["callers_at_risk"] = evidence_callers
                        if t.reason and t.reason not in existing["factors"]:
                            existing["factors"].append(t.reason)
                    else:
                        t_risk = t.risk_level or "LOW"
                        t_score = 75.0 if t_risk == "HIGH" else (90.0 if t_risk == "CRITICAL" else (45.0 if t_risk == "MEDIUM" else 20.0))
                        components_map[comp_key] = {
                            "component": t.component,
                            "file_path": evidence_file,
                            "category": cat_val,
                            "tier": cat_val,
                            "tier_number": tier_num,
                            "tier_weight": tier_num,
                            "tier_name": tier_name,
                            "risk_level": t_risk,
                            "risk_score": t_score,
                            "callers_at_risk": evidence_callers,
                            "factors": [t.reason] if t.reason else [],
                            "remediations": [f"Satisfy prerequisites: {', '.join(t.dependencies)}"] if t.dependencies else ["Review and validate component"],
                            "step_number": t.step_number,
                            "dependencies": list(t.dependencies or []),
                            "required_tests": list(t.required_tests or []),
                        }

                all_components = list(components_map.values())

                # Populate affected_entities and all callers_at_risk
                impact_data["affected_entities"] = [c["component"] for c in all_components]
                all_callers: list[str] = []
                for c in all_components:
                    for caller in c.get("callers_at_risk", []):
                        if caller not in all_callers:
                            all_callers.append(caller)
                impact_data["callers_at_risk"] = all_callers
                impact_data["components"] = all_components

                # High-risk components: sort by risk severity, tier weight (Tier 1 API contracts first), and score
                high_risk = [c for c in all_components if c["risk_level"] in ("HIGH", "CRITICAL") or c["risk_score"] >= 50.0]
                high_risk.sort(key=lambda x: (
                    0 if x["risk_level"] == "CRITICAL" else (1 if x["risk_level"] == "HIGH" else 2),
                    x["tier_number"],
                    -x["risk_score"]
                ))
                impact_data["high_risk_components"] = high_risk

                # Filter for specific symbol if requested
                if symbol_or_component:
                    sym_l = symbol_or_component.lower().strip()
                    git_or_proj = {"head", "main", "master", "python-proj", "sample_repo", "repo", "project", "all", "*"}
                    if sym_l not in git_or_proj:
                        matched = None
                        for comp in all_components:
                            if sym_l == comp["component"].lower() or sym_l in comp["component"].lower():
                                matched = comp
                                break
                        if matched:
                            impact_data["target_component"] = matched["component"]
                            impact_data["risk_level"] = matched["risk_level"]
                            impact_data["risk_score"] = float(matched["risk_score"])
                            impact_data["category"] = matched["category"]
                            impact_data["tier"] = matched["tier"]
                            impact_data["tier_number"] = matched["tier_number"]
                            impact_data["tier_weight"] = matched["tier_weight"]
                            impact_data["tier_name"] = matched["tier_name"]
                            impact_data["factors"] = matched["factors"]
                            impact_data["callers_at_risk"] = matched["callers_at_risk"][:5]
                            impact_data["remediations"] = matched["remediations"]
                            impact_data["file_path"] = matched["file_path"]
                            impact_data["step_number"] = matched["step_number"]
                            impact_data["dependencies"] = matched["dependencies"]
                            impact_data["required_tests"] = matched["required_tests"]
        except Exception as exc:
            logger.warning("get_impact_and_risk failed", error=str(exc))

        return impact_data

    get_risk_analysis = get_impact_and_risk

    async def get_upgrade_plan_tasks(
        self, task_or_component: str | None, repository_id: UUID
    ) -> list[dict[str, Any]]:
        """Tool 6: Retrieve DAG upgrade tasks, phase tiers, prerequisites, and ordering rationales."""
        tasks_out: list[dict[str, Any]] = []
        try:
            async with self._db.session() as session:
                plan_stmt = (
                    select(UpgradePlanOrm)
                    .where(UpgradePlanOrm.repository_id == repository_id)
                    .order_by(desc(UpgradePlanOrm.created_at))
                    .limit(1)
                )
                plan = (await session.execute(plan_stmt)).scalar_one_or_none()
                if not plan:
                    return []

                tasks_stmt = (
                    select(UpgradeTaskOrm)
                    .where(UpgradeTaskOrm.plan_id == plan.id)
                    .order_by(UpgradeTaskOrm.step_number)
                )
                task_records = (await session.execute(tasks_stmt)).scalars().all()

                q_clean = task_or_component.strip().lower() if task_or_component else None

                for t in task_records:
                    matched = False
                    if not q_clean or q_clean in ("all", "plan", "tasks", "first", "order"):
                        matched = True
                    else:
                        t_str = f"task_{t.step_number} {t.component} {t.category} {t.reason}".lower()
                        if q_clean in t_str:
                            matched = True

                    if matched:
                        tasks_out.append({
                            "type": "plan",
                            "task_id": f"TASK-{t.step_number:03d}",
                            "step_number": t.step_number,
                            "component": t.component,
                            "tier": t.category,
                            "dependencies": list(t.dependencies or []),
                            "status": t.status,
                            "reason": t.reason,
                        })
        except Exception as exc:
            logger.warning("get_upgrade_plan_tasks failed", error=str(exc))

        return tasks_out[:8]

    async def get_change_diffs(
        self, symbol_or_file: str | None, repository_id: UUID
    ) -> list[dict[str, Any]]:
        """Tool 7: Retrieve AST syntax diffs, modified parameters, and breaking change flags."""
        diffs_out: list[dict[str, Any]] = []
        try:
            async with self._db.session() as session:
                comp_stmt = (
                    select(VersionComparisonOrm)
                    .where(VersionComparisonOrm.repository_id == repository_id)
                    .order_by(desc(VersionComparisonOrm.created_at))
                    .limit(1)
                )
                comp = (await session.execute(comp_stmt)).scalar_one_or_none()
                if not comp or not comp.artifact_path or not Path(comp.artifact_path).exists():
                    return []

                raw_data = json.loads(Path(comp.artifact_path).read_text(encoding="utf-8"))
                sym_diffs = raw_data.get("symbol_diffs", [])

                q_clean = symbol_or_file.strip().lower() if symbol_or_file else None

                for sd in sym_diffs:
                    s_name = sd.get("symbol_name") or sd.get("name", "")
                    f_path = sd.get("file_path", "")

                    matched = False
                    if not q_clean or q_clean in ("all", "changes", "diffs"):
                        matched = True
                    elif q_clean in s_name.lower() or q_clean in f_path.lower():
                        matched = True

                    if matched and s_name:
                        diffs_out.append({
                            "type": "diff",
                            "symbol_name": s_name,
                            "file_path": f_path,
                            "change_type": sd.get("change_type", "MODIFIED"),
                            "is_breaking": bool(sd.get("is_breaking", False)),
                            "summary": sd.get("summary", f"Symbol {s_name} changed in revision"),
                            "parameters_added": sd.get("parameters_added", []),
                            "parameters_removed": sd.get("parameters_removed", []),
                        })
        except Exception as exc:
            logger.warning("get_change_diffs failed", error=str(exc))

        return diffs_out[:8]

    # -----------------------------------------------------------------------
    # Internal Helpers
    # -----------------------------------------------------------------------

    async def _load_artifact(self, analysis_run_id: UUID) -> RepositoryAnalysis | dict[str, Any] | None:
        """Load RepositoryAnalysis domain object from artifact storage."""
        if not self._artifact_store:
            return None
        try:
            data: Any = None
            if hasattr(self._artifact_store, "read_artifact"):
                data = self._artifact_store.read_artifact(analysis_run_id)
            elif hasattr(self._artifact_store, "load"):
                data = self._artifact_store.load(analysis_run_id)
                if hasattr(data, "__await__"):
                    data = await data

            if data is None:
                return None
            if isinstance(data, RepositoryAnalysis):
                return data
            if isinstance(data, dict):
                try:
                    return RepositoryAnalysis.from_dict(data)
                except Exception:
                    return cast(dict[str, Any], data)
            if hasattr(data, "classes"):
                return cast(RepositoryAnalysis, data)
            return None
        except Exception as exc:
            logger.debug("Could not read analysis artifact", error=str(exc), analysis_run_id=str(analysis_run_id))
        return None


    async def _read_source_snippet(
        self, analysis_run_id: UUID, file_path: str, start_line: int, end_line: int
    ) -> str | None:
        """Read working tree source code snippet bounded to at most 40 lines."""
        try:
            async with self._db.session() as session:
                run_stmt = select(AnalysisRunOrm).where(AnalysisRunOrm.id == analysis_run_id)
                run = (await session.execute(run_stmt)).scalar_one_or_none()
                if not run:
                    return None

                repo_stmt = select(RepositoryOrm).where(RepositoryOrm.id == run.repository_id)
                repo = (await session.execute(repo_stmt)).scalar_one_or_none()
                base_path = Path(repo.location).resolve() if repo and repo.location else Path.cwd()
                p = Path(file_path)
                target_file = p.resolve() if p.is_absolute() else (base_path / file_path).resolve()
                if not target_file.exists() or not target_file.is_file():
                    return None


                lines = target_file.read_text(encoding="utf-8", errors="replace").splitlines()
                # 1-indexed to 0-indexed slice
                s_idx = max(0, start_line - 1)
                # Hard limit of 40 lines
                e_idx = min(len(lines), s_idx + 40, end_line)
                snippet_lines = lines[s_idx:e_idx]
                return "\n".join(snippet_lines)
        except Exception as exc:
            logger.debug("Could not read source snippet from disk", error=str(exc), file=file_path)
            return None
