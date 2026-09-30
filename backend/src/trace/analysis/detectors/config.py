"""Configuration and settings reference detector."""

import ast
from dataclasses import dataclass, field
from pathlib import Path
from trace.domain.analysis import (
    AnalysisRelationship,
    Class,
    ConfigAccessKind,
    ConfigurationReference,
    EntityKind,
    Function,
    Module,
    RelationshipKind,
    SourceLocation,
)
from typing import Any


@dataclass(frozen=True)
class ConfigDetectionResult:
    configurations: tuple[ConfigurationReference, ...] = field(default_factory=tuple)
    relationships: tuple[AnalysisRelationship, ...] = field(default_factory=tuple)


class ConfigDetector:
    """Statically detects environment variables, config lookups, and Pydantic settings."""

    def detect(
        self,
        working_tree: Path,
        scan_result: Any,
        parsed_trees: list[tuple[str, Path, ast.AST]],
        modules: tuple[Module, ...],
        classes: tuple[Class, ...],
        functions: tuple[Function, ...],
    ) -> Any:
        configs: list[ConfigurationReference] = []
        relationships: list[AnalysisRelationship] = []

        # 1. Pydantic Settings classes
        for cls in classes:
            is_settings = (
                cls.name.endswith("Settings")
                or "Settings" in cls.parent_classes
                or "BaseSettings" in cls.parent_classes
                or "BaseModel" in cls.parent_classes
            )
            if is_settings:
                # Find the class AST node to inspect fields
                for rel_path, _, tree in parsed_trees:
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ClassDef) and node.name == cls.name:
                            for item in node.body:
                                # Annotated fields or assignments: e.g. database_url: str = ...
                                if isinstance(item, ast.AnnAssign) and isinstance(
                                    item.target, ast.Name
                                ):
                                    key_name = item.target.id
                                    loc = SourceLocation(
                                        file_path=rel_path,
                                        start_line=item.lineno,
                                        end_line=getattr(item, "end_lineno", item.lineno),
                                    )
                                    ref = ConfigurationReference(
                                        key_name=key_name,
                                        referencing_symbol=cls.qualified_name,
                                        access_kind=ConfigAccessKind.READ,
                                        location=loc,
                                    )
                                    configs.append(ref)
                                    relationships.append(
                                        AnalysisRelationship(
                                            source_type=EntityKind.CLASS,
                                            source_identifier=cls.qualified_name,
                                            relationship_type=RelationshipKind.CONFIGURED_BY,
                                            target_type=EntityKind.CONFIG,
                                            target_identifier=key_name,
                                            evidence_location=loc,
                                        )
                                    )

        # 2. os.environ / os.getenv AST usages
        for rel_path, _, tree in parsed_trees:
            for node in ast.walk(tree):
                # Call to os.getenv("KEY", ...)
                if isinstance(node, ast.Call):
                    callee = ast.unparse(node.func)
                    if callee in {"os.getenv", "getenv", "os.environ.get"} and node.args:
                        if isinstance(node.args[0], ast.Constant) and isinstance(
                            node.args[0].value, str
                        ):
                            key_name = node.args[0].value
                            loc = SourceLocation(
                                file_path=rel_path,
                                start_line=node.lineno,
                                end_line=getattr(node, "end_lineno", node.lineno),
                            )
                            ref = ConfigurationReference(
                                key_name=key_name,
                                referencing_symbol=rel_path,
                                access_kind=ConfigAccessKind.READ,
                                location=loc,
                            )
                            configs.append(ref)
                            relationships.append(
                                AnalysisRelationship(
                                    source_type=EntityKind.MODULE,
                                    source_identifier=rel_path,
                                    relationship_type=RelationshipKind.READS,
                                    target_type=EntityKind.CONFIG,
                                    target_identifier=key_name,
                                    evidence_location=loc,
                                )
                            )

                # Subscript os.environ["KEY"]
                elif isinstance(node, ast.Subscript):
                    val_str = ast.unparse(node.value)
                    if val_str == "os.environ" and isinstance(node.slice, ast.Constant):
                        key_name = str(node.slice.value)
                        loc = SourceLocation(
                            file_path=rel_path,
                            start_line=node.lineno,
                            end_line=getattr(node, "end_lineno", node.lineno),
                        )
                        ref = ConfigurationReference(
                            key_name=key_name,
                            referencing_symbol=rel_path,
                            access_kind=ConfigAccessKind.READ,
                            location=loc,
                        )
                        configs.append(ref)
                        relationships.append(
                            AnalysisRelationship(
                                source_type=EntityKind.MODULE,
                                source_identifier=rel_path,
                                relationship_type=RelationshipKind.READS,
                                target_type=EntityKind.CONFIG,
                                target_identifier=key_name,
                                evidence_location=loc,
                            )
                        )

        return ConfigDetectionResult(
            configurations=tuple(configs),
            relationships=tuple(relationships),
        )
