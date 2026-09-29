"""External dependency manifest detector for pyproject.toml and requirements.txt."""

import ast
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from trace.domain.analysis import (
    AnalysisRelationship,
    Class,
    EntityKind,
    ExternalDependency,
    Function,
    Module,
    RelationshipKind,
    SourceLocation,
)
from typing import Any

# Regex to parse package name and version from requirements spec: e.g. "fastapi>=0.115.0"
DEP_SPEC_RE = re.compile(r"^([a-zA-Z0-9_\-\.]+)(.*)$")


@dataclass(frozen=True)
class DependencyDetectionResult:
    dependencies: tuple[ExternalDependency, ...] = field(default_factory=tuple)
    relationships: tuple[AnalysisRelationship, ...] = field(default_factory=tuple)


class DependencyDetector:
    """Statically parses dependency manifests and creates DEPENDS_ON relationships."""

    def _parse_spec(self, raw_dep: str, manifest_path: str) -> ExternalDependency | None:
        cleaned = raw_dep.strip()
        if not cleaned or cleaned.startswith("#") or cleaned.startswith("-"):
            return None

        # Remove environment markers (e.g. ; python_version > '3.8')
        if ";" in cleaned:
            cleaned = cleaned.split(";", 1)[0].strip()

        match = DEP_SPEC_RE.match(cleaned)
        if not match:
            return None

        pkg_name = match.group(1).strip()
        version_spec = match.group(2).strip() or None

        return ExternalDependency(
            package_name=pkg_name,
            version_spec=version_spec,
            manifest_path=manifest_path,
        )

    def detect(
        self,
        working_tree: Path,
        scan_result: Any,
        parsed_trees: list[tuple[str, Path, ast.AST]],
        modules: tuple[Module, ...],
        classes: tuple[Class, ...],
        functions: tuple[Function, ...],
    ) -> Any:
        deps: list[ExternalDependency] = []
        relationships: list[AnalysisRelationship] = []

        # 1. Inspect pyproject.toml
        pyproject_file = working_tree / "pyproject.toml"
        if pyproject_file.is_file():
            rel_manifest = "pyproject.toml"
            try:
                data = tomllib.loads(pyproject_file.read_text(encoding="utf-8"))
                # standard [project.dependencies]
                raw_deps = data.get("project", {}).get("dependencies", [])
                for d in raw_deps:
                    dep = self._parse_spec(str(d), rel_manifest)
                    if dep:
                        deps.append(dep)

                # [project.optional-dependencies]
                opt_deps = data.get("project", {}).get("optional-dependencies", {})
                for group_deps in opt_deps.values():
                    if isinstance(group_deps, list):
                        for d in group_deps:
                            dep = self._parse_spec(str(d), rel_manifest)
                            if dep:
                                deps.append(dep)

                # poetry [tool.poetry.dependencies]
                poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
                for pkg, spec in poetry_deps.items():
                    if pkg.lower() != "python":
                        version_str = str(spec) if isinstance(spec, str) else None
                        deps.append(
                            ExternalDependency(
                                package_name=pkg,
                                version_spec=version_str,
                                manifest_path=rel_manifest,
                            )
                        )
            except Exception:
                pass

        # 2. Inspect requirements*.txt
        for req_file in working_tree.glob("requirements*.txt"):
            if req_file.is_file():
                rel_manifest = req_file.relative_to(working_tree).as_posix()
                try:
                    for line in req_file.read_text(encoding="utf-8").splitlines():
                        dep = self._parse_spec(line, rel_manifest)
                        if dep:
                            deps.append(dep)
                except Exception:
                    pass

        # Create DEPENDS_ON relationships for root modules
        root_module_name = modules[0].qualified_name.split(".")[0] if modules else "repository"
        for dep in deps:
            relationships.append(
                AnalysisRelationship(
                    source_type=EntityKind.MODULE,
                    source_identifier=root_module_name,
                    relationship_type=RelationshipKind.DEPENDS_ON,
                    target_type=EntityKind.DEPENDENCY,
                    target_identifier=dep.package_name,
                    evidence_location=SourceLocation(
                        file_path=dep.manifest_path, start_line=1, end_line=1
                    ),
                )
            )

        return DependencyDetectionResult(
            dependencies=tuple(deps),
            relationships=tuple(relationships),
        )
