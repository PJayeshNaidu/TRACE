"""Repository analysis summary JSON builder and persistence adhering to test.json schema."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from trace.domain.analysis import (
    CallResolutionStatus,
    DatabaseOperationKind,
    FileKind,
    FunctionKind,
    RepositoryAnalysis,
)
from typing import Any
from uuid import UUID


def resolve_repo_analysis_dir(configured_dir: str | Path | None = None) -> Path:
    """Resolve the directory where repo_analysis summary JSON files are saved.

    Searches in configured_dir, CWD, CWD parent (project root when running in backend/),
    or the TRACE root directory.
    """
    if configured_dir:
        p = Path(configured_dir)
        if p.is_absolute():
            p.mkdir(parents=True, exist_ok=True)
            return p
        candidates = [
            Path.cwd() / p,
            Path.cwd().parent / p,
            Path(__file__).resolve().parents[4] / p,
        ]
        for c in candidates:
            if c.exists() and c.is_dir():
                return c
        target = candidates[1] if (Path.cwd() / "backend").exists() else candidates[0]
        target.mkdir(parents=True, exist_ok=True)
        return target

    candidates = [
        Path.cwd() / "repo_analysis",
        Path.cwd().parent / "repo_analysis",
        Path(__file__).resolve().parents[4] / "repo_analysis",
    ]
    for c in candidates:
        if c.exists() and c.is_dir():
            return c

    target = candidates[1] if (Path.cwd() / "backend").exists() else candidates[0]
    target.mkdir(parents=True, exist_ok=True)
    return target


def _sanitize_name(name: str) -> str:
    """Sanitize name to make safe for filenames and identifiers."""
    cleaned = re.sub(r"[^\w\-.]+", "-", name).strip("-")
    return cleaned or "unknown"


def format_summary_filename(repo_name: str, branch_name: str | None = None) -> str:
    """Generate summary filename in nameofrepo-branchname.json format."""
    safe_repo = _sanitize_name(repo_name)
    if branch_name:
        safe_branch = _sanitize_name(branch_name)
        return f"{safe_repo}-{safe_branch}.json"
    return f"{safe_repo}.json"


def _compute_file_hash(path: Path) -> str:
    """Compute SHA-256 hash of a file's content or fallback to hash of its string path."""
    if path.is_file():
        try:
            return hashlib.sha256(path.read_bytes()).hexdigest()
        except Exception:
            pass
    return hashlib.sha256(str(path).encode("utf-8")).hexdigest()


def _determine_callee_type(
    callee: str,
    resolution_status: CallResolutionStatus,
    known_methods: set[str],
) -> str:
    """Classify callee type as function, method, or external per test.json."""
    if resolution_status == CallResolutionStatus.RESOLVED_INTERNAL:
        if callee in known_methods or ("." in callee and not callee.startswith("self.")):
            return "method"
        return "function"
    elif resolution_status == CallResolutionStatus.RESOLVED_EXTERNAL:
        return "external"
    else:
        if "." in callee:
            return "method"
        return "function"


def _extract_version_control(
    wt_path: Path,
    branch: str,
    commit_hash: str,
    timestamp_str: str,
    default_branch: str,
) -> dict[str, Any]:
    """Build the version_control payload, probing git repository metadata if available."""
    commit_sha = commit_hash or "0000000000000000000000000000000000000000"
    short_sha = commit_sha[:7] if commit_sha else ""

    commits: list[dict[str, Any]] = []
    tags: list[dict[str, Any]] = []
    branches: list[dict[str, Any]] = []

    git_dir = wt_path / ".git"
    if git_dir.exists():
        try:
            proc = subprocess.run(
                [
                    "git",
                    "-C",
                    str(wt_path),
                    "log",
                    "-n",
                    "10",
                    "--format=%H|%h|%P|%s|%an|%cI",
                ],
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                for line in proc.stdout.strip().splitlines():
                    parts = line.split("|")
                    if len(parts) >= 6:
                        c_h, c_short, c_parents, c_msg, c_auth, c_time = (
                            parts[0],
                            parts[1],
                            parts[2],
                            parts[3],
                            parts[4],
                            parts[5],
                        )
                        parent_list = [p for p in c_parents.split() if p]
                        commits.append(
                            {
                                "commit_sha": c_h,
                                "short_sha": c_short,
                                "parent_commits": parent_list,
                                "message": c_msg,
                                "author": c_auth,
                                "timestamp": c_time,
                            }
                        )

            tag_proc = subprocess.run(
                [
                    "git",
                    "-C",
                    str(wt_path),
                    "tag",
                    "--list",
                    "--format=%(refname:short)|%(objectname)|%(creatordate:iso-strict)",
                ],
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
            )
            if tag_proc.returncode == 0 and tag_proc.stdout.strip():
                for tline in tag_proc.stdout.strip().splitlines():
                    tparts = tline.split("|")
                    if len(tparts) >= 2:
                        tags.append(
                            {
                                "name": tparts[0],
                                "commit_sha": tparts[1],
                                "created_at": (
                                    tparts[2]
                                    if len(tparts) > 2 and tparts[2]
                                    else timestamp_str
                                ),
                            }
                        )
        except Exception:
            pass

    # If commit_sha is unpopulated/zero but we discovered genuine git commits, use the HEAD commit
    if (not commit_sha or commit_sha == "0000000000000000000000000000000000000000") and commits:
        commit_sha = commits[0]["commit_sha"]
        short_sha = commits[0]["short_sha"]

    effective_branch = branch if (branch and branch != "string") else default_branch

    if not commits and commit_sha != "0000000000000000000000000000000000000000":
        commits.append(
            {
                "commit_sha": commit_sha,
                "short_sha": short_sha,
                "parent_commits": [],
                "message": f"Commit {short_sha}",
                "author": "TRACE",
                "timestamp": timestamp_str,
            }
        )

    branches.append(
        {
            "branch_id": f"branch:{effective_branch}",
            "name": effective_branch,
            "is_default": effective_branch == default_branch,
            "is_remote": False,
            "remote": None,
            "head_commit": commit_sha,
            "base_branch": None,
            "base_commit": None,
            "commits": commits,
        }
    )

    current_tag = tags[0]["name"] if tags else None

    return {
        "current_version": {
            "commit_sha": commit_sha,
            "branch": effective_branch,
            "tag": current_tag,
        },
        "branches": branches,
        "tags": tags,
    }


def build_repository_summary_payload(
    analysis_run_id: UUID,
    repository_id: UUID,
    status: str,
    started_at: datetime | None,
    completed_at: datetime | None,
    duration_ms: float | None,
    repo_name: str,
    repo_url: str,
    branch: str,
    commit_hash: str,
    working_tree_path: Path | str,
    artifact: RepositoryAnalysis,
    default_branch: str | None = None,
) -> dict[str, Any]:
    """Construct complete summary dictionary adhering strictly to updated test.json schema."""
    wt_path = Path(working_tree_path).resolve()
    effective_default_branch = default_branch or branch or "main"
    start_ts = (
        started_at.isoformat()
        if started_at
        else (completed_at.isoformat() if completed_at else datetime.now(UTC).isoformat())
    )
    comp_ts = (
        completed_at.isoformat()
        if completed_at
        else (started_at.isoformat() if started_at else datetime.now(UTC).isoformat())
    )
    final_duration = round(float(duration_ms), 2) if duration_ms is not None else 0.0

    # 1. analysis_run
    analysis_run_dict = {
        "analysis_run_id": str(analysis_run_id),
        "repository_id": str(repository_id),
        "status": str(status),
        "started_at": start_ts,
        "completed_at": comp_ts,
        "duration_ms": final_duration,
        "analyzer_version": "0.1.0",
    }

    # 2. repository
    repository_dict = {
        "repository_id": str(repository_id),
        "name": repo_name,
        "url": repo_url,
        "root_path": str(wt_path),
        "default_branch": effective_default_branch,
    }

    # 3. version_control
    version_control_dict = _extract_version_control(
        wt_path=wt_path,
        branch=branch,
        commit_hash=commit_hash,
        timestamp_str=comp_ts,
        default_branch=effective_default_branch,
    )

    # 4. files
    files_data: list[dict[str, Any]] = []
    for af in artifact.files:
        norm_path = af.path.replace("\\", "/")
        abs_f = wt_path / af.path
        f_lines = 0
        if abs_f.is_file():
            try:
                raw_text = abs_f.read_text(encoding="utf-8", errors="replace")
                f_lines = len(raw_text.splitlines())
            except Exception:
                f_lines = 0

        is_test_f = bool(
            "test" in norm_path.lower()
            or norm_path.startswith("tests/")
            or af.file_type == FileKind.TEST
        )
        if norm_path.endswith(".py"):
            lang = "python"
        elif norm_path.endswith((".md", ".rst")):
            lang = "markdown"
        else:
            lang = Path(norm_path).suffix.lstrip(".").lower() or "text"

        files_data.append(
            {
                "file_id": f"file:{norm_path}",
                "name": Path(norm_path).name,
                "path": norm_path,
                "extension": Path(norm_path).suffix,
                "language": lang,
                "size_bytes": af.size_bytes,
                "line_count": f_lines,
                "hash": _compute_file_hash(abs_f),
                "is_test": is_test_f,
                "is_generated": af.is_generated,
            }
        )

    # Gather known method qualified names for call classification
    known_methods = {
        fn.qualified_name for fn in artifact.functions if fn.enclosing_class is not None
    }

    # 5. python_files list
    python_files_data: list[dict[str, Any]] = []

    # Map entities by file_path
    modules_by_file: dict[str, list[Any]] = {}
    for m in artifact.modules:
        modules_by_file.setdefault(m.file_path, []).append(m)

    classes_by_file: dict[str, list[Any]] = {}
    for c in artifact.classes:
        classes_by_file.setdefault(c.location.file_path, []).append(c)

    functions_by_file: dict[str, list[Any]] = {}
    for fn in artifact.functions:
        functions_by_file.setdefault(fn.location.file_path, []).append(fn)

    endpoints_by_file: dict[str, list[Any]] = {}
    for e in artifact.endpoints:
        endpoints_by_file.setdefault(e.location.file_path, []).append(e)

    db_by_file: dict[str, list[Any]] = {}
    for db in artifact.database_references:
        if db.operation == DatabaseOperationKind.MODEL_DECLARATION:
            db_by_file.setdefault(db.location.file_path, []).append(db)

    tests_by_file: dict[str, list[Any]] = {}
    for t in artifact.tests:
        tests_by_file.setdefault(t.location.file_path, []).append(t)

    imports_by_file: dict[str, list[Any]] = {}
    for imp in artifact.imports:
        imports_by_file.setdefault(imp.location.file_path, []).append(imp)

    calls_by_file: dict[str, list[Any]] = {}
    for cl in artifact.calls:
        calls_by_file.setdefault(cl.location.file_path, []).append(cl)

    relationships_by_file: dict[str, list[Any]] = {}
    for r in artifact.relationships:
        relationships_by_file.setdefault(r.evidence_location.file_path, []).append(r)

    py_analyzed_files = [f for f in artifact.files if f.file_type == FileKind.PYTHON]

    for af in py_analyzed_files:
        rel_path = af.path.replace("\\", "/")
        abs_file = wt_path / af.path

        line_count = 0
        if abs_file.is_file():
            try:
                raw_text = abs_file.read_text(encoding="utf-8", errors="replace")
                line_count = len(raw_text.splitlines())
            except Exception:
                line_count = 0

        parent_dir = str(Path(rel_path).parent.as_posix())
        if parent_dir == ".":
            pkg_name = "root"
            pkg_path = "."
        else:
            pkg_name = parent_dir.replace("/", ".")
            pkg_path = parent_dir

        file_obj = {
            "file_id": f"file:{rel_path}",
            "name": Path(rel_path).name,
            "path": rel_path,
            "location": str(abs_file.resolve()),
            "size_bytes": af.size_bytes,
            "line_count": line_count,
            "hash": _compute_file_hash(abs_file),
        }

        package_obj = {
            "package_id": f"package:{pkg_name}",
            "name": pkg_name,
            "path": pkg_path,
        }

        # Modules
        file_modules = modules_by_file.get(af.path, []) or modules_by_file.get(rel_path, [])
        modules_list = [
            {
                "module_id": f"mod:{m.qualified_name}",
                "name": m.qualified_name.split(".")[-1],
                "qualified_name": m.qualified_name,
                "location": {
                    "line_start": m.location.start_line,
                    "line_end": m.location.end_line,
                },
            }
            for m in file_modules
        ]

        # Classes
        file_classes = classes_by_file.get(af.path, []) or classes_by_file.get(rel_path, [])
        file_functions = functions_by_file.get(af.path, []) or functions_by_file.get(rel_path, [])

        classes_list = [
            {
                "class_id": f"class:{c.qualified_name}",
                "name": c.name,
                "qualified_name": c.qualified_name,
                "location": {
                    "line_start": c.location.start_line,
                    "line_end": c.location.end_line,
                },
                "base_classes": list(c.parent_classes),
                "methods": [
                    {
                        "method_id": f"fn:{m.qualified_name}",
                        "name": m.name,
                        "qualified_name": m.qualified_name,
                        "location": {
                            "line_start": m.location.start_line,
                            "line_end": m.location.end_line,
                        },
                    }
                    for m in file_functions
                    if m.enclosing_class == c.qualified_name
                ],
            }
            for c in file_classes
        ]

        # Standalone Functions
        functions_list = [
            {
                "function_id": f"fn:{fn.qualified_name}",
                "name": fn.name,
                "qualified_name": fn.qualified_name,
                "location": {
                    "line_start": fn.location.start_line,
                    "line_end": fn.location.end_line,
                },
                "parameters": [
                    {
                        "name": p.name,
                        "type": p.type_annotation or "Any",
                        "default": p.default_value,
                    }
                    for p in fn.parameters
                ],
                "return_type": fn.return_type or "Any",
                "is_async": (
                    getattr(fn, "is_async", False)
                    or fn.kind in (FunctionKind.ASYNC_FUNCTION, FunctionKind.ASYNC_METHOD)
                ),
            }
            for fn in file_functions
            if fn.enclosing_class is None
        ]

        # Methods
        methods_list = [
            {
                "method_id": f"fn:{fn.qualified_name}",
                "name": fn.name,
                "qualified_name": fn.qualified_name,
                "class_id": f"class:{fn.enclosing_class}",
                "location": {
                    "line_start": fn.location.start_line,
                    "line_end": fn.location.end_line,
                },
                "parameters": [
                    {
                        "name": p.name,
                        "type": p.type_annotation or "Any",
                    }
                    for p in fn.parameters
                ],
                "return_type": fn.return_type or "Any",
                "is_async": (
                    getattr(fn, "is_async", False)
                    or fn.kind in (FunctionKind.ASYNC_FUNCTION, FunctionKind.ASYNC_METHOD)
                ),
            }
            for fn in file_functions
            if fn.enclosing_class is not None
        ]

        # Endpoints
        file_endpoints = endpoints_by_file.get(af.path, []) or endpoints_by_file.get(rel_path, [])
        endpoints_list = [
            {
                "endpoint_id": f"endpoint:{e.http_method}:{e.path}",
                "method": e.http_method,
                "path": e.path,
                "framework": e.framework,
                "handler": e.handler_qualified_name,
                "location": {
                    "line_start": e.location.start_line,
                    "line_end": e.location.end_line,
                },
            }
            for e in file_endpoints
        ]

        # Database Models
        file_db_models = db_by_file.get(af.path, []) or db_by_file.get(rel_path, [])
        database_models_list = [
            {
                "model_id": f"db:{db.target_entity}",
                "name": db.target_entity,
                "table_name": db.target_entity.lower(),
                "framework": "sqlalchemy",
                "location": {
                    "line_start": db.location.start_line,
                    "line_end": db.location.end_line,
                },
                "fields": [],
            }
            for db in file_db_models
        ]

        # Test Functions
        file_tests = tests_by_file.get(af.path, []) or tests_by_file.get(rel_path, [])
        test_functions_list = [
            {
                "test_id": f"test:{t.test_qualified_name}",
                "name": t.test_name,
                "framework": t.framework,
                "location": {
                    "line_start": t.location.start_line,
                    "line_end": t.location.end_line,
                },
                "tests": (
                    [
                        {
                            "target_id": t.target_symbol,
                            "target_type": "function",
                        }
                    ]
                    if t.target_symbol
                    else []
                ),
            }
            for t in file_tests
        ]

        # Imports
        file_imports = imports_by_file.get(af.path, []) or imports_by_file.get(rel_path, [])
        imports_list = [
            {
                "import_id": (
                    f"import:{rel_path}:{imp.location.start_line}:{imp.imported_symbol}"
                ),
                "name": imp.imported_symbol,
                "source": imp.source_module,
                "type": "external" if imp.is_external else "internal",
                "location": {
                    "line": imp.location.start_line,
                },
            }
            for imp in file_imports
        ]

        # Calls
        file_calls = calls_by_file.get(af.path, []) or calls_by_file.get(rel_path, [])
        calls_list = [
            {
                "call_id": (
                    f"call:{rel_path}:{cl.location.start_line}:"
                    f"{cl.caller_qualified_name}->{cl.callee_expression}"
                ),
                "caller_id": f"fn:{cl.caller_qualified_name}",
                "callee_id": cl.resolved_target or cl.callee_expression,
                "callee_type": _determine_callee_type(
                    cl.callee_expression,
                    cl.resolution_status,
                    known_methods,
                ),
                "location": {
                    "line": cl.location.start_line,
                },
            }
            for cl in file_calls
        ]

        # Dependencies
        dependencies_list = []
        for imp in file_imports:
            dep_target = imp.source_module
            dep_type = "external_dependency" if imp.is_external else "module"
            dependencies_list.append(
                {
                    "dependency_id": f"dep:{rel_path}:{dep_target}",
                    "target_id": dep_target,
                    "target_type": dep_type,
                    "dependency_type": "imports",
                }
            )
        for cl in file_calls:
            target = cl.resolved_target or cl.callee_expression
            dependencies_list.append(
                {
                    "dependency_id": f"dep:{rel_path}:{target}",
                    "target_id": target,
                    "target_type": _determine_callee_type(
                        cl.callee_expression,
                        cl.resolution_status,
                        known_methods,
                    ),
                    "dependency_type": "calls",
                }
            )

        # Relationships
        file_relationships = relationships_by_file.get(af.path, []) or relationships_by_file.get(
            rel_path, []
        )
        relationships_list = [
            {
                "relationship_id": (
                    f"rel:{rel_path}:{r.evidence_location.start_line}:"
                    f"{r.relationship_type.value}:{r.target_identifier}"
                ),
                "source": {
                    "id": r.source_identifier,
                    "type": r.source_type.value,
                },
                "target": {
                    "id": r.target_identifier,
                    "type": r.target_type.value,
                },
                "relationship_type": r.relationship_type.value,
                "location": {
                    "line": r.evidence_location.start_line,
                },
            }
            for r in file_relationships
        ]

        python_files_data.append(
            {
                "file": file_obj,
                "package": package_obj,
                "modules": modules_list,
                "classes": classes_list,
                "functions": functions_list,
                "methods": methods_list,
                "endpoints": endpoints_list,
                "database_models": database_models_list,
                "test_functions": test_functions_list,
                "imports": imports_list,
                "calls": calls_list,
                "dependencies": dependencies_list,
                "relationships": relationships_list,
            }
        )

    # 6. metrics
    total_files_count = len(artifact.files)
    python_files_count = len(python_files_data)
    total_modules_count = len(artifact.modules)
    total_packages_count = sum(1 for m in artifact.modules if m.is_package)
    total_classes_count = len(artifact.classes)
    total_methods_count = len(known_methods)
    total_functions_count = sum(1 for fn in artifact.functions if fn.enclosing_class is None)
    total_endpoints_count = len(artifact.endpoints)
    total_db_models_count = sum(
        1
        for db in artifact.database_references
        if db.operation == DatabaseOperationKind.MODEL_DECLARATION
    )
    total_tests_count = len(artifact.tests)
    total_external_deps = len(artifact.dependencies)
    total_relationships_count = len(artifact.relationships)
    diagnostics_count = len(artifact.diagnostics)

    metrics_dict = {
        "total_files": total_files_count,
        "python_files": python_files_count,
        "modules": total_modules_count,
        "packages": total_packages_count,
        "classes": total_classes_count,
        "functions": total_functions_count,
        "methods": total_methods_count,
        "endpoints": total_endpoints_count,
        "database_models": total_db_models_count,
        "test_functions": total_tests_count,
        "external_dependencies": total_external_deps,
        "total_relationships": total_relationships_count,
        "diagnostics_count": diagnostics_count,
    }

    # 7. external_dependencies
    external_deps_data = [
        {
            "dependency_id": f"dep:{dep.package_name}",
            "name": dep.package_name,
            "version": dep.version_spec or "*",
            "type": "external",
            "source": dep.manifest_path.replace("\\", "/"),
        }
        for dep in artifact.dependencies
    ]

    # 8. relationships
    top_relationships_data = [
        {
            "relationship_id": (
                f"rel:{r.source_identifier}:{r.relationship_type.value}:{r.target_identifier}"
            ),
            "source": {
                "id": r.source_identifier,
                "type": r.source_type.value,
            },
            "target": {
                "id": r.target_identifier,
                "type": r.target_type.value,
            },
            "relationship_type": r.relationship_type.value,
        }
        for r in artifact.relationships
    ]

    # 9. dependency_graph
    graph_edges = [
        {
            "source_id": r.source_identifier,
            "target_id": r.target_identifier,
            "relationship_type": r.relationship_type.value,
        }
        for r in artifact.relationships
    ]

    graph_nodes_dict: dict[str, dict[str, Any]] = {}
    for m in artifact.modules:
        mod_id = f"mod:{m.qualified_name}"
        graph_nodes_dict[mod_id] = {
            "id": mod_id,
            "type": "module",
            "name": m.qualified_name.split(".")[-1],
            "file_id": f"file:{m.file_path.replace('\\', '/')}",
        }
    for c in artifact.classes:
        cls_id = f"class:{c.qualified_name}"
        graph_nodes_dict[cls_id] = {
            "id": cls_id,
            "type": "class",
            "name": c.name,
            "file_id": f"file:{c.location.file_path.replace('\\', '/')}",
        }
    for fn in artifact.functions:
        fn_id = f"fn:{fn.qualified_name}"
        graph_nodes_dict[fn_id] = {
            "id": fn_id,
            "type": "function" if fn.enclosing_class is None else "method",
            "name": fn.name,
            "file_id": f"file:{fn.location.file_path.replace('\\', '/')}",
        }
    for ep in artifact.endpoints:
        ep_id = f"endpoint:{ep.http_method}:{ep.path}"
        graph_nodes_dict[ep_id] = {
            "id": ep_id,
            "type": "endpoint",
            "name": f"{ep.http_method} {ep.path}",
            "file_id": f"file:{ep.location.file_path.replace('\\', '/')}",
        }
    for db in artifact.database_references:
        db_id = f"db:{db.target_entity}"
        graph_nodes_dict[db_id] = {
            "id": db_id,
            "type": "database_model",
            "name": db.target_entity,
            "file_id": f"file:{db.location.file_path.replace('\\', '/')}",
        }
    for dep in artifact.dependencies:
        dep_id = f"dep:{dep.package_name}"
        graph_nodes_dict[dep_id] = {
            "id": dep_id,
            "type": "external_dependency",
            "name": dep.package_name,
            "file_id": f"file:{dep.manifest_path.replace('\\', '/')}",
        }

    dependency_graph_dict = {
        "nodes": list(graph_nodes_dict.values()),
        "edges": graph_edges,
    }

    # 10. changes
    changes_dict = {
        "base_version": {
            "commit_sha": commit_hash,
            "branch": branch,
        },
        "target_version": {
            "commit_sha": commit_hash,
            "branch": branch,
        },
        "files": {
            "added": [],
            "modified": [],
            "deleted": [],
            "renamed": [],
        },
        "packages": {
            "added": [],
            "modified": [],
            "deleted": [],
        },
        "modules": {
            "added": [],
            "modified": [],
            "deleted": [],
        },
        "classes": {
            "added": [],
            "modified": [],
            "deleted": [],
        },
        "functions": {
            "added": [],
            "modified": [],
            "deleted": [],
        },
        "methods": {
            "added": [],
            "modified": [],
            "deleted": [],
        },
        "endpoints": {
            "added": [],
            "modified": [],
            "deleted": [],
        },
        "database_models": {
            "added": [],
            "modified": [],
            "deleted": [],
        },
        "test_functions": {
            "added": [],
            "modified": [],
            "deleted": [],
        },
        "dependencies": {
            "added": [],
            "modified": [],
            "deleted": [],
        },
        "relationships": {
            "added": [],
            "modified": [],
            "deleted": [],
        },
    }

    # 11. architecture
    architecture_dict = {
        "components": [],
        "layers": [],
        "services": [
            {
                "name": s.name,
                "type": (
                    s.service_type.value
                    if hasattr(s, "service_type")
                    else "service"
                ),
                "location": (
                    str(s.location.file_path).replace("\\", "/")
                    if hasattr(s, "location")
                    else ""
                ),
            }
            for s in artifact.services
        ],
        "entry_points": [
            {
                "id": f"endpoint:{ep.http_method}:{ep.path}",
                "method": ep.http_method,
                "path": ep.path,
                "handler": ep.handler_qualified_name,
            }
            for ep in artifact.endpoints
        ],
        "circular_dependencies": [],
    }

    # 12. configuration
    frameworks = sorted(
        {ep.framework for ep in artifact.endpoints if ep.framework}
        | {t.framework for t in artifact.tests if t.framework}
    )
    pkg_managers = []
    if any(f.path.endswith("requirements.txt") for f in artifact.files):
        pkg_managers.append("pip")
    if any(
        f.path.endswith("poetry.lock") or f.path.endswith("pyproject.toml")
        for f in artifact.files
    ):
        pkg_managers.append("poetry")

    config_files = [
        f.path.replace("\\", "/")
        for f in artifact.files
        if f.file_type == FileKind.CONFIG
        or any(
            f.path.endswith(ext)
            for ext in (".toml", ".ini", ".cfg", ".yaml", ".yml", ".env")
        )
    ]

    configuration_dict = {
        "frameworks": frameworks,
        "package_managers": pkg_managers,
        "configuration_files": config_files,
    }

    # 13. diagnostics
    diagnostics_list = [
        {
            "code": diag.code,
            "severity": diag.severity.value,
            "message": diag.message,
            "file_path": diag.file_path.replace("\\", "/"),
            "line": diag.line,
            "column": diag.column,
        }
        for diag in artifact.diagnostics
    ]

    return {
        "schema_version": "1.0.0",
        "analysis_run": analysis_run_dict,
        "repository": repository_dict,
        "version_control": version_control_dict,
        "metrics": metrics_dict,
        "files": files_data,
        "python_files": python_files_data,
        "external_dependencies": external_deps_data,
        "relationships": top_relationships_data,
        "dependency_graph": dependency_graph_dict,
        "changes": changes_dict,
        "architecture": architecture_dict,
        "configuration": configuration_dict,
        "diagnostics": diagnostics_list,
    }


def save_repository_summary_json(
    summary_payload: dict[str, Any],
    repo_name: str,
    output_dir: Path | str | None = None,
    run_id: UUID | None = None,
    branch_name: str | None = None,
) -> Path:
    """Save the summary payload to the repo_analysis directory in strict test.json format."""
    dir_path = resolve_repo_analysis_dir(output_dir)
    effective_branch = branch_name
    if not effective_branch and "version_control" in summary_payload:
        effective_branch = (
            summary_payload["version_control"].get("current_version", {}).get("branch")
        )
    if not effective_branch and "repository" in summary_payload:
        effective_branch = summary_payload["repository"].get("default_branch")

    filename = format_summary_filename(repo_name, effective_branch)
    target_file = dir_path / filename

    content = json.dumps(summary_payload, indent=2, default=str)
    target_file.write_text(content, encoding="utf-8")

    # Also write by run_id if provided so lookups by run_id are supported
    if run_id:
        run_file = dir_path / f"{run_id}.json"
        run_file.write_text(content, encoding="utf-8")

    return target_file
