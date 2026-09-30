"""Inverted call graph construction, multi-hop BFS traversal, and Mermaid visualization."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from trace.domain.analysis import RepositoryAnalysis
from trace.domain.impact import CallerAtRisk, GraphEdgePayload, GraphNodePayload


@dataclass(frozen=True)
class TraversalResult:
    """Blast radius traversal result for a modified entity."""

    direct_callers: tuple[str, ...]
    callers_at_risk: tuple[CallerAtRisk, ...]


class TransposedGraphEngine:
    """Builds directed call graph G and inverts it to G^T to trace upstream callers via BFS."""

    def __init__(self, max_depth: int = 3) -> None:
        self._max_depth = max_depth

    def build_call_graphs(
        self,
        analysis: RepositoryAnalysis,
    ) -> tuple[dict[str, set[str]], dict[str, set[str]], dict[str, str]]:
        """Construct forward graph G, inverted graph G^T, and symbol-to-file mapping.

        G: caller -> {callees}
        G^T: callee -> {callers}
        """
        forward_graph: dict[str, set[str]] = {}
        transposed_graph: dict[str, set[str]] = {}
        symbol_files: dict[str, str] = {}

        # Record file locations for all functions and endpoints
        for f in analysis.functions:
            symbol_files[f.qualified_name] = f.location.file_path
            symbol_files[f.name] = f.location.file_path
        for ep in analysis.endpoints:
            ep_name = f"{ep.http_method} {ep.path}"
            symbol_files[ep_name] = ep.location.file_path

        # Populate from explicit calls
        for c in analysis.calls:
            caller = c.caller_qualified_name
            callee = c.resolved_target or c.callee_expression
            forward_graph.setdefault(caller, set()).add(callee)
            transposed_graph.setdefault(callee, set()).add(caller)

        # Populate from structural relationships (CALLS, IMPORTS, EXTENDS, DEPENDS_ON)
        for rel in analysis.relationships:
            rel_type = (
                rel.relationship_type.value
                if hasattr(rel.relationship_type, "value")
                else str(rel.relationship_type)
            )
            if rel_type in ("CALLS", "EXTENDS", "DEPENDS_ON"):
                src = rel.source_identifier
                tgt = rel.target_identifier
                forward_graph.setdefault(src, set()).add(tgt)
                transposed_graph.setdefault(tgt, set()).add(src)
                if rel.evidence_location and src not in symbol_files:
                    symbol_files[src] = rel.evidence_location.file_path

        return forward_graph, transposed_graph, symbol_files

    def traverse_blast_radius(
        self,
        target_symbol: str,
        transposed_graph: dict[str, set[str]],
        symbol_files: dict[str, str],
        max_depth: int | None = None,
    ) -> TraversalResult:
        """Run BFS on G^T from target_symbol up to max_depth to find all upstream callers."""
        limit_depth = max_depth or self._max_depth
        direct_callers: list[str] = []
        callers_at_risk: list[CallerAtRisk] = []

        # Find direct callers
        immed = transposed_graph.get(target_symbol, set())
        # Try suffix match if exact match not found (e.g. function short name)
        if not immed and "." in target_symbol:
            short_name = target_symbol.split(".")[-1]
            immed = transposed_graph.get(short_name, set())

        direct_callers = sorted(list(immed))

        # BFS queue: (current_node, current_depth, call_chain)
        queue: deque[tuple[str, int, list[str]]] = deque()
        visited: set[str] = {target_symbol}

        for caller in direct_callers:
            if caller != target_symbol:
                visited.add(caller)
                queue.append((caller, 1, [caller, target_symbol]))

        while queue:
            curr_node, depth, chain = queue.popleft()

            callers_at_risk.append(
                CallerAtRisk(
                    qualified_name=curr_node,
                    file_path=symbol_files.get(curr_node, ""),
                    distance=depth,
                    call_chain=tuple(chain),
                )
            )

            if depth < limit_depth:
                upstream_nodes = transposed_graph.get(curr_node, set())
                if not upstream_nodes and "." in curr_node:
                    upstream_nodes = transposed_graph.get(curr_node.split(".")[-1], set())

                for up in sorted(upstream_nodes):
                    if up not in visited:
                        visited.add(up)
                        queue.append((up, depth + 1, [up] + chain))

        # Sort callers at risk by distance ascending
        callers_at_risk.sort(key=lambda c: (c.distance, c.qualified_name))
        return TraversalResult(
            direct_callers=tuple(direct_callers),
            callers_at_risk=tuple(callers_at_risk),
        )


class MermaidGenerator:
    """Generates styled Mermaid diagrams for impact and blast radius visualization."""

    def generate(
        self,
        nodes: list[GraphNodePayload],
        edges: list[GraphEdgePayload],
    ) -> str:
        """Generate Mermaid code block with CSS styling for modified and at-risk nodes."""
        lines: list[str] = ["graph TD"]

        # Subgraph for modified entities
        if nodes:
            lines.append("  subgraph Modified [Modified Entities]")
            for n in nodes:
                safe_id = self._sanitize_id(n.changed_entity)
                lines.append(f'    {safe_id}["{n.changed_entity} ({n.file})"]:::modifiedNode')
            lines.append("  end")

        # Set of modified entity safe IDs
        modified_ids = {self._sanitize_id(n.changed_entity) for n in nodes}

        # Subgraph for at-risk callers
        at_risk_callers: set[str] = set()
        for e in edges:
            safe_caller = self._sanitize_id(e.caller)
            if safe_caller not in modified_ids:
                at_risk_callers.add(e.caller)

        if at_risk_callers:
            lines.append("  subgraph AtRisk [At-Risk Callers]")
            for c in sorted(at_risk_callers):
                safe_id = self._sanitize_id(c)
                lines.append(f'    {safe_id}["{c}"]:::riskNode')
            lines.append("  end")

        # Directed call edges: Caller --> Callee
        for e in edges:
            safe_caller = self._sanitize_id(e.caller)
            safe_callee = self._sanitize_id(e.callee)
            lines.append(f"  {safe_caller} --> {safe_callee}")

        # CSS Class definitions
        lines.append("  classDef modifiedNode fill:#ef4444,stroke:#b91c1c,color:#ffffff,stroke-width:2px,font-weight:bold;")
        lines.append("  classDef riskNode fill:#f59e0b,stroke:#d97706,color:#ffffff,stroke-width:2px;")
        lines.append("  classDef default fill:#1e293b,stroke:#475569,color:#e2e8f0;")

        return "\n".join(lines)

    def _sanitize_id(self, name: str) -> str:
        """Replace non-alphanumeric characters with underscores for valid Mermaid node IDs."""
        return "".join(c if c.isalnum() else "_" for c in name)
