# Data Model: TRACE Phase 3B — F04: Version / Change Analyzer

**Feature Branch**: `Version-Change-Analyser`  
**Date**: 2026-09-29  
**Spec Reference**: [spec.md](spec.md)

---

## 1. Domain Entities & Value Objects

### 1.1 `FileChangeType` (Enum)
- `ADDED`: New file introduced in `target_ref`.
- `MODIFIED`: Existing file changed.
- `DELETED`: File removed in `target_ref`.
- `RENAMED`: File moved or renamed.

### 1.2 `SymbolChangeKind` (Enum)
- `ADDED`: Symbol introduced in target revision.
- `MODIFIED`: Symbol implementation or signature changed.
- `DELETED`: Symbol removed in target revision.
- `RENAMED`: Symbol renamed.

### 1.3 `DiffHunk` (Value Object)
```python
@dataclass(frozen=True)
class DiffHunk:
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    header: str
```

### 1.4 `FileDiff` (Value Object)
```python
@dataclass(frozen=True)
class FileDiff:
    old_path: str | None
    new_path: str | None
    change_type: FileChangeType
    insertions: int
    deletions: int
    hunks: list[DiffHunk]
```

### 1.5 `SymbolDiff` (Value Object)
```python
@dataclass(frozen=True)
class SymbolDiff:
    symbol_id: str
    qualified_name: str
    kind: str  # "function", "class", "endpoint", "module"
    file_path: str
    change_kind: SymbolChangeKind
    is_breaking: bool
    breaking_reason: str | None
    old_signature: str | None
    new_signature: str | None
```

### 1.6 `BlastRadiusItem` (Value Object)
```python
@dataclass(frozen=True)
class BlastRadiusItem:
    target_symbol_id: str
    affected_symbol_id: str
    affected_qualified_name: str
    affected_kind: str
    affected_file_path: str
    relationship_kind: str  # "CALLS", "EXTENDS", "DEPENDS_ON", "TESTED_BY"
    depth: int
```

### 1.7 `VersionComparison` (Domain Aggregate)
```python
@dataclass(frozen=True)
class VersionComparison:
    id: uuid.UUID
    repository_id: uuid.UUID
    base_ref: str
    target_ref: str
    base_commit_hash: str
    target_commit_hash: str
    created_at: datetime
    total_files_changed: int
    total_insertions: int
    total_deletions: int
    total_symbols_changed: int
    total_breaking_changes: int
    risk_level: str  # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    file_diffs: list[FileDiff]
    symbol_diffs: list[SymbolDiff]
    blast_radius: list[BlastRadiusItem]
    commit_messages: list[str]
```

---

## 2. Database Model: `version_comparisons`

```python
class VersionComparisonOrm(Base):
    __tablename__ = "version_comparisons"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repository_id = Column(UUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    base_ref = Column(String(255), nullable=False)
    target_ref = Column(String(255), nullable=False)
    base_commit_hash = Column(String(40), nullable=False)
    target_commit_hash = Column(String(40), nullable=False)
    risk_level = Column(String(20), nullable=False, default="LOW")
    total_files_changed = Column(Integer, nullable=False, default=0)
    total_symbols_changed = Column(Integer, nullable=False, default=0)
    total_breaking_changes = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=func.now())
    artifact_path = Column(Text, nullable=True)
```
