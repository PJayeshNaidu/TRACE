"""Unit tests for F02 analysis domain models and value objects."""

from datetime import UTC, datetime
from trace.domain.analysis import (
    AnalysisDiagnostic,
    AnalysisRelationship,
    AnalyzedFile,
    APIEndpoint,
    Call,
    CallResolutionStatus,
    Class,
    ConfigAccessKind,
    ConfigurationReference,
    DatabaseOperationKind,
    DatabaseReference,
    DecoratorDescriptor,
    DiagnosticSeverity,
    DocumentationKind,
    DocumentationReference,
    EntityKind,
    ExternalDependency,
    FileKind,
    FileStatus,
    Function,
    FunctionKind,
    Import,
    ImportKind,
    Module,
    ParameterDescriptor,
    RelationshipKind,
    RepositoryAnalysis,
    Service,
    ServiceKind,
    SourceLocation,
    TestReference,
)
from uuid import uuid4

import pytest


def test_source_location_immutability():
    """Verify SourceLocation fields, immutability, and serialization."""
    loc = SourceLocation(
        file_path="app/main.py",
        start_line=10,
        end_line=20,
        start_column=1,
        end_column=15,
    )
    assert loc.file_path == "app/main.py"
    assert loc.start_line == 10
    assert loc.end_line == 20
    assert loc.to_dict()["file_path"] == "app/main.py"

    with pytest.raises(AttributeError):
        loc.start_line = 11  # type: ignore[misc]


def test_repository_analysis_aggregate():
    """Verify complete RepositoryAnalysis aggregate creation and to_dict()."""
    run_id = uuid4()
    repo_id = uuid4()
    now = datetime.now(UTC)
    loc = SourceLocation(file_path="app/main.py", start_line=1, end_line=10)

    analysis = RepositoryAnalysis(
        run_id=run_id,
        repository_id=repo_id,
        analyzed_at=now,
        resolved_revision="a" * 40,
        commit_hash="a" * 40,
        files=(
            AnalyzedFile(
                path="app/main.py",
                file_type=FileKind.PYTHON,
                size_bytes=100,
                status=FileStatus.PARSED,
            ),
        ),
        modules=(
            Module(
                qualified_name="app.main",
                file_path="app/main.py",
                is_package=False,
                docstring="Doc",
                location=loc,
            ),
        ),
        classes=(
            Class(
                name="MyClass",
                qualified_name="app.main.MyClass",
                module_name="app.main",
                parent_classes=("Base",),
                decorators=(),
                docstring=None,
                location=loc,
            ),
        ),
        functions=(
            Function(
                name="my_func",
                qualified_name="app.main.my_func",
                module_name="app.main",
                enclosing_class=None,
                kind=FunctionKind.FUNCTION,
                parameters=(ParameterDescriptor(name="x", type_annotation="int"),),
                return_type="str",
                decorators=(
                    DecoratorDescriptor(
                        name="decorator",
                        raw_expression="@decorator",
                        line_number=1,
                    ),
                ),
                docstring=None,
                location=loc,
            ),
        ),
        services=(
            Service(
                name="MyService",
                qualified_name="app.main.MyService",
                module_name="app.main",
                service_kind=ServiceKind.CLASS_SERVICE,
                methods=("ping",),
                location=loc,
            ),
        ),
        imports=(
            Import(
                source_module="app.main",
                imported_symbol="FastAPI",
                alias=None,
                import_type=ImportKind.IMPORT_FROM,
                is_relative=False,
                is_external=True,
                location=loc,
            ),
        ),
        calls=(
            Call(
                caller_qualified_name="app.main.my_func",
                callee_expression="print",
                resolved_target="builtins.print",
                resolution_status=CallResolutionStatus.RESOLVED_INTERNAL,
                location=loc,
            ),
        ),
        endpoints=(
            APIEndpoint(
                http_method="GET",
                path="/items",
                handler_qualified_name="app.main.my_func",
                framework="FastAPI",
                location=loc,
            ),
        ),
        configurations=(
            ConfigurationReference(
                key_name="DATABASE_URL",
                referencing_symbol="app.main.my_func",
                access_kind=ConfigAccessKind.READ,
                location=loc,
            ),
        ),
        database_references=(
            DatabaseReference(
                target_entity="items",
                referencing_symbol="app.main.my_func",
                operation=DatabaseOperationKind.QUERY,
                location=loc,
            ),
        ),
        tests=(
            TestReference(
                test_name="test_my_func",
                test_qualified_name="tests.test_main.test_my_func",
                target_symbol="app.main.my_func",
                framework="pytest",
                location=loc,
            ),
        ),
        documentation=(
            DocumentationReference(
                title="README.md",
                doc_type=DocumentationKind.MARKDOWN_FILE,
                file_path="README.md",
                associated_symbol=None,
                location=loc,
            ),
        ),
        dependencies=(
            ExternalDependency(
                package_name="fastapi",
                version_spec=">=0.115.0",
                manifest_path="pyproject.toml",
            ),
        ),
        relationships=(
            AnalysisRelationship(
                source_type=EntityKind.FUNCTION,
                source_identifier="app.main.my_func",
                relationship_type=RelationshipKind.EXPOSES,
                target_type=EntityKind.ENDPOINT,
                target_identifier="/items",
                evidence_location=loc,
            ),
        ),
        diagnostics=(
            AnalysisDiagnostic(
                file_path="app/main.py",
                severity=DiagnosticSeverity.INFO,
                code="PARSED_OK",
                message="Parsed successfully",
            ),
        ),
        summary={"total_files": 1, "python_files": 1},
    )

    d = analysis.to_dict()
    assert d["run_id"] == run_id
    assert d["repository_id"] == repo_id
    assert len(d["files"]) == 1
    assert len(d["services"]) == 1
    assert d["summary"]["total_files"] == 1
