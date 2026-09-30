"""Mathematical AST interval intersection and patch snippet extraction engine."""

from __future__ import annotations

from dataclasses import dataclass
from trace.domain.analysis import APIEndpoint, Class, Function, RepositoryAnalysis
from trace.domain.diff import DiffHunk, FileChangeType, FileDiff


@dataclass(frozen=True)
class OverlapResult:
    """Result of an interval overlap between a diff hunk and an AST entity."""

    entity_name: str
    entity_type: str  # function, method, class, endpoint
    file_path: str
    qualified_name: str
    lines_affected: tuple[int, int]
    diff_snippet: str
    outbound_calls: tuple[str, ...] = ()


def hunk_to_interval(hunk: DiffHunk) -> tuple[int, int]:
    """Convert unified diff hunk into inclusive 1-indexed target line interval [H_start, H_end].

    Formula:
        H_start = new_start
        H_end = H_start if new_lines == 0 else H_start + new_lines - 1
    """
    h_start = hunk.new_start
    if hunk.new_lines == 0:
        h_end = h_start
    else:
        h_end = h_start + max(1, hunk.new_lines) - 1
    return h_start, h_end


def intervals_overlap(f_start: int, f_end: int, h_start: int, h_end: int) -> bool:
    """Check mathematical interval overlap condition: max(F_start, H_start) <= min(F_end, H_end)."""
    return max(f_start, h_start) <= min(f_end, h_end)


def extract_diff_patch_snippet(hunk_content: str, max_chars: int = 350) -> str:
    """Extract patch lines (+ and -) from a hunk, capped for token safety."""
    if not hunk_content:
        return ""
    patch_lines: list[str] = []
    for line in hunk_content.splitlines():
        if (line.startswith("+") and not line.startswith("+++")) or (
            line.startswith("-") and not line.startswith("---")
        ):
            patch_lines.append(line)

    joined = "\n".join(patch_lines)
    if len(joined) > max_chars:
        return joined[:max_chars] + "\n... [diff truncated]"
    return joined


class IntervalOverlapEngine:
    """Intersects diff hunks with AST symbol boundaries using decorator expansion."""

    def __init__(self, snippet_max_chars: int = 350) -> None:
        self._snippet_max_chars = snippet_max_chars

    def find_modified_entities(
        self,
        file_diffs: list[FileDiff],
        analysis: RepositoryAnalysis | None,
    ) -> list[OverlapResult]:
        """Intersect file diff hunks with AST symbols from repository analysis.

        Applies:
        1. Decorator Expansion Rule: Function start is expanded to the line of its first decorator.
        2. Mathematical Overlap Test: max(F_start, H_start) <= min(F_end, H_end).
        3. Patch text binding: Attaches diff_snippet to the entity.
        """
        if not analysis or not file_diffs:
            return []

        results: list[OverlapResult] = []
        seen_keys: set[str] = set()

        # Build map of functions by file path
        funcs_by_file: dict[str, list[Function]] = {}
        for f in analysis.functions:
            funcs_by_file.setdefault(f.location.file_path, []).append(f)

        # Build map of classes by file path
        classes_by_file: dict[str, list[Class]] = {}
        for c in analysis.classes:
            classes_by_file.setdefault(c.location.file_path, []).append(c)

        # Build map of endpoints by file path
        endpoints_by_file: dict[str, list[APIEndpoint]] = {}
        for ep in analysis.endpoints:
            endpoints_by_file.setdefault(ep.location.file_path, []).append(ep)

        # Build map of outbound calls by caller qualified name
        calls_by_caller: dict[str, list[str]] = {}
        for call in analysis.calls:
            target = call.resolved_target or call.callee_expression
            calls_by_caller.setdefault(call.caller_qualified_name, []).append(target)

        for fd in file_diffs:
            if fd.change_type == FileChangeType.DELETED:
                continue

            file_path = fd.new_path or fd.old_path or ""
            funcs = funcs_by_file.get(file_path, [])
            endpoints = endpoints_by_file.get(file_path, [])
            classes = classes_by_file.get(file_path, [])

            # Intersect functions
            for f in funcs:
                f_start = f.location.start_line
                f_end = f.location.end_line

                # Decorator Expansion Rule: Set F_start to the start of the first decorator
                if f.decorators:
                    min_dec_line = min(d.line_number for d in f.decorators)
                    if min_dec_line > 0:
                        f_start = min(f_start, min_dec_line)

                matching_hunks: list[DiffHunk] = []
                overlap_starts: list[int] = []
                overlap_ends: list[int] = []

                for hunk in fd.hunks:
                    h_start, h_end = hunk_to_interval(hunk)
                    if intervals_overlap(f_start, f_end, h_start, h_end):
                        matching_hunks.append(hunk)
                        overlap_starts.append(max(f_start, h_start))
                        overlap_ends.append(min(f_end, h_end))

                if matching_hunks:
                    key = f"func:{f.qualified_name}"
                    if key not in seen_keys:
                        seen_keys.add(key)
                        snippet_parts = [
                            extract_diff_patch_snippet(h.content, self._snippet_max_chars)
                            for h in matching_hunks
                        ]
                        diff_snippet = "\n".join(p for p in snippet_parts if p)
                        lines_affected = (min(overlap_starts), max(overlap_ends))
                        outbound = tuple(calls_by_caller.get(f.qualified_name, ()))

                        results.append(
                            OverlapResult(
                                entity_name=f.name,
                                entity_type="method" if "." in f.qualified_name and not f.qualified_name.endswith(f".{f.name}") else "function",
                                file_path=file_path,
                                qualified_name=f.qualified_name,
                                lines_affected=lines_affected,
                                diff_snippet=diff_snippet,
                                outbound_calls=outbound,
                            )
                        )

            # Intersect endpoints
            for ep in endpoints:
                ep_start = ep.location.start_line
                ep_end = ep.location.end_line

                matching_hunks = []
                overlap_starts = []
                overlap_ends = []
                for hunk in fd.hunks:
                    h_start, h_end = hunk_to_interval(hunk)
                    if intervals_overlap(ep_start, ep_end, h_start, h_end):
                        matching_hunks.append(hunk)
                        overlap_starts.append(max(ep_start, h_start))
                        overlap_ends.append(min(ep_end, h_end))

                if matching_hunks:
                    key = f"endpoint:{ep.http_method}:{ep.path}"
                    if key not in seen_keys:
                        seen_keys.add(key)
                        diff_snippet = "\n".join(
                            extract_diff_patch_snippet(h.content, self._snippet_max_chars)
                            for h in matching_hunks
                        )
                        lines_affected = (min(overlap_starts), max(overlap_ends))
                        results.append(
                            OverlapResult(
                                entity_name=f"{ep.http_method} {ep.path}",
                                entity_type="endpoint",
                                file_path=file_path,
                                qualified_name=f"{ep.http_method} {ep.path}",
                                lines_affected=lines_affected,
                                diff_snippet=diff_snippet,
                                outbound_calls=tuple(calls_by_caller.get(ep.handler_qualified_name, ())),
                            )
                        )

        return results
