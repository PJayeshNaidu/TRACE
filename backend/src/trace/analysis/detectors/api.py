"""Web API endpoint detector for FastAPI and Flask routes."""

import ast
from dataclasses import dataclass, field
from pathlib import Path
from trace.domain.analysis import (
    AnalysisRelationship,
    APIEndpoint,
    Class,
    EntityKind,
    Function,
    Module,
    RelationshipKind,
)
from typing import Any

HTTP_METHODS = {"get", "post", "put", "delete", "patch", "options", "head"}


@dataclass(frozen=True)
class APIDetectionResult:
    endpoints: tuple[APIEndpoint, ...] = field(default_factory=tuple)
    relationships: tuple[AnalysisRelationship, ...] = field(default_factory=tuple)


class APIDetector:
    """Statically detects web API endpoints and creates EXPOSES relationships."""

    def detect(
        self,
        working_tree: Path,
        scan_result: Any,
        parsed_trees: list[tuple[str, Path, ast.AST]],
        modules: tuple[Module, ...],
        classes: tuple[Class, ...],
        functions: tuple[Function, ...],
    ) -> Any:
        endpoints: list[APIEndpoint] = []
        relationships: list[AnalysisRelationship] = []

        for fn in functions:
            for dec in fn.decorators:
                dec_name = dec.name.lower()
                http_method: str | None = None
                framework = "FastAPI"

                # FastAPI pattern: @app.<method> or @router.<method>
                if "." in dec_name:
                    caller, method = dec_name.split(".", 1)
                    if method in HTTP_METHODS:
                        http_method = method.upper()

                # Flask pattern: @app.route(..., methods=[...])
                if "route" in dec_name:
                    framework = "Flask"
                    http_method = "GET"  # default
                    for arg in dec.arguments:
                        if "methods=" in arg:
                            # Parse methods list
                            val = arg.split("methods=", 1)[1]
                            for m in HTTP_METHODS:
                                if m in val.lower():
                                    http_method = m.upper()
                                    break

                if http_method:
                    # Extract route path from decorator arguments
                    path = "/"
                    if dec.arguments:
                        raw_arg0 = dec.arguments[0]
                        # Strip quotes if string literal
                        path = raw_arg0.strip("\"'")

                    endpoint = APIEndpoint(
                        http_method=http_method,
                        path=path,
                        handler_qualified_name=fn.qualified_name,
                        framework=framework,
                        location=fn.location,
                    )
                    endpoints.append(endpoint)

                    relationships.append(
                        AnalysisRelationship(
                            source_type=EntityKind.FUNCTION,
                            source_identifier=fn.qualified_name,
                            relationship_type=RelationshipKind.EXPOSES,
                            target_type=EntityKind.ENDPOINT,
                            target_identifier=f"{http_method} {path}",
                            evidence_location=fn.location,
                        )
                    )

        return APIDetectionResult(
            endpoints=tuple(endpoints),
            relationships=tuple(relationships),
        )
