# Contract: Downstream Consumption for Phase 3A (F03) & Phase 3B (F04)

**Feature Branch**: `003-repository-code-analyzer`  
**Date**: 2026-09-29  
**Spec Reference**: [spec.md](../spec.md)

---

## 1. Overview & Architectural Boundaries

F02 produces structured, deterministic code intelligence encapsulated in `RepositoryAnalysis` and persisted to both PostgreSQL (`analysis_runs`) and the artifact directory (`storage/artifacts/analyses/{run_id}.json`).

F02 explicitly **does NOT**:
- Create Neo4j nodes or edges (owned by **F03: Dependency Graph**).
- Diff commits or calculate semantic delta impacts (owned by **F04: Version / Change Analyzer**).

Below are the explicit contracts governing how F03 and F04 consume F02 outputs.

---

## 2. Phase 3A (F03: Dependency Graph) Ingestion Contract

F03 ingests the `RepositoryAnalysis` artifact produced by F02 and projects it directly into Neo4j graph nodes and relationships.

### 2.1 Entity to Neo4j Node Mapping

| F02 Domain Entity | Neo4j Node Label | Primary Cypher Key | Indexed Properties |
|---|---|---|---|
| `RepositoryAnalysis` | `:Repository` | `repository_id` | `repository_id`, `resolved_revision`, `commit_hash` |
| `Module` | `:Module` | `qualified_name` | `qualified_name`, `file_path`, `is_package` |
| `Class` | `:Class` | `qualified_name` | `qualified_name`, `name`, `module_name` |
| `Function` | `:Function` | `qualified_name` | `qualified_name`, `name`, `kind`, `return_type` |
| `Service` | `:Service` | `qualified_name` | `qualified_name`, `name`, `service_kind` |
| `APIEndpoint` | `:Endpoint` | `http_method` + `path` | `http_method`, `path`, `framework` |
| `DatabaseReference` | `:DatabaseEntity` | `target_entity` | `target_entity`, `operation` |
| `ConfigurationReference` | `:ConfigSetting` | `key_name` | `key_name`, `access_kind` |
| `TestReference` | `:TestUnit` | `test_qualified_name` | `test_qualified_name`, `framework` |
| `ExternalDependency` | `:ExternalPackage` | `package_name` | `package_name`, `version_spec` |
| `DocumentationReference` | `:DocArtifact` | `file_path` / `associated_symbol` | `file_path`, `doc_type` |

### 2.2 Relationship to Neo4j Cypher Edge Mapping

Each `AnalysisRelationship` record in F02 maps 1-to-1 to a directed Neo4j relationship:

```cypher
// Example Cypher projection executed by F03:
MATCH (source {qualified_name: $rel.source_identifier})
MATCH (target {qualified_name: $rel.target_identifier})
MERGE (source)-[r:CALLS {
    file_path: $rel.evidence_location.file_path,
    line: $rel.evidence_location.start_line
}]->(target)
```

| F02 `RelationshipKind` | Neo4j Edge Type | Cypher Semantics |
|---|---|---|
| `IMPORTS` | `[:IMPORTS]` | `(:Module)-[:IMPORTS]->(:Module \| :Class \| :Function)` |
| `CALLS` | `[:CALLS]` | `(:Function)-[:CALLS]->(:Function)` |
| `EXTENDS` | `[:EXTENDS]` | `(:Class)-[:EXTENDS]->(:Class)` |
| `EXPOSES` | `[:EXPOSES]` | `(:Function)-[:EXPOSES]->(:Endpoint)` |
| `READS` | `[:READS]` | `(:Function)-[:READS]->(:DatabaseEntity \| :ConfigSetting)` |
| `WRITES` | `[:WRITES]` | `(:Function)-[:WRITES]->(:DatabaseEntity \| :ConfigSetting)` |
| `TESTED_BY` | `[:TESTED_BY]` | `(:Function \| :Class)-[:TESTED_BY]->(:TestUnit)` |
| `DEPENDS_ON` | `[:DEPENDS_ON]` | `(:Module)-[:DEPENDS_ON]->(:ExternalPackage)` |
| `CONFIGURED_BY` | `[:CONFIGURED_BY]` | `(:Module \| :Class)-[:CONFIGURED_BY]->(:ConfigSetting)` |
| `DOCUMENTED_BY` | `[:DOCUMENTED_BY]` | `(:Class \| :Function)-[:DOCUMENTED_BY]->(:DocArtifact)` |

---

## 3. Phase 3B (F04: Version / Change Analyzer) Symbol Mapping Contract

F04 determines what changed between two repository commits (or working tree vs base commit). It maps line-based Git diff hunks onto F02's semantic symbol structure.

### 3.1 Mapping Algorithm: Git Diff to Code Symbol

1. **Git Diff Extraction**: F04 runs Git diff between commit $C_1$ and commit $C_2$, extracting modified files and affected line intervals:
   $$\text{Hunk} = (\text{file\_path}, \text{start\_line}, \text{line\_count})$$
2. **F02 Symbol Lookup**: F04 loads the F02 `RepositoryAnalysis` artifact for commit $C_1$ (base) and/or commit $C_2$ (head).
3. **SourceLocation Interval Intersection**:
   For each symbol $S$ (Function, Method, or Class) in `file_path`:
   $$\text{Affected if: } [\text{Hunk.start\_line}, \text{Hunk.end\_line}] \cap [S.\text{location.start\_line}, S.\text{location.end\_line}] \neq \emptyset$$
4. **Change Classification**:
   - If interval falls inside a method: Tag method $S$ as `MODIFIED`.
   - If symbol exists in $C_2$ but not $C_1$: Tag symbol as `ADDED`.
   - If symbol exists in $C_1$ but not $C_2$: Tag symbol as `REMOVED`.

### 3.2 Required F02 Guarantees for F04

To ensure F04 can execute accurate symbol mapping:
- **Exact Line Ranges**: Every `Function` and `Class` must have accurate `start_line` (including decorators/docstrings) and `end_line` matching the physical file.
- **Relative POSIX Paths**: All `SourceLocation.file_path` values must be normalized POSIX relative paths matching the relative paths output by Git diff (e.g. `trace/services/repository.py`).
- **Deterministic Qualified Names**: Identical code elements must yield the exact same `qualified_name` across analysis runs.
