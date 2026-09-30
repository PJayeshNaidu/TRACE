"""Deterministic offline heuristic reasoning engine."""

from __future__ import annotations

from trace.analysis.delta_inference import DeltaInferenceEngine
from typing import Any


class HeuristicRuleEngine:
    """Offline, deterministic reasoning engine using AST facts and syntax delta rules."""

    def __init__(self, delta_engine: DeltaInferenceEngine | None = None) -> None:
        self._delta_engine = delta_engine or DeltaInferenceEngine()

    async def reason(
        self,
        entity_summary: dict[str, Any],
        diff_snippet: str,
        inbound_callers: tuple[str, ...],
        downstream_files: tuple[str, ...],
    ) -> dict[str, str]:
        """Synthesize change_summary, remediation_guidance, and justification deterministically."""
        entity_name = entity_summary.get("entity", "entity")
        file_path = entity_summary.get("file", "unknown")
        lines = entity_summary.get("lines_affected", (0, 0))

        delta = self._delta_engine.infer_delta(
            entity_name=entity_name,
            diff_snippet=diff_snippet,
            inbound_callers=inbound_callers,
        )

        callers_desc = (
            f"Directly impacts upstream callers ({', '.join(f'`{c}`' for c in inbound_callers)})."
            if inbound_callers
            else "No direct upstream callers detected."
        )
        downstream_desc = (
            f"Propagates risk to {len(downstream_files)} downstream dependent file(s)."
            if downstream_files
            else "Localized to source file."
        )

        justification = (
            f"Core {entity_summary.get('entity_type', 'function')} `{entity_name}` in `{file_path}` "
            f"modified (lines {lines[0]}-{lines[1]}); {delta.justification_snippet} "
            f"{callers_desc} {downstream_desc}"
        )

        return {
            "change_summary": delta.change_summary,
            "remediation_guidance": delta.remediation_guidance,
            "justification": justification,
        }
