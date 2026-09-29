"""Pure domain models for code intelligence, analysis results, and run lifecycle."""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class AnalysisStatus(StrEnum):
    """Lifecycle status of an analysis run."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class FileKind(StrEnum):
    """Categorization of a repository file."""

    PYTHON = "PYTHON"
    TEST = "TEST"
    CONFIG = "CONFIG"
    DOCUMENTATION = "DOCUMENTATION"
    DEPENDENCY = "DEPENDENCY"
    OTHER = "OTHER"


class FileStatus(StrEnum):
    """Processing status of an individual file."""

    PARSED = "PARSED"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"


class FunctionKind(StrEnum):
    """Kind of callable function or method."""

    FUNCTION = "FUNCTION"
    METHOD = "METHOD"
    CLASS_METHOD = "CLASS_METHOD"
    STATIC_METHOD = "STATIC_METHOD"
    ASYNC_FUNCTION = "ASYNC_FUNCTION"
    ASYNC_METHOD = "ASYNC_METHOD"


class ImportKind(StrEnum):
    """Kind of import statement."""

    IMPORT = "IMPORT"
    IMPORT_FROM = "IMPORT_FROM"


class CallResolutionStatus(StrEnum):
    """Static target resolution state for a call site."""

    RESOLVED_INTERNAL = "RESOLVED_INTERNAL"
    RESOLVED_EXTERNAL = "RESOLVED_EXTERNAL"
    UNRESOLVED_DYNAMIC = "UNRESOLVED_DYNAMIC"


class ConfigAccessKind(StrEnum):
    """Kind of configuration access."""

    READ = "READ"
    WRITE = "WRITE"


class DatabaseOperationKind(StrEnum):
    """Kind of database operation or declaration."""

    MODEL_DECLARATION = "MODEL_DECLARATION"
    QUERY = "QUERY"
    WRITE = "WRITE"


class DocumentationKind(StrEnum):
    """Type of documentation element."""

    INLINE_DOCSTRING = "INLINE_DOCSTRING"
    MARKDOWN_FILE = "MARKDOWN_FILE"


class ServiceKind(StrEnum):
    """Classification of a detected service component."""

    CLASS_SERVICE = "CLASS_SERVICE"
    FUNCTIONAL_SERVICE = "FUNCTIONAL_SERVICE"


class EntityKind(StrEnum):
    """Types of code intelligence entities in structural relationships."""

    FILE = "FILE"
    MODULE = "MODULE"
    CLASS = "CLASS"
    FUNCTION = "FUNCTION"
    SERVICE = "SERVICE"
    ENDPOINT = "ENDPOINT"
    CONFIG = "CONFIG"
    DATABASE = "DATABASE"
    TEST = "TEST"
    DOCUMENTATION = "DOCUMENTATION"
    DEPENDENCY = "DEPENDENCY"


class RelationshipKind(StrEnum):
    """Directed semantic relationship between entities."""

    IMPORTS = "IMPORTS"
    CALLS = "CALLS"
    EXTENDS = "EXTENDS"
    DEPENDS_ON = "DEPENDS_ON"
    EXPOSES = "EXPOSES"
    READS = "READS"
    WRITES = "WRITES"
    TESTED_BY = "TESTED_BY"
    DOCUMENTED_BY = "DOCUMENTED_BY"
    CONFIGURED_BY = "CONFIGURED_BY"


class DiagnosticSeverity(StrEnum):
    """Severity level of an analysis diagnostic."""

    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass(frozen=True)
class SourceLocation:
    """Precise source code coordinate within a repository file."""

    file_path: str  # Relative POSIX path from repository root
    start_line: int  # 1-indexed
    end_line: int  # 1-indexed
    start_column: int | None = None
    end_column: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "start_column": self.start_column,
            "end_column": self.end_column,
        }


@dataclass(frozen=True)
class DecoratorDescriptor:
    """Structured descriptor of a decorator invocation."""

    name: str  # e.g., "app.get", "property", "dataclass"
    raw_expression: str  # Complete source text of decorator
    line_number: int
    arguments: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParameterDescriptor:
    """Descriptor of a function/method formal parameter."""

    name: str
    type_annotation: str | None = None
    has_default: bool = False
    default_value: str | None = None


@dataclass(frozen=True)
class AnalyzedFile:
    """Discovered repository file and its processing disposition."""

    path: str  # Relative POSIX path
    file_type: FileKind
    size_bytes: int
    status: FileStatus
    is_generated: bool = False


@dataclass(frozen=True)
class Module:
    """Python module or package."""

    qualified_name: str  # e.g., "trace.domain.analysis"
    file_path: str
    is_package: bool
    docstring: str | None
    location: SourceLocation


@dataclass(frozen=True)
class Class:
    """Python class definition."""

    name: str
    qualified_name: str  # e.g., "trace.domain.analysis.RepositoryAnalysis"
    module_name: str
    parent_classes: tuple[str, ...]
    decorators: tuple[DecoratorDescriptor, ...]
    docstring: str | None
    location: SourceLocation


@dataclass(frozen=True)
class Function:
    """Python function or method definition."""

    name: str
    qualified_name: str  # e.g., "trace.services.analysis.AnalysisService.trigger"
    module_name: str
    enclosing_class: str | None
    kind: FunctionKind
    parameters: tuple[ParameterDescriptor, ...]
    return_type: str | None
    decorators: tuple[DecoratorDescriptor, ...]
    docstring: str | None
    location: SourceLocation


@dataclass(frozen=True)
class Service:
    """Business or domain service component."""

    name: str
    qualified_name: str
    module_name: str
    service_kind: ServiceKind
    methods: tuple[str, ...]
    location: SourceLocation


@dataclass(frozen=True)
class Import:
    """Import statement."""

    source_module: str
    imported_symbol: str
    alias: str | None
    import_type: ImportKind
    is_relative: bool
    is_external: bool
    location: SourceLocation


@dataclass(frozen=True)
class Call:
    """Function or method call site."""

    caller_qualified_name: str
    callee_expression: str
    resolved_target: str | None
    resolution_status: CallResolutionStatus
    location: SourceLocation


@dataclass(frozen=True)
class APIEndpoint:
    """Exposed HTTP API route."""

    http_method: str
    path: str
    handler_qualified_name: str
    framework: str
    location: SourceLocation


@dataclass(frozen=True)
class ConfigurationReference:
    """Configuration or environment setting usage."""

    key_name: str
    referencing_symbol: str
    access_kind: ConfigAccessKind
    location: SourceLocation


@dataclass(frozen=True)
class DatabaseReference:
    """Database entity declaration or query interaction."""

    target_entity: str
    referencing_symbol: str
    operation: DatabaseOperationKind
    location: SourceLocation


@dataclass(frozen=True)
class TestReference:
    """Test component and link to component under test."""

    __test__ = False

    test_name: str
    test_qualified_name: str
    target_symbol: str | None
    framework: str
    location: SourceLocation


@dataclass(frozen=True)
class DocumentationReference:
    """Inline docstring or documentation file reference."""

    title: str
    doc_type: DocumentationKind
    file_path: str
    associated_symbol: str | None
    location: SourceLocation


@dataclass(frozen=True)
class ExternalDependency:
    """External dependency declared in manifests."""

    package_name: str
    version_spec: str | None
    manifest_path: str


@dataclass(frozen=True)
class AnalysisRelationship:
    """Directed semantic relationship edge supported by source evidence."""

    source_type: EntityKind
    source_identifier: str
    relationship_type: RelationshipKind
    target_type: EntityKind
    target_identifier: str
    evidence_location: SourceLocation


@dataclass(frozen=True)
class AnalysisDiagnostic:
    """Diagnostic error, warning, or notice encountered during analysis."""

    file_path: str
    severity: DiagnosticSeverity
    code: str
    message: str
    line: int | None = None
    column: int | None = None


@dataclass(frozen=True)
class AnalysisRun:
    """Domain model of an analysis run lifecycle and summary metrics."""

    id: UUID
    repository_id: UUID
    project_id: UUID
    status: AnalysisStatus
    created_at: datetime
    updated_at: datetime
    target_ref: str | None = None
    resolved_revision: str | None = None
    commit_hash: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: float | None = None
    total_files: int = 0
    python_files: int = 0
    total_modules: int = 0
    total_classes: int = 0
    total_functions: int = 0
    total_relationships: int = 0
    total_diagnostics: int = 0
    error_message: str | None = None
    artifact_path: str | None = None


@dataclass(frozen=True)
class RepositoryAnalysis:
    """Root aggregate containing the complete static code intelligence of a repository."""

    run_id: UUID
    repository_id: UUID
    analyzed_at: datetime
    files: tuple[AnalyzedFile, ...]
    modules: tuple[Module, ...]
    classes: tuple[Class, ...]
    functions: tuple[Function, ...]
    services: tuple[Service, ...]
    imports: tuple[Import, ...]
    calls: tuple[Call, ...]
    endpoints: tuple[APIEndpoint, ...]
    configurations: tuple[ConfigurationReference, ...]
    database_references: tuple[DatabaseReference, ...]
    tests: tuple[TestReference, ...]
    documentation: tuple[DocumentationReference, ...]
    dependencies: tuple[ExternalDependency, ...]
    relationships: tuple[AnalysisRelationship, ...]
    diagnostics: tuple[AnalysisDiagnostic, ...]
    summary: dict[str, int | float] = field(default_factory=dict)
    resolved_revision: str | None = None
    commit_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize complete aggregate to a JSON-compatible dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RepositoryAnalysis":
        """Deserialize dictionary back to a RepositoryAnalysis domain aggregate."""
        analyzed_at = data["analyzed_at"]
        if isinstance(analyzed_at, str):
            analyzed_at = datetime.fromisoformat(analyzed_at)

        run_id = data["run_id"]
        if isinstance(run_id, str):
            run_id = UUID(run_id)

        repo_id = data["repository_id"]
        if isinstance(repo_id, str):
            repo_id = UUID(repo_id)

        files = tuple(
            AnalyzedFile(
                path=f["path"],
                file_type=FileKind(f["file_type"]),
                size_bytes=f["size_bytes"],
                status=FileStatus(f.get("status", FileStatus.PARSED)),
                is_generated=f.get("is_generated", False),
            )
            for f in data.get("files", [])
        )

        modules = tuple(
            Module(
                qualified_name=m["qualified_name"],
                file_path=m["file_path"],
                is_package=m["is_package"],
                docstring=m.get("docstring"),
                location=SourceLocation(**m["location"]),
            )
            for m in data.get("modules", [])
        )

        classes = tuple(
            Class(
                name=c["name"],
                qualified_name=c["qualified_name"],
                module_name=c["module_name"],
                parent_classes=tuple(c.get("parent_classes", ())),
                decorators=tuple(
                    DecoratorDescriptor(
                        name=d["name"],
                        raw_expression=d.get("raw_expression", d["name"]),
                        line_number=d.get("line_number", 0),
                        arguments=tuple(d.get("arguments", ())),
                    )
                    for d in c.get("decorators", ())
                ),
                docstring=c.get("docstring"),
                location=SourceLocation(**c["location"]),
            )
            for c in data.get("classes", [])
        )

        functions = tuple(
            Function(
                name=fn["name"],
                qualified_name=fn["qualified_name"],
                module_name=fn["module_name"],
                enclosing_class=fn.get("enclosing_class"),
                kind=FunctionKind(fn["kind"]),
                parameters=tuple(
                    ParameterDescriptor(
                        name=p["name"],
                        type_annotation=p.get("type_annotation"),
                        default_value=p.get("default_value"),
                    )
                    for p in fn.get("parameters", ())
                ),
                return_type=fn.get("return_type"),
                decorators=tuple(
                    DecoratorDescriptor(
                        name=d["name"],
                        raw_expression=d.get("raw_expression", d["name"]),
                        line_number=d.get("line_number", 0),
                        arguments=tuple(d.get("arguments", ())),
                    )
                    for d in fn.get("decorators", ())
                ),
                docstring=fn.get("docstring"),
                location=SourceLocation(**fn["location"]),
            )
            for fn in data.get("functions", [])
        )

        services = tuple(
            Service(
                name=s["name"],
                qualified_name=s["qualified_name"],
                module_name=s["module_name"],
                service_kind=ServiceKind(s["service_kind"]),
                methods=tuple(s.get("methods", ())),
                location=SourceLocation(**s["location"]),
            )
            for s in data.get("services", [])
        )

        imports = tuple(
            Import(
                source_module=i["source_module"],
                imported_symbol=i["imported_symbol"],
                alias=i.get("alias"),
                import_type=ImportKind(i["import_type"]),
                is_relative=i.get("is_relative", False),
                is_external=i.get("is_external", False),
                location=SourceLocation(**i["location"]),
            )
            for i in data.get("imports", [])
        )

        calls = tuple(
            Call(
                caller_qualified_name=c["caller_qualified_name"],
                callee_expression=c["callee_expression"],
                resolved_target=c.get("resolved_target"),
                resolution_status=CallResolutionStatus(c["resolution_status"]),
                location=SourceLocation(**c["location"]),
            )
            for c in data.get("calls", [])
        )

        endpoints = tuple(
            APIEndpoint(
                http_method=e["http_method"],
                path=e["path"],
                handler_qualified_name=e["handler_qualified_name"],
                framework=e["framework"],
                location=SourceLocation(**e["location"]),
            )
            for e in data.get("endpoints", [])
        )

        configurations = tuple(
            ConfigurationReference(
                key_name=cfg["key_name"],
                referencing_symbol=cfg["referencing_symbol"],
                access_kind=ConfigAccessKind(cfg["access_kind"]),
                location=SourceLocation(**cfg["location"]),
            )
            for cfg in data.get("configurations", [])
        )

        database_references = tuple(
            DatabaseReference(
                target_entity=db["target_entity"],
                referencing_symbol=db["referencing_symbol"],
                operation=DatabaseOperationKind(db["operation"]),
                location=SourceLocation(**db["location"]),
            )
            for db in data.get("database_references", [])
        )

        tests = tuple(
            TestReference(
                test_name=t["test_name"],
                test_qualified_name=t["test_qualified_name"],
                target_symbol=t.get("target_symbol"),
                framework=t["framework"],
                location=SourceLocation(**t["location"]),
            )
            for t in data.get("tests", [])
        )

        documentation = tuple(
            DocumentationReference(
                title=doc["title"],
                doc_type=DocumentationKind(doc["doc_type"]),
                file_path=doc["file_path"],
                associated_symbol=doc.get("associated_symbol"),
                location=SourceLocation(**doc["location"]),
            )
            for doc in data.get("documentation", [])
        )

        dependencies = tuple(
            ExternalDependency(
                package_name=dep["package_name"],
                version_spec=dep.get("version_spec"),
                manifest_path=dep["manifest_path"],
            )
            for dep in data.get("dependencies", [])
        )

        relationships = tuple(
            AnalysisRelationship(
                source_type=EntityKind(r["source_type"]),
                source_identifier=r["source_identifier"],
                relationship_type=RelationshipKind(r["relationship_type"]),
                target_type=EntityKind(r["target_type"]),
                target_identifier=r["target_identifier"],
                evidence_location=SourceLocation(**r["evidence_location"]),
            )
            for r in data.get("relationships", [])
        )

        diagnostics = tuple(
            AnalysisDiagnostic(
                file_path=d["file_path"],
                severity=DiagnosticSeverity(d["severity"]),
                code=d["code"],
                message=d["message"],
                line=d.get("line"),
                column=d.get("column"),
            )
            for d in data.get("diagnostics", [])
        )

        return cls(
            run_id=run_id,
            repository_id=repo_id,
            analyzed_at=analyzed_at,
            files=files,
            modules=modules,
            classes=classes,
            functions=functions,
            services=services,
            imports=imports,
            calls=calls,
            endpoints=endpoints,
            configurations=configurations,
            database_references=database_references,
            tests=tests,
            documentation=documentation,
            dependencies=dependencies,
            relationships=relationships,
            diagnostics=diagnostics,
            summary=data.get("summary", {}),
            resolved_revision=data.get("resolved_revision"),
            commit_hash=data.get("commit_hash"),
        )
