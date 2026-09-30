"""OpenRouter LLM reasoning engine for contextual architectural synthesis."""

from __future__ import annotations

import json
import re
from trace.analysis.reasoner.heuristic import HeuristicRuleEngine
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)


class OpenRouterLlmReasoner:
    """Invokes OpenRouter LLM API to enrich reasoning, with automatic fallback to heuristics."""

    OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(
        self,
        api_key: str,
        model: str = "anthropic/claude-3.5-sonnet",
        timeout_seconds: float = 15.0,
        fallback_engine: HeuristicRuleEngine | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model or "anthropic/claude-3.5-sonnet"
        self._timeout = timeout_seconds
        self._fallback = fallback_engine or HeuristicRuleEngine()

    def _extract_json(self, raw_content: str) -> dict[str, Any] | None:
        """Safely parse JSON from raw LLM output, handling markdown code fences."""
        cleaned = raw_content.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        try:
            return json.loads(cleaned)
        except Exception:
            m = re.search(r"(\{.*\})", cleaned, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(1))
                except Exception:
                    pass
        return None

    async def reason(
        self,
        entity_summary: dict[str, Any],
        diff_snippet: str,
        inbound_callers: tuple[str, ...],
        downstream_files: tuple[str, ...],
    ) -> dict[str, str]:
        """Query OpenRouter API for architectural reasoning, falling back to heuristics on failure."""
        entity_name = entity_summary.get("entity", "entity")
        file_path = entity_summary.get("file", "unknown")
        entity_type = entity_summary.get("entity_type", "function")

        prompt = {
            "entity": entity_name,
            "entity_type": entity_type,
            "file": file_path,
            "lines_affected": entity_summary.get("lines_affected"),
            "diff_snippet": diff_snippet[:350],
            "inbound_callers": list(inbound_callers),
            "downstream_files": list(downstream_files),
        }

        system_msg = (
            "You are an expert software architect analyzing code change impact. "
            "Analyze the given entity modification and return a JSON object with EXACTLY three string keys: "
            "'change_summary' (one clear sentence on what changed), "
            "'remediation_guidance' (actionable instructions for developers to update callers), "
            "'justification' (concise architectural rationale explaining why callers are at risk). "
            "Respond ONLY with valid JSON."
        )

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://trace.observatory",
            "X-Title": "TRACE Impact Engine",
        }

        body: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": f"Analyze this change:\n{json.dumps(prompt, indent=2)}"},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(self.OPENROUTER_URL, headers=headers, json=body)
                # If provider does not support response_format (common for free/community models like Nemotron)
                if resp.status_code == 400 and "response_format" in resp.text:
                    body.pop("response_format", None)
                    resp = await client.post(self.OPENROUTER_URL, headers=headers, json=body)

                if resp.status_code == 200:
                    data = resp.json()
                    raw_content = data["choices"][0]["message"]["content"]
                    parsed = self._extract_json(raw_content)
                    if (
                        parsed
                        and "change_summary" in parsed
                        and "remediation_guidance" in parsed
                        and "justification" in parsed
                    ):
                        return {
                            "change_summary": str(parsed["change_summary"]).strip(),
                            "remediation_guidance": str(parsed["remediation_guidance"]).strip(),
                            "justification": str(parsed["justification"]).strip(),
                        }
                else:
                    logger.warning(
                        "OpenRouter API call failed, falling back to heuristics",
                        status_code=resp.status_code,
                        model=self._model,
                        response=resp.text[:200],
                    )
        except Exception as exc:
            logger.warning(
                "OpenRouter LLM reasoning exception, falling back to heuristics",
                model=self._model,
                error=str(exc),
            )

        # Graceful fallback to deterministic rule engine
        return await self._fallback.reason(
            entity_summary=entity_summary,
            diff_snippet=diff_snippet,
            inbound_callers=inbound_callers,
            downstream_files=downstream_files,
        )

    async def synthesize_developer_directive(
        self,
        changed_entities: list[dict[str, Any]],
        callers_at_risk: list[dict[str, Any]],
        deleted_files: list[str],
        downstream_files: list[str],
    ) -> dict[str, Any]:
        """Generate a single unified developer directive explaining WHERE and WHAT changes need to be made."""
        compact_entities = [
            {
                "entity": e.get("entity"),
                "file": e.get("file"),
                "lines": e.get("lines_affected"),
                "summary": e.get("change_summary"),
            }
            for e in changed_entities[:8]
        ]
        compact_callers = [
            {
                "caller": c.get("qualified_name"),
                "file": c.get("file_path"),
                "distance": c.get("distance"),
            }
            for c in callers_at_risk[:10]
        ]

        system_msg = (
            "You are an expert software architect analyzing a code change impact report. "
            "Your task is to provide a concise, high-level developer action report telling the engineer exactly WHERE and WHAT changes need to be made across downstream callers and configuration files to adapt to these changes. "
            "Respond ONLY with a JSON object containing: "
            "'executive_summary' (1 clear sentence summarizing the overall changeset impact), "
            "'where_to_change' (list of specific files or components needing updates), "
            "'what_to_change' (list of concrete developer actions to take), "
            "'precautions' (list of critical risks or regression precautions). "
            "Keep answers concise and actionable. Respond ONLY with valid JSON."
        )

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://trace.observatory",
            "X-Title": "TRACE Impact Engine",
        }

        body: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_msg},
                {
                    "role": "user",
                    "content": f"Changeset context:\n{json.dumps({'changed_entities': compact_entities, 'callers_at_risk': compact_callers, 'deleted_files': deleted_files[:5], 'downstream_files': downstream_files[:8]}, indent=2)}",
                },
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(self.OPENROUTER_URL, headers=headers, json=body)
                if resp.status_code == 400 and "response_format" in resp.text:
                    body.pop("response_format", None)
                    resp = await client.post(self.OPENROUTER_URL, headers=headers, json=body)

                if resp.status_code == 200:
                    data = resp.json()
                    raw_content = data["choices"][0]["message"]["content"]
                    parsed = self._extract_json(raw_content)
                    if parsed and isinstance(parsed, dict) and "executive_summary" in parsed:
                        return {
                            "executive_summary": str(parsed.get("executive_summary", "")).strip(),
                            "where_to_change": [str(x) for x in parsed.get("where_to_change", [])],
                            "what_to_change": [str(x) for x in parsed.get("what_to_change", [])],
                            "precautions": [str(x) for x in parsed.get("precautions", [])],
                        }
        except Exception as exc:
            logger.warning(
                "OpenRouter developer directive synthesis failed, using fallback",
                model=self._model,
                error=str(exc),
            )

        # Fallback directive
        return {
            "executive_summary": f"Detected {len(changed_entities)} changed code entities impacting {len(callers_at_risk)} upstream callers.",
            "where_to_change": list(set([c.get("file_path") for c in callers_at_risk if c.get("file_path")] + [e.get("file") for e in changed_entities if e.get("file")])),
            "what_to_change": [
                f"Verify call sites and imports in {c.get('qualified_name', 'caller')} ({c.get('file_path', '')})"
                for c in callers_at_risk[:5]
            ],
            "precautions": ["Execute unit tests covering modified functions and direct callers."],
        }
