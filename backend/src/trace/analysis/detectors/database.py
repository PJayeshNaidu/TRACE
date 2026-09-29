"""Database model and query operation detector."""

import ast
from dataclasses import dataclass, field
from pathlib import Path
from trace.domain.analysis import (
    AnalysisRelationship,
    Class,
    DatabaseOperationKind,
    DatabaseReference,
    EntityKind,
    Function,
    Module,
    RelationshipKind,
    SourceLocation,
)
from typing import Any


@dataclass(frozen=True)
class DatabaseDetectionResult:
    database_references: tuple[DatabaseReference, ...] = field(default_factory=tuple)
    relationships: tuple[AnalysisRelationship, ...] = field(default_factory=tuple)


class DatabaseDetector:
    """Statically detects SQLAlchemy declarative models, queries, and write operations."""

    def detect(
        self,
        working_tree: Path,
        scan_result: Any,
        parsed_trees: list[tuple[str, Path, ast.AST]],
        modules: tuple[Module, ...],
        classes: tuple[Class, ...],
        functions: tuple[Function, ...],
    ) -> Any:
        db_refs: list[DatabaseReference] = []
        relationships: list[AnalysisRelationship] = []

        # 1. Model Declarations
        for cls in classes:
            is_model = (
                any(
                    "Base" in base or "DeclarativeBase" in base or "Model" in base
                    for base in cls.parent_classes
                )
                or cls.name.endswith("Orm")
                or cls.name.endswith("Model")
            )

            # Check for __tablename__ attribute
            table_name: str | None = None
            for _rel_path, _, tree in parsed_trees:
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef) and node.name == cls.name:
                        for item in node.body:
                            if isinstance(item, ast.Assign):
                                for target in item.targets:
                                    if (
                                        isinstance(target, ast.Name)
                                        and target.id == "__tablename__"
                                    ):
                                        if isinstance(item.value, ast.Constant):
                                            table_name = str(item.value.value)

            if is_model or table_name:
                entity_name = table_name or cls.name
                ref = DatabaseReference(
                    target_entity=entity_name,
                    referencing_symbol=cls.qualified_name,
                    operation=DatabaseOperationKind.MODEL_DECLARATION,
                    location=cls.location,
                )
                db_refs.append(ref)
                relationships.append(
                    AnalysisRelationship(
                        source_type=EntityKind.CLASS,
                        source_identifier=cls.qualified_name,
                        relationship_type=RelationshipKind.WRITES,
                        target_type=EntityKind.DATABASE,
                        target_identifier=entity_name,
                        evidence_location=cls.location,
                    )
                )

        # 2. Query and Write Operations
        for rel_path, _, tree in parsed_trees:
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    callee = ast.unparse(node.func)
                    loc = SourceLocation(
                        file_path=rel_path,
                        start_line=node.lineno,
                        end_line=getattr(node, "end_lineno", node.lineno),
                    )

                    # Query patterns: session.execute, session.query, session.scalars
                    if any(q in callee for q in ("execute", "query", "scalars", "select")):
                        ref = DatabaseReference(
                            target_entity="database",
                            referencing_symbol=rel_path,
                            operation=DatabaseOperationKind.QUERY,
                            location=loc,
                        )
                        db_refs.append(ref)
                        relationships.append(
                            AnalysisRelationship(
                                source_type=EntityKind.MODULE,
                                source_identifier=rel_path,
                                relationship_type=RelationshipKind.READS,
                                target_type=EntityKind.DATABASE,
                                target_identifier="database",
                                evidence_location=loc,
                            )
                        )

                    # Write patterns: session.add, session.commit, session.delete
                    elif any(w in callee for w in ("add", "commit", "delete", "flush")):
                        ref = DatabaseReference(
                            target_entity="database",
                            referencing_symbol=rel_path,
                            operation=DatabaseOperationKind.WRITE,
                            location=loc,
                        )
                        db_refs.append(ref)
                        relationships.append(
                            AnalysisRelationship(
                                source_type=EntityKind.MODULE,
                                source_identifier=rel_path,
                                relationship_type=RelationshipKind.WRITES,
                                target_type=EntityKind.DATABASE,
                                target_identifier="database",
                                evidence_location=loc,
                            )
                        )

        return DatabaseDetectionResult(
            database_references=tuple(db_refs),
            relationships=tuple(relationships),
        )
