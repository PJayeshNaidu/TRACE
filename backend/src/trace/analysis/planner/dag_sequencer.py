"""Directed Acyclic Graph (DAG) sequencing engine with Tarjan's SCC cycle detection."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from trace.analysis.planner.tier_mapper import TierMapper
from trace.domain.plan import TaskCategory
from typing import Any


@dataclass
class SequencedNode:
    """Output node from topological DAG sequencing."""

    component: str
    step_number: int
    category: TaskCategory
    dependencies: list[str] = field(default_factory=list)
    is_circular: bool = False
    parallel_group_id: int = 1


class DagSequencer:
    """Constructs a directed task graph, detects cycles via Tarjan's SCC,
    and computes topological order.
    """

    @classmethod
    def sequence_tasks(
        cls,
        nodes: list[dict[str, Any]],
        call_edges: list[tuple[str, str]] | None = None,
    ) -> list[SequencedNode]:
        """Sequence task candidate nodes into a topologically ordered execution plan.

        Args:
            nodes: List of node dicts, each having at least 'component',
                and optionally 'category' and 'dependencies'.
            call_edges: Optional list of (caller, callee) tuples.
                A callee must be updated before its caller.

        Returns:
            List of SequencedNode objects ordered strictly by step_number.
        """
        if not nodes:
            return []

        # 1. Index nodes and determine categories
        component_to_node: dict[str, dict[str, Any]] = {}
        component_to_category: dict[str, TaskCategory] = {}
        for n in nodes:
            comp = n["component"]
            component_to_node[comp] = n
            cat = n.get("category")
            if not isinstance(cat, TaskCategory):
                cat = TierMapper.classify(
                    entity_name=comp,
                    entity_type=n.get("component_type", "function"),
                    file_path=n.get("file", ""),
                )
            component_to_category[comp] = cat

        all_components = list(component_to_node.keys())

        # 2. Build adjacency list for G_plan (u -> v means u must complete before v)
        adj: dict[str, set[str]] = {c: set() for c in all_components}
        rev_adj: dict[str, set[str]] = {c: set() for c in all_components}

        # A) Explicit dependencies from node dicts (dependency -> component)
        for n in nodes:
            comp = n["component"]
            for dep in n.get("dependencies", []):
                if dep in adj and dep != comp:
                    adj[dep].add(comp)
                    rev_adj[comp].add(dep)

        # B) Call edges: (caller, callee) -> callee must update before caller (callee -> caller)
        if call_edges:
            for caller, callee in call_edges:
                if callee in adj and caller in adj and callee != caller:
                    adj[callee].add(caller)
                    rev_adj[caller].add(callee)

        # 3. Detect Cycles via Tarjan's Strongly Connected Components (SCC)
        sccs = cls._find_strongly_connected_components(all_components, adj)
        circular_nodes: set[str] = set()
        component_to_scc_id: dict[str, int] = {}
        scc_map: dict[int, list[str]] = {}

        for scc_id, scc in enumerate(sccs):
            scc_map[scc_id] = scc
            if len(scc) > 1:
                for c in scc:
                    circular_nodes.add(c)
            for c in scc:
                component_to_scc_id[c] = scc_id

        # 4. Build condensation DAG (edges between SCCs)
        scc_adj: dict[int, set[int]] = {i: set() for i in range(len(sccs))}
        scc_in_degree: dict[int, int] = dict.fromkeys(range(len(sccs)), 0)

        for u in all_components:
            u_scc = component_to_scc_id[u]
            for v in adj[u]:
                v_scc = component_to_scc_id[v]
                if u_scc != v_scc and v_scc not in scc_adj[u_scc]:
                    scc_adj[u_scc].add(v_scc)

        for u_scc in scc_adj:
            for v_scc in scc_adj[u_scc]:
                scc_in_degree[v_scc] += 1

        # 5. Compute Weakly Connected Components (Parallel Execution Streams)
        parallel_groups = cls._compute_weakly_connected_components(all_components, adj, rev_adj)

        # 6. Topological Sort on Condensation DAG using Priority Queue / Tier Sorting
        # Deterministic tie-breaker: (lowest architectural tier weight, component name)
        def scc_sort_key(scc_id: int) -> tuple[int, str]:
            members = scc_map[scc_id]
            min_weight = min(TierMapper.get_tier_weight(component_to_category[m]) for m in members)
            first_name = sorted(members)[0]
            return (min_weight, first_name)

        ready_queue: list[int] = [i for i, deg in scc_in_degree.items() if deg == 0]
        ready_queue.sort(key=scc_sort_key)

        ordered_components: list[str] = []
        visited_count = 0

        while ready_queue:
            # Pop the highest priority SCC (lowest tier weight)
            current_scc = ready_queue.pop(0)
            visited_count += 1

            # Expand current SCC members in tier/alphabetical order
            members = scc_map[current_scc]
            sorted_members = sorted(
                members,
                key=lambda m: (TierMapper.get_tier_weight(component_to_category[m]), m),
            )
            ordered_components.extend(sorted_members)

            # Reduce in-degrees of neighbors
            newly_ready = []
            for neighbor_scc in sorted(scc_adj[current_scc], key=scc_sort_key):
                scc_in_degree[neighbor_scc] -= 1
                if scc_in_degree[neighbor_scc] == 0:
                    newly_ready.append(neighbor_scc)

            if newly_ready:
                ready_queue.extend(newly_ready)
                ready_queue.sort(key=scc_sort_key)

        # Fallback if any unvisited nodes remain (should not occur with condensation DAG)
        if len(ordered_components) < len(all_components):
            remaining = [c for c in all_components if c not in ordered_components]
            remaining.sort(key=lambda m: (TierMapper.get_tier_weight(component_to_category[m]), m))
            ordered_components.extend(remaining)

        # 7. Construct final SequencedNode list with 1-indexed step_number
        result: list[SequencedNode] = []
        for step, comp in enumerate(ordered_components, 1):
            dependencies = sorted(rev_adj[comp])
            result.append(
                SequencedNode(
                    component=comp,
                    step_number=step,
                    category=component_to_category[comp],
                    dependencies=dependencies,
                    is_circular=(comp in circular_nodes),
                    parallel_group_id=parallel_groups.get(comp, 1),
                )
            )

        return result

    @classmethod
    def _find_strongly_connected_components(
        cls,
        nodes: list[str],
        adj: dict[str, set[str]],
    ) -> list[list[str]]:
        """Tarjan's strongly connected components algorithm."""
        index = 0
        indices: dict[str, int] = {}
        lowlink: dict[str, int] = {}
        on_stack: dict[str, bool] = defaultdict(bool)
        stack: list[str] = []
        sccs: list[list[str]] = []

        def strongconnect(v: str) -> None:
            nonlocal index
            indices[v] = index
            lowlink[v] = index
            index += 1
            stack.append(v)
            on_stack[v] = True

            for w in adj.get(v, ()):
                if w not in indices:
                    strongconnect(w)
                    lowlink[v] = min(lowlink[v], lowlink[w])
                elif on_stack[w]:
                    lowlink[v] = min(lowlink[v], indices[w])

            if lowlink[v] == indices[v]:
                scc: list[str] = []
                while True:
                    w = stack.pop()
                    on_stack[w] = False
                    scc.append(w)
                    if w == v:
                        break
                sccs.append(scc)

        for node in nodes:
            if node not in indices:
                strongconnect(node)

        return sccs

    @classmethod
    def _compute_weakly_connected_components(
        cls,
        nodes: list[str],
        adj: dict[str, set[str]],
        rev_adj: dict[str, set[str]],
    ) -> dict[str, int]:
        """Compute parallel execution stream IDs using undirected BFS on the graph."""
        visited: set[str] = set()
        groups: dict[str, int] = {}
        current_group = 1

        for start_node in nodes:
            if start_node in visited:
                continue

            queue = deque([start_node])
            visited.add(start_node)

            while queue:
                curr = queue.popleft()
                groups[curr] = current_group

                # Undirected neighbors = forward + reverse edges
                neighbors = adj.get(curr, set()) | rev_adj.get(curr, set())
                for neighbor in neighbors:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)

            current_group += 1

        return groups
