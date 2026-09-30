"""Shared test fixture factories for F03 and beyond.

Provides factory functions that produce minimal, valid domain aggregates
for use in unit tests without requiring real file I/O or live services.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from trace.domain.analysis import (
    AnalysisRelationship,
    AnalyzedFile,
    Class,
    EntityKind,
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
    SourceLocation,
)


def make_minimal_repository_analysis(
    run_id: uuid.UUID | None = None,
    repository_id: uuid.UUID | None = None,
) -> RepositoryAnalysis:
    """Produce a minimal but structurally valid RepositoryAnalysis for tests.

    Contains one module, one class, two functions, one import, and one CALLS relationship
    to allow node and relationship projection tests to exercise real code paths.
    """
    run_id = run_id or uuid.uuid4()
    repository_id = repository_id or uuid.uuid4()
    now = datetime.now(UTC)

    loc = SourceLocation(file_path="trace/services/payment.py", start_line=1, end_line=10)

    module = Module(
        qualified_name="trace.services.payment",
        file_path="trace/services/payment.py",
        is_package=False,
        docstring="Payment service module.",
        location=loc,
    )

    cls = Class(
        name="PaymentService",
        qualified_name="trace.services.payment.PaymentService",
        module_name="trace.services.payment",
        parent_classes=(),
        decorators=(),
        docstring="Handles payment flows.",
        location=SourceLocation(file_path="trace/services/payment.py", start_line=5, end_line=30),
    )

    fn_process = Function(
        name="process_payment",
        qualified_name="trace.services.payment.PaymentService.process_payment",
        module_name="trace.services.payment",
        enclosing_class="trace.services.payment.PaymentService",
        kind=FunctionKind.ASYNC_METHOD,
        parameters=(ParameterDescriptor(name="self"), ParameterDescriptor(name="amount")),
        return_type="bool",
        decorators=(),
        docstring=None,
        location=SourceLocation(file_path="trace/services/payment.py", start_line=10, end_line=20),
    )

    fn_helper = Function(
        name="validate_amount",
        qualified_name="trace.services.payment.validate_amount",
        module_name="trace.services.payment",
        enclosing_class=None,
        kind=FunctionKind.FUNCTION,
        parameters=(ParameterDescriptor(name="amount"),),
        return_type="bool",
        decorators=(),
        docstring=None,
        location=SourceLocation(file_path="trace/services/payment.py", start_line=1, end_line=5),
    )

    imp = Import(
        source_module="trace.domain.analysis",
        imported_symbol="RepositoryAnalysis",
        alias=None,
        import_type=ImportKind.IMPORT_FROM,
        is_relative=False,
        is_external=False,
        location=loc,
    )

    rel = AnalysisRelationship(
        source_type=EntityKind.FUNCTION,
        source_identifier="trace.services.payment.PaymentService.process_payment",
        relationship_type=RelationshipKind.CALLS,
        target_type=EntityKind.FUNCTION,
        target_identifier="trace.services.payment.validate_amount",
        evidence_location=SourceLocation(
            file_path="trace/services/payment.py", start_line=12, end_line=12
        ),
    )

    file_obj = AnalyzedFile(
        path="trace/services/payment.py",
        file_type=FileKind.PYTHON,
        size_bytes=512,
        status=FileStatus.PARSED,
    )

    return RepositoryAnalysis(
        run_id=run_id,
        repository_id=repository_id,
        analyzed_at=now,
        files=(file_obj,),
        modules=(module,),
        classes=(cls,),
        functions=(fn_process, fn_helper),
        services=(),
        imports=(imp,),
        calls=(),
        endpoints=(),
        configurations=(),
        database_references=(),
        tests=(),
        documentation=(),
        dependencies=(),
        relationships=(rel,),
        diagnostics=(),
        summary={},
        resolved_revision="abc123",
        commit_hash="abc123",
    )
