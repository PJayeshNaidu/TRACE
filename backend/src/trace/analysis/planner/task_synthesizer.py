"""Task metadata and prescriptive guidance synthesis engine for F07 Upgrade Planner."""

from __future__ import annotations

import json
from trace.analysis.planner.tier_mapper import TierMapper
from trace.domain.plan import (
    InformationalChange,
    TaskActionType,
    TaskCategory,
    TaskEvidence,
    UpgradeTask,
)
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)


class TaskSynthesizer:
    """Synthesizes human-actionable reason, expected changes, required tests,
    and verified evidence.
    """

    @classmethod
    def synthesize_task_metadata(
        cls,
        component: str,
        category: TaskCategory,
        component_type: str = "function",
        file_path: str = "",
        raw_impact: dict[str, Any] | None = None,
        caller_info: dict[str, Any] | None = None,
        test_associations: list[str] | None = None,
        action_type: TaskActionType | str | None = None,
    ) -> tuple[str, str, list[str], TaskEvidence]:
        """Synthesize reason, expected_changes, required_tests, and evidence for a component.

        Returns:
            Tuple of (reason, expected_changes, required_tests, evidence).
        """
        raw_impact = raw_impact or {}
        caller_info = caller_info or {}
        required_tests = list(test_associations or [])

        diff_snippet = raw_impact.get("diff_snippet", "")
        lines = tuple(raw_impact.get("lines_affected", (0, 0)))
        call_chain = tuple(caller_info.get("call_chain", ()))

        # Detection of task nature
        is_doc_diff = bool(diff_snippet and TierMapper.is_documentation_diff(diff_snippet))
        is_doc_task = is_doc_diff or category == TaskCategory.DOCUMENTATION_CONFIG
        is_test_task = category == TaskCategory.INTEGRATION_TEST or (
            bool(file_path)
            and any(p in file_path.lower() for p in ("tests/", "/test/", "test_", "_test.py"))
        )

        # 1. Synthesize Reason
        if is_doc_task:
            if diff_snippet:
                reason = (
                    f"Documentation or comment-only update in '{component}'. "
                    "No executable logic or runtime behavior modified."
                )
            else:
                reason = (
                    f"Documentation or configuration update in '{component}'. "
                    "Non-executable changes."
                )
        elif is_test_task and raw_impact:
            summary = raw_impact.get("change_summary", "").strip()
            if summary:
                reason = f"Test suite or fixture modified in '{component}'. {summary}."
            else:
                reason = (
                    f"Test suite or fixture modified in '{component}'. "
                    "Ensures test coverage and assertions align with updated specifications."
                )
        elif raw_impact:
            summary = raw_impact.get("change_summary", "").strip()
            justification = raw_impact.get("justification", "").strip()
            if summary and justification:
                reason = f"Directly modified component '{component}'. {summary}. {justification}"
            elif summary:
                reason = f"Directly modified component '{component}'. {summary}."
            elif justification:
                reason = f"Directly modified component '{component}'. {justification}"
            else:
                reason = f"Directly modified component '{component}' in current changeset."
        elif caller_info:
            distance = caller_info.get("distance", 1)
            target = caller_info.get("target_entity", "callee")
            chain = caller_info.get("call_chain", ())
            chain_str = " ➜ ".join(chain) if chain else f"{component} ➜ ... ➜ {target}"
            if caller_info.get("is_doc_only"):
                reason = (
                    f"Caller of '{target}' in '{file_path}'. Note: '{target}' has only "
                    "documentation updates, no functional changes required."
                )
            elif distance <= 1:
                reason = (
                    f"Direct caller in '{file_path}' invoking modified component '{target}'. "
                    f"Directly affected by contract or implementation updates in '{target}'."
                )
            else:
                reason = (
                    f"Transitive caller at depth {distance} invoking '{target}' via "
                    f"call path ({chain_str}). Indirectly affected through call chain; "
                    "no incompatible direct usage was detected. "
                    "Regression/integration validation is recommended."
                )
        else:
            reason = f"Component '{component}' requires updating as part of architectural upgrade."

        # 2. Synthesize Expected Changes
        if is_doc_task:
            expected_changes = (
                f"Review docstring / documentation updates in '{file_path}' "
                "for technical accuracy and formatting. No code changes or test runs required."
            )
        elif is_test_task and raw_impact:
            expected_changes = (
                f"Execute test suite '{file_path}' to verify test assertions pass "
                "against updated implementations."
            )
        elif raw_impact:
            remediation = raw_impact.get("remediation_guidance", "").strip()
            if remediation:
                expected_changes = f"Update '{component}' in '{file_path}': {remediation}"
            else:
                expected_changes = (
                    f"Update implementation of '{component}' in '{file_path}' "
                    "to satisfy new specifications."
                )
        elif caller_info:
            distance = caller_info.get("distance", 1)
            target = caller_info.get("target_entity", "callee")
            chain = caller_info.get("call_chain", ())
            chain_str = " ➜ ".join(chain) if chain else f"{component} ➜ ... ➜ {target}"
            if caller_info.get("is_doc_only"):
                expected_changes = (
                    f"No functional changes needed for '{target}' in '{file_path}'. "
                    "Verify comments or docstrings if relevant."
                )
            elif distance <= 1:
                expected_changes = (
                    f"'{component}' must adapt to updated contract and signature of '{target}'. "
                    f"Audit direct call site of '{target}' in '{file_path}', update call "
                    "arguments, verify return value handling, and update affected tests."
                )
            else:
                expected_changes = (
                    f"Validate indirect invocation along call chain ({chain_str}). "
                    f"Verify indirect integration with '{target}' and run regression tests "
                    f"to prevent cascading breakage in '{file_path}'."
                )
        else:
            if category == TaskCategory.CONTRACT_API:
                expected_changes = (
                    f"Update API endpoint contract, route schemas, "
                    f"and response validation in '{file_path}'."
                )
            elif category == TaskCategory.DATA_MAPPING:
                expected_changes = (
                    f"Verify database column definitions, ORM attributes, "
                    f"and migration scripts in '{file_path}'."
                )
            elif category == TaskCategory.INTEGRATION_TEST:
                expected_changes = (
                    f"Update test assertions, test fixtures, and parameter mocks in '{file_path}'."
                )
            elif category == TaskCategory.DOCUMENTATION_CONFIG:
                expected_changes = (
                    f"Synchronize documentation, configuration values, "
                    f"and deployment manifests in '{file_path}'."
                )
            else:
                expected_changes = f"Review and adapt internal business logic in '{file_path}'."

        # 3. Required Tests
        if not required_tests:
            if is_doc_task:
                required_tests = []
            elif is_test_task:
                if file_path:
                    required_tests.append(file_path)
                else:
                    required_tests.append(component)
            elif file_path:
                stem = file_path.rsplit("/", 1)[-1].replace(".py", "")
                required_tests.append(f"tests/test_{stem}.py")

        # 4. Synthesize Evidence
        evidence = TaskEvidence(
            diff_snippet=diff_snippet,
            lines_affected=lines,
            call_chain=call_chain,
            file_path=file_path,
            target_symbol=component,
        )

        return reason, expected_changes, required_tests, evidence

    @classmethod
    def generate_llm_refactoring_prompt(
        cls,
        component: str,
        category: TaskCategory,
        component_type: str,
        file_path: str,
        heuristic_reason: str,
        heuristic_changes: str,
        diff_snippet: str = "",
        callers: list[str] | None = None,
    ) -> dict[str, Any]:
        """Construct prompt and messages payload for OpenRouter per-task review (T043)."""
        system_prompt = (
            "You are an expert senior software architect reviewing a dependency-ordered "
            "codebase refactoring task. Analyze the component, diff snippet, and caller "
            "propagation to provide actionable, high-signal developer guidance. "
            "Evaluate whether this change requires code action ('UPGRADE'), "
            "human inspection ('REVIEW'), is purely non-behavioral documentation "
            "('INFORMATIONAL'), or is a minor typo/formatting to ignore ('IGNORE').\n\n"
            "Also evaluate whether this entity requires a code change ('REQUIRED_CHANGE') "
            "or validation/testing only ('VALIDATION_ONLY').\n\n"
            "If you recommend tests, provide concrete test function or file paths "
            "(e.g. tests/test_app.py::test_request_context) rather than generic "
            "phrases like 'Run tests'.\n\n"
            "Respond ONLY with valid JSON having the keys:\n"
            "- 'refined_reason': string\n"
            "- 'detailed_expected_changes': string\n"
            "- 'recommended_tests': list of strings\n"
            "- 'actionability': 'UPGRADE' | 'REVIEW' | 'INFORMATIONAL' | 'IGNORE'\n"
            "- 'action_type': 'REQUIRED_CHANGE' | 'VALIDATION_ONLY' | "
            "'LOW_PRIORITY_REVIEW' | 'NO_ACTION'\n"
            "- 'confidence': 'HIGH' | 'MEDIUM' | 'LOW' (or float between 0.0 and 1.0)\n"
            "- 'explanation': string describing rationale"
        )
        user_content = (
            f"Component: {component} ({component_type})\n"
            f"Category: {category.value}\n"
            f"File: {file_path}\n"
            f"Baseline Reason: {heuristic_reason}\n"
            f"Baseline Expected Changes: {heuristic_changes}\n"
            f"Callers at risk: {', '.join(callers or [])}\n"
            f"Diff Snippet:\n{diff_snippet[:1500] if diff_snippet else 'N/A'}\n\n"
            "Provide concise, high-signal developer guidance in JSON format."
        )
        return {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "response_format": {"type": "json_object"},
        }

    @classmethod
    def parse_llm_enrichment(cls, raw_json_str: str) -> dict[str, Any] | None:
        """Parse and sanitize LLM response JSON."""
        try:
            cleaned = raw_json_str.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            data = json.loads(cleaned.strip())
            if isinstance(data, dict):
                return {
                    "reason": data.get("refined_reason"),
                    "expected_changes": data.get("detailed_expected_changes"),
                    "recommended_tests": data.get("recommended_tests"),
                    "actionability": data.get("actionability"),
                    "action_type": data.get("action_type"),
                    "confidence": data.get("confidence"),
                    "explanation": data.get("explanation"),
                }
        except Exception:
            pass
        return None

    @classmethod
    async def enrich_task_with_openrouter(
        cls,
        component: str,
        category: TaskCategory,
        component_type: str,
        file_path: str,
        heuristic_reason: str,
        heuristic_changes: str,
        api_key: str,
        model: str = "mistralai/mistral-7b-instruct:free",
        diff_snippet: str = "",
        callers: list[str] | None = None,
        timeout_seconds: float = 10.0,
    ) -> tuple[str, str, list[str] | None, dict[str, Any] | None]:
        """Call OpenRouter to enrich task guidance with graceful fallback on failure (T044)."""
        prompt_payload = cls.generate_llm_refactoring_prompt(
            component=component,
            category=category,
            component_type=component_type,
            file_path=file_path,
            heuristic_reason=heuristic_reason,
            heuristic_changes=heuristic_changes,
            diff_snippet=diff_snippet,
            callers=callers,
        )

        headers = {
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://trace.local",
            "X-Title": "TRACE Upgrade Planner",
        }
        body = {
            "model": model,
            "messages": prompt_payload["messages"],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }

        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions", json=body, headers=headers
                )
                if resp.status_code == 200:
                    resp_json = resp.json()
                    choices = resp_json.get("choices", [])
                    if choices:
                        content = choices[0].get("message", {}).get("content", "")
                        parsed = cls.parse_llm_enrichment(content)
                        if parsed:
                            refined_r = parsed.get("reason") or heuristic_reason
                            refined_c = parsed.get("expected_changes") or heuristic_changes
                            rec_t = parsed.get("recommended_tests")
                            ai_review = {
                                "actionability": parsed.get("actionability"),
                                "action_type": parsed.get("action_type"),
                                "confidence": parsed.get("confidence"),
                                "explanation": parsed.get("explanation"),
                            }
                            return refined_r, refined_c, rec_t, ai_review
        except Exception as exc:
            logger.warning(
                "OpenRouter enrichment call failed, using heuristic baseline", error=str(exc)
            )

        return heuristic_reason, heuristic_changes, None, None

    @classmethod
    def generate_whole_plan_review_prompt(
        cls,
        tasks: list[UpgradeTask],
        informational_changes: list[InformationalChange] | None = None,
        repository_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Construct prompt and messages payload for whole-plan LLM review."""
        system_prompt = (
            "You are a senior software architect conducting an engineering peer review "
            "of an upgrade plan. Evaluate the overall revision significance, whether an upgrade "
            "plan is warranted, and the necessity of each candidate task.\n\n"
            "Key questions to assess:\n"
            "1. What actually changed? Is the revision MAJOR_CHANGE, MODERATE_CHANGE, "
            "MINOR_CHANGE, or NO_ACTION_REQUIRED?\n"
            "2. Is an active coordinated upgrade plan required, or is no major upgrade work "
            "needed?\n"
            "3. Why is this sequence ordered in this specific way (order_rationale)?\n"
            "4. For each task, does it genuinely require code changes ('REQUIRED_CHANGE') "
            "or validation only ('VALIDATION_ONLY')?\n"
            "5. What low-priority suggestions (e.g. docs, formatting) should be noted "
            "separately?\n\n"
            "Respond ONLY with valid JSON having the exact keys:\n"
            "- 'change_significance': 'MAJOR_CHANGE' | 'MODERATE_CHANGE' | 'MINOR_CHANGE' | "
            "'NO_ACTION_REQUIRED'\n"
            "- 'significance_reasoning': string explaining the semantic impact\n"
            "- 'recommended_action': string (e.g. 'A coordinated upgrade is recommended.' or "
            "'No major upgrade work required.')\n"
            "- 'order_rationale': string explaining why this ordering is safe\n"
            "- 'optional_suggestions': list of strings (advisory non-task suggestions)\n"
            "- 'sequence_valid': boolean\n"
            "- 'confidence': float (between 0.0 and 1.0) or string ('HIGH', 'MEDIUM', 'LOW')\n"
            "- 'task_evaluations': list of objects {'component': str, 'action_type': "
            "'REQUIRED_CHANGE'|'VALIDATION_ONLY'|'LOW_PRIORITY_REVIEW'|'NO_ACTION', "
            "'reason': str}\n"
            "- 'warnings': list of strings\n"
            "- 'unnecessary_tasks': list of objects {'component': str, 'reason': str, "
            "'confidence': float|str}\n"
            "- 'missing_task_suggestions': list of objects {'component': str, 'reason': str, "
            "'confidence': float|str}\n"
            "- 'test_recommendations': list of objects {'component': str, "
            "'recommended_tests': list[str], 'is_verified': bool}\n"
            "- 'actionability_reviews': list of objects {'component': str, "
            "'suggested_actionability': 'IGNORE'|'INFORMATIONAL'|'REVIEW'|'UPGRADE', "
            "'reason': str, 'confidence': float|str}"
        )

        task_lines = []
        for t in tasks:
            deps_str = ", ".join(t.dependencies) if t.dependencies else "None"
            tests_str = ", ".join(t.required_tests) if t.required_tests else "None"
            ev_snippet = (
                t.evidence.diff_snippet[:300] if t.evidence and t.evidence.diff_snippet else "N/A"
            ).replace("\n", " ")
            task_lines.append(
                f"Step {t.step_number}: Component='{t.component}' "
                f"({t.component_type}, {t.category.value})\n"
                f"  Reason: {t.reason}\n"
                f"  Prerequisites: {deps_str}\n"
                f"  Expected: {t.expected_changes}\n"
                f"  Tests: {tests_str}\n"
                f"  Diff: {ev_snippet}"
            )

        info_lines = []
        for ic in informational_changes or []:
            info_lines.append(f"- '{ic.component}' ({ic.category.value}): {ic.reason}")

        user_content = (
            f"=== UPGRADE PLAN UNDER REVIEW ===\n"
            f"Total Tasks: {len(tasks)}\n\n"
            f"--- ORDERED TASKS ---\n"
            + ("\n".join(task_lines) if task_lines else "No upgrade tasks.")
            + "\n\n--- INFORMATIONAL / NON-BEHAVIORAL CHANGES ---\n"
            + ("\n".join(info_lines) if info_lines else "None")
            + "\n\nProvide your senior architectural review strictly in JSON format."
        )

        return {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "response_format": {"type": "json_object"},
        }

    @classmethod
    def parse_plan_review_response(cls, raw_json_str: str) -> dict[str, Any] | None:
        """Parse and sanitize whole-plan LLM review JSON."""
        try:
            cleaned = raw_json_str.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            data = json.loads(cleaned.strip())
            if isinstance(data, dict):
                conf = data.get("confidence", 0.9)
                if isinstance(conf, (int, float)):
                    conf = round(float(conf), 2)

                raw_evals = (
                    data.get("task_assessments")
                    or data.get("task_evaluations")
                    or []
                )
                formatted_evals = []
                if isinstance(raw_evals, list):
                    for item in raw_evals:
                        if isinstance(item, dict):
                            comp = item.get("entity") or item.get("component") or ""
                            act = item.get("action") or item.get("action_type") or ""
                            formatted_evals.append({
                                "component": comp,
                                "entity": comp,
                                "action_type": act,
                                "action": act,
                                "reason": item.get("reason", ""),
                                "risk": item.get("risk"),
                                "recommended_changes": item.get("recommended_changes", []),
                                "recommended_tests": item.get("recommended_tests", []),
                                "confidence": item.get("confidence", 1.0),
                            })

                raw_suggs = (
                    data.get("low_priority_suggestions")
                    or data.get("optional_suggestions")
                    or []
                )
                suggestions = [str(s) for s in raw_suggs] if isinstance(raw_suggs, list) else []

                sig_reasoning = (
                    data.get("overall_reason")
                    or data.get("significance_reasoning")
                    or ""
                )
                order_rat = (
                    data.get("sequence_guidance")
                    or data.get("order_rationale")
                    or ""
                )

                return {
                    "change_significance": data.get("change_significance"),
                    "significance_reasoning": sig_reasoning,
                    "recommended_action": data.get("recommended_action"),
                    "order_rationale": order_rat,
                    "optional_suggestions": suggestions,
                    "task_evaluations": formatted_evals,
                    "sequence_valid": bool(data.get("sequence_valid", True)),
                    "confidence": conf,
                    "warnings": [str(w) for w in data.get("warnings", [])],
                    "unnecessary_tasks": list(data.get("unnecessary_tasks", [])),
                    "missing_task_suggestions": list(data.get("missing_task_suggestions", [])),
                    "test_recommendations": list(data.get("test_recommendations", [])),
                    "actionability_reviews": list(data.get("actionability_reviews", [])),
                }
        except Exception:
            pass
        return None

    @classmethod
    async def review_whole_plan_with_openrouter(
        cls,
        tasks: list[UpgradeTask],
        informational_changes: list[InformationalChange] | None = None,
        repository_context: dict[str, Any] | None = None,
        api_key: str = "",
        model: str = "mistralai/mistral-7b-instruct:free",
        timeout_seconds: float = 15.0,
    ) -> dict[str, Any] | None:
        """Call OpenRouter for whole-plan architecture review with graceful offline fallback."""
        if not api_key or not api_key.strip():
            return None

        prompt_payload = cls.generate_whole_plan_review_prompt(
            tasks=tasks,
            informational_changes=informational_changes,
            repository_context=repository_context,
        )

        headers = {
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://trace.local",
            "X-Title": "TRACE Upgrade Planner",
        }
        body = {
            "model": model,
            "messages": prompt_payload["messages"],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }

        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    json=body,
                    headers=headers,
                )
                if resp.status_code == 200:
                    resp_json = resp.json()
                    choices = resp_json.get("choices", [])
                    if choices:
                        content = choices[0].get("message", {}).get("content", "")
                        parsed = cls.parse_plan_review_response(content)
                        if parsed:
                            # Validate missing task suggestions against repository context
                            verified_suggestions = []
                            known_components = {t.component for t in tasks}
                            if repository_context and "known_files" in repository_context:
                                known_files = set(repository_context["known_files"])
                            else:
                                known_files = set()

                            for sug in parsed.get("missing_task_suggestions", []):
                                comp = sug.get("component", "")
                                is_verified = bool(
                                    comp in known_files or any(comp in c for c in known_components)
                                )
                                sug["is_verified"] = is_verified
                                verified_suggestions.append(sug)
                                if not is_verified:
                                    parsed["warnings"].append(
                                        f"AI suggested missing component '{comp}', but it is not "
                                        "verified in repository AST evidence. "
                                        "Retained as advisory suggestion."
                                    )
                            parsed["missing_task_suggestions"] = verified_suggestions
                            return parsed
                else:
                    logger.warning(
                        "OpenRouter whole-plan review returned non-200",
                        status_code=resp.status_code,
                    )
        except Exception as exc:
            logger.warning(
                "OpenRouter whole-plan review call failed, continuing with deterministic plan",
                error=str(exc),
            )

        return None
