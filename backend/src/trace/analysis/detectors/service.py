"""Service component detector for domain and application services."""

import ast
from dataclasses import dataclass, field
from pathlib import Path
from trace.domain.analysis import (
    Class,
    Function,
    Module,
    Service,
    ServiceKind,
)
from typing import Any


@dataclass(frozen=True)
class ServiceDetectionResult:
    services: tuple[Service, ...] = field(default_factory=tuple)


class ServiceDetector:
    """Statically detects domain and application services."""

    def detect(
        self,
        working_tree: Path,
        scan_result: Any,
        parsed_trees: list[tuple[str, Path, ast.AST]],
        modules: tuple[Module, ...],
        classes: tuple[Class, ...],
        functions: tuple[Function, ...],
    ) -> Any:
        services: list[Service] = []

        for cls in classes:
            # Criteria: name ends with Service, or inherits from a *Service base class
            is_service = (
                cls.name.endswith("Service")
                or any("Service" in base for base in cls.parent_classes)
                or any("service" in d.name.lower() for d in cls.decorators)
            )

            if is_service:
                # Find public methods and __init__
                cls_methods = [
                    f.name
                    for f in functions
                    if f.enclosing_class == cls.name and f.module_name == cls.module_name
                ]
                svc = Service(
                    name=cls.name,
                    qualified_name=cls.qualified_name,
                    module_name=cls.module_name,
                    service_kind=ServiceKind.CLASS_SERVICE,
                    methods=tuple(cls_methods),
                    location=cls.location,
                )
                services.append(svc)

        return ServiceDetectionResult(services=tuple(services))
