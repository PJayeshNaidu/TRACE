"""Service layer orchestrating F07: Upgrade Planner."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from trace.analysis.planner.dag_sequencer import DagSequencer
from trace.analysis.planner.task_synthesizer import TaskSynthesizer
from trace.analysis.planner.tier_mapper import TierMapper
from trace.domain.exceptions import RepositoryNotFoundError
from trace.domain.impact import (
    AnalysisMetadataPayload,
    CallerAtRisk,
    DependencyGraphPayload,
    DetailedImpact,
    GraphEdgePayload,
    GraphNodePayload,
    ImpactAnalysisAggregate,
    ReasoningMode,
    RemediationStep,
    RiskAnalysisPayload,
    RiskFactor,
    RiskLevel,
)
from trace.domain.plan import (
    Actionability,
    ChangeSignificance,
    InformationalChange,
    TaskActionType,
    TaskCategory,
    TaskEvidence,
    TaskStatus,
    UpgradePlan,
    UpgradeTask,
)
from trace.infrastructure.database.gateway import DatabaseGateway
from trace.infrastructure.database.models import (
    RepositoryOrm,
    UpgradePlanOrm,
    UpgradeTaskOrm,
)
from trace.infrastructure.git.provider import GitProvider
from trace.infrastructure.storage.artifact_store import FileArtifactStore
from trace.services.impact import ImpactAnalysisService
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

logger = structlog.get_logger(__name__)


class UpgradePlanNotFoundError(Exception):
    """Raised when an upgrade plan is not found."""

    def __init__(self, plan_id: uuid.UUID) -> None:
        super().__init__(f"Upgrade plan {plan_id} not found.")
        self.plan_id = plan_id


class UpgradeTaskNotFoundError(Exception):
    """Raised when a specific upgrade task is not found."""

    def __init__(self, task_id: uuid.UUID) -> None:
        super().__init__(f"Upgrade task {task_id} not found.")
        self.task_id = task_id


class UpgradePlanService:
    """Orchestrates topological DAG plan generation, task synthesis,
    persistence, and lifecycle tracking.
    """

    def __init__(
        self,
        db_gateway: DatabaseGateway,
        artifact_store: FileArtifactStore,
        impact_service: ImpactAnalysisService,
        git_provider: GitProvider | None = None,
    ) -> None:
        self._db_gateway = db_gateway
        self._artifact_store = artifact_store
        self._impact_service = impact_service
        self._git_provider = git_provider

    async def generate_plan(
        self,
        repository_id: uuid.UUID,
        impact_analysis_id: uuid.UUID | None = None,
        base_ref: str = "HEAD~1",
        target_ref: str = "HEAD",
        title: str | None = None,
        llm_config: dict[str, Any] | None = None,
    ) -> UpgradePlan:
        """Generate an actionable, dependency-ordered upgrade plan from an impact analysis."""
        # 1. Verify Repository Exists
        async with self._db_gateway.session() as session:
            repo_res = await session.execute(
                select(RepositoryOrm).where(RepositoryOrm.id == repository_id)
            )
            repo = repo_res.scalar_one_or_none()
            if not repo:
                raise RepositoryNotFoundError(repository_id)

        # 2. Ingest or Run Impact Analysis
        if impact_analysis_id:
            impact_res = await self._impact_service.get_analysis(impact_analysis_id)
            if isinstance(impact_res, ImpactAnalysisAggregate):
                impact_aggregate = impact_res
            elif isinstance(impact_res, dict):
                impact_aggregate = self._dict_to_impact_aggregate(impact_res)
            else:
                raise ValueError(f"Unexpected impact analysis response type: {type(impact_res)}")
        else:
            api_key = (
                str(llm_config["api_key"]).strip()
                if (llm_config and llm_config.get("api_key"))
                else None
            )
            model = (
                str(llm_config["model"]).strip()
                if (llm_config and llm_config.get("model"))
                else None
            )
            impact_aggregate = await self._impact_service.evaluate_impact(
                repository_id=repository_id,
                base_ref=base_ref,
                target_ref=target_ref,
                openrouter_api_key=api_key,
                openrouter_model=model,
            )
            impact_analysis_id = impact_aggregate.metadata.analysis_id

        # 3. Assess Change Significance and Initial Risk deterministically
        det_significance, det_reasoning = TierMapper.assess_change_significance(
            detailed_impacts=impact_aggregate.detailed_impacts,
            risk_analysis=impact_aggregate.risk_analysis,
        )
        caller_count = (
            impact_aggregate.metadata.total_callers_at_risk
            if impact_aggregate.metadata
            else sum(len(d.callers_at_risk) for d in impact_aggregate.detailed_impacts)
        )
        key_factors = (
            impact_aggregate.risk_analysis.key_risk_factors
            if impact_aggregate.risk_analysis
            else ()
        )
        f06_risk = (
            (
                impact_aggregate.risk_analysis.risk_level.value
                if hasattr(impact_aggregate.risk_analysis.risk_level, "value")
                else str(impact_aggregate.risk_analysis.risk_level)
            )
            if impact_aggregate.risk_analysis
            else None
        )

        overall_risk = TierMapper.calculate_plan_risk(
            significance=det_significance,
            caller_count=caller_count,
            key_risk_factors=key_factors,
            base_risk_level=f06_risk,
        )

        plan_id = uuid.uuid4()
        base_short = impact_aggregate.metadata.base_commit[:7]
        target_short = impact_aggregate.metadata.current_commit[:7]
        plan_title = title or f"Upgrade Plan: {base_short} ➜ {target_short}"
        reasoning_mode = (
            impact_aggregate.metadata.reasoning_mode.value
            if hasattr(impact_aggregate.metadata.reasoning_mode, "value")
            else str(impact_aggregate.metadata.reasoning_mode)
        )

        # 4. Extract Candidates & Call Edges
        candidates_map: dict[str, dict[str, Any]] = {}
        call_edges: list[tuple[str, str]] = []
        informational_changes: list[InformationalChange] = []

        # If change is deterministically minor or no action, suppress tasks immediately
        if det_significance in (
            ChangeSignificance.MINOR_CHANGE,
            ChangeSignificance.NO_ACTION_REQUIRED,
        ):
            rec_action = (
                "No major upgrade work required. The revision contains documentation-only changes "
                "with no executable behavior or API contract changes."
                if det_significance == ChangeSignificance.MINOR_CHANGE
                else "No upgrade action required. No functional or contract changes detected."
            )
            suggestions = (
                [
                    "Review documentation formatting.",
                    "Run documentation build/lint if applicable.",
                    "No code migration required.",
                ]
                if det_significance == ChangeSignificance.MINOR_CHANGE
                else []
            )

            for d in impact_aggregate.detailed_impacts:
                comp_name = (
                    TierMapper.canonicalize_component(d.entity, d.file)
                    if d.entity
                    else d.file
                )
                category = TierMapper.classify(
                    entity_name=d.entity or d.file,
                    entity_type=d.entity_type,
                    file_path=d.file,
                    diff_snippet=d.diff_snippet,
                )
                actionability = TierMapper.classify_actionability(
                    diff_snippet=d.diff_snippet,
                    file_path=d.file,
                    entity_name=d.entity or d.file,
                    entity_type=d.entity_type,
                    category=category,
                    change_summary=d.change_summary,
                    has_callers=bool(d.callers_at_risk),
                )
                if actionability not in (Actionability.IGNORE, Actionability.INFORMATIONAL):
                    actionability = Actionability.INFORMATIONAL

                informational_changes.append(
                    InformationalChange(
                        component=comp_name,
                        file_path=d.file,
                        category=category,
                        reason=(
                            f"Documentation or comment-only change detected in '{comp_name}'. "
                            "No behavioral or contract upgrade required."
                        ),
                        diff_snippet=d.diff_snippet,
                        actionability=actionability,
                    )
                )

            plan = UpgradePlan(
                id=plan_id,
                repository_id=repository_id,
                impact_analysis_id=impact_analysis_id,
                title=plan_title,
                base_commit=impact_aggregate.metadata.base_commit,
                target_commit=impact_aggregate.metadata.current_commit,
                risk_level=overall_risk,
                status="COMPLETED",
                tasks=[],
                informational_changes=informational_changes,
                reasoning_mode=reasoning_mode,
                change_significance=det_significance,
                significance_reasoning=det_reasoning,
                recommended_action=rec_action,
                order_rationale="No upgrade tasks requiring dependency ordering.",
                optional_suggestions=suggestions,
            )
            await self._persist_plan(plan)
            return plan

        # A) Add modified entities
        for d in impact_aggregate.detailed_impacts:
            comp_name = (
                TierMapper.canonicalize_component(d.entity, d.file)
                if d.entity
                else d.file
            )
            category = TierMapper.classify(
                entity_name=d.entity or d.file,
                entity_type=d.entity_type,
                file_path=d.file,
                diff_snippet=d.diff_snippet,
            )
            actionability = TierMapper.classify_actionability(
                diff_snippet=d.diff_snippet,
                file_path=d.file,
                entity_name=d.entity or d.file,
                entity_type=d.entity_type,
                category=category,
                change_summary=d.change_summary,
                has_callers=bool(d.callers_at_risk),
            )

            # Documentation/comment/whitespace changes do NOT become upgrade tasks
            # and do NOT propagate to callers.
            if actionability in (Actionability.IGNORE, Actionability.INFORMATIONAL):
                informational_changes.append(
                    InformationalChange(
                        component=comp_name,
                        file_path=d.file,
                        category=category,
                        reason=(
                            f"Documentation or comment-only change detected in '{comp_name}'. "
                            "No behavioral or contract upgrade required."
                        ),
                        diff_snippet=d.diff_snippet,
                        actionability=actionability,
                    )
                )
                continue

            candidates_map[comp_name] = {
                "component": comp_name,
                "component_type": d.entity_type,
                "file": d.file,
                "category": category,
                "actionability": actionability,
                "action_type": TaskActionType.REQUIRED_CHANGE,
                "raw_impact": {
                    "change_summary": d.change_summary,
                    "remediation_guidance": d.remediation_guidance,
                    "justification": d.justification,
                    "diff_snippet": d.diff_snippet,
                    "lines_affected": d.lines_affected,
                },
                "dependencies": [],
            }

            # Outbound calls: (modified_entity, outbound) -> outbound precedes modified
            for outbound in d.outbound_calls:
                call_edges.append((comp_name, outbound))

            # B) Add callers at risk (only for genuine behavioral/API/contract changes)
            for c in d.callers_at_risk:
                caller_comp = (
                    TierMapper.canonicalize_component(c.qualified_name, c.file_path)
                    if c.qualified_name
                    else c.file_path
                )
                caller_cat = TierMapper.classify(
                    entity_name=c.qualified_name or c.file_path,
                    entity_type="function",
                    file_path=c.file_path,
                )
                caller_action_type = TierMapper.evaluate_caller_action_type(
                    caller_distance=c.distance,
                    target_diff_snippet=d.diff_snippet,
                    target_category=category,
                )

                # Wire call chain hop-by-hop dependencies
                canon_chain: list[str] = []
                if c.call_chain:
                    for sym in c.call_chain:
                        if sym in (c.qualified_name, caller_comp, caller_comp.split("::")[-1]):
                            canon_chain.append(caller_comp)
                        elif sym in (d.entity, comp_name, comp_name.split("::")[-1]):
                            canon_chain.append(comp_name)
                        else:
                            canon_chain.append(TierMapper.canonicalize_component(sym, c.file_path))

                if len(canon_chain) >= 2:
                    for i in range(len(canon_chain) - 1):
                        call_edges.append((canon_chain[i], canon_chain[i + 1]))
                    immediate_dep = canon_chain[1]
                else:
                    immediate_dep = comp_name
                    call_edges.append((caller_comp, comp_name))

                if caller_comp not in candidates_map:
                    candidates_map[caller_comp] = {
                        "component": caller_comp,
                        "component_type": "function",
                        "file": c.file_path,
                        "category": caller_cat,
                        "actionability": Actionability.UPGRADE,
                        "action_type": caller_action_type,
                        "caller_info": {
                            "distance": c.distance,
                            "target_entity": comp_name,
                            "call_chain": c.call_chain,
                        },
                        "dependencies": [immediate_dep],
                    }
                else:
                    if immediate_dep not in candidates_map[caller_comp]["dependencies"]:
                        candidates_map[caller_comp]["dependencies"].append(immediate_dep)
                    if caller_action_type == TaskActionType.REQUIRED_CHANGE:
                        candidates_map[caller_comp]["action_type"] = TaskActionType.REQUIRED_CHANGE

            # C) Downstream non-code files (YAML, Docs, Configs)
            for down_file in d.downstream_dependent_files:
                if down_file != d.file and down_file not in candidates_map:
                    doc_cat = TierMapper.classify(
                        entity_name=down_file, entity_type="file", file_path=down_file
                    )
                    # Non-code files should not become upgrade tasks
                    if doc_cat == TaskCategory.DOCUMENTATION_CONFIG:
                        informational_changes.append(
                            InformationalChange(
                                component=down_file,
                                file_path=down_file,
                                category=doc_cat,
                                reason=(
                                    f"Downstream non-code file '{down_file}' "
                                    "may benefit from review."
                                ),
                                diff_snippet="",
                                actionability=Actionability.INFORMATIONAL,
                            )
                        )
                    else:
                        candidates_map[down_file] = {
                            "component": down_file,
                            "component_type": "file",
                            "file": down_file,
                            "category": doc_cat,
                            "actionability": Actionability.INFORMATIONAL,
                            "action_type": TaskActionType.LOW_PRIORITY_REVIEW,
                            "dependencies": [comp_name],
                        }
                        call_edges.append((down_file, comp_name))

        # D) Dependency graph explicit edges from F05
        for edge in impact_aggregate.dependency_graph.edges:
            call_edges.append(
                (
                    TierMapper.canonicalize_component(edge.caller),
                    TierMapper.canonicalize_component(edge.callee),
                )
            )

        # 5. Handle Zero-Impact Case
        if not candidates_map:
            plan = UpgradePlan(
                id=plan_id,
                repository_id=repository_id,
                impact_analysis_id=impact_analysis_id,
                title=plan_title,
                base_commit=impact_aggregate.metadata.base_commit,
                target_commit=impact_aggregate.metadata.current_commit,
                risk_level=overall_risk,
                status="COMPLETED",
                tasks=[],
                informational_changes=informational_changes,
                reasoning_mode=reasoning_mode,
                change_significance=det_significance,
                significance_reasoning=det_reasoning,
                recommended_action="No functional or contract upgrade tasks required.",
                order_rationale="No upgrade tasks requiring dependency ordering.",
                optional_suggestions=[],
            )
            await self._persist_plan(plan)
            return plan

        # 6. Run Topological DAG Sequencing
        sequenced_nodes = DagSequencer.sequence_tasks(list(candidates_map.values()), call_edges)
        order_rationale = TierMapper.explain_topological_order(sequenced_nodes)
        recommended_action = "A coordinated upgrade is recommended."
        optional_suggestions: list[str] = []

        # 7. Synthesize Full Task Metadata with Granular Task Risk
        upgrade_tasks: list[UpgradeTask] = []
        for s_node in sequenced_nodes:
            cand = candidates_map[s_node.component]
            action_type = cand.get("action_type", TaskActionType.REQUIRED_CHANGE)
            reason, expected_changes, req_tests, evidence = (
                TaskSynthesizer.synthesize_task_metadata(
                    component=s_node.component,
                    category=s_node.category,
                    component_type=cand.get("component_type", "function"),
                    file_path=cand.get("file", ""),
                    raw_impact=cand.get("raw_impact"),
                    caller_info=cand.get("caller_info"),
                    action_type=action_type,
                )
            )

            c_info = cand.get("caller_info") or {}
            c_dist = c_info.get("distance", 0)
            raw_imp = cand.get("raw_impact") or {}
            diff_snip = raw_imp.get("diff_snippet", "")
            has_sig = TierMapper.is_callable_contract_change(diff_snip)
            task_risk = TierMapper.calculate_task_risk(
                action_type=action_type,
                category=s_node.category,
                change_significance=det_significance,
                caller_distance=c_dist,
                has_signature_change=has_sig,
            )

            task_obj = UpgradeTask(
                id=uuid.uuid4(),
                plan_id=plan_id,
                step_number=s_node.step_number,
                component=s_node.component,
                component_type=cand.get("component_type", "function"),
                category=s_node.category,
                reason=reason,
                dependencies=tuple(s_node.dependencies),
                expected_changes=expected_changes,
                required_tests=tuple(req_tests),
                risk_level=task_risk,
                status=TaskStatus.PENDING,
                is_circular=s_node.is_circular,
                parallel_group_id=s_node.parallel_group_id,
                evidence=evidence,
                actionability=cand.get("actionability", Actionability.UPGRADE),
                action_type=action_type,
                tier_name=s_node.category.tier_name,
                tier_meaning=s_node.category.tier_meaning,
                change_significance=det_significance,
            )
            upgrade_tasks.append(task_obj)

        # 8. OpenRouter LLM Refactoring Enrichment & Whole-Plan Review
        ai_plan_review = None
        if llm_config and llm_config.get("api_key"):
            api_key = str(llm_config["api_key"]).strip()
            model = str(llm_config.get("model") or "mistralai/mistral-7b-instruct:free")
            if api_key:
                any_enriched = False
                # 8A. Per-task review
                for task_obj in upgrade_tasks:
                    cand = candidates_map.get(task_obj.component, {})
                    raw_imp = cand.get("raw_impact") or {}
                    diff_snippet = raw_imp.get("diff_snippet", "")
                    callers = [
                        caller for caller, callee in call_edges if callee == task_obj.component
                    ]
                    ref_r, ref_c, rec_t, ai_rev = await TaskSynthesizer.enrich_task_with_openrouter(
                        component=task_obj.component,
                        category=task_obj.category,
                        component_type=task_obj.component_type,
                        file_path=cand.get("file", ""),
                        heuristic_reason=task_obj.reason,
                        heuristic_changes=task_obj.expected_changes,
                        api_key=api_key,
                        model=model,
                        diff_snippet=diff_snippet,
                        callers=callers,
                    )
                    if ref_r != task_obj.reason or ref_c != task_obj.expected_changes:
                        task_obj.reason = ref_r
                        task_obj.expected_changes = ref_c
                        any_enriched = True
                    if rec_t:
                        task_obj.required_tests = tuple(
                            dict.fromkeys(list(task_obj.required_tests) + list(rec_t))
                        )
                        any_enriched = True
                    if ai_rev:
                        task_obj.ai_review = ai_rev
                        if ai_rev.get("confidence"):
                            task_obj.ai_confidence = str(ai_rev["confidence"])

                        # Evaluate action_type refinement from AI
                        if ai_rev.get("action_type") in TaskActionType.__members__.values():
                            suggested_action = TaskActionType(ai_rev["action_type"])
                            cand_info = cand.get("caller_info")
                            # Guardrail: direct caller of signature change should not be NO_ACTION
                            if (
                                cand_info
                                and cand_info.get("distance") == 1
                                and suggested_action == TaskActionType.NO_ACTION
                            ):
                                ai_rev["override_note"] = (
                                    "Retained as VALIDATION_ONLY due to direct invocation site."
                                )
                                task_obj.action_type = TaskActionType.VALIDATION_ONLY
                            else:
                                task_obj.action_type = suggested_action

                        # AI false-positive detection check:
                        # If AI suggested IGNORE, verify against deterministic evidence
                        if ai_rev.get("actionability") == "IGNORE":
                            is_det_code = bool(
                                diff_snippet and not TierMapper.is_documentation_diff(diff_snippet)
                            )
                            if (
                                is_det_code
                                or callers
                                or task_obj.category == TaskCategory.CONTRACT_API
                            ):
                                ai_rev["override_note"] = (
                                    "AI suggested IGNORE, but task retained due to deterministic "
                                    "evidence of executable code/contract modification."
                                )
                            else:
                                task_obj.actionability = Actionability.IGNORE

                # 8B. Whole-plan review
                plan_review = await TaskSynthesizer.review_whole_plan_with_openrouter(
                    tasks=upgrade_tasks,
                    informational_changes=informational_changes,
                    repository_context={"known_files": list(candidates_map.keys())},
                    api_key=api_key,
                    model=model,
                )
                if plan_review:
                    ai_plan_review = plan_review
                    any_enriched = True

                    # Extract fields from whole-plan review
                    llm_sig = plan_review.get("change_significance")
                    if llm_sig in ChangeSignificance.__members__.values():
                        # Guardrail: Do not let LLM downgrade a deterministic MAJOR_CHANGE
                        # if there is signature/contract changes in the diff
                        if not (
                            det_significance == ChangeSignificance.MAJOR_CHANGE
                            and llm_sig
                            in (
                                ChangeSignificance.MINOR_CHANGE.value,
                                ChangeSignificance.NO_ACTION_REQUIRED.value,
                            )
                        ):
                            det_significance = ChangeSignificance(llm_sig)

                    if plan_review.get("significance_reasoning"):
                        det_reasoning = str(plan_review["significance_reasoning"])
                    if plan_review.get("recommended_action"):
                        recommended_action = str(plan_review["recommended_action"])
                    if plan_review.get("order_rationale"):
                        order_rationale = str(plan_review["order_rationale"])
                    if plan_review.get("optional_suggestions") and isinstance(
                        plan_review["optional_suggestions"], list
                    ):
                        optional_suggestions = [str(s) for s in plan_review["optional_suggestions"]]

                    # Per-task evaluations from whole plan review
                    task_evals = plan_review.get("task_evaluations")
                    if isinstance(task_evals, list):
                        eval_by_comp: dict[str, dict[str, Any]] = {}
                        for ev in task_evals:
                            if isinstance(ev, dict):
                                c_key = ev.get("component") or ev.get("entity") or ""
                                eval_by_comp[c_key] = ev
                                eval_by_comp[TierMapper.canonicalize_component(c_key)] = ev
                        for t in upgrade_tasks:
                            ev = eval_by_comp.get(t.component)
                            if ev and ev.get("action_type") in TaskActionType.__members__.values():
                                t.action_type = TaskActionType(ev["action_type"])
                    elif isinstance(task_evals, dict):
                        for t in upgrade_tasks:
                            if t.component in task_evals:
                                ev = task_evals[t.component]
                                if (
                                    isinstance(ev, dict)
                                    and ev.get("action_type") in TaskActionType.__members__.values()
                                ):
                                    t.action_type = TaskActionType(ev["action_type"])

                    # If LLM classified as MINOR_CHANGE, drop tasks and clear
                    if det_significance in (
                        ChangeSignificance.MINOR_CHANGE,
                        ChangeSignificance.NO_ACTION_REQUIRED,
                    ):
                        upgrade_tasks = []
                        recommended_action = (
                            "No major upgrade work required. The revision contains "
                            "documentation-only changes with no executable behavior "
                            "or API contract changes."
                            if det_significance == ChangeSignificance.MINOR_CHANGE
                            else (
                                "No upgrade action required. No functional or contract "
                                "changes detected."
                            )
                        )
                        if (
                            not optional_suggestions
                            and det_significance == ChangeSignificance.MINOR_CHANGE
                        ):
                            optional_suggestions = [
                                "Review documentation formatting.",
                                "Run documentation build/lint if applicable.",
                                "No code migration required.",
                            ]

                    # Recalculate overall and per-task risk with final significance
                    overall_risk = TierMapper.calculate_plan_risk(
                        significance=det_significance,
                        caller_count=caller_count,
                        key_risk_factors=key_factors,
                        base_risk_level=f06_risk,
                    )
                    for t in upgrade_tasks:
                        cand = candidates_map.get(t.component, {})
                        c_info = cand.get("caller_info") or {}
                        c_dist = c_info.get("distance", 0)
                        raw_imp = cand.get("raw_impact") or {}
                        diff_snip = raw_imp.get("diff_snippet", "")
                        has_sig = TierMapper.is_callable_contract_change(diff_snip)
                        t.risk_level = TierMapper.calculate_task_risk(
                            action_type=t.action_type,
                            category=t.category,
                            change_significance=det_significance,
                            caller_distance=c_dist,
                            has_signature_change=has_sig,
                        )
                        t.change_significance = det_significance

                if any_enriched:
                    reasoning_mode = "LLM_ENRICHED"

        # 9. Construct and Persist Plan Aggregate
        plan = UpgradePlan(
            id=plan_id,
            repository_id=repository_id,
            impact_analysis_id=impact_analysis_id,
            title=plan_title,
            base_commit=impact_aggregate.metadata.base_commit,
            target_commit=impact_aggregate.metadata.current_commit,
            risk_level=overall_risk,
            status="DRAFT",
            tasks=upgrade_tasks,
            informational_changes=informational_changes,
            ai_plan_review=ai_plan_review,
            reasoning_mode=reasoning_mode,
            change_significance=det_significance,
            significance_reasoning=det_reasoning,
            recommended_action=recommended_action,
            order_rationale=order_rationale,
            optional_suggestions=optional_suggestions,
        )

        await self._persist_plan(plan)
        return plan

    async def get_plan(self, plan_id: uuid.UUID) -> UpgradePlan:
        """Retrieve complete upgrade plan with task DAG and summary metrics."""
        async with self._db_gateway.session() as session:
            stmt = (
                select(UpgradePlanOrm)
                .options(selectinload(UpgradePlanOrm.tasks))
                .where(UpgradePlanOrm.id == plan_id)
            )
            res = await session.execute(stmt)
            plan_orm = res.scalar_one_or_none()

            if not plan_orm:
                raise UpgradePlanNotFoundError(plan_id)

            domain_plan = self._to_domain_plan(plan_orm)
            # Restore informational_changes and ai_plan_review from artifact if available
            if self._artifact_store.exists(plan_id):
                try:
                    artifact_data = self._artifact_store.read_artifact(plan_id)
                    raw_info = artifact_data.get("informational_changes", [])
                    info_objs = []
                    for raw in raw_info:
                        cat_str = raw.get("category", "DOCUMENTATION_CONFIG")
                        cat = (
                            TaskCategory(cat_str)
                            if cat_str in TaskCategory.__members__.values()
                            else TaskCategory.DOCUMENTATION_CONFIG
                        )
                        act_str = raw.get("actionability", "INFORMATIONAL")
                        try:
                            act = Actionability(act_str)
                        except ValueError:
                            act = Actionability.INFORMATIONAL
                        info_objs.append(
                            InformationalChange(
                                component=raw.get("component", ""),
                                file_path=raw.get("file_path", ""),
                                category=cat,
                                reason=raw.get("reason", ""),
                                diff_snippet=raw.get("diff_snippet", ""),
                                actionability=act,
                            )
                        )
                    domain_plan.informational_changes = info_objs
                    domain_plan.ai_plan_review = artifact_data.get("ai_plan_review")
                    if artifact_data.get("change_significance"):
                        try:
                            domain_plan.change_significance = ChangeSignificance(
                                artifact_data["change_significance"]
                            )
                        except ValueError:
                            pass
                    if artifact_data.get("significance_reasoning"):
                        domain_plan.significance_reasoning = artifact_data["significance_reasoning"]
                    if artifact_data.get("recommended_action"):
                        domain_plan.recommended_action = artifact_data["recommended_action"]
                    if artifact_data.get("order_rationale"):
                        domain_plan.order_rationale = artifact_data["order_rationale"]
                    if artifact_data.get("optional_suggestions"):
                        domain_plan.optional_suggestions = list(
                            artifact_data["optional_suggestions"]
                        )
                except Exception as exc:
                    logger.warning("Failed to restore plan artifact details", error=str(exc))
            return domain_plan

    async def list_plans_for_repository(self, repository_id: uuid.UUID) -> list[UpgradePlan]:
        """List historical upgrade plans for a repository ordered by creation date."""
        async with self._db_gateway.session() as session:
            stmt = (
                select(UpgradePlanOrm)
                .options(selectinload(UpgradePlanOrm.tasks))
                .where(UpgradePlanOrm.repository_id == repository_id)
                .order_by(UpgradePlanOrm.created_at.desc())
            )
            res = await session.execute(stmt)
            plan_orms = res.scalars().all()
            return [self._to_domain_plan(p) for p in plan_orms]

    async def list_tasks(
        self,
        plan_id: uuid.UUID,
        status: str | None = None,
        category: str | None = None,
        risk_level: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[int, list[UpgradeTask]]:
        """Retrieve paginated and filtered tasks for an upgrade plan."""
        async with self._db_gateway.session() as session:
            # Base query
            query = select(UpgradeTaskOrm).where(UpgradeTaskOrm.plan_id == plan_id)

            if status:
                query = query.where(UpgradeTaskOrm.status == status.upper())
            if category:
                query = query.where(UpgradeTaskOrm.category == category.upper())
            if risk_level:
                query = query.where(UpgradeTaskOrm.risk_level == risk_level.upper())

            # Count total matching
            count_stmt = select(func.count()).select_from(query.subquery())
            total = (await session.execute(count_stmt)).scalar() or 0

            # Fetch page
            page_stmt = query.order_by(UpgradeTaskOrm.step_number.asc()).limit(limit).offset(offset)
            res = await session.execute(page_stmt)
            task_orms = res.scalars().all()

            tasks = [self._to_domain_task(t) for t in task_orms]
            return total, tasks

    async def update_task_status(
        self,
        plan_id: uuid.UUID,
        task_id: uuid.UUID,
        new_status: TaskStatus,
        notes: str | None = None,
    ) -> UpgradeTask:
        """Update an individual task's status and recalculate plan progress."""
        async with self._db_gateway.session() as session:
            # Fetch target task
            t_res = await session.execute(
                select(UpgradeTaskOrm).where(
                    UpgradeTaskOrm.id == task_id,
                    UpgradeTaskOrm.plan_id == plan_id,
                )
            )
            task_orm = t_res.scalar_one_or_none()
            if not task_orm:
                raise UpgradeTaskNotFoundError(task_id)

            task_orm.status = new_status.value if hasattr(new_status, "value") else str(new_status)
            if notes is not None:
                task_orm.notes = notes
            task_orm.updated_at = datetime.now(UTC)

            # Fetch all tasks for plan to evaluate aggregate status
            all_t_res = await session.execute(
                select(UpgradeTaskOrm).where(UpgradeTaskOrm.plan_id == plan_id)
            )
            all_tasks = all_t_res.scalars().all()

            total_count = len(all_tasks)
            completed_count = sum(
                1 for t in all_tasks if t.status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED)
            )
            in_progress_count = sum(1 for t in all_tasks if t.status == TaskStatus.IN_PROGRESS)

            # Update plan status
            p_res = await session.execute(
                select(UpgradePlanOrm).where(UpgradePlanOrm.id == plan_id)
            )
            plan_orm = p_res.scalar_one_or_none()
            if plan_orm:
                if total_count > 0 and completed_count == total_count:
                    plan_orm.status = "COMPLETED"
                elif in_progress_count > 0 or completed_count > 0:
                    plan_orm.status = "IN_PROGRESS"
                plan_orm.updated_at = datetime.now(UTC)

            await session.commit()
            await session.refresh(task_orm)

            # Refresh artifact cache asynchronously
            if plan_orm:
                domain_plan = self._to_domain_plan(plan_orm)
                self._save_plan_artifact(domain_plan)

            return self._to_domain_task(task_orm)

    async def _persist_plan(self, plan: UpgradePlan) -> None:
        """Persist plan and tasks to database and artifact store."""
        artifact_path = self._save_plan_artifact(plan)

        async with self._db_gateway.session() as session:
            plan_orm = UpgradePlanOrm(
                id=plan.id,
                repository_id=plan.repository_id,
                impact_analysis_id=plan.impact_analysis_id,
                title=plan.title,
                base_commit=plan.base_commit,
                target_commit=plan.target_commit,
                risk_level=plan.risk_level,
                status=plan.status,
                reasoning_mode=plan.reasoning_mode,
                artifact_path=str(artifact_path),
                created_at=plan.created_at,
                updated_at=plan.updated_at,
            )
            session.add(plan_orm)

            for t in plan.tasks:
                task_orm = UpgradeTaskOrm(
                    id=t.id,
                    plan_id=plan.id,
                    step_number=t.step_number,
                    component=t.component,
                    component_type=t.component_type,
                    category=t.category.value if hasattr(t.category, "value") else str(t.category),
                    reason=t.reason,
                    dependencies=list(t.dependencies),
                    expected_changes=t.expected_changes,
                    required_tests=list(t.required_tests),
                    risk_level=t.risk_level,
                    status=t.status.value if hasattr(t.status, "value") else str(t.status),
                    is_circular=t.is_circular,
                    parallel_group_id=t.parallel_group_id,
                    notes=t.notes,
                    evidence={
                        "diff_snippet": t.evidence.diff_snippet if t.evidence else "",
                        "lines_affected": list(t.evidence.lines_affected) if t.evidence else [0, 0],
                        "call_chain": list(t.evidence.call_chain) if t.evidence else [],
                        "file_path": t.evidence.file_path if t.evidence else "",
                        "target_symbol": t.evidence.target_symbol if t.evidence else "",
                        "actionability": str(
                            t.actionability.value
                            if hasattr(t.actionability, "value")
                            else t.actionability
                        ),
                        "action_type": str(
                            t.action_type.value
                            if hasattr(t.action_type, "value")
                            else t.action_type
                        ),
                        "tier_name": t.tier_name,
                        "tier_meaning": t.tier_meaning,
                        "change_significance": (
                            t.change_significance.value
                            if hasattr(t.change_significance, "value")
                            else str(t.change_significance)
                        )
                        if t.change_significance
                        else None,
                        "ai_confidence": t.ai_confidence,
                        "ai_review": t.ai_review,
                    }
                    if t.evidence
                    else None,
                    created_at=t.created_at,
                    updated_at=t.updated_at,
                )
                session.add(task_orm)

            await session.commit()

    def _save_plan_artifact(self, plan: UpgradePlan) -> str:
        """Write complete plan JSON payload to artifact storage."""
        payload = {
            "plan_id": str(plan.id),
            "repository_id": str(plan.repository_id),
            "impact_analysis_id": str(plan.impact_analysis_id),
            "title": plan.title,
            "base_commit": plan.base_commit,
            "target_commit": plan.target_commit,
            "risk_level": plan.risk_level,
            "status": plan.status,
            "reasoning_mode": plan.reasoning_mode,
            "change_significance": (
                plan.change_significance.value
                if hasattr(plan.change_significance, "value")
                else str(plan.change_significance)
            ),
            "significance_reasoning": plan.significance_reasoning,
            "recommended_action": plan.recommended_action,
            "order_rationale": plan.order_rationale,
            "optional_suggestions": list(plan.optional_suggestions),
            "summary_metrics": {
                "total_tasks": plan.total_tasks,
                "completed_tasks": plan.completed_tasks,
                "in_progress_tasks": plan.in_progress_tasks,
                "pending_tasks": plan.pending_tasks,
                "blocked_tasks": plan.blocked_tasks,
                "skipped_tasks": plan.skipped_tasks,
                "progress_percentage": plan.progress_percentage,
            },
            "informational_changes": [
                {
                    "component": ic.component,
                    "file_path": ic.file_path,
                    "category": str(ic.category),
                    "reason": ic.reason,
                    "diff_snippet": ic.diff_snippet,
                    "actionability": str(ic.actionability),
                }
                for ic in plan.informational_changes
            ],
            "ai_plan_review": plan.ai_plan_review,
            "tasks": [
                {
                    "id": str(t.id),
                    "step_number": t.step_number,
                    "component": t.component,
                    "component_type": t.component_type,
                    "category": str(t.category),
                    "reason": t.reason,
                    "dependencies": list(t.dependencies),
                    "expected_changes": t.expected_changes,
                    "required_tests": list(t.required_tests),
                    "risk_level": t.risk_level,
                    "status": str(t.status),
                    "is_circular": t.is_circular,
                    "parallel_group_id": t.parallel_group_id,
                    "notes": t.notes,
                    "actionability": str(
                        t.actionability.value
                        if hasattr(t.actionability, "value")
                        else t.actionability
                    ),
                    "action_type": str(
                        t.action_type.value if hasattr(t.action_type, "value") else t.action_type
                    ),
                    "tier_name": t.tier_name,
                    "tier_meaning": t.tier_meaning,
                    "change_significance": (
                        t.change_significance.value
                        if hasattr(t.change_significance, "value")
                        else str(t.change_significance)
                    )
                    if t.change_significance
                    else None,
                    "ai_confidence": t.ai_confidence,
                    "ai_review": t.ai_review,
                    "evidence": {
                        "diff_snippet": t.evidence.diff_snippet if t.evidence else "",
                        "lines_affected": list(t.evidence.lines_affected) if t.evidence else [0, 0],
                        "call_chain": list(t.evidence.call_chain) if t.evidence else [],
                        "file_path": t.evidence.file_path if t.evidence else "",
                    }
                    if t.evidence
                    else {},
                }
                for t in plan.tasks
            ],
        }
        path = self._artifact_store.write_artifact(plan.id, payload)
        return str(path)

    @classmethod
    def _to_domain_plan(cls, orm: UpgradePlanOrm) -> UpgradePlan:
        """Convert UpgradePlanOrm to domain UpgradePlan aggregate."""
        tasks = [cls._to_domain_task(t) for t in orm.tasks]
        return UpgradePlan(
            id=orm.id,
            repository_id=orm.repository_id,
            impact_analysis_id=orm.impact_analysis_id,
            title=orm.title,
            base_commit=orm.base_commit,
            target_commit=orm.target_commit,
            risk_level=orm.risk_level,
            status=orm.status,
            tasks=tasks,
            reasoning_mode=orm.reasoning_mode,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    @classmethod
    def _to_domain_task(cls, orm: UpgradeTaskOrm) -> UpgradeTask:
        """Convert UpgradeTaskOrm to domain UpgradeTask entity."""
        ev_dict = orm.evidence or {}
        evidence = (
            TaskEvidence(
                diff_snippet=ev_dict.get("diff_snippet", ""),
                lines_affected=tuple(ev_dict.get("lines_affected", (0, 0))),
                call_chain=tuple(ev_dict.get("call_chain", ())),
                file_path=ev_dict.get("file_path", ""),
                target_symbol=ev_dict.get("target_symbol", ""),
            )
            if orm.evidence
            else None
        )
        act_str = ev_dict.get("actionability") or "UPGRADE"
        try:
            actionability = Actionability(act_str)
        except ValueError:
            actionability = Actionability.UPGRADE

        act_type_str = ev_dict.get("action_type") or "REQUIRED_CHANGE"
        try:
            action_type = TaskActionType(act_type_str)
        except ValueError:
            action_type = TaskActionType.REQUIRED_CHANGE

        sig_str = ev_dict.get("change_significance")
        change_sig = None
        if sig_str:
            try:
                change_sig = ChangeSignificance(sig_str)
            except ValueError:
                change_sig = None

        tier_name = ev_dict.get("tier_name") or ""
        tier_meaning = ev_dict.get("tier_meaning") or ""

        return UpgradeTask(
            id=orm.id,
            plan_id=orm.plan_id,
            step_number=orm.step_number,
            component=orm.component,
            component_type=orm.component_type,
            category=TaskCategory(orm.category)
            if orm.category in TaskCategory.__members__.values()
            else TaskCategory.CORE_LOGIC,
            reason=orm.reason,
            dependencies=tuple(orm.dependencies or ()),
            expected_changes=orm.expected_changes,
            required_tests=tuple(orm.required_tests or ()),
            risk_level=orm.risk_level,
            status=TaskStatus(orm.status)
            if orm.status in TaskStatus.__members__.values()
            else TaskStatus.PENDING,
            is_circular=orm.is_circular,
            parallel_group_id=orm.parallel_group_id,
            notes=orm.notes,
            evidence=evidence,
            actionability=actionability,
            action_type=action_type,
            tier_name=tier_name,
            tier_meaning=tier_meaning,
            change_significance=change_sig,
            ai_confidence=ev_dict.get("ai_confidence"),
            ai_review=ev_dict.get("ai_review"),
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    @classmethod
    def _dict_to_impact_aggregate(cls, data: dict[str, Any]) -> ImpactAnalysisAggregate:
        """Convert a 4-key F05/F06 impact artifact payload into an ImpactAnalysisAggregate."""
        meta_raw = data.get("analysis_metadata", {})
        impact_raw = data.get("impact_analysis", {})
        dep_raw = data.get("dependency_graph", {})
        risk_raw = data.get("risk_analysis", {})

        raw_analysis_id = meta_raw.get("analysis_id")
        analysis_id = uuid.UUID(str(raw_analysis_id)) if raw_analysis_id else uuid.uuid4()

        raw_mode = meta_raw.get("reasoning_mode", "HEURISTIC")
        reasoning_mode = (
            ReasoningMode(raw_mode)
            if raw_mode in ReasoningMode.__members__.values()
            else ReasoningMode.HEURISTIC
        )

        metadata = AnalysisMetadataPayload(
            analysis_id=analysis_id,
            repository=str(meta_raw.get("repository", "")),
            base_commit=str(meta_raw.get("base_commit", "")),
            current_commit=str(meta_raw.get("current_commit", "")),
            reasoning_mode=reasoning_mode,
            total_changed_entities=int(meta_raw.get("total_changed_entities", 0)),
            total_deleted_files=int(meta_raw.get("total_deleted_files", 0)),
            total_impacted_downstream_files=int(meta_raw.get("total_impacted_downstream_files", 0)),
            total_callers_at_risk=int(meta_raw.get("total_callers_at_risk", 0)),
        )

        detailed_impacts: list[DetailedImpact] = []
        for d in impact_raw.get("detailed_impacts", []):
            callers = [
                CallerAtRisk(
                    qualified_name=c.get("qualified_name", ""),
                    file_path=c.get("file_path", ""),
                    distance=int(c.get("distance", 1)),
                    call_chain=tuple(c.get("call_chain", ())),
                )
                for c in d.get("callers_at_risk", [])
            ]
            raw_lines = d.get("lines_affected", (0, 0))
            lines_tuple = (
                (int(raw_lines[0]), int(raw_lines[1]))
                if isinstance(raw_lines, (list, tuple)) and len(raw_lines) >= 2
                else (0, 0)
            )
            detailed_impacts.append(
                DetailedImpact(
                    file=d.get("file", ""),
                    entity=d.get("entity", ""),
                    entity_type=d.get("entity_type", "function"),
                    lines_affected=lines_tuple,
                    diff_snippet=d.get("diff_snippet", ""),
                    change_summary=d.get("change_summary", ""),
                    remediation_guidance=d.get("remediation_guidance", ""),
                    justification=d.get("justification", ""),
                    outbound_calls=tuple(d.get("outbound_calls", ())),
                    inbound_callers=tuple(d.get("inbound_callers", ())),
                    callers_at_risk=tuple(callers),
                    downstream_dependent_files=tuple(d.get("downstream_dependent_files", ())),
                )
            )

        graph_nodes = [
            GraphNodePayload(
                changed_entity=n.get("changed_entity", ""),
                file=n.get("file", ""),
                downstream_dependent_files=tuple(n.get("downstream_dependent_files", ())),
                inbound_callers=tuple(n.get("inbound_callers", ())),
                outbound_calls=tuple(n.get("outbound_calls", ())),
            )
            for n in dep_raw.get("nodes", [])
        ]
        graph_edges = [
            GraphEdgePayload(
                caller=e.get("caller", ""),
                callee=e.get("callee", ""),
                relationship=e.get("relationship", "direct_call"),
            )
            for e in dep_raw.get("edges", [])
        ]
        dep_graph = DependencyGraphPayload(
            nodes=tuple(graph_nodes),
            edges=tuple(graph_edges),
            mermaid=dep_raw.get("mermaid", ""),
        )

        risk_lvl_str = risk_raw.get("risk_level", "LOW")
        risk_level = (
            RiskLevel(risk_lvl_str)
            if risk_lvl_str in RiskLevel.__members__.values()
            else RiskLevel.LOW
        )
        risk_factors = [
            RiskFactor(
                factor=f.get("factor", ""),
                severity=f.get("severity", "LOW"),
                justification=f.get("justification", ""),
            )
            for f in risk_raw.get("key_risk_factors", [])
        ]
        rem_steps = [
            RemediationStep(
                step_number=int(s.get("step_number", 1)),
                category=s.get("category", ""),
                action_description=s.get("action_description", ""),
                affected_targets=tuple(s.get("affected_targets", ())),
            )
            for s in risk_raw.get("actionable_remediation_plan", [])
        ]
        risk_payload = RiskAnalysisPayload(
            risk_level=risk_level,
            key_risk_factors=tuple(risk_factors),
            ci_cd_recommendations=tuple(risk_raw.get("ci_cd_recommendations", ())),
            actionable_remediation_plan=tuple(rem_steps),
        )

        return ImpactAnalysisAggregate(
            metadata=metadata,
            summary=impact_raw.get("summary", ""),
            detailed_impacts=tuple(detailed_impacts),
            dependency_graph=dep_graph,
            risk_analysis=risk_payload,
            created_at=datetime.now(UTC),
            ai_directive=risk_raw.get("ai_directive"),
        )
