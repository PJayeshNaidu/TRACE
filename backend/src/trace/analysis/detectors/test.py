"""Test unit and tested-by relationship detector."""

import ast
from dataclasses import dataclass, field
from pathlib import Path
from trace.domain.analysis import (
    AnalysisRelationship,
    Class,
    EntityKind,
    Function,
    Module,
    RelationshipKind,
    TestReference,
)
from typing import Any


@dataclass(frozen=True)
class TestDetectionResult:
    tests: tuple[TestReference, ...] = field(default_factory=tuple)
    relationships: tuple[AnalysisRelationship, ...] = field(default_factory=tuple)


class TestDetector:
    """Statically detects test functions and synthesizes TESTED_BY relationships."""

    def detect(
        self,
        working_tree: Path,
        scan_result: Any,
        parsed_trees: list[tuple[str, Path, ast.AST]],
        modules: tuple[Module, ...],
        classes: tuple[Class, ...],
        functions: tuple[Function, ...],
    ) -> Any:
        tests: list[TestReference] = []
        relationships: list[AnalysisRelationship] = []

        # Map available classes/functions by simple name and qualname for matching targets
        known_symbols: dict[str, str] = {c.name: c.qualified_name for c in classes}
        for f in functions:
            known_symbols[f.name] = f.qualified_name

        for fn in functions:
            is_test_file = (
                "test" in fn.location.file_path.lower()
                or fn.location.file_path.startswith("tests/")
            )
            is_test_fn = fn.name.startswith("test_") or (
                fn.enclosing_class and fn.enclosing_class.startswith("Test")
            )

            if is_test_file and is_test_fn:
                # Infer target under test by inspecting calls/references in test function AST
                target_symbol: str | None = None
                target_qualname: str | None = None

                # Look for matching tree
                for rel_path, _, tree in parsed_trees:
                    if rel_path == fn.location.file_path:
                        for node in ast.walk(tree):
                            if (
                                isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
                                and node.name == fn.name
                            ):
                                for child in ast.walk(node):
                                    if isinstance(child, ast.Name):
                                        # Check if Name matches a known non-test class/function
                                        if child.id in known_symbols and not child.id.startswith(
                                            "test_"
                                        ):
                                            target_symbol = child.id
                                            target_qualname = known_symbols[child.id]
                                            break
                                if target_symbol:
                                    break

                test_ref = TestReference(
                    test_name=fn.name,
                    test_qualified_name=fn.qualified_name,
                    target_symbol=target_qualname or target_symbol,
                    framework="pytest",
                    location=fn.location,
                )
                tests.append(test_ref)

                if target_qualname:
                    relationships.append(
                        AnalysisRelationship(
                            source_type=EntityKind.CLASS
                            if target_symbol in {c.name for c in classes}
                            else EntityKind.FUNCTION,
                            source_identifier=target_qualname,
                            relationship_type=RelationshipKind.TESTED_BY,
                            target_type=EntityKind.TEST,
                            target_identifier=fn.qualified_name,
                            evidence_location=fn.location,
                        )
                    )

        return TestDetectionResult(
            tests=tuple(tests),
            relationships=tuple(relationships),
        )
