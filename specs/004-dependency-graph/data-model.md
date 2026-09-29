# Data Model: TRACE Phase 3A — F03: Dependency Graph

**Feature Branch**: `Dependency-Graph`  
**Date**: 2026-09-29  
**Spec Reference**: [spec.md](./spec.md)

---

## 1. Storage Architecture

F03 uses a **dual-tier storage model**:

1. **PostgreSQL** — tracks `GraphBuildRun` lifecycle (status, stats, timing, errors)  
2. **Neo4j** — stores the structural knowledge graph (nodes + edges scoped by `analysis_run_id`)

---

## 2. PostgreSQL: graph_build_runs Table

Tracks the status and outcome of each graph build attempt.

```
┌────────────────────────────────────────────────────────┐
│                    graph_build_runs                    │
├────────────────────────────────────────────────────────┤
│ id: UUID [PK]                                          │
│ analysis_run_id: UUID [FK -> analysis_runs.id, Idx]   │
│ repository_id: UUID [FK -> repositories.id, Idx]      │
│ status: String(20) [Idx]  ('PENDING'|'IN_PROGRESS'|   │
│                             'COMPLETED'|'FAILED')      │
│ nodes_created: Integer [Default: 0]                    │
│ relationships_created: Integer [Default: 0]            │
│ duration_ms: Float [Nullable]                          │
│ error_message: Text [Nullable]                         │
│ started_at: DateTime(UTC) [Nullable]                   │
│ completed_at: DateTime(UTC) [Nullable]                 │
│ created_at: DateTime(UTC)                              │
│ updated_at: DateTime(UTC)                              │
└────────────────────────────────────────────────────────┘
```

---

## 3. Neo4j Graph Schema

### 3.1 Node Labels & Properties

All nodes carry `analysis_run_id` as a scoping property. The compound `(label, analysis_run_id, primary_key)` tuple is always unique.

#### :AnalysisRoot
```cypher
(:AnalysisRoot {
  analysis_run_id: String,   // UUID
  repository_id:  String,   // UUID
  commit_hash:    String,
  analyzed_at:    String    // ISO datetime
})
```

#### :Module
```cypher
(:Module {
  id:             String,   // "{qualified_name}::{analysis_run_id}"
  analysis_run_id: String,
  qualified_name: String,
  file_path:      String,
  is_package:     Boolean,
  docstring:      String    // nullable
})
```

#### :Class
```cypher
(:Class {
  id:             String,
  analysis_run_id: String,
  qualified_name: String,
  name:           String,
  module_name:    String,
  parent_classes: [String], // list
  docstring:      String    // nullable
})
```

#### :Function
```cypher
(:Function {
  id:             String,
  analysis_run_id: String,
  qualified_name: String,
  name:           String,
  kind:           String,   // FunctionKind value
  enclosing_class: String,  // nullable
  return_type:    String,   // nullable
  is_async:       Boolean
})
```

#### :Service
```cypher
(:Service {
  id:             String,
  analysis_run_id: String,
  qualified_name: String,
  name:           String,
  service_kind:   String
})
```

#### :Endpoint
```cypher
(:Endpoint {
  id:             String,   // "{http_method}:{path}::{analysis_run_id}"
  analysis_run_id: String,
  http_method:    String,
  path:           String,
  handler:        String,   // handler_qualified_name
  framework:      String
})
```

#### :DatabaseEntity
```cypher
(:DatabaseEntity {
  id:             String,   // "{target_entity}::{analysis_run_id}"
  analysis_run_id: String,
  target_entity:  String,
  operation:      String,   // DatabaseOperationKind value
  referencing_symbol: String
})
```

#### :ConfigSetting
```cypher
(:ConfigSetting {
  id:             String,   // "{key_name}::{analysis_run_id}"
  analysis_run_id: String,
  key_name:       String,
  access_kind:    String,
  referencing_symbol: String
})
```

#### :TestUnit
```cypher
(:TestUnit {
  id:             String,   // "{test_qualified_name}::{analysis_run_id}"
  analysis_run_id: String,
  test_name:      String,
  test_qualified_name: String,
  framework:      String,
  target_symbol:  String    // nullable
})
```

#### :ExternalPackage
```cypher
(:ExternalPackage {
  id:             String,   // "{package_name}::{analysis_run_id}"
  analysis_run_id: String,
  package_name:   String,
  version_spec:   String,   // nullable
  manifest_path:  String
})
```

#### :DocArtifact
```cypher
(:DocArtifact {
  id:             String,   // "{file_path}::{analysis_run_id}"
  analysis_run_id: String,
  title:          String,
  doc_type:       String,   // DocumentationKind value
  file_path:      String,
  associated_symbol: String // nullable
})
```

---

### 3.2 Relationship Types & Properties

All relationships carry evidence metadata from F02's `AnalysisRelationship.evidence_location`.

```cypher
(source)-[:RELATIONSHIP_TYPE {
  evidence_file_path:  String,
  evidence_start_line: Integer,
  analysis_run_id:     String   // for edge scoping
}]->(target)
```

| Edge Type | Source Label | Target Label | Semantics |
|---|---|---|---|
| `IMPORTS` | `:Module` | `:Module`, `:Class`, `:Function` | Module imports symbol |
| `CALLS` | `:Function` | `:Function` | Function calls another function |
| `EXTENDS` | `:Class` | `:Class` | Class inherits from another |
| `DEPENDS_ON` | `:Module` | `:ExternalPackage` | Module uses external package |
| `EXPOSES` | `:Function` | `:Endpoint` | Handler function exposes HTTP endpoint |
| `READS` | `:Function` | `:DatabaseEntity`, `:ConfigSetting` | Function reads from DB/config |
| `WRITES` | `:Function` | `:DatabaseEntity`, `:ConfigSetting` | Function writes to DB/config |
| `TESTED_BY` | `:Function`, `:Class` | `:TestUnit` | Component is tested by a test |
| `DOCUMENTED_BY` | `:Class`, `:Function` | `:DocArtifact` | Component is documented |
| `CONFIGURED_BY` | `:Module`, `:Class` | `:ConfigSetting` | Component reads config at module level |

---

### 3.3 Uniqueness Constraints (Neo4j)

```cypher
CREATE CONSTRAINT module_id_unique IF NOT EXISTS
  FOR (n:Module) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT class_id_unique IF NOT EXISTS
  FOR (n:Class) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT function_id_unique IF NOT EXISTS
  FOR (n:Function) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT service_id_unique IF NOT EXISTS
  FOR (n:Service) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT endpoint_id_unique IF NOT EXISTS
  FOR (n:Endpoint) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT dbentity_id_unique IF NOT EXISTS
  FOR (n:DatabaseEntity) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT configsetting_id_unique IF NOT EXISTS
  FOR (n:ConfigSetting) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT testunit_id_unique IF NOT EXISTS
  FOR (n:TestUnit) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT extpkg_id_unique IF NOT EXISTS
  FOR (n:ExternalPackage) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT docartifact_id_unique IF NOT EXISTS
  FOR (n:DocArtifact) REQUIRE n.id IS UNIQUE;
```

---

## 4. Domain Models (Python)

### GraphBuildStatus
```python
class GraphBuildStatus(StrEnum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
```

### GraphBuildRun
```python
@dataclass(frozen=True)
class GraphBuildRun:
    id: UUID
    analysis_run_id: UUID
    repository_id: UUID
    status: GraphBuildStatus
    nodes_created: int
    relationships_created: int
    duration_ms: float | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
```

### GraphNode (read model for API responses)
```python
@dataclass(frozen=True)
class GraphNode:
    id: str
    label: str
    qualified_name: str
    analysis_run_id: str
    properties: dict[str, Any]
```

### GraphRelationship (read model for API responses)
```python
@dataclass(frozen=True)
class GraphRelationship:
    source_id: str
    source_label: str
    relationship_type: str
    target_id: str
    target_label: str
    evidence_file_path: str | None
    evidence_start_line: int | None
```
