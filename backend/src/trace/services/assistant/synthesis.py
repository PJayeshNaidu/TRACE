"""LLM synthesis and deterministic fallback engine for TRACE AI Assistant (F10)."""

from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID

import httpx
import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from trace.core.config import ApplicationConfig
from trace.schemas.assistant import AssistantQueryRequest, AssistantQueryResponse, EvidenceSource
from trace.services.assistant.retrieval import (
    AssistantRetrievalService,
    CompactEvidenceBundle,
    DiffHunkEvidence,
    GraphNeighborEvidence,
    PlanStepEvidence,
    RiskItemEvidence,
)

logger = structlog.get_logger(__name__)

ASSISTANT_SYSTEM_PROMPT = (
    "You are the TRACE Code Intelligence Assistant, an expert software architecture peer. "
    "Your goal is to answer questions about codebase dependencies, architectural risks, and upgrade plans.\n\n"
    "CRITICAL OUTPUT RULES:\n"
    "1. Output ONLY the final user-facing response directly. NEVER output any chain-of-thought, thinking processes, planning notes, checklists, drafts, internal monologues (e.g. 'I will...', 'Check rules', 'Draft:'), or rule recitations.\n"
    "2. Be concise, direct, and helpful. Provide a direct, helpful, and natural response answering the question immediately.\n"
    "3. Ground all answers strictly in the provided context. Explicitly name the actual components/symbols, their architectural tiers/weights (e.g. Tier 2 - CORE_LOGIC), risk levels/scores, and callers at risk.\n"
    "4. Clearly distinguish between aggregate repository-level risk metrics and individual component risk scores.\n"
    "5. Only describe caller and dependency relationships that are explicitly supported by the evidence. Do not invent non-existent relationships.\n"
    "6. If evidence is missing for a requested symbol, explicitly state that no static analysis or graph records were found in the active run.\n"
    "7. NEVER mention 'JSON', 'provided context', 'system prompt', or internal schemas.\n"
    "8. Ensure all sentences and Markdown spans are complete and properly closed."
)

DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct:free"
OFFLINE_FALLBACK_MODEL = "offline-deterministic-fallback"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"


# ---------------------------------------------------------------------------
# LLM Response Sanitizer
# ---------------------------------------------------------------------------


def clean_llm_response(text: str) -> str:
    """Scrub chain-of-thought, internal planning notes, draft markers, and repair truncated markdown spans."""
    if not text:
        return ""

    cleaned = text.strip()

    # 1. Remove XML-style thinking tags (<think>...</think>, <thought>...</thought>, etc.)
    cleaned = re.sub(r"(?is)<think>.*?</think>", "", cleaned)
    cleaned = re.sub(r"(?is)<thought>.*?</thought>", "", cleaned)
    cleaned = re.sub(r"(?is)<scratchpad>.*?</scratchpad>", "", cleaned)

    # 2. Check for transition markers from planning/drafting to final answer
    marker_pattern = r"(?i)(?:^|\n)\s*(?:#{1,6}\s*)?(?:draft(?:\s+response|\s+answer)?|final\s+answer|final\s+response|formulate\s+response|formulate\s+answer|here's\s+(?:the\s+)?final\s+answer|actual\s+response)\s*:\s*"
    parts = re.split(marker_pattern, cleaned)
    if len(parts) > 1:
        cleaned = parts[-1].strip()

    # 3. Strip explicit thinking process blocks if remaining
    if "thinking process:" in cleaned.lower() or "analyze user input:" in cleaned.lower():
        cleaned = re.sub(r"(?is)^.*?(?:here's a thinking process|analyze user input):.*?(?=\n\s*#{1,6}\s+|\n\s*[A-Z][a-zA-Z\s]{2,}:|\n\s*`|\Z)", "", cleaned).strip()

    # 4. Strip leading internal monologue lines if model leaked self-talk before the answer
    lines = cleaned.splitlines()
    start_idx = 0
    in_planning_block = False

    planning_start_patterns = (
        r"(?i)^\s*(?:I'll\b|I will\b|Let's\b|Let me\b)",
        r"(?i)^\s*(?:Check\s+rules|Checking\s+rules|Review\s+rules|Rule\s+check)\b",
        r"(?i)^\s*(?:Structure\s+response|Response\s+structure|Formatting\s+plan)\b",
        r"(?i)^\s*(?:Thinking\s+process|Here's\s+a\s+thinking\s+process|Analyze\s+user\s+input|Reasoning)\b",
        r"(?i)^\s*(?:Plan|Notes|Internal\s+notes)\s*:\s*$",
        r"(?i)^\s*\"\s*(?:distinguish|explicitly|if evidence|never mention|output only|be helpful|answer strictly|rules?:)",
        r"(?i)^\s*[-*]\s*(?:I'll\b|I will\b|Check\b|Rule\b|Draft\b|Note\b|Step\b|\"\w+)",
    )

    for i, line in enumerate(lines):
        line_s = line.strip()
        if not line_s or line_s in ("**", "---", "***"):
            continue
        if any(re.search(p, line_s) for p in planning_start_patterns):
            in_planning_block = True
            continue
        if in_planning_block:
            if re.match(r"^(?:#{1,6}\s+|Based on|The highest|In this codebase|According to|Here are|- `|\d+\.\s+`|Repository-level|\*Repository)", line_s, re.IGNORECASE):
                start_idx = i
                break
            continue
        else:
            start_idx = i
            break

    if in_planning_block and start_idx > 0:
        cleaned = "\n".join(lines[start_idx:]).strip()

    # 5. Remove any remaining prefix like "Draft: " or "Final Answer: " on first line
    cleaned = re.sub(r"(?i)^(?:Draft|Final Answer|Answer|Response):\s*", "", cleaned).strip()

    # 6. Repair markdown code spans and backtick mismatches
    fence_count = len(re.findall(r"```", cleaned))
    if fence_count % 2 != 0:
        cleaned += "\n```"

    cleaned_lines: list[str] = []
    in_fence = False
    for line in cleaned.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            cleaned_lines.append(line)
            continue
        if not in_fence:
            bt_count = len(re.findall(r"(?<!\\)`", line))
            if bt_count % 2 != 0:
                line = line.rstrip() + "`"
        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines).strip()
    return cleaned


# ---------------------------------------------------------------------------
# Prompt Builder
# ---------------------------------------------------------------------------


class AssistantPromptBuilder:
    """Builds prompt messages grounded strictly in retrieved JSON evidence."""

    @classmethod
    def build_user_prompt(cls, question: str, bundle: CompactEvidenceBundle) -> str:
        """Construct user prompt containing serialized JSON evidence and question."""
        context_json = bundle.to_compact_json()

        prompt = (
            f"User Question: {question}\n\n"
            f"Available Project Context:\n"
            f"```json\n{context_json}\n```\n\n"
            "Provide a direct, helpful, and natural response. "
            "Do NOT output your thinking process, planning notes, or drafts. Output ONLY the final user-facing answer."
        )
        return prompt

    @classmethod
    def build_messages(
        cls, question: str, bundle: CompactEvidenceBundle
    ) -> list[dict[str, str]]:
        """Construct standard chat completion messages list."""
        return [
            {"role": "system", "content": ASSISTANT_SYSTEM_PROMPT},
            {"role": "user", "content": cls.build_user_prompt(question, bundle)},
        ]


# ---------------------------------------------------------------------------
# Deterministic Fallback Generator
# ---------------------------------------------------------------------------


class DeterministicFallbackGenerator:
    """Deterministic markdown generator used for offline mode, testing, and error recovery."""

    _TASK_NUM_PATTERN = re.compile(r"(?i)\btask[_\-\s]*(\d+)\b")

    @classmethod
    def generate(cls, question: str, bundle: CompactEvidenceBundle) -> str:
        """Format raw JSON evidence into readable markdown when LLM is unavailable."""
        # Empty state handling
        has_symbols = bool(bundle.matched_symbols)
        has_graph = bool(bundle.graph_paths)
        has_risk = bool(bundle.risk_items)
        has_plan = bool(bundle.plan_steps)
        has_diff = bool(bundle.diff_hunks)

        if not any([has_symbols, has_graph, has_risk, has_plan, has_diff]):
            return (
                f"No matching code symbols, graph dependencies, or plan steps were found "
                f"in the current analysis snapshot for query: **\"{question}\"**.\n\n"
                "Please verify that the symbol name, module path, or task identifier is spelled correctly, "
                "or check that the repository has been analyzed in TRACE."
            )

        # Check if question is a plan sequencing query (e.g. "Why does Task 1 precede Task 4?")
        task_nums = [int(m) for m in cls._TASK_NUM_PATTERN.findall(question)]
        if len(task_nums) >= 2 and has_plan:
            seq_explanation = cls._explain_plan_sequence(task_nums[0], task_nums[1], bundle.plan_steps)
            if seq_explanation:
                return seq_explanation + f"\n\n*(Generated via TRACE deterministic offline engine)*"

        sections: list[str] = []

        # 1. Queried Symbols Section
        if bundle.matched_symbols:
            symbols_str = ", ".join(f"`{s}`" for s in bundle.matched_symbols)
            sections.append(f"### 🎯 Identified Target Entities\n- **Symbols**: {symbols_str}")

        # 2. Graph Dependencies Section
        if bundle.graph_paths:
            graph_lines = ["### 🕸️ Dependency Graph Paths"]
            for g in bundle.graph_paths:
                file_info = f" *(in `{g.file_path}`)*" if g.file_path else ""
                graph_lines.append(
                    f"- **{g.depth}-hop [{g.relationship_kind}]**: `{g.source_symbol}` ➔ `{g.target_symbol}`{file_info}"
                )
            if bundle.total_graph_paths_count > len(bundle.graph_paths):
                remaining = bundle.total_graph_paths_count - len(bundle.graph_paths)
                graph_lines.append(f"- *... and {remaining} additional call graph path(s) omitted for budget.*")
            sections.append("\n".join(graph_lines))

        # 3. Risk Assessment Section
        if bundle.risk_items:
            risk_lines = ["### ⚠️ Assessed Risk Breakdown"]
            for r in bundle.risk_items:
                factors_str = ", ".join(r.factors) if r.factors else "None reported"
                recs_str = "; ".join(r.recommendations) if r.recommendations else "No specific remediation"
                loc = f" *(in `{r.file_path}`)*" if r.file_path else ""
                tier_str = f" | Tier {r.tier_number} - {r.tier_name} (Weight: {r.tier_number})" if r.tier_name and r.tier_number else (f" | [{r.tier}]" if r.tier else "")
                callers_str = f"\n  - *Callers at Risk*: {', '.join(f'`{c}`' for c in r.callers_at_risk)}" if r.callers_at_risk else ""
                risk_lines.append(
                    f"- **`{r.symbol_name}`**{loc}: Level **{r.risk_level}** (Score: `{r.risk_score:.1f}`){tier_str}\n"
                    f"  - *Contributing Factors*: {factors_str}{callers_str}\n"
                    f"  - *Recommendations*: {recs_str}"
                )
            sections.append("\n".join(risk_lines))

        # 4. Upgrade Plan Steps Section
        if bundle.plan_steps:
            plan_lines = ["### 📋 Upgrade Plan Sequence & Tasks"]
            for p in bundle.plan_steps:
                deps_str = ", ".join(f"Task {d}" for d in p.dependencies) if p.dependencies else "None (Root)"
                plan_lines.append(
                    f"- **{p.task_id} (Step {p.step_number})**: `{p.component}` [{p.tier}]\n"
                    f"  - *Status*: `{p.status}` | *Dependencies*: {deps_str}\n"
                    f"  - *Rationale*: {p.reason}"
                )
            sections.append("\n".join(plan_lines))

        # 5. Diff Hunks Section
        if bundle.diff_hunks:
            diff_lines = ["### 📝 AST Syntax & Diff Changes"]
            for d in bundle.diff_hunks:
                breaking_tag = " [BREAKING]" if d.is_breaking else ""
                diff_lines.append(
                    f"- **`{d.symbol_name}`** (`{d.change_type}`{breaking_tag}) in `{d.file_path}`: {d.summary}"
                )
            sections.append("\n".join(diff_lines))

        body = "\n\n".join(sections)
        return f"{body}\n\n*(Generated via TRACE deterministic offline engine)*"

    @classmethod
    def _explain_plan_sequence(
        cls, first_step_num: int, second_step_num: int, plan_steps: list[PlanStepEvidence]
    ) -> str | None:
        """Generate structured explanation for task sequencing."""
        step_map = {p.step_number: p for p in plan_steps}
        # Also map by task_id if needed
        for p in plan_steps:
            m = re.search(r"(\d+)", p.task_id)
            if m:
                step_map[int(m.group(1))] = p

        task_a = step_map.get(first_step_num)
        task_b = step_map.get(second_step_num)

        if not task_a or not task_b:
            return None

        # Check direct dependency
        is_direct_dep = (
            str(task_a.step_number) in task_b.dependencies
            or task_a.task_id in task_b.dependencies
            or any(str(task_a.step_number) in str(d) for d in task_b.dependencies)
        )

        lines = [
            f"### 📋 Upgrade Plan Sequence Rationale: Step {task_a.step_number} vs Step {task_b.step_number}",
            f"- **Preceding Task (Step {task_a.step_number})**: `{task_a.component}` (Tier: `{task_a.tier}`, Status: `{task_a.status}`)",
            f"- **Subsequent Task (Step {task_b.step_number})**: `{task_b.component}` (Tier: `{task_b.tier}`, Status: `{task_b.status}`)",
        ]

        if is_direct_dep:
            lines.append(
                f"\n**Ordering Rationale**: Step {task_b.step_number} (`{task_b.component}`) directly declares "
                f"Step {task_a.step_number} (`{task_a.component}`) as a prerequisite dependency. "
                f"Therefore, Step {task_a.step_number} must execute and stabilize first to satisfy structural contracts."
            )
        else:
            lines.append(
                f"\n**Ordering Rationale**: Step {task_a.step_number} is scheduled prior to Step {task_b.step_number} "
                f"based on topological DAG ordering and tier hierarchy (Tier `{task_a.tier}` precedes Tier `{task_b.tier}`)."
            )

        if task_a.reason:
            lines.append(f"- *Step {task_a.step_number} Goal*: {task_a.reason}")
        if task_b.reason:
            lines.append(f"- *Step {task_b.step_number} Goal*: {task_b.reason}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# OpenRouter Synthesis Service
# ---------------------------------------------------------------------------


class AssistantSynthesisService:
    """Invokes OpenRouter LLM or falls back to deterministic markdown generation."""

    def __init__(
        self,
        config: ApplicationConfig | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._config = config or ApplicationConfig()
        self._http_client = http_client

    async def synthesize(
        self, question: str, bundle: CompactEvidenceBundle
    ) -> tuple[str, str]:
        """Synthesize answer from compact evidence bundle.

        Returns:
            Tuple of (answer_text, model_used).
        """
        # If external calls are explicitly disabled in config, use offline fallback
        if not self._config.llm_enable_external_calls:
            logger.info(
                "Using deterministic offline assistant synthesis (external calls disabled)",
                has_key=bool(self._config.openrouter_api_key),
            )
            fallback_text = DeterministicFallbackGenerator.generate(question, bundle)
            return fallback_text, OFFLINE_FALLBACK_MODEL

        api_key = (
            self._config.openrouter_api_key.get_secret_value().strip()
            if self._config.openrouter_api_key
            else ""
        )
        if not api_key:
            import os
            api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()

        model = self._config.openrouter_model or DEFAULT_MODEL

        # If LLM unkeyed, use deterministic offline fallback immediately
        if not api_key:
            logger.info(
                "Using deterministic offline assistant synthesis (no API key provided)",
                has_key=False,
            )
            fallback_text = DeterministicFallbackGenerator.generate(question, bundle)
            return fallback_text, OFFLINE_FALLBACK_MODEL

        messages = AssistantPromptBuilder.build_messages(question, bundle)
        base_url = (
            str(self._config.openrouter_base_url).rstrip("/")
            if self._config.openrouter_base_url
            else "https://openrouter.ai/api/v1"
        )
        url = f"{base_url}/chat/completions"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "TRACE",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 2048,
        }

        # Candidate models to try if the primary model is deprecated or unavailable on OpenRouter
        models_to_try = [model]
        for fallback_m in ["meta-llama/llama-3.3-70b-instruct:free", "openrouter/free"]:
            if fallback_m not in models_to_try:
                models_to_try.append(fallback_m)

        for current_model in models_to_try:
            payload["model"] = current_model
            try:
                answer = await self._call_openrouter_with_retries(url, headers, payload)
                if answer and answer.strip():
                    return answer.strip(), current_model
            except Exception as exc:
                logger.error(
                    f"OpenRouter call failed for model '{current_model}': {exc}",
                    exc_info=True,
                    model=current_model,
                )

        logger.error("All OpenRouter candidate models failed or returned empty; using deterministic fallback engine")
        fallback_text = DeterministicFallbackGenerator.generate(question, bundle)
        return fallback_text, OFFLINE_FALLBACK_MODEL

    async def _call_openrouter_with_retries(
        self, url: str, headers: dict[str, str], payload: dict[str, Any]
    ) -> str | None:
        """Call OpenRouter chat completions with exponential retry on transient errors."""
        timeout = httpx.Timeout(15.0, connect=5.0)

        async def _attempt_request() -> str | None:
            if self._http_client and not self._http_client.is_closed:
                client = self._http_client
                resp = await client.post(url, json=payload, headers=headers, timeout=timeout)
            else:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(url, json=payload, headers=headers)

            if resp.status_code == 200:
                response_json = resp.json()
                choices = response_json.get("choices", [])
                if choices:
                    output_text = choices[0].get("message", {}).get("content", "")
                    if output_text:
                        cleaned = clean_llm_response(output_text)
                        return cleaned if cleaned else output_text.strip()
                return None

            if resp.status_code in (429, 500, 502, 503, 504):
                raise httpx.HTTPStatusError(
                    f"Transient OpenRouter status: {resp.status_code}",
                    request=resp.request,
                    response=resp,
                )

            logger.error(
                f"OpenRouter call failed with status {resp.status_code}: {resp.text}",
                status_code=resp.status_code,
                response_text=resp.text[:300],
            )
            return None

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential_jitter(initial=0.5, max=3.0),
            retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
            reraise=True,
        ):
            with attempt:
                return await _attempt_request()

        return None


# ---------------------------------------------------------------------------
# High-Level Assistant Orchestrator Service
# ---------------------------------------------------------------------------


class AssistantService:
    """Coordinates deterministic retrieval and synthesis for the AI Assistant."""

    def __init__(
        self,
        retrieval_service: AssistantRetrievalService,
        synthesis_service: AssistantSynthesisService | None = None,
        config: ApplicationConfig | None = None,
        tools: Any | None = None,
    ) -> None:
        self._retrieval_service = retrieval_service
        self._synthesis_service = synthesis_service or AssistantSynthesisService(config=config)
        self._config = config or ApplicationConfig()
        if tools is not None:
            self._tools = tools
        else:
            db_gw = getattr(retrieval_service, "_db", None)
            graph_gw = getattr(retrieval_service, "_graph", None)
            art_store = getattr(retrieval_service, "_artifact_store", None)
            if db_gw is not None and graph_gw is not None:
                from trace.services.assistant.tools import AssistantTools

                self._tools = AssistantTools(
                    db_gateway=db_gw,
                    graph_gateway=graph_gw,
                    artifact_store=art_store,
                )
            else:
                self._tools = None

    async def ask(self, request: AssistantQueryRequest) -> AssistantQueryResponse:
        """Execute retrieval and synthesis to answer a contextual code query."""
        logger.info(
            "Processing assistant query",
            project_id=str(request.project_id),
            analysis_run_id=str(request.analysis_run_id) if request.analysis_run_id else None,
            question=request.question,
        )

        if self._tools is not None:
            try:
                from trace.services.assistant.state import AssistantState
                from trace.services.assistant.workflow import build_assistant_graph

                workflow = build_assistant_graph(self._tools, self._synthesis_service)
                initial_state = AssistantState(
                    project_id=request.project_id,
                    analysis_run_id=request.analysis_run_id,
                    question=request.question,
                    history=request.history,
                )
                result = await workflow.ainvoke(initial_state)

                intents = result.get("intents") or ["GENERAL_OBSERVATORY"]
                primary_intent = intents[0] if intents else "GENERAL_OBSERVATORY"

                return AssistantQueryResponse(
                    answer=result.get("final_answer", ""),
                    intent=primary_intent,
                    sources=result.get("sources", []),
                    grounding_status=result.get("grounding_status", "FALLBACK_DETERMINISTIC"),
                    model_used=result.get("model_used", "offline-deterministic-fallback"),
                    suggested_followups=result.get("suggested_followups", []),
                )
            except Exception as exc:
                logger.warning(
                    "LangGraph workflow execution encountered an issue; falling back to baseline orchestrator",
                    error=str(exc),
                )
        # Baseline fallback for resilience or when tools are not initialized
        bundle = await self._retrieval_service.retrieve(
            question=request.question,
            project_id=request.project_id,
            analysis_run_id=request.analysis_run_id,
        )
        answer, model_used = await self._synthesis_service.synthesize(
            question=request.question, bundle=bundle
        )
        return AssistantQueryResponse(
            answer=answer,
            intent="GENERAL_OBSERVATORY",
            sources=bundle.sources,
            grounding_status="FALLBACK_DETERMINISTIC",
            model_used=model_used,
        )

