"""AST Symbol Diff and Breaking Change Detection Engine for F04."""

from trace.domain.analysis import (
    APIEndpoint,
    Class,
    Function,
    Module,
    ParameterDescriptor,
    RepositoryAnalysis,
)
from trace.domain.diff import (
    DiffHunk,
    FileChangeType,
    FileDiff,
    SymbolChangeKind,
    SymbolDiff,
)


def _format_function_signature(func: Function) -> str:
    """Format readable function signature string."""
    params: list[str] = []
    for p in func.parameters:
        part = p.name
        if p.type_annotation:
            part += f": {p.type_annotation}"
        if p.has_default:
            part += f" = {p.default_value if p.default_value is not None else '...'}"
        params.append(part)
    param_str = ", ".join(params)
    ret = f" -> {func.return_type}" if func.return_type else ""
    return f"{func.name}({param_str}){ret}"


def _format_endpoint_signature(ep: APIEndpoint) -> str:
    """Format readable API endpoint signature."""
    return f"{ep.http_method} {ep.path} -> {ep.handler_qualified_name}"


def _hunk_overlaps(hunk: DiffHunk, start_line: int, end_line: int) -> bool:
    """Check if diff hunk line interval intersects with symbol line interval."""
    hunk_start = hunk.new_start
    hunk_end = hunk.new_start + max(1, hunk.new_lines) - 1
    return not (hunk_end < start_line or hunk_start > end_line)


class SymbolDiffEngine:
    """Computes semantic symbol-level changes and identifies breaking changes."""

    def compute_symbol_diffs(
        self,
        file_diffs: list[FileDiff],
        base_analysis: RepositoryAnalysis | None,
        target_analysis: RepositoryAnalysis | None,
    ) -> list[SymbolDiff]:
        """Intersect file diff hunks with AST symbols from base and target analyses.

        Args:
            file_diffs: Parsed list of FileDiff instances.
            base_analysis: AST analysis artifact of base revision (if available).
            target_analysis: AST analysis artifact of target revision (if available).

        Returns:
            List of SymbolDiff instances detailing symbol modifications and breaking status.
        """
        symbol_diffs: list[SymbolDiff] = []
        processed_symbols: set[str] = set()

        # Build lookup maps for base symbols
        base_funcs: dict[str, Function] = {}
        base_classes: dict[str, Class] = {}
        base_endpoints: dict[str, APIEndpoint] = {}
        base_modules: dict[str, Module] = {}

        if base_analysis:
            for f in base_analysis.functions:
                base_funcs[f.qualified_name] = f
            for c in base_analysis.classes:
                base_classes[c.qualified_name] = c
            for ep in base_analysis.endpoints:
                base_endpoints[f"{ep.http_method}:{ep.path}"] = ep
            for m in base_analysis.modules:
                base_modules[m.qualified_name] = m

        # Build lookup maps for target symbols
        target_funcs: dict[str, Function] = {}
        target_classes: dict[str, Class] = {}
        target_endpoints: dict[str, APIEndpoint] = {}
        target_modules: dict[str, Module] = {}

        if target_analysis:
            for f in target_analysis.functions:
                target_funcs[f.qualified_name] = f
            for c in target_analysis.classes:
                target_classes[c.qualified_name] = c
            for ep in target_analysis.endpoints:
                target_endpoints[f"{ep.http_method}:{ep.path}"] = ep
            for m in target_analysis.modules:
                target_modules[m.qualified_name] = m

        for file_diff in file_diffs:
            # Case 1: Deleted file -> all base symbols in that file are DELETED & BREAKING
            if file_diff.change_type == FileChangeType.DELETED:
                old_file = file_diff.old_path or ""
                if base_analysis:
                    for f in base_analysis.functions:
                        if f.location.file_path == old_file:
                            key = f"func:{f.qualified_name}"
                            if key not in processed_symbols:
                                processed_symbols.add(key)
                                symbol_diffs.append(
                                    SymbolDiff(
                                        symbol_id=key,
                                        qualified_name=f.qualified_name,
                                        kind="function",
                                        file_path=old_file,
                                        change_kind=SymbolChangeKind.DELETED,
                                        is_breaking=True,
                                        breaking_reason=f"Function '{f.name}' was removed with deleted file.",
                                        old_signature=_format_function_signature(f),
                                        new_signature=None,
                                    )
                                )
                    for c in base_analysis.classes:
                        if c.location.file_path == old_file:
                            key = f"class:{c.qualified_name}"
                            if key not in processed_symbols:
                                processed_symbols.add(key)
                                symbol_diffs.append(
                                    SymbolDiff(
                                        symbol_id=key,
                                        qualified_name=c.qualified_name,
                                        kind="class",
                                        file_path=old_file,
                                        change_kind=SymbolChangeKind.DELETED,
                                        is_breaking=True,
                                        breaking_reason=f"Class '{c.name}' was removed with deleted file.",
                                        old_signature=f"class {c.name}",
                                        new_signature=None,
                                    )
                                )
                    for ep in base_analysis.endpoints:
                        if ep.location.file_path == old_file:
                            key = f"endpoint:{ep.http_method}:{ep.path}"
                            if key not in processed_symbols:
                                processed_symbols.add(key)
                                symbol_diffs.append(
                                    SymbolDiff(
                                        symbol_id=key,
                                        qualified_name=f"{ep.http_method} {ep.path}",
                                        kind="endpoint",
                                        file_path=old_file,
                                        change_kind=SymbolChangeKind.DELETED,
                                        is_breaking=True,
                                        breaking_reason=f"API Endpoint '{ep.http_method} {ep.path}' was removed.",
                                        old_signature=_format_endpoint_signature(ep),
                                        new_signature=None,
                                    )
                                )
                continue

            # Case 2: Added file -> all target symbols in that file are ADDED
            if file_diff.change_type == FileChangeType.ADDED:
                new_file = file_diff.new_path or ""
                if target_analysis:
                    for f in target_analysis.functions:
                        if f.location.file_path == new_file:
                            key = f"func:{f.qualified_name}"
                            if key not in processed_symbols:
                                processed_symbols.add(key)
                                symbol_diffs.append(
                                    SymbolDiff(
                                        symbol_id=key,
                                        qualified_name=f.qualified_name,
                                        kind="function",
                                        file_path=new_file,
                                        change_kind=SymbolChangeKind.ADDED,
                                        is_breaking=False,
                                        old_signature=None,
                                        new_signature=_format_function_signature(f),
                                    )
                                )
                    for c in target_analysis.classes:
                        if c.location.file_path == new_file:
                            key = f"class:{c.qualified_name}"
                            if key not in processed_symbols:
                                processed_symbols.add(key)
                                symbol_diffs.append(
                                    SymbolDiff(
                                        symbol_id=key,
                                        qualified_name=c.qualified_name,
                                        kind="class",
                                        file_path=new_file,
                                        change_kind=SymbolChangeKind.ADDED,
                                        is_breaking=False,
                                        old_signature=None,
                                        new_signature=f"class {c.name}",
                                    )
                                )
                    for ep in target_analysis.endpoints:
                        if ep.location.file_path == new_file:
                            key = f"endpoint:{ep.http_method}:{ep.path}"
                            if key not in processed_symbols:
                                processed_symbols.add(key)
                                symbol_diffs.append(
                                    SymbolDiff(
                                        symbol_id=key,
                                        qualified_name=f"{ep.http_method} {ep.path}",
                                        kind="endpoint",
                                        file_path=new_file,
                                        change_kind=SymbolChangeKind.ADDED,
                                        is_breaking=False,
                                        old_signature=None,
                                        new_signature=_format_endpoint_signature(ep),
                                    )
                                )
                continue

            # Case 3: Modified or Renamed file -> intersect hunks with symbols
            new_file = file_diff.new_path or file_diff.old_path or ""
            old_file = file_diff.old_path or file_diff.new_path or ""

            # Check deleted symbols in this file
            if base_analysis and target_analysis:
                for f in base_analysis.functions:
                    if f.location.file_path == old_file and f.qualified_name not in target_funcs:
                        key = f"func:{f.qualified_name}"
                        if key not in processed_symbols:
                            processed_symbols.add(key)
                            symbol_diffs.append(
                                SymbolDiff(
                                    symbol_id=key,
                                    qualified_name=f.qualified_name,
                                    kind="function",
                                    file_path=old_file,
                                    change_kind=SymbolChangeKind.DELETED,
                                    is_breaking=True,
                                    breaking_reason=f"Function '{f.name}' was removed.",
                                    old_signature=_format_function_signature(f),
                                    new_signature=None,
                                )
                            )
                for c in base_analysis.classes:
                    if c.location.file_path == old_file and c.qualified_name not in target_classes:
                        key = f"class:{c.qualified_name}"
                        if key not in processed_symbols:
                            processed_symbols.add(key)
                            symbol_diffs.append(
                                SymbolDiff(
                                    symbol_id=key,
                                    qualified_name=c.qualified_name,
                                    kind="class",
                                    file_path=old_file,
                                    change_kind=SymbolChangeKind.DELETED,
                                    is_breaking=True,
                                    breaking_reason=f"Class '{c.name}' was removed.",
                                    old_signature=f"class {c.name}",
                                    new_signature=None,
                                )
                            )
                for ep in base_analysis.endpoints:
                    ep_key = f"{ep.http_method}:{ep.path}"
                    if ep.location.file_path == old_file and ep_key not in target_endpoints:
                        key = f"endpoint:{ep_key}"
                        if key not in processed_symbols:
                            processed_symbols.add(key)
                            symbol_diffs.append(
                                SymbolDiff(
                                    symbol_id=key,
                                    qualified_name=f"{ep.http_method} {ep.path}",
                                    kind="endpoint",
                                    file_path=old_file,
                                    change_kind=SymbolChangeKind.DELETED,
                                    is_breaking=True,
                                    breaking_reason=f"API Endpoint '{ep.http_method} {ep.path}' was removed.",
                                    old_signature=_format_endpoint_signature(ep),
                                    new_signature=None,
                                )
                            )

            # Check modified / added symbols in target file
            if target_analysis:
                # Functions
                for f in target_analysis.functions:
                    if f.location.file_path == new_file:
                        overlaps = any(
                            _hunk_overlaps(hunk, f.location.start_line, f.location.end_line)
                            for hunk in file_diff.hunks
                        )
                        if overlaps:
                            key = f"func:{f.qualified_name}"
                            if key not in processed_symbols:
                                processed_symbols.add(key)
                                base_f = base_funcs.get(f.qualified_name)
                                if not base_f:
                                    # Added function in modified file
                                    symbol_diffs.append(
                                        SymbolDiff(
                                            symbol_id=key,
                                            qualified_name=f.qualified_name,
                                            kind="function",
                                            file_path=new_file,
                                            change_kind=SymbolChangeKind.ADDED,
                                            is_breaking=False,
                                            old_signature=None,
                                            new_signature=_format_function_signature(f),
                                        )
                                    )
                                else:
                                    # Modified function -> evaluate breaking changes
                                    is_breaking, reason = self._check_function_breaking_changes(
                                        base_f, f
                                    )
                                    symbol_diffs.append(
                                        SymbolDiff(
                                            symbol_id=key,
                                            qualified_name=f.qualified_name,
                                            kind="function",
                                            file_path=new_file,
                                            change_kind=SymbolChangeKind.MODIFIED,
                                            is_breaking=is_breaking,
                                            breaking_reason=reason,
                                            old_signature=_format_function_signature(base_f),
                                            new_signature=_format_function_signature(f),
                                        )
                                    )

                # Classes
                for c in target_analysis.classes:
                    if c.location.file_path == new_file:
                        overlaps = any(
                            _hunk_overlaps(hunk, c.location.start_line, c.location.end_line)
                            for hunk in file_diff.hunks
                        )
                        if overlaps:
                            key = f"class:{c.qualified_name}"
                            if key not in processed_symbols:
                                processed_symbols.add(key)
                                base_c = base_classes.get(c.qualified_name)
                                if not base_c:
                                    symbol_diffs.append(
                                        SymbolDiff(
                                            symbol_id=key,
                                            qualified_name=c.qualified_name,
                                            kind="class",
                                            file_path=new_file,
                                            change_kind=SymbolChangeKind.ADDED,
                                            is_breaking=False,
                                            old_signature=None,
                                            new_signature=f"class {c.name}",
                                        )
                                    )
                                else:
                                    # Check class changes (e.g. parent class alteration)
                                    is_breaking = False
                                    reason = None
                                    if set(base_c.parent_classes) != set(c.parent_classes):
                                        is_breaking = True
                                        reason = f"Inheritance hierarchy changed from {base_c.parent_classes} to {c.parent_classes}"

                                    symbol_diffs.append(
                                        SymbolDiff(
                                            symbol_id=key,
                                            qualified_name=c.qualified_name,
                                            kind="class",
                                            file_path=new_file,
                                            change_kind=SymbolChangeKind.MODIFIED,
                                            is_breaking=is_breaking,
                                            breaking_reason=reason,
                                            old_signature=f"class {base_c.name}({', '.join(base_c.parent_classes)})",
                                            new_signature=f"class {c.name}({', '.join(c.parent_classes)})",
                                        )
                                    )

                # Endpoints
                for ep in target_analysis.endpoints:
                    if ep.location.file_path == new_file:
                        overlaps = any(
                            _hunk_overlaps(hunk, ep.location.start_line, ep.location.end_line)
                            for hunk in file_diff.hunks
                        )
                        if overlaps:
                            key = f"endpoint:{ep.http_method}:{ep.path}"
                            if key not in processed_symbols:
                                processed_symbols.add(key)
                                base_ep = base_endpoints.get(f"{ep.http_method}:{ep.path}")
                                if not base_ep:
                                    symbol_diffs.append(
                                        SymbolDiff(
                                            symbol_id=key,
                                            qualified_name=f"{ep.http_method} {ep.path}",
                                            kind="endpoint",
                                            file_path=new_file,
                                            change_kind=SymbolChangeKind.ADDED,
                                            is_breaking=False,
                                            old_signature=None,
                                            new_signature=_format_endpoint_signature(ep),
                                        )
                                    )
                                else:
                                    symbol_diffs.append(
                                        SymbolDiff(
                                            symbol_id=key,
                                            qualified_name=f"{ep.http_method} {ep.path}",
                                            kind="endpoint",
                                            file_path=new_file,
                                            change_kind=SymbolChangeKind.MODIFIED,
                                            is_breaking=False,
                                            old_signature=_format_endpoint_signature(base_ep),
                                            new_signature=_format_endpoint_signature(ep),
                                        )
                                    )

        return symbol_diffs

    def _check_function_breaking_changes(
        self, old_func: Function, new_func: Function
    ) -> tuple[bool, str | None]:
        """Evaluate if changes to a function signature constitute a breaking change."""
        old_params = {p.name: p for p in old_func.parameters}
        new_params = {p.name: p for p in new_func.parameters}

        reasons: list[str] = []

        # 1. Removed parameters
        for p_name in old_params:
            if p_name not in new_params and p_name not in ("self", "cls"):
                reasons.append(f"Parameter '{p_name}' was removed")

        # 2. Added required parameters without default
        for p_name, p in new_params.items():
            if (
                p_name not in old_params
                and not p.has_default
                and p_name not in ("self", "cls", "*args", "**kwargs")
            ):
                reasons.append(f"Required parameter '{p_name}' was added without default value")

        # 3. Return type changed incompatibly
        if (
            old_func.return_type
            and new_func.return_type
            and old_func.return_type != new_func.return_type
        ):
            reasons.append(
                f"Return type changed from '{old_func.return_type}' to '{new_func.return_type}'"
            )

        if reasons:
            return True, "; ".join(reasons)
        return False, None
