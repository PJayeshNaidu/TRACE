"""Deterministic diff syntax delta inference and prioritized remediation plan synthesis."""

from __future__ import annotations

import re
from dataclasses import dataclass
from trace.domain.impact import RemediationStep


@dataclass(frozen=True)
class DeltaInferenceResult:
    """Inferred change category and prescriptive remediation advice."""

    change_summary: str
    remediation_guidance: str
    justification_snippet: str
    is_signature_change: bool = False
    is_return_change: bool = False
    is_exception_change: bool = False


class DeltaInferenceEngine:
    """Inspects diff patch snippets to infer semantic changes and produce prescriptive advice."""

    DEF_PATTERN = re.compile(r"^[+-]\s*(async\s+)?def\s+([a-zA-Z_]\w*)", re.MULTILINE)
    RETURN_PATTERN = re.compile(r"^[+-]\s*return\b", re.MULTILINE)
    RAISE_PATTERN = re.compile(r"^[+-]\s*raise\b", re.MULTILINE)

    def infer_delta(
        self,
        entity_name: str,
        diff_snippet: str,
        inbound_callers: tuple[str, ...] = (),
    ) -> DeltaInferenceResult:
        """Infer change semantics deterministically from the patch lines."""
        if not diff_snippet:
            return DeltaInferenceResult(
                change_summary="Internal function implementation updated.",
                remediation_guidance=f"Run unit tests for `{entity_name}` and regression tests on direct callers.",
                justification_snippet="Internal statements altered without signature changes.",
            )

        has_def = bool(self.DEF_PATTERN.search(diff_snippet))
        has_return = bool(self.RETURN_PATTERN.search(diff_snippet))
        has_raise = bool(self.RAISE_PATTERN.search(diff_snippet))

        callers_str = ", ".join(f"`{c}`" for c in inbound_callers[:3]) if inbound_callers else "call sites"

        # Case 1: Function / Method signature modified
        if has_def:
            return DeltaInferenceResult(
                change_summary="Method signature / parameter definitions modified.",
                remediation_guidance=f"Audit all call sites of `{entity_name}` ({callers_str}) to ensure argument compatibility with the updated parameter list.",
                justification_snippet="Parameter definitions altered, altering the callable contract.",
                is_signature_change=True,
            )

        # Case 2: Return value contract alteration
        if has_return:
            return DeltaInferenceResult(
                change_summary="Return value logic / returned payload altered.",
                remediation_guidance=f"Verify upstream callers ({callers_str}) expecting prior return types or values from `{entity_name}`.",
                justification_snippet="Return value semantics modified, risking downstream type mismatches.",
                is_return_change=True,
            )

        # Case 3: Exception flow alteration
        if has_raise:
            return DeltaInferenceResult(
                change_summary="Exception raising / error handling flow updated.",
                remediation_guidance=f"Update error handlers in upstream callers ({callers_str}) to catch or propagate new exception types.",
                justification_snippet="Exception raising updated, requiring caller error-handling audit.",
                is_exception_change=True,
            )

        # Case 4: Internal calculation / statements
        add_count = sum(1 for line in diff_snippet.splitlines() if line.startswith("+"))
        del_count = sum(1 for line in diff_snippet.splitlines() if line.startswith("-"))
        return DeltaInferenceResult(
            change_summary=f"Internal function execution statements updated (+{add_count} / -{del_count} lines).",
            remediation_guidance=f"Run unit and regression test suite across upstream callers ({callers_str}).",
            justification_snippet="Internal calculation logic altered while preserving signature contract.",
        )

    def synthesize_remediation_plan(
        self,
        signature_changed_entities: list[str],
        deleted_files: list[str],
        inbound_callers: list[str],
        downstream_files: list[str],
    ) -> list[RemediationStep]:
        """Synthesize prioritized 4-step remediation plan."""
        plan: list[RemediationStep] = []
        step_num = 1

        # Step 1: Contract Changes
        if signature_changed_entities:
            plan.append(
                RemediationStep(
                    step_number=step_num,
                    category="Contract Changes",
                    action_description=f"Adapt call sites for functions with altered signatures: {', '.join(signature_changed_entities)}.",
                    affected_targets=tuple(signature_changed_entities),
                )
            )
            step_num += 1

        # Step 2: Missing Modules
        if deleted_files:
            plan.append(
                RemediationStep(
                    step_number=step_num,
                    category="Missing Modules",
                    action_description=f"Audit imports and configuration references for deleted files: {', '.join(deleted_files)}.",
                    affected_targets=tuple(deleted_files),
                )
            )
            step_num += 1

        # Step 3: Direct Callers
        if inbound_callers:
            unique_callers = sorted(list(set(inbound_callers)))
            plan.append(
                RemediationStep(
                    step_number=step_num,
                    category="Direct Callers",
                    action_description=f"Execute unit and regression tests for all direct upstream callers: {', '.join(unique_callers)}.",
                    affected_targets=tuple(unique_callers),
                )
            )
            step_num += 1

        # Step 4: Integration Validation
        all_downstream = sorted(list(set(downstream_files)))
        plan.append(
            RemediationStep(
                step_number=step_num,
                category="Integration Validation",
                action_description=f"Run end-to-end integration and smoke tests across downstream dependent files: {', '.join(all_downstream) if all_downstream else 'all primary workflows'}.",
                affected_targets=tuple(all_downstream),
            )
        )

        return plan
