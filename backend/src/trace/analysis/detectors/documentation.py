"""Documentation reference detector for docstrings and markdown files."""

import ast
from dataclasses import dataclass, field
from pathlib import Path
from trace.domain.analysis import (
    AnalysisRelationship,
    Class,
    DocumentationKind,
    DocumentationReference,
    EntityKind,
    FileKind,
    Function,
    Module,
    RelationshipKind,
    SourceLocation,
)
from typing import Any


@dataclass(frozen=True)
class DocumentationDetectionResult:
    documentation: tuple[DocumentationReference, ...] = field(default_factory=tuple)
    relationships: tuple[AnalysisRelationship, ...] = field(default_factory=tuple)


class DocumentationDetector:
    """Statically detects docstrings and repository markdown documentation."""

    def detect(
        self,
        working_tree: Path,
        scan_result: Any,
        parsed_trees: list[tuple[str, Path, ast.AST]],
        modules: tuple[Module, ...],
        classes: tuple[Class, ...],
        functions: tuple[Function, ...],
    ) -> Any:
        docs: list[DocumentationReference] = []
        relationships: list[AnalysisRelationship] = []

        # 1. Module Docstrings
        for mod in modules:
            if mod.docstring:
                title = f"Module docstring: {mod.qualified_name}"
                doc_ref = DocumentationReference(
                    title=title,
                    doc_type=DocumentationKind.INLINE_DOCSTRING,
                    file_path=mod.file_path,
                    associated_symbol=mod.qualified_name,
                    location=mod.location,
                )
                docs.append(doc_ref)
                relationships.append(
                    AnalysisRelationship(
                        source_type=EntityKind.MODULE,
                        source_identifier=mod.qualified_name,
                        relationship_type=RelationshipKind.DOCUMENTED_BY,
                        target_type=EntityKind.DOCUMENTATION,
                        target_identifier=title,
                        evidence_location=mod.location,
                    )
                )

        # 2. Class Docstrings
        for cls in classes:
            if cls.docstring:
                title = f"Class docstring: {cls.qualified_name}"
                doc_ref = DocumentationReference(
                    title=title,
                    doc_type=DocumentationKind.INLINE_DOCSTRING,
                    file_path=cls.location.file_path,
                    associated_symbol=cls.qualified_name,
                    location=cls.location,
                )
                docs.append(doc_ref)
                relationships.append(
                    AnalysisRelationship(
                        source_type=EntityKind.CLASS,
                        source_identifier=cls.qualified_name,
                        relationship_type=RelationshipKind.DOCUMENTED_BY,
                        target_type=EntityKind.DOCUMENTATION,
                        target_identifier=title,
                        evidence_location=cls.location,
                    )
                )

        # 3. Function/Method Docstrings
        for fn in functions:
            if fn.docstring:
                title = f"Function docstring: {fn.qualified_name}"
                doc_ref = DocumentationReference(
                    title=title,
                    doc_type=DocumentationKind.INLINE_DOCSTRING,
                    file_path=fn.location.file_path,
                    associated_symbol=fn.qualified_name,
                    location=fn.location,
                )
                docs.append(doc_ref)
                relationships.append(
                    AnalysisRelationship(
                        source_type=EntityKind.FUNCTION,
                        source_identifier=fn.qualified_name,
                        relationship_type=RelationshipKind.DOCUMENTED_BY,
                        target_type=EntityKind.DOCUMENTATION,
                        target_identifier=title,
                        evidence_location=fn.location,
                    )
                )

        # 4. Markdown and Repository Documentation Files
        if hasattr(scan_result, "files"):
            for f in scan_result.files:
                if f.file_type == FileKind.DOCUMENTATION:
                    loc = SourceLocation(file_path=f.path, start_line=1, end_line=1)
                    doc_ref = DocumentationReference(
                        title=Path(f.path).name,
                        doc_type=DocumentationKind.MARKDOWN_FILE,
                        file_path=f.path,
                        associated_symbol=None,
                        location=loc,
                    )
                    docs.append(doc_ref)

        return DocumentationDetectionResult(
            documentation=tuple(docs),
            relationships=tuple(relationships),
        )
