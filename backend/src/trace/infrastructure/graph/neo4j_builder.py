"""Neo4j Cypher write engine for F03 Dependency Graph.

Responsible for projecting a RepositoryAnalysis domain aggregate into Neo4j
using idempotent MERGE-based batch Cypher operations.

This module has NO dependency on FastAPI, SQLAlchemy, or the service layer.
It depends only on the neo4j async driver and domain models.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from neo4j import AsyncDriver

from trace.domain.analysis import (
    EntityKind,
    FunctionKind,
    RepositoryAnalysis,
)

logger = structlog.get_logger(__name__)

_BATCH_SIZE = 100

# ---------------------------------------------------------------------------
# Constraint DDL — run once on startup or first build
# ---------------------------------------------------------------------------

_CONSTRAINT_QUERIES: list[str] = [
    "CREATE CONSTRAINT module_id_unique IF NOT EXISTS FOR (n:Module) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT class_id_unique IF NOT EXISTS FOR (n:Class) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT function_id_unique IF NOT EXISTS FOR (n:Function) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT service_id_unique IF NOT EXISTS FOR (n:Service) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT endpoint_id_unique IF NOT EXISTS FOR (n:Endpoint) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT dbentity_id_unique IF NOT EXISTS FOR (n:DatabaseEntity) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT configsetting_id_unique IF NOT EXISTS FOR (n:ConfigSetting) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT testunit_id_unique IF NOT EXISTS FOR (n:TestUnit) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT extpkg_id_unique IF NOT EXISTS FOR (n:ExternalPackage) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT docartifact_id_unique IF NOT EXISTS FOR (n:DocArtifact) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT analysisroot_run_id_unique IF NOT EXISTS FOR (n:AnalysisRoot) REQUIRE n.analysis_run_id IS UNIQUE",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _node_id(label: str, key: str, run_id: str) -> str:
    """Generate a stable, unique node ID for MERGE operations.

    The ID is composed of the label, primary key value, and analysis_run_id
    so that nodes across different analysis runs never collide.
    """
    return f"{label}::{key}::{run_id}"


def _is_async_kind(kind: FunctionKind) -> bool:
    return kind in (FunctionKind.ASYNC_FUNCTION, FunctionKind.ASYNC_METHOD)


# ---------------------------------------------------------------------------
# Node row builders — produce flat dicts for UNWIND + MERGE Cypher
# ---------------------------------------------------------------------------


def _build_node_rows(
    analysis: RepositoryAnalysis,
) -> dict[str, list[dict[str, Any]]]:
    """Build per-label lists of node property dicts for batch MERGE."""
    run_id = str(analysis.run_id)
    rows: dict[str, list[dict[str, Any]]] = {
        "AnalysisRoot": [],
        "Module": [],
        "Class": [],
        "Function": [],
        "Service": [],
        "Endpoint": [],
        "DatabaseEntity": [],
        "ConfigSetting": [],
        "TestUnit": [],
        "ExternalPackage": [],
        "DocArtifact": [],
    }

    # AnalysisRoot — one per analysis run
    rows["AnalysisRoot"].append(
        {
            "id": _node_id("AnalysisRoot", str(analysis.run_id), run_id),
            "analysis_run_id": run_id,
            "repository_id": str(analysis.repository_id),
            "commit_hash": analysis.commit_hash or "",
            "analyzed_at": analysis.analyzed_at.isoformat(),
        }
    )

    for m in analysis.modules:
        rows["Module"].append(
            {
                "id": _node_id("Module", m.qualified_name, run_id),
                "analysis_run_id": run_id,
                "qualified_name": m.qualified_name,
                "file_path": m.file_path,
                "is_package": m.is_package,
                "docstring": m.docstring or "",
            }
        )

    for c in analysis.classes:
        rows["Class"].append(
            {
                "id": _node_id("Class", c.qualified_name, run_id),
                "analysis_run_id": run_id,
                "qualified_name": c.qualified_name,
                "name": c.name,
                "module_name": c.module_name,
                "parent_classes": list(c.parent_classes),
                "docstring": c.docstring or "",
            }
        )

    for fn in analysis.functions:
        rows["Function"].append(
            {
                "id": _node_id("Function", fn.qualified_name, run_id),
                "analysis_run_id": run_id,
                "qualified_name": fn.qualified_name,
                "name": fn.name,
                "kind": fn.kind.value,
                "enclosing_class": fn.enclosing_class or "",
                "return_type": fn.return_type or "",
                "is_async": _is_async_kind(fn.kind),
            }
        )

    for s in analysis.services:
        rows["Service"].append(
            {
                "id": _node_id("Service", s.qualified_name, run_id),
                "analysis_run_id": run_id,
                "qualified_name": s.qualified_name,
                "name": s.name,
                "service_kind": s.service_kind.value,
            }
        )

    for ep in analysis.endpoints:
        ep_key = f"{ep.http_method}:{ep.path}"
        rows["Endpoint"].append(
            {
                "id": _node_id("Endpoint", ep_key, run_id),
                "analysis_run_id": run_id,
                "http_method": ep.http_method,
                "path": ep.path,
                "handler": ep.handler_qualified_name,
                "framework": ep.framework,
            }
        )

    for db in analysis.database_references:
        db_key = f"{db.target_entity}:{db.operation.value}"
        rows["DatabaseEntity"].append(
            {
                "id": _node_id("DatabaseEntity", db_key, run_id),
                "analysis_run_id": run_id,
                "target_entity": db.target_entity,
                "operation": db.operation.value,
                "referencing_symbol": db.referencing_symbol,
            }
        )

    for cfg in analysis.configurations:
        cfg_key = f"{cfg.key_name}:{cfg.referencing_symbol}"
        rows["ConfigSetting"].append(
            {
                "id": _node_id("ConfigSetting", cfg_key, run_id),
                "analysis_run_id": run_id,
                "key_name": cfg.key_name,
                "access_kind": cfg.access_kind.value,
                "referencing_symbol": cfg.referencing_symbol,
            }
        )

    for t in analysis.tests:
        rows["TestUnit"].append(
            {
                "id": _node_id("TestUnit", t.test_qualified_name, run_id),
                "analysis_run_id": run_id,
                "test_name": t.test_name,
                "test_qualified_name": t.test_qualified_name,
                "framework": t.framework,
                "target_symbol": t.target_symbol or "",
            }
        )

    for dep in analysis.dependencies:
        rows["ExternalPackage"].append(
            {
                "id": _node_id("ExternalPackage", dep.package_name, run_id),
                "analysis_run_id": run_id,
                "package_name": dep.package_name,
                "version_spec": dep.version_spec or "",
                "manifest_path": dep.manifest_path,
            }
        )

    for doc in analysis.documentation:
        rows["DocArtifact"].append(
            {
                "id": _node_id("DocArtifact", doc.file_path, run_id),
                "analysis_run_id": run_id,
                "title": doc.title,
                "doc_type": doc.doc_type.value,
                "file_path": doc.file_path,
                "associated_symbol": doc.associated_symbol or "",
            }
        )

    return rows


# ---------------------------------------------------------------------------
# Relationship row builder
# ---------------------------------------------------------------------------

_ENTITY_KIND_TO_LABEL: dict[EntityKind, str] = {
    EntityKind.FILE: "File",
    EntityKind.MODULE: "Module",
    EntityKind.CLASS: "Class",
    EntityKind.FUNCTION: "Function",
    EntityKind.SERVICE: "Service",
    EntityKind.ENDPOINT: "Endpoint",
    EntityKind.CONFIG: "ConfigSetting",
    EntityKind.DATABASE: "DatabaseEntity",
    EntityKind.TEST: "TestUnit",
    EntityKind.DOCUMENTATION: "DocArtifact",
    EntityKind.DEPENDENCY: "ExternalPackage",
}


def _build_rel_rows(analysis: RepositoryAnalysis) -> list[dict[str, Any]]:
    """Build comprehensive relationship property dicts for batch MERGE."""
    run_id = str(analysis.run_id)
    rows: list[dict[str, Any]] = []

    # 1. Build fast lookup index for all projected nodes in this run
    node_id_lookup: dict[tuple[str, str], str] = {}
    name_lookup: dict[str, str] = {}

    root_id = _node_id("AnalysisRoot", str(analysis.run_id), run_id)
    node_id_lookup[("AnalysisRoot", str(analysis.run_id))] = root_id

    for m in analysis.modules:
        m_id = _node_id("Module", m.qualified_name, run_id)
        node_id_lookup[("Module", m.qualified_name)] = m_id
        name_lookup[m.qualified_name] = m_id

    for c in analysis.classes:
        c_id = _node_id("Class", c.qualified_name, run_id)
        node_id_lookup[("Class", c.qualified_name)] = c_id
        name_lookup[c.qualified_name] = c_id
        name_lookup[c.name] = c_id

    for fn in analysis.functions:
        fn_id = _node_id("Function", fn.qualified_name, run_id)
        node_id_lookup[("Function", fn.qualified_name)] = fn_id
        name_lookup[fn.qualified_name] = fn_id

    for s in analysis.services:
        s_id = _node_id("Service", s.qualified_name, run_id)
        node_id_lookup[("Service", s.qualified_name)] = s_id
        name_lookup[s.qualified_name] = s_id

    for ep in analysis.endpoints:
        ep_key = f"{ep.http_method}:{ep.path}"
        ep_id = _node_id("Endpoint", ep_key, run_id)
        node_id_lookup[("Endpoint", ep_key)] = ep_id
        name_lookup[ep_key] = ep_id

    for dep in analysis.dependencies:
        dep_id = _node_id("ExternalPackage", dep.package_name, run_id)
        node_id_lookup[("ExternalPackage", dep.package_name)] = dep_id
        name_lookup[dep.package_name] = dep_id

    # 2. Add structural containment edges to connect the entire architecture hierarchy
    # Module -> Class (DEFINES)
    for c in analysis.classes:
        if c.module_name in name_lookup:
            rows.append({
                "rel_type": "DEFINES",
                "source_id": name_lookup[c.module_name],
                "target_id": _node_id("Class", c.qualified_name, run_id),
                "evidence_file_path": c.location.file_path,
                "evidence_start_line": c.location.start_line,
                "analysis_run_id": run_id,
            })

    # Module/Class -> Function (DEFINES)
    for fn in analysis.functions:
        fn_id = _node_id("Function", fn.qualified_name, run_id)
        if fn.enclosing_class and fn.enclosing_class in name_lookup:
            rows.append({
                "rel_type": "DEFINES",
                "source_id": name_lookup[fn.enclosing_class],
                "target_id": fn_id,
                "evidence_file_path": getattr(fn.location, "file_path", "") if hasattr(fn, "location") else "",
                "evidence_start_line": getattr(fn.location, "start_line", 1) if hasattr(fn, "location") else 1,
                "analysis_run_id": run_id,
            })
        else:
            mod_name = fn.qualified_name.rsplit(".", 1)[0] if "." in fn.qualified_name else ""
            if mod_name in name_lookup:
                rows.append({
                    "rel_type": "DEFINES",
                    "source_id": name_lookup[mod_name],
                    "target_id": fn_id,
                    "evidence_file_path": getattr(fn.location, "file_path", "") if hasattr(fn, "location") else "",
                    "evidence_start_line": getattr(fn.location, "start_line", 1) if hasattr(fn, "location") else 1,
                    "analysis_run_id": run_id,
                })

    # Endpoint -> Handler (EXPOSES)
    for ep in analysis.endpoints:
        ep_key = f"{ep.http_method}:{ep.path}"
        if ep.handler_qualified_name and ep.handler_qualified_name in name_lookup:
            rows.append({
                "rel_type": "EXPOSES",
                "source_id": _node_id("Endpoint", ep_key, run_id),
                "target_id": name_lookup[ep.handler_qualified_name],
                "evidence_file_path": "",
                "evidence_start_line": 1,
                "analysis_run_id": run_id,
            })

    # 3. Add all static AST relationships (CALLS, IMPORTS, EXTENDS, DEPENDS_ON, etc.)
    for rel in analysis.relationships:
        src_label = _ENTITY_KIND_TO_LABEL.get(rel.source_type, "Unknown")
        tgt_label = _ENTITY_KIND_TO_LABEL.get(rel.target_type, "Unknown")

        src_id = node_id_lookup.get((src_label, rel.source_identifier)) or name_lookup.get(rel.source_identifier) or _node_id(src_label, rel.source_identifier, run_id)
        tgt_id = node_id_lookup.get((tgt_label, rel.target_identifier)) or name_lookup.get(rel.target_identifier) or _node_id(tgt_label, rel.target_identifier, run_id)

        rows.append(
            {
                "rel_type": rel.relationship_type.value,
                "source_id": src_id,
                "target_id": tgt_id,
                "evidence_file_path": rel.evidence_location.file_path,
                "evidence_start_line": rel.evidence_location.start_line,
                "analysis_run_id": run_id,
            }
        )

    return rows


# ---------------------------------------------------------------------------
# Cypher query templates
# ---------------------------------------------------------------------------

_MERGE_NODE_QUERY_TEMPLATE = """
UNWIND $rows AS row
MERGE (n:{label} {{id: row.id}})
SET n += row
"""

# For relationships we cannot parameterise the relationship type in MERGE,
# so we dispatch one query per relationship type.
_MERGE_REL_QUERY_TEMPLATE = """
UNWIND $rows AS row
MATCH (src {{id: row.source_id}})
MATCH (tgt {{id: row.target_id}})
MERGE (src)-[r:{rel_type} {{analysis_run_id: row.analysis_run_id,
                             evidence_file_path: row.evidence_file_path,
                             evidence_start_line: row.evidence_start_line}}]->(tgt)
"""

_CLEAR_GRAPH_QUERY = """
MATCH (n {analysis_run_id: $run_id})
DETACH DELETE n
RETURN count(n) AS deleted
"""


# ---------------------------------------------------------------------------
# Main builder class
# ---------------------------------------------------------------------------


class Neo4jGraphBuilder:
    """Encapsulates all Cypher write logic for projecting a RepositoryAnalysis into Neo4j.

    This class is stateless — it holds no driver reference itself.
    The driver is passed into each method call, making it easily testable.
    """

    async def ensure_constraints(self, driver: AsyncDriver) -> None:
        """Create Neo4j uniqueness constraints if they do not already exist.

        Safe to call multiple times (uses IF NOT EXISTS).
        """
        async with driver.session() as session:
            for query in _CONSTRAINT_QUERIES:
                try:
                    await session.run(query)
                except Exception as exc:
                    logger.warning(
                        "Constraint creation skipped (may already exist)",
                        query=query[:60],
                        error=str(exc),
                    )
        logger.info("Neo4j constraints ensured")

    async def build_graph(
        self, driver: AsyncDriver, analysis: RepositoryAnalysis
    ) -> tuple[int, int]:
        """Project a complete RepositoryAnalysis into Neo4j.

        All writes use MERGE for idempotency. Safe to call multiple times for the same run.

        Args:
            driver: Neo4j AsyncDriver instance.
            analysis: Complete RepositoryAnalysis domain aggregate from F02.

        Returns:
            Tuple of (total_nodes_merged, total_relationships_merged).
        """
        run_id = str(analysis.run_id)
        logger.info("Starting Neo4j graph build", run_id=run_id)

        node_rows = _build_node_rows(analysis)
        rel_rows = _build_rel_rows(analysis)

        total_nodes = 0
        total_rels = 0

        # --- Write nodes ---
        async with driver.session() as session:
            for label, rows in node_rows.items():
                if not rows:
                    continue
                query = _MERGE_NODE_QUERY_TEMPLATE.format(label=label)
                for batch_start in range(0, len(rows), _BATCH_SIZE):
                    batch = rows[batch_start : batch_start + _BATCH_SIZE]
                    await session.run(query, rows=batch)
                    total_nodes += len(batch)
                logger.debug("Merged nodes", label=label, count=len(rows))

        # --- Write relationships (grouped by type) ---
        from collections import defaultdict

        rels_by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rel_rows:
            rels_by_type[row["rel_type"]].append(row)

        async with driver.session() as session:
            for rel_type, rows in rels_by_type.items():
                query = _MERGE_REL_QUERY_TEMPLATE.format(rel_type=rel_type)
                for batch_start in range(0, len(rows), _BATCH_SIZE):
                    batch = rows[batch_start : batch_start + _BATCH_SIZE]
                    await session.run(query, rows=batch)
                    total_rels += len(batch)
                logger.debug("Merged relationships", rel_type=rel_type, count=len(rows))

        logger.info(
            "Neo4j graph build complete",
            run_id=run_id,
            total_nodes=total_nodes,
            total_rels=total_rels,
        )
        return total_nodes, total_rels

    async def clear_graph(self, driver: AsyncDriver, analysis_run_id: str) -> int:
        """Delete all nodes (and their relationships) scoped to the given analysis_run_id.

        Args:
            driver: Neo4j AsyncDriver instance.
            analysis_run_id: UUID string of the analysis run to clear.

        Returns:
            Number of nodes deleted.
        """
        async with driver.session() as session:
            result = await session.run(_CLEAR_GRAPH_QUERY, run_id=analysis_run_id)
            record = await result.single()
            deleted = record["deleted"] if record else 0
            logger.info(
                "Cleared graph nodes for run",
                analysis_run_id=analysis_run_id,
                deleted=deleted,
            )
            return int(deleted)

    def build_node_rows(self, analysis: RepositoryAnalysis) -> dict[str, list[dict[str, Any]]]:
        """Public accessor for node rows — used in tests."""
        return _build_node_rows(analysis)

    def build_rel_rows(self, analysis: RepositoryAnalysis) -> list[dict[str, Any]]:
        """Public accessor for relationship rows — used in tests."""
        return _build_rel_rows(analysis)

    @staticmethod
    def node_id(label: str, key: str, run_id: str) -> str:
        """Public accessor for node ID generation — used in tests."""
        return _node_id(label, key, run_id)
