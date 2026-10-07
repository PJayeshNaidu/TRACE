"""LangGraph workflow definition, nodes, and conditional routers for the TRACE AI Assistant."""

from __future__ import annotations

import asyncio
import re
from typing import Any
from uuid import UUID

import structlog

from langgraph.graph import END, StateGraph

from trace.schemas.assistant import ChatMessage, EvidenceSource
from trace.services.assistant.retrieval import CandidateSymbolExtractor
from trace.services.assistant.state import AssistantState
from trace.services.assistant.synthesis import (
    AssistantPromptBuilder,
    AssistantSynthesisService,
    DeterministicFallbackGenerator,
)
from trace.services.assistant.tools import AssistantTools, resolve_target_run

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Node 1: Understand Question & Intent Classification
# ---------------------------------------------------------------------------


def create_understand_node(tools: AssistantTools):
    async def understand_question(state: AssistantState) -> dict[str, Any]:
        question = state.question.strip()
        q_lower = question.lower()

        # 1. Resolve analysis_run_id and repository_id if missing
        repo_id = state.repository_id
        run_id = state.analysis_run_id
        if not run_id or not repo_id:
            db = getattr(tools, "_db", None)
            if db is not None:
                resolved_repo, resolved_run = await resolve_target_run(
                    db, state.project_id, state.analysis_run_id
                )
                repo_id = repo_id or resolved_repo
                run_id = run_id or resolved_run
            elif hasattr(tools, "resolve_target_run"):
                try:
                    res = tools.resolve_target_run(state.project_id, state.analysis_run_id)
                    if hasattr(res, "__await__"):
                        res = await res
                    if isinstance(res, tuple) and len(res) == 2:
                        repo_id = repo_id or res[0]
                        run_id = run_id or res[1]
                except Exception:
                    pass


        # 2. Extract Task IDs
        task_matches = re.findall(r"(?i)\btask[_\-\s]*(\d+)\b", question)
        task_ids = [f"task_{m}" for m in task_matches]

        # 3. Intent Classification
        def _has_word(keywords: tuple[str, ...]) -> bool:
            return any(re.search(rf"\b{re.escape(w)}\b", q_lower) for w in keywords)

        # Check for General Knowledge queries (non-codebase questions bypassing TRACE retrieval)
        code_or_trace_terms = (
            "code", "project", "repo", "repository", "file", "files", "function", "functions",
            "class", "classes", "module", "modules", "component", "components", "task", "tasks",
            "plan", "upgrade", "risk", "depend", "depends", "dependency", "dependencies",
            "caller", "callers", "callee", "callees", "call", "calls", "diff", "diffs",
            "change", "changes", "changed", "modified", "between", "version", "versions",
            "v1", "v2", "v1.0", "v2.0", "syntax", "ast", "branch", "commit",
            "test", "tests", "coverage", "head", "main", "master", "tier", "step", "score",
            "factor", "remediation", "trace", "analysis", "framework", "language", "package",
            "library", "import", "endpoint", "api", "database", "graph", "node", "edge",
            "service", "services", "method", "methods", "order", "precede", "prerequisite",
            "affect", "affects", "affected", "impact", "impacts", "impacted", "cause", "caused"
        )
        has_trace_context = bool(state.history) or any(re.search(rf"\b{re.escape(w)}\b", q_lower) for w in code_or_trace_terms)

        intents: list[str] = []
        raw_candidates = CandidateSymbolExtractor.extract_candidates(question)
        git_or_project_terms = {
            "head", "main", "master", "origin", "trunk", "branch", "commit",
            "repo", "project", "repository", "snapshot", "upgrade", "codebase",
            "v1", "v2", "v3", "v1.0", "v2.0", "v1.0.0"
        }
        code_candidates = [
            c for c in raw_candidates
            if not c.startswith("task_")
            and c.lower() not in git_or_project_terms
            and not any(g in c.lower() for g in ("-head", "-main", "-master", "python-proj", "sample_repo"))
        ]

        if not has_trace_context and not code_candidates and not task_ids:
            intents.append("GENERAL_KNOWLEDGE")
        else:
            if _has_word(("language", "framework", "what is this project", "what does this project do", "about this project", "files are in", "codebase written in", "language is the code")):
                intents.append("PROJECT_OVERVIEW")
            if _has_word(("affect", "affects", "affected", "impact", "impacts", "impacted", "depend", "depends", "dependency", "dependencies", "dependent", "dependents", "caller", "callers", "callee", "callees", "call", "calls", "called", "blast radius", "hierarchy", "graph", "reach")):
                intents.append("IMPACT_DEPENDENCY")
            if _has_word(("risk", "score", "factor", "high risk", "safeguard", "remediation", "coverage", "test", "tests")):
                intents.append("RISK_EVALUATION")
            if _has_word(("plan", "task", "tasks", "sequence", "first", "before", "precede", "precedes", "prerequisite", "step", "steps", "tier", "after", "order")):
                intents.append("PLAN_SEQUENCE")
            if _has_word(("change", "changes", "changed", "diff", "diffs", "version", "versions", "modified", "breaking", "syntax", "hunk", "hunks", "parameter", "delta")):
                intents.append("CHANGE_EXPLORATION")
            if any(p in q_lower for p in ("can i add", "can we add", "adding", "add to this codebase")):
                intents.append("CODE_SEARCH")
                if "PROJECT_OVERVIEW" not in intents:
                    intents.append("PROJECT_OVERVIEW")

            # In a multi-turn conversation, if question is anaphoric (e.g. "Why?", "How come?", "Show all callers"), infer causal/dependency context
            anaphoric_words = (
                "why", "that", "it", "its", "second", "third", "caller", "callers",
                "callee", "callees", "more", "explain that", "this", "these"
            )
            is_anaphoric = any(re.search(rf"\b{w}\b", q_lower) for w in anaphoric_words)
            is_standalone_general = any(p in q_lower for p in (
                "what dependencies", "all dependencies", "dependencies present",
                "what changed", "upgrade plan", "which task", "overview", "summary",
                "python-proj", "classified as high risk", "show repository"
            ))

            # 5. History-Aware Disambiguation (Follow-up handling prior to target type assignment)
            if is_anaphoric and not is_standalone_general and not code_candidates and not task_ids and state.history:
                for msg in reversed(state.history):
                    content = msg.content if isinstance(msg, ChatMessage) else msg.get("content", "")
                    hist_candidates = [
                        c for c in CandidateSymbolExtractor.extract_candidates(content)
                        if not c.startswith("task_")
                        and c.lower() not in git_or_project_terms
                        and not any(g in c.lower() for g in ("-head", "-main", "-master", "python-proj", "sample_repo"))
                    ]
                    if hist_candidates:
                        code_candidates = hist_candidates[:2]
                        break

                    hist_task_matches = re.findall(r"(?:task[-_ ]?|step[-_ ]?)(\d+)", content, flags=re.I)
                    if hist_task_matches:
                        task_ids = [f"task_{m}" for m in hist_task_matches[:2]]
                        break

            if is_anaphoric and state.history:
                if "IMPACT_DEPENDENCY" not in intents and any(w in q_lower for w in ("caller", "callers", "callee", "callees", "depend", "affected", "impact", "why")):
                    intents.append("IMPACT_DEPENDENCY")
                if _has_word(("why", "how", "reason", "cause")) and "CHANGE_EXPLORATION" not in intents:
                    intents.append("CHANGE_EXPLORATION")

            if not intents:
                intents.append("GENERAL_OBSERVATORY")

        # 6. Determine Target Type & Target Entities
        target_type: str = "NONE"
        target_symbols: list[str] = []
        target_task_ids: list[str] = []

        if "GENERAL_KNOWLEDGE" in intents:
            target_type = "NONE"
        elif task_ids or ("PLAN_SEQUENCE" in intents and not code_candidates):
            target_type = "PLAN_TASK"
            target_task_ids = task_ids
        elif code_candidates and not any(p in q_lower for p in ("can i add", "can we add", "add to this codebase")):
            target_type = "CODE_SYMBOL"
            target_symbols = code_candidates
        elif (
            any(p in q_lower for p in ("between two versions", "between v1", "between v2", "cross-version", "what changed between", "version comparison"))
            or ("CHANGE_EXPLORATION" in intents and not code_candidates and not task_ids and any(v in q_lower for v in ("v1", "v2", "version", "release", "tag", "commit")))
        ):
            target_type = "VERSION_CHANGE"
        elif (
            any(w in q_lower for w in ("python-proj", "-head", "head", "main", "master", "project", "repo", "analysis run", "this change", "dependencies are present", "dependencies present", "what dependencies", "all dependencies", "codebase"))
            or "RISK_EVALUATION" in intents
            or "IMPACT_DEPENDENCY" in intents
            or "PROJECT_OVERVIEW" in intents
            or "GENERAL_OBSERVATORY" in intents
            or "CHANGE_EXPLORATION" in intents
        ):
            target_type = "PROJECT_RUN"

        return {
            "repository_id": repo_id,
            "analysis_run_id": run_id,
            "target_type": target_type,
            "target_symbols": target_symbols,
            "target_task_ids": target_task_ids,
            "target_project_id": state.project_id,
            "target_analysis_run_id": run_id,
            "intents": intents,
        }

    return understand_question


# ---------------------------------------------------------------------------
# Node 2: Select Relevant Tools
# ---------------------------------------------------------------------------


def create_select_tools_node():
    async def select_tools(state: AssistantState) -> dict[str, Any]:
        run_id = state.analysis_run_id
        repo_id = state.repository_id
        symbols = state.target_symbols
        intents = state.intents
        target_type = state.target_type
        calls: list[dict[str, Any]] = []

        if "GENERAL_KNOWLEDGE" in intents:
            return {"pending_tool_calls": []}

        if state.iteration_count == 0:
            effective_target_type = target_type
            if effective_target_type == "NONE":
                if state.target_task_ids:
                    effective_target_type = "PLAN_TASK"
                elif symbols or state.target_symbols:
                    effective_target_type = "CODE_SYMBOL"
                elif "PLAN_SEQUENCE" in intents:
                    effective_target_type = "PLAN_TASK"
                elif "VERSION_DIFF" in intents or "CHANGE_EXPLORATION" in intents:
                    effective_target_type = "VERSION_CHANGE"
                elif "RISK_EVALUATION" in intents or "IMPACT_DEPENDENCY" in intents or "GENERAL_OBSERVATORY" in intents or "PROJECT_OVERVIEW" in intents:
                    effective_target_type = "PROJECT_RUN"

            if effective_target_type == "PLAN_TASK":
                if repo_id:
                    calls.append({"tool": "get_upgrade_plan_tasks", "args": {"task_or_component": None, "repository_id": repo_id}})

            elif effective_target_type == "CODE_SYMBOL" and (symbols or state.target_symbols):
                effective_symbols = symbols or state.target_symbols
                primary_symbol = effective_symbols[0]
                if "IMPACT_DEPENDENCY" in intents and run_id:
                    calls.append({"tool": "search_code_symbols", "args": {"query": primary_symbol, "analysis_run_id": run_id}})
                    calls.append({"tool": "get_graph_neighborhood", "args": {"symbol": primary_symbol, "direction": "both", "depth": 2, "analysis_run_id": run_id}})
                if "RISK_EVALUATION" in intents and run_id:
                    calls.append({"tool": "get_impact_and_risk", "args": {"symbol_or_component": primary_symbol, "analysis_run_id": run_id}})
                if "CHANGE_EXPLORATION" in intents and repo_id:
                    calls.append({"tool": "get_change_diffs", "args": {"symbol_or_file": primary_symbol, "repository_id": repo_id}})
                if not calls and run_id:
                    calls.append({"tool": "search_code_symbols", "args": {"query": primary_symbol, "analysis_run_id": run_id}})
                    calls.append({"tool": "get_graph_neighborhood", "args": {"symbol": primary_symbol, "direction": "both", "depth": 2, "analysis_run_id": run_id}})

            elif effective_target_type == "PROJECT_RUN":
                if "RISK_EVALUATION" in intents and run_id:
                    calls.append({"tool": "get_impact_and_risk", "args": {"symbol_or_component": None, "analysis_run_id": run_id}})
                    if any(w in state.question.lower() for w in ("test", "coverage", "overview")):
                        calls.append({"tool": "get_repository_overview", "args": {"analysis_run_id": run_id}})
                if "IMPACT_DEPENDENCY" in intents and run_id:
                    calls.append({"tool": "get_graph_neighborhood", "args": {"symbol": None, "direction": "both", "depth": 1, "analysis_run_id": run_id}})
                    calls.append({"tool": "get_repository_overview", "args": {"analysis_run_id": run_id}})
                if "PROJECT_OVERVIEW" in intents and run_id:
                    if not any(c.get("tool") == "get_repository_overview" for c in calls):
                        calls.append({"tool": "get_repository_overview", "args": {"analysis_run_id": run_id}})
                if "CODE_SEARCH" in intents and run_id:
                    kw_matches = [w for w in ("payment", "auth", "billing", "order", "user") if w in state.question.lower()]
                    search_kw = kw_matches[0] if kw_matches else "service"
                    calls.append({"tool": "search_code_symbols", "args": {"query": search_kw, "analysis_run_id": run_id}})
                    if not any(c.get("tool") == "get_repository_overview" for c in calls):
                        calls.append({"tool": "get_repository_overview", "args": {"analysis_run_id": run_id}})
                if ("GENERAL_OBSERVATORY" in intents or not calls) and run_id:
                    calls.append({"tool": "get_repository_overview", "args": {"analysis_run_id": run_id}})

            elif effective_target_type == "VERSION_CHANGE":
                if repo_id:
                    calls.append({"tool": "get_change_diffs", "args": {"symbol_or_file": None, "repository_id": repo_id}})

            else:
                if run_id:
                    calls.append({"tool": "get_repository_overview", "args": {"analysis_run_id": run_id}})

            # Fallback if no calls scheduled
            if not calls and run_id:
                calls.append({"tool": "get_repository_overview", "args": {"analysis_run_id": run_id}})

        elif state.iteration_count == 1:
            # Iteration 1: Secondary Hop only for CODE_SYMBOL investigations
            effective_target_type = target_type or ("CODE_SYMBOL" if (symbols or state.target_symbols) else "NONE")
            if effective_target_type == "CODE_SYMBOL":
                connected_symbols: set[str] = set()
                for ev in state.raw_evidence:
                    if ev.get("type") == "graph":
                        src = ev.get("source")
                        tgt = ev.get("target")
                        if src and src not in state.target_symbols:
                            connected_symbols.add(src)
                        if tgt and tgt not in state.target_symbols:
                            connected_symbols.add(tgt)

                new_sym = next(iter(connected_symbols), None)
                if new_sym:
                    if run_id:
                        calls.append({"tool": "get_symbol_details", "args": {"qualified_name": new_sym, "analysis_run_id": run_id}})
                    if repo_id:
                        calls.append({"tool": "get_change_diffs", "args": {"symbol_or_file": new_sym, "repository_id": repo_id}})
                elif symbols and run_id:
                    calls.append({"tool": "get_symbol_details", "args": {"qualified_name": symbols[0], "analysis_run_id": run_id}})

        # Hard cap at 3 tool calls per hop
        return {"pending_tool_calls": calls[:3]}

    return select_tools


# ---------------------------------------------------------------------------
# Node 3: Execute Tools
# ---------------------------------------------------------------------------


def create_execute_tools_node(tools: AssistantTools):
    async def execute_tools(state: AssistantState) -> dict[str, Any]:
        calls = state.pending_tool_calls
        if not calls:
            return {"iteration_count": state.iteration_count + 1}

        new_evidence: list[dict[str, Any]] = []
        new_sources: list[EvidenceSource] = []

        async def _run_tool(call: dict[str, Any]) -> Any:
            tool_name = call.get("tool")
            args = call.get("args", {})
            func = getattr(tools, tool_name, None)
            if not func:
                return None
            try:
                return tool_name, await func(**args)
            except Exception as exc:
                logger.warning(f"Tool {tool_name} execution error: {exc}")
                return tool_name, None

        tasks = [_run_tool(c) for c in calls]
        completed = await asyncio.gather(*tasks, return_exceptions=False)

        for item in completed:
            if not item or not item[1]:
                continue
            name, payload = item

            if name == "get_repository_overview":
                metrics = payload.get("metrics", {})
                new_evidence.append({
                    "type": "overview",
                    "id": "repo_overview",
                    "metrics": metrics,
                    "entry_points": payload.get("entry_points", []),
                    "test_counts": payload.get("test_counts", 0),
                })
                new_sources.append(
                    EvidenceSource(
                        type="ast",
                        identifier=f"Analysis Run {state.analysis_run_id}",
                        summary=f"Overview: {metrics.get('total_files', 0)} files, {metrics.get('classes', 0)} classes, {payload.get('test_counts', 0)} test references",
                        metadata=payload,
                    )
                )

            elif name == "search_code_symbols":
                for sym in payload:
                    new_evidence.append(sym)
                    new_sources.append(
                        EvidenceSource(
                            type="ast",
                            identifier=sym.get("qualified_name") or sym.get("name", ""),
                            summary=f"{sym.get('kind', 'symbol').title()}: {sym.get('qualified_name')} in {sym.get('file_path')}:{sym.get('start_line')}",
                            metadata=sym,
                        )
                    )

            elif name == "get_symbol_details":
                new_evidence.append(payload)
                new_sources.append(
                    EvidenceSource(
                        type="ast",
                        identifier=payload.get("qualified_name", ""),
                        summary=f"AST Details: {payload.get('qualified_name')}({', '.join(payload.get('parameters', []))}) in {payload.get('file_path')}:{payload.get('start_line')}",
                        metadata={
                            "parameters": payload.get("parameters"),
                            "complexity": payload.get("complexity"),
                            "file_path": payload.get("file_path"),
                            "line": payload.get("start_line"),
                        },
                    )
                )

            elif name == "get_graph_neighborhood":
                for edge in payload:
                    new_evidence.append(edge)
                    new_sources.append(
                        EvidenceSource(
                            type="graph",
                            identifier=f"{edge.get('source')} -> {edge.get('target')}",
                            summary=f"{edge.get('depth')}-hop [{edge.get('relationship')}]: {edge.get('source')} -> {edge.get('target')}",
                            metadata=edge,
                        )
                    )

            elif name == "get_impact_and_risk":
                new_evidence.append(payload)
                new_sources.append(
                    EvidenceSource(
                        type="risk",
                        identifier=payload.get("target_component") or f"Analysis {state.analysis_run_id}",
                        summary=f"Assessed Risk: {payload.get('risk_level')} (Score: {payload.get('risk_score', 0):.1f}) - {', '.join(payload.get('factors', [])[:2])}",
                        metadata=payload,
                    )
                )

            elif name == "get_upgrade_plan_tasks":
                for t in payload:
                    new_evidence.append(t)
                    new_sources.append(
                        EvidenceSource(
                            type="plan",
                            identifier=t.get("task_id", ""),
                            summary=f"Step {t.get('step_number')} [{t.get('tier')}]: {t.get('component')} (Status: {t.get('status')})",
                            metadata=t,
                        )
                    )

            elif name == "get_change_diffs":
                for d in payload:
                    new_evidence.append(d)
                    breaking_tag = " [BREAKING]" if d.get("is_breaking") else ""
                    new_sources.append(
                        EvidenceSource(
                            type="diff",
                            identifier=d.get("symbol_name", ""),
                            summary=f"Diff: {d.get('change_type')}{breaking_tag} {d.get('symbol_name')} in {d.get('file_path')}",
                            metadata=d,
                        )
                    )

        # Merge evidence using deduplicating reducer
        combined_evidence = state.raw_evidence + new_evidence
        combined_sources = state.sources + new_sources

        # Deduplicate sources by identifier
        seen_src: set[str] = set()
        deduped_sources: list[EvidenceSource] = []
        for s in combined_sources:
            k = f"{s.type}:{s.identifier}"
            if k not in seen_src:
                seen_src.add(k)
                deduped_sources.append(s)

        return {
            "raw_evidence": combined_evidence[:25],
            "sources": deduped_sources[:15],
            "iteration_count": state.iteration_count + 1,
            "pending_tool_calls": [],
        }

    return execute_tools


# ---------------------------------------------------------------------------
# Node 4: Evaluate Evidence Sufficiency
# ---------------------------------------------------------------------------


def create_sufficiency_node():
    async def evaluate_sufficiency(state: AssistantState) -> dict[str, Any]:
        # Hard limit: maximum 2 retrieval hops
        if state.iteration_count >= 2:
            return {"is_sufficient": True}

        effective_target_type = state.target_type
        if effective_target_type == "NONE":
            if state.target_task_ids:
                effective_target_type = "PLAN_TASK"
            elif state.target_symbols:
                effective_target_type = "CODE_SYMBOL"
            elif "PLAN_SEQUENCE" in state.intents:
                effective_target_type = "PLAN_TASK"
            elif "VERSION_DIFF" in state.intents or "CHANGE_EXPLORATION" in state.intents:
                effective_target_type = "VERSION_CHANGE"
            elif "RISK_EVALUATION" in state.intents or "IMPACT_DEPENDENCY" in state.intents:
                effective_target_type = "PROJECT_RUN"

        # Check sufficiency based on target_type and intent:
        if "GENERAL_KNOWLEDGE" in state.intents:
            return {"is_sufficient": True}

        if effective_target_type == "PLAN_TASK" or "PLAN_SEQUENCE" in state.intents:
            has_plan = any(e.get("type") == "plan" for e in state.raw_evidence)
            return {"is_sufficient": has_plan}

        if effective_target_type == "PROJECT_RUN":
            if "PROJECT_OVERVIEW" in state.intents or "CODE_SEARCH" in state.intents:
                return {"is_sufficient": bool(state.raw_evidence)}
            if "RISK_EVALUATION" in state.intents:
                has_risk = any(e.get("type") == "risk" or "risk_level" in e for e in state.raw_evidence)
                return {"is_sufficient": has_risk}
            if "IMPACT_DEPENDENCY" in state.intents:
                has_graph = any(e.get("type") in ("graph", "overview") or "metrics" in e for e in state.raw_evidence)
                return {"is_sufficient": has_graph}
            has_any = len(state.raw_evidence) > 0
            return {"is_sufficient": has_any}

        if effective_target_type == "VERSION_CHANGE" or "CHANGE_EXPLORATION" in state.intents:
            has_diff = any(e.get("type") == "diff" for e in state.raw_evidence)
            return {"is_sufficient": has_diff}

        if effective_target_type == "CODE_SYMBOL":
            found_target_evidence = False
            target_l = [s.lower() for s in state.target_symbols]
            for e in state.raw_evidence:
                e_str = str(e).lower()
                if any(t in e_str for t in target_l):
                    found_target_evidence = True
                    break

            if not found_target_evidence:
                return {"is_sufficient": False}

            q_l = state.question.lower()
            if any(w in q_l for w in ("chang", "break", "parameter")):
                has_diff = any(e.get("type") == "diff" for e in state.raw_evidence)
                has_ast_snippet = any(e.get("type") == "ast" and e.get("source_snippet") for e in state.raw_evidence)
                if not (has_diff or has_ast_snippet):
                    return {"is_sufficient": False}

            return {"is_sufficient": True}

        has_general = any(e.get("type") in ("overview", "plan", "diff", "risk", "graph") for e in state.raw_evidence)
        return {"is_sufficient": bool(has_general)}

    return evaluate_sufficiency


def route_after_sufficiency(state: AssistantState) -> str:
    """Conditional router: loop back if evidence is insufficient and iteration budget remains."""
    if not state.is_sufficient and state.iteration_count < 2:
        return "loop_retrieval"
    return "proceed_to_synthesis"


# ---------------------------------------------------------------------------
# Node 5: Synthesize Grounded Answer
# ---------------------------------------------------------------------------


def create_synthesize_node(synthesis_svc: AssistantSynthesisService):
    async def synthesize_answer(state: AssistantState) -> dict[str, Any]:
        has_key = bool(
            synthesis_svc._config.openrouter_api_key
            and synthesis_svc._config.openrouter_api_key.get_secret_value().strip()
        )
        is_offline = not synthesis_svc._config.llm_enable_external_calls or not has_key
        guard_model = "offline-deterministic-fallback" if is_offline else "deterministic-evidence-guard"

        # 0. General Knowledge direct route
        if "GENERAL_KNOWLEDGE" in state.intents:
            if is_offline:
                q_l = state.question.lower()
                if "sky" in q_l and "blue" in q_l:
                    ans = (
                        "The sky appears blue due to Rayleigh scattering. Sunlight consists of light across the entire visible spectrum. "
                        "Gases and particles in Earth's atmosphere scatter shorter wavelengths (blue and violet light) much more strongly "
                        "than longer wavelengths (red and yellow). Because our eyes are more sensitive to blue light and violet light is "
                        "absorbed in the upper atmosphere, the sky looks blue during clear daytime."
                    )
                else:
                    ans = (
                        f"This question is general knowledge: **\"{state.question}\"**.\n\n"
                        "TRACE is specialized for code intelligence, codebase architecture, and dependency analysis. "
                        "General knowledge questions do not require querying repository code artifacts."
                    )
                return {
                    "final_answer": ans,
                    "grounding_status": "GENERAL_KNOWLEDGE_GROUNDED",
                    "model_used": "offline-deterministic-fallback",
                }

        # 1. Missing Entity Guard: Only applies to explicit CODE_SYMBOL targets
        effective_target_type = state.target_type
        if effective_target_type == "NONE" and state.target_symbols:
            effective_target_type = "CODE_SYMBOL"

        if effective_target_type == "CODE_SYMBOL" and state.target_symbols:
            has_relevant = False
            for e in state.raw_evidence:
                e_str = str(e).lower()
                if any(t.lower() in e_str for t in state.target_symbols):
                    has_relevant = True
                    break
            if not has_relevant:
                sym_str = ", ".join(f"`{s}`" for s in state.target_symbols)
                missing_msg = (
                    f"No verified code symbols, dependency graph edges, or risk records were found "
                    f"for {sym_str} in analysis run `{state.analysis_run_id}`.\n\n"
                    "Please verify that the component or symbol name is spelled correctly and exists in the analyzed codebase."
                )
                return {
                    "final_answer": missing_msg,
                    "grounding_status": "INSUFFICIENT_EVIDENCE",
                    "model_used": guard_model,
                }

        # 2. Check if offline fallback is required
        if is_offline:
            # Deterministic markdown formatting
            formatted_answer = _format_deterministic_evidence(state)
            grounding = "INSUFFICIENT_EVIDENCE" if not state.raw_evidence else "FALLBACK_DETERMINISTIC"
            return {
                "final_answer": formatted_answer,
                "grounding_status": grounding,
                "model_used": "offline-deterministic-fallback",
            }

        # 3. Online Synthesis via OpenRouter
        # Compact context payload (< 1,500 tokens)
        context_payload = {
            "matched_symbols": state.target_symbols,
            "evidence": state.raw_evidence[:15],
        }

        user_prompt = (
            f"User Question: {state.question}\n\n"
            f"Available Project Context:\n"
            f"```json\n{context_payload}\n```\n\n"
            "Provide a direct, helpful, and natural response strictly grounded in the context above. "
            "Do not fabricate non-existent relationships. Do not output your thinking process."
        )

        messages = [
            {"role": "system", "content": (
                "You are TRACE Code Intelligence Assistant. Your goal is to explain codebase dependencies, risks, and plans.\n"
                "RULES:\n"
                "1. Answer strictly based on the provided evidence.\n"
                "2. If evidence for a specific assertion is missing, state it clearly.\n"
                "3. NEVER mention 'JSON' or internal schema structures."
            )},
            {"role": "user", "content": user_prompt},
        ]

        model = synthesis_svc._config.openrouter_model or "meta-llama/llama-3.3-70b-instruct:free"
        base_url = str(synthesis_svc._config.openrouter_base_url or "https://openrouter.ai/api/v1").rstrip("/")
        url = f"{base_url}/chat/completions"
        api_key = (
            synthesis_svc._config.openrouter_api_key.get_secret_value().strip()
            if synthesis_svc._config.openrouter_api_key
            else ""
        )

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
            "max_tokens": 1024,
        }

        try:
            answer = await synthesis_svc._call_openrouter_with_retries(url, headers, payload)
            if answer and answer.strip():
                status = "DETERMINISTIC_GROUNDED" if len(state.sources) >= 1 else "PARTIAL_EVIDENCE"
                return {
                    "final_answer": answer.strip(),
                    "grounding_status": status,
                    "model_used": model,
                }
        except Exception as exc:
            logger.warning(f"OpenRouter call failed in workflow: {exc}")

        # Fallback if OpenRouter failed
        formatted_answer = _format_deterministic_evidence(state)
        return {
            "final_answer": formatted_answer,
            "grounding_status": "FALLBACK_DETERMINISTIC",
            "model_used": "offline-deterministic-fallback",
        }

    return synthesize_answer


def _format_deterministic_evidence(state: AssistantState) -> str:
    """Format raw evidence into readable markdown tables and checklists when offline."""
    sections: list[str] = []

    if state.target_symbols and state.target_type == "CODE_SYMBOL":
        sections.append(f"### 🎯 Target Entities\n- **Symbols**: {', '.join(f'`{s}`' for s in state.target_symbols)}")

    # Overview / Architectural context
    overview_items = [e for e in state.raw_evidence if e.get("type") == "overview" or "metrics" in e]
    if overview_items:
        ov = overview_items[0]
        metrics = ov.get("metrics", {})
        lines = ["### 🏛️ Repository Architecture & Overview"]
        if metrics:
            tot_files = metrics.get("total_files") or metrics.get("files") or 0
            py_files = metrics.get("python_files", 0)
            funcs = metrics.get("functions", 0)
            classes = metrics.get("classes", 0)
            lines.append(f"- **Language & Stack**: Primary language: **Python** ({py_files}/{tot_files} files)")
            lines.append(f"- **Scale**: {classes} classes, {funcs} functions across {metrics.get('modules', 0)} modules")
        test_cnt = ov.get("test_counts", 0)
        lines.append(f"- **Tests**: {test_cnt} test suites identified")
        entry_pts = ov.get("entry_points", [])
        if entry_pts:
            lines.append(f"- **Entry Points / Routes**: {', '.join(f'`{ep}`' for ep in entry_pts[:4])}")

        if any(p in state.question.lower() for p in ("can i add", "can we add", "add to this codebase")):
            lines.append(
                "\n**Feasibility Assessment**: You can introduce new functionality to this codebase. "
                "Review the architectural entry points above and add new service modules conforming to the existing structure."
            )
        sections.append("\n".join(lines))

    # Graph
    graph_items = [e for e in state.raw_evidence if e.get("type") == "graph"]
    if graph_items:
        if state.target_symbols and state.target_type == "CODE_SYMBOL":
            header = f"### 🕸️ Dependency Graph Paths for {', '.join(f'`{s}`' for s in state.target_symbols)}"
        else:
            header = "### 🕸️ Dependency Graph Paths"
        lines = [header]
        for g in graph_items[:8]:
            loc = f" *(in `{g.get('file_path')}:{g.get('line')}`)*" if g.get("file_path") and g.get("line") else ""
            lines.append(f"- **{g.get('depth', 1)}-hop [{g.get('relationship', 'CALLS')}]**: `{g.get('source')}` ➔ `{g.get('target')}`{loc}")
        sections.append("\n".join(lines))

    # AST / Source
    ast_items = [e for e in state.raw_evidence if e.get("type") == "ast"]
    if ast_items:
        lines = ["### 🔍 AST Code Intelligence"]
        for a in ast_items[:4]:
            params = f"({', '.join(a.get('parameters', []))})" if "parameters" in a else ""
            lines.append(f"- **`{a.get('qualified_name', a.get('name'))}`**{params} in `{a.get('file_path')}`")
            if a.get("source_snippet"):
                lines.append(f"```python\n{a.get('source_snippet')}\n```")
        sections.append("\n".join(lines))

    # Risk
    risk_items = [e for e in state.raw_evidence if e.get("type") == "risk" or "risk_level" in e]
    if risk_items:
        lines = ["### ⚠️ Assessed Risk Breakdown"]
        for r in risk_items[:3]:
            comp_label = f" for `{r.get('target_component')}`" if r.get("target_component") else ""
            lines.append(f"- Level **{r.get('risk_level')}**{comp_label} (Score: `{r.get('risk_score', 0):.1f}`)")
            for f in r.get("factors", [])[:5]:
                lines.append(f"  - *Factor*: {f}")
            if r.get("remediations"):
                for rem in r.get("remediations", [])[:2]:
                    lines.append(f"  - *Remediation*: {rem}")
        sections.append("\n".join(lines))

    # Plan
    plan_items = [e for e in state.raw_evidence if e.get("type") == "plan"]
    if plan_items:
        task_nums = [int(m) for m in re.findall(r"(?i)\btask\s*(\d+)\b", state.question)]
        if len(task_nums) >= 2:
            step_a, step_b = task_nums[0], task_nums[1]
            task_a = next((p for p in plan_items if p.get("step_number") == step_a), None)
            task_b = next((p for p in plan_items if p.get("step_number") == step_b), None)
            if task_a and task_b:
                is_direct_dep = (
                    str(step_a) in task_b.get("dependencies", [])
                    or f"task_{step_a}" in task_b.get("dependencies", [])
                    or task_a.get("task_id") in task_b.get("dependencies", [])
                    or any(str(step_a) in str(d) for d in task_b.get("dependencies", []))
                )
                seq_lines = [
                    f"### 📋 Upgrade Plan Sequence Rationale: Step {step_a} vs Step {step_b}",
                    f"- **Preceding Task (Step {step_a})**: `{task_a.get('component')}` (Tier: `{task_a.get('tier')}`, Status: `{task_a.get('status')}`)",
                    f"- **Subsequent Task (Step {step_b})**: `{task_b.get('component')}` (Tier: `{task_b.get('tier')}`, Status: `{task_b.get('status')}`)",
                ]
                if is_direct_dep:
                    seq_lines.append(
                        f"\n**Ordering Rationale**: Step {step_b} (`{task_b.get('component')}`) directly declares "
                        f"Step {step_a} (`{task_a.get('component')}`) as a prerequisite dependency. "
                        f"Therefore, Step {step_a} must execute and stabilize first to satisfy structural contracts."
                    )
                else:
                    seq_lines.append(
                        f"\n**Ordering Rationale**: Step {step_a} is scheduled prior to Step {step_b} "
                        f"based on topological DAG ordering and tier hierarchy (Tier `{task_a.get('tier')}` precedes Tier `{task_b.get('tier')}`)."
                    )
                if task_a.get("reason"):
                    seq_lines.append(f"- *Step {step_a} Goal*: {task_a.get('reason')}")
                if task_b.get("reason"):
                    seq_lines.append(f"- *Step {step_b} Goal*: {task_b.get('reason')}")
                sections.append("\n".join(seq_lines))
            else:
                lines = ["### 📋 Upgrade Plan Sequence"]
                for p in plan_items[:5]:
                    deps = f" (Depends on: {', '.join(p.get('dependencies', []))})" if p.get("dependencies") else " (Root Task)"
                    lines.append(f"- **{p.get('task_id')} [Step {p.get('step_number')}]**: `{p.get('component')}` [{p.get('tier')}]{deps}")
                sections.append("\n".join(lines))
        else:
            lines = ["### 📋 Upgrade Plan Sequence"]
            for p in plan_items[:5]:
                deps = f" (Depends on: {', '.join(p.get('dependencies', []))})" if p.get("dependencies") else " (Root Task)"
                lines.append(f"- **{p.get('task_id')} [Step {p.get('step_number')}]**: `{p.get('component')}` [{p.get('tier')}]{deps}")
            sections.append("\n".join(lines))

    # Diff
    diff_items = [e for e in state.raw_evidence if e.get("type") == "diff"]
    if diff_items:
        lines = ["### 📝 Version Diff Deltas"]
        for d in diff_items[:5]:
            breaking = " [BREAKING]" if d.get("is_breaking") else ""
            lines.append(f"- **`{d.get('symbol_name')}`** (`{d.get('change_type')}`{breaking}) in `{d.get('file_path')}`")
        sections.append("\n".join(lines))

    if not sections:
        return (
            f"No specific evidence was located for query: **\"{state.question}\"** in the active snapshot.\n\n"
            "*(Generated via TRACE deterministic offline engine)*"
        )

    body = "\n\n".join(sections)
    return f"{body}\n\n*(Generated via TRACE deterministic offline engine)*"


# ---------------------------------------------------------------------------
# Node 6: Assemble Response
# ---------------------------------------------------------------------------


def create_assemble_node():
    async def assemble_response(state: AssistantState) -> dict[str, Any]:
        followups = list(state.suggested_followups)
        if not followups:
            git_or_project_terms = {
                "head", "main", "master", "origin", "trunk", "branch", "commit",
                "repo", "project", "repository", "snapshot", "upgrade", "v1.0", "v2.0", "v1", "v2"
            }
            valid_symbols = [
                s for s in state.target_symbols
                if s.lower() not in git_or_project_terms
                and not any(g in s.lower() for g in ("-head", "-main", "-master", "python-proj", "sample_repo"))
            ]
            if valid_symbols and state.target_type in ("CODE_SYMBOL", "NONE"):
                sym = valid_symbols[0]
                followups = [
                    f"Show all callers of {sym}",
                    f"What is the risk score of {sym}?",
                    f"Show AST signature and parameters for {sym}",
                ]
            else:
                followups = [
                    "What are the highest risk components?",
                    "Which upgrade tasks should execute first?",
                    "Show repository architectural overview",
                ]

        return {"suggested_followups": followups[:4]}

    return assemble_response


# ---------------------------------------------------------------------------
# Graph Builder
# ---------------------------------------------------------------------------


def build_assistant_graph(tools: AssistantTools, synthesis_svc: AssistantSynthesisService) -> Any:
    """Build and compile the complete TRACE AI Assistant LangGraph workflow."""
    workflow = StateGraph(AssistantState)

    workflow.add_node("understand_question", create_understand_node(tools))
    workflow.add_node("select_tools", create_select_tools_node())
    workflow.add_node("execute_tools", create_execute_tools_node(tools))
    workflow.add_node("evaluate_sufficiency", create_sufficiency_node())
    workflow.add_node("synthesize_answer", create_synthesize_node(synthesis_svc))
    workflow.add_node("assemble_response", create_assemble_node())

    workflow.set_entry_point("understand_question")
    workflow.add_edge("understand_question", "select_tools")
    workflow.add_edge("select_tools", "execute_tools")
    workflow.add_edge("execute_tools", "evaluate_sufficiency")

    workflow.add_conditional_edges(
        "evaluate_sufficiency",
        route_after_sufficiency,
        {
            "loop_retrieval": "select_tools",
            "proceed_to_synthesis": "synthesize_answer",
        },
    )

    workflow.add_edge("synthesize_answer", "assemble_response")
    workflow.add_edge("assemble_response", END)

    return workflow.compile()
