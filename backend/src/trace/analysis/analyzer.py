"""Static code analyzer protocol and Python static code analyzer engine."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from trace.analysis.extractor import SymbolExtractor
from trace.analysis.parser import PythonAstParser
from trace.analysis.scanner import RepositoryScanner
from trace.domain.analysis import (
    AnalysisDiagnostic,
    AnalysisRelationship,
    AnalyzedFile,
    APIEndpoint,
    Call,
    Class,
    ConfigurationReference,
    DatabaseReference,
    DocumentationReference,
    ExternalDependency,
    Function,
    Import,
    Module,
    RepositoryAnalysis,
    Service,
    TestReference,
)
from typing import Any, Protocol, runtime_checkable
from uuid import UUID


@dataclass(frozen=True)
class AnalysisContext:
    """Contextual metadata and configuration passed to an analyzer."""

    run_id: UUID
    repository_id: UUID
    working_tree_path: Path
    target_ref: str | None = None
    resolved_revision: str | None = None
    commit_hash: str | None = None
    exclude_patterns: tuple[str, ...] = ()


@runtime_checkable
class CodeAnalyzer(Protocol):
    """Protocol for static code analysis engines in TRACE."""

    @property
    def supported_language(self) -> str:
        """The primary programming language supported by this analyzer (e.g. 'python')."""
        ...

    def analyze(self, context: AnalysisContext) -> RepositoryAnalysis:
        """Execute deterministic static analysis over the repository working tree.

        Args:
            context: Execution context containing working tree path and configuration.

        Returns:
            The complete, strongly typed RepositoryAnalysis domain aggregate.

        Raises:
            AnalysisExecutionError: If repository traversal cannot be performed.
        """
        ...


class PythonCodeAnalyzer:
    """Deterministic static code analyzer for Python repositories."""

    def __init__(
        self,
        scanner: RepositoryScanner | None = None,
        parser: PythonAstParser | None = None,
        extractor: SymbolExtractor | None = None,
        detectors: tuple[Any, ...] | None = None,
    ) -> None:
        self._scanner = scanner or RepositoryScanner()
        self._parser = parser or PythonAstParser()
        self._extractor = extractor or SymbolExtractor()
        if detectors is None:
            from trace.analysis.detectors import get_default_detectors

            self._detectors = get_default_detectors()
        else:
            self._detectors = detectors

    @property
    def supported_language(self) -> str:
        return "python"

    def analyze(self, context: AnalysisContext) -> RepositoryAnalysis:
        """Analyze a Python repository working tree deterministically."""
        working_tree = Path(context.working_tree_path).resolve()
        scan_result = self._scanner.scan(
            root_path=working_tree,
            exclude_patterns=context.exclude_patterns,
        )

        all_files: list[AnalyzedFile] = list(scan_result.files)
        all_modules: list[Module] = []
        all_classes: list[Class] = []
        all_functions: list[Function] = []
        all_services: list[Service] = []
        all_imports: list[Import] = []
        all_calls: list[Call] = []
        all_endpoints: list[APIEndpoint] = []
        all_configs: list[ConfigurationReference] = []
        all_db_refs: list[DatabaseReference] = []
        all_tests: list[TestReference] = []
        all_docs: list[DocumentationReference] = []
        all_dependencies: list[ExternalDependency] = []
        all_relationships: list[AnalysisRelationship] = []
        all_diagnostics: list[AnalysisDiagnostic] = []

        # Store parsed AST trees for detector passes: list of (rel_path, abs_path, ast_tree)
        parsed_trees: list[tuple[str, Path, Any]] = []

        # Parse each candidate Python file
        for py_path in scan_result.python_files:
            rel_path = py_path.relative_to(working_tree).as_posix()
            tree, diagnostic = self._parser.parse_file(py_path, rel_path=rel_path)

            if diagnostic is not None:
                all_diagnostics.append(diagnostic)

            if tree is not None:
                try:
                    total_lines = len(
                        py_path.read_text(encoding="utf-8", errors="replace").splitlines()
                    )
                except Exception:
                    total_lines = 1

                extracted = self._extractor.extract(
                    tree=tree,
                    file_path=rel_path,
                    source_root=scan_result.source_root,
                    total_lines=total_lines,
                )
                all_modules.append(extracted.module)
                all_classes.extend(extracted.classes)
                all_functions.extend(extracted.functions)
                all_imports.extend(extracted.imports)
                all_calls.extend(extracted.calls)
                all_relationships.extend(extracted.relationships)

                parsed_trees.append((rel_path, py_path, tree))

        # Run specialized pattern detectors (if registered)
        for detector in self._detectors:
            if hasattr(detector, "detect"):
                detector_result = detector.detect(
                    working_tree=working_tree,
                    scan_result=scan_result,
                    parsed_trees=parsed_trees,
                    modules=tuple(all_modules),
                    classes=tuple(all_classes),
                    functions=tuple(all_functions),
                )
                if hasattr(detector_result, "services"):
                    all_services.extend(detector_result.services)
                if hasattr(detector_result, "endpoints"):
                    all_endpoints.extend(detector_result.endpoints)
                if hasattr(detector_result, "configurations"):
                    all_configs.extend(detector_result.configurations)
                if hasattr(detector_result, "database_references"):
                    all_db_refs.extend(detector_result.database_references)
                if hasattr(detector_result, "tests"):
                    all_tests.extend(detector_result.tests)
                if hasattr(detector_result, "documentation"):
                    all_docs.extend(detector_result.documentation)
                if hasattr(detector_result, "dependencies"):
                    all_dependencies.extend(detector_result.dependencies)
                if hasattr(detector_result, "relationships"):
                    all_relationships.extend(detector_result.relationships)
                if hasattr(detector_result, "diagnostics"):
                    all_diagnostics.extend(detector_result.diagnostics)

        summary: dict[str, int | float] = {
            "total_files": len(all_files),
            "python_files": len(scan_result.python_files),
            "total_modules": len(all_modules),
            "total_classes": len(all_classes),
            "total_functions": len(all_functions),
            "total_services": len(all_services),
            "total_relationships": len(all_relationships),
            "total_diagnostics": len(all_diagnostics),
        }

        return RepositoryAnalysis(
            run_id=context.run_id,
            repository_id=context.repository_id,
            analyzed_at=datetime.now(UTC),
            resolved_revision=context.resolved_revision,
            commit_hash=context.commit_hash or context.resolved_revision,
            files=tuple(all_files),
            modules=tuple(all_modules),
            classes=tuple(all_classes),
            functions=tuple(all_functions),
            services=tuple(all_services),
            imports=tuple(all_imports),
            calls=tuple(all_calls),
            endpoints=tuple(all_endpoints),
            configurations=tuple(all_configs),
            database_references=tuple(all_db_refs),
            tests=tuple(all_tests),
            documentation=tuple(all_docs),
            dependencies=tuple(all_dependencies),
            relationships=tuple(all_relationships),
            diagnostics=tuple(all_diagnostics),
            summary=summary,
        )
