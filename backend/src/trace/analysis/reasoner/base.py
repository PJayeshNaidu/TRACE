"""Base protocol for Dual-Track reasoning engines."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class DualTrackReasoner(Protocol):
    """Protocol for impact analysis reasoning and explanation generation."""

    async def reason(
        self,
        entity_summary: dict[str, Any],
        diff_snippet: str,
        inbound_callers: tuple[str, ...],
        downstream_files: tuple[str, ...],
    ) -> dict[str, str]:
        """Generate change_summary, remediation_guidance, and justification.

        Returns:
            Dictionary with keys: "change_summary", "remediation_guidance", "justification".
        """
        ...
