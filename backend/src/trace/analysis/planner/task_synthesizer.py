"""Task metadata and prescriptive guidance synthesis engine for F07 Upgrade Planner."""

from __future__ import annotations

import json
from trace.domain.plan import TaskCategory, TaskEvidence
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
    ) -> tuple[str, str, list[str], TaskEvidence]:
        """Synthesize reason, expected_changes, required_tests, and evidence for a component.

        Returns:
            Tuple of (reason, expected_changes, required_tests, evidence).
        """
        raw_impact = raw_impact or {}
        caller_info = caller_info or {}
        required_tests = list(test_associations or [])

        # 1. Synthesize Reason
        if raw_impact:
            summary = raw_impact.get("change_summary", "")
            justification = raw_impact.get("justification", "")
            if summary and justification:
                reason = f"{summary}. {justification}"
            elif summary:
                reason = summary
            elif justification:
                reason = justification
            else:
                reason = f"Component '{component}' modified directly in current changeset."
        elif caller_info:
            distance = caller_info.get("distance", 1)
            target = caller_info.get("target_entity", "callee")
            chain = caller_info.get("call_chain", ())
            chain_str = " ➜ ".join(chain) if chain else f"{component} ➜ {target}"
            reason = (
                f"Upstream caller at depth {distance} invoking '{target}' via chain ({chain_str}). "
                "Subject to breaking runtime or signature propagation."
            )
        else:
            reason = f"Component '{component}' requires updating as part of architectural upgrade."

        # 2. Synthesize Expected Changes
        if raw_impact:
            remediation = raw_impact.get("remediation_guidance", "")
            if remediation:
                expected_changes = remediation
            else:
                expected_changes = (
                    f"Update '{component}' implementation in '{file_path}' "
                    "to satisfy new specifications."
                )
        elif caller_info:
            target = caller_info.get("target_entity", "callee")
            expected_changes = (
                f"Audit invocation site for '{target}' in '{file_path}'. "
                "Verify parameters, return types, and exception handlers."
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
            # Infer plausible test targets if not provided explicitly
            if category == TaskCategory.INTEGRATION_TEST:
                required_tests.append(component)
            elif file_path:
                stem = file_path.rsplit("/", 1)[-1].replace(".py", "")
                required_tests.append(f"tests/test_{stem}.py")

        # 4. Synthesize Evidence
        diff_snippet = raw_impact.get("diff_snippet", "")
        lines = tuple(raw_impact.get("lines_affected", (0, 0)))
        call_chain = tuple(caller_info.get("call_chain", ()))
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
        """Construct prompt and messages payload for OpenRouter completion (T043)."""
        system_prompt = (
            "You are an expert software architect assisting in dependency-ordered "
            "codebase refactoring. Analyze the given component, diff snippet, and caller "
            "propagation to provide actionable refactoring instructions. Respond ONLY "
            "with valid JSON having keys: 'refined_reason', 'detailed_expected_changes', "
            "'recommended_tests'."
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
        model: str = "anthropic/claude-3.5-sonnet",
        diff_snippet: str = "",
        callers: list[str] | None = None,
        timeout_seconds: float = 10.0,
    ) -> tuple[str, str, list[str] | None]:
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
            "Authorization": f"Bearer {api_key}",
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
                            return refined_r, refined_c, rec_t
        except Exception as exc:
            logger.warning(
                "OpenRouter enrichment call failed, using heuristic baseline", error=str(exc)
            )

        return heuristic_reason, heuristic_changes, None
