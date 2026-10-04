"""Architectural tier classification engine for F07 Upgrade Planner."""

from __future__ import annotations

from pathlib import Path
from trace.domain.plan import (
    Actionability,
    ChangeSignificance,
    TaskActionType,
    TaskCategory,
)
from typing import Any


class TierMapper:
    """Classifies code symbols, files, and endpoints into 7 architectural categories."""

    TIER_WEIGHTS: dict[TaskCategory, int] = {
        TaskCategory.CONTRACT_API: 1,
        TaskCategory.CORE_LOGIC: 2,
        TaskCategory.DATA_MAPPING: 3,
        TaskCategory.CONSUMER_HANDLER: 4,
        TaskCategory.CLIENT_UI: 5,
        TaskCategory.INTEGRATION_TEST: 6,
        TaskCategory.DOCUMENTATION_CONFIG: 7,
    }

    @classmethod
    def canonicalize_component(cls, component: str, file_path: str = "") -> str:
        """Normalize component identifier to prevent duplicates like
        main.py::calculate_total vs main.py::main.calculate_total.
        """
        if not component:
            comp_file = (file_path or "").strip().replace("\\", "/")
            return comp_file[2:] if comp_file.startswith("./") else comp_file

        comp = component.strip().replace("\\", "/")
        if comp.startswith("./"):
            comp = comp[2:]

        if "::" in comp:
            file_part, entity_part = comp.split("::", 1)
            file_path = file_part
            entity_name = entity_part
        else:
            file_path = (file_path or "").strip().replace("\\", "/")
            if file_path.startswith("./"):
                file_path = file_path[2:]
            entity_name = comp if comp != file_path else ""

        file_path = file_path.strip().replace("\\", "/")
        if file_path.startswith("./"):
            file_path = file_path[2:]

        if not entity_name:
            return file_path
        if not file_path:
            return entity_name

        # Strip module / file stem prefix if repeated in entity_name
        stem = Path(file_path).stem  # e.g., 'main'
        if entity_name.startswith(stem + "."):
            entity_name = entity_name[len(stem) + 1 :]
        else:
            parts = Path(file_path).with_suffix("").parts
            for i in range(len(parts)):
                mod_cand = ".".join(parts[i:])
                if entity_name.startswith(mod_cand + "."):
                    entity_name = entity_name[len(mod_cand) + 1 :]
                    break

        return f"{file_path}::{entity_name}"

    @classmethod
    def assess_change_significance(
        cls,
        detailed_impacts: tuple[Any, ...] | list[Any] = (),
        risk_analysis: Any | None = None,
    ) -> tuple[ChangeSignificance, str]:
        """Deterministically assess the semantic significance of a changeset.

        Returns:
            (ChangeSignificance, reasoning)
        """
        if not detailed_impacts:
            return (
                ChangeSignificance.NO_ACTION_REQUIRED,
                "No changed entities detected in revision comparison.",
            )

        all_doc_or_whitespace = True
        for d in detailed_impacts:
            diff = getattr(d, "diff_snippet", "")
            file_p = getattr(d, "file", "")
            summary = getattr(d, "change_summary", "")
            if not cls.is_documentation_only(diff, file_p, change_summary=summary):
                all_doc_or_whitespace = False
                break

        if all_doc_or_whitespace:
            return (
                ChangeSignificance.MINOR_CHANGE,
                "The revision contains documentation-only changes with no executable behavior "
                "or API contract changes.",
            )

        import re

        # Check for indicators of MAJOR_CHANGE:
        # 1. Public API / Contract category
        # 2. Function / Method signature changes in diff (def / async def parameter changes)
        # 3. Return type modifications (->)
        # 4. Database schema / migration models (DATA_MAPPING)
        # 5. Exception changes (raise)
        # 6. Breaking risk factors from F06
        has_major = False
        sig_indicators: list[str] = []

        risk_factors = getattr(risk_analysis, "key_risk_factors", ()) if risk_analysis else ()
        for rf in risk_factors:
            rf_str = str(rf).lower()
            if any(
                term in rf_str
                for term in ("breaking", "signature", "removed parameter", "incompatible")
            ):
                has_major = True
                sig_indicators.append(f"Risk factor: {rf}")

        for d in detailed_impacts:
            diff = getattr(d, "diff_snippet", "")
            file_p = getattr(d, "file", "")
            cat = cls.classify(
                getattr(d, "entity", "") or file_p,
                getattr(d, "entity_type", "function"),
                file_p,
                diff,
            )
            if cat == TaskCategory.CONTRACT_API:
                has_major = True
                sig_indicators.append("Public API / endpoint contract modified")
            elif cat == TaskCategory.DATA_MAPPING:
                has_major = True
                sig_indicators.append("Database schema / persistence mapping modified")

            # Check diff for signature / return type / exception modifications (ignoring comments)
            if diff:
                code_lines = []
                for line in diff.splitlines():
                    if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
                        stripped = line[1:].strip()
                        if stripped and not stripped.startswith(
                            ("#", "//", "/*", "*", '"""', "'''")
                        ):
                            code_lines.append(line)
                code_text = "\n".join(code_lines)
                if code_text:
                    if re.search(r"^\s*[-+]\s*(async\s+def\b|def\b)", code_text, re.MULTILINE):
                        has_major = True
                        sig_indicators.append("Function or method signature modified")
                    if re.search(r"^\s*[-+].*->\s*[a-zA-Z_]", code_text, re.MULTILINE):
                        has_major = True
                        sig_indicators.append("Return type annotation or contract modified")
                    if re.search(r"^\s*[-+]\s*raise\s+[a-zA-Z_]", code_text, re.MULTILINE):
                        has_major = True
                        sig_indicators.append("Exception behavior modified")

        if has_major:
            reason = (
                f"Major change: {'; '.join(dict.fromkeys(sig_indicators))}"
                if sig_indicators
                else "Public API, contract, schema, or functional signature modifications detected."
            )
            return (ChangeSignificance.MAJOR_CHANGE, reason)

        return (
            ChangeSignificance.MODERATE_CHANGE,
            "Internal implementation changes with potential caller or integration impact.",
        )

    @classmethod
    def calculate_plan_risk(
        cls,
        significance: ChangeSignificance,
        blast_radius: int = 0,
        risk_factors: tuple[Any, ...] | list[Any] = (),
        caller_count: int | None = None,
        key_risk_factors: tuple[Any, ...] | list[Any] | None = None,
        base_risk_level: str | None = None,
    ) -> str:
        """Calculate overall plan risk: Change Severity × Blast Radius × Evidence.

        Documentation/comment/minor changes are strictly LOW risk regardless of caller count.
        """
        if caller_count is not None:
            blast_radius = caller_count
        if key_risk_factors is not None:
            risk_factors = key_risk_factors
        if significance in (
            ChangeSignificance.MINOR_CHANGE,
            ChangeSignificance.NO_ACTION_REQUIRED,
        ):
            return "LOW"

        if blast_radius >= 10 or any("critical" in str(rf).lower() for rf in risk_factors):
            return "CRITICAL"

        if significance == ChangeSignificance.MAJOR_CHANGE:
            if blast_radius >= 5:
                return "CRITICAL"
            elif blast_radius >= 2 or base_risk_level == "HIGH":
                return "HIGH"
            elif base_risk_level:
                return base_risk_level
            elif blast_radius >= 1:
                return "MEDIUM"
            return "LOW"

        # MODERATE_CHANGE
        if base_risk_level:
            return base_risk_level
        if blast_radius >= 3:
            return "MEDIUM"
        return "LOW"

    @classmethod
    def evaluate_caller_action_type(
        cls,
        distance: int = 1,
        callee_has_signature_change: bool = False,
        caller_distance: int | None = None,
        target_diff_snippet: str = "",
        target_category: TaskCategory | None = None,
    ) -> TaskActionType:
        """Determine whether an affected caller needs code changes or only validation."""
        if caller_distance is not None:
            distance = caller_distance
        if target_diff_snippet and not callee_has_signature_change:
            callee_has_signature_change = cls.is_callable_contract_change(target_diff_snippet)
        if target_category == TaskCategory.CONTRACT_API:
            callee_has_signature_change = True

        if callee_has_signature_change:
            if distance <= 1:
                return TaskActionType.REQUIRED_CHANGE
            return TaskActionType.VALIDATION_ONLY
        return TaskActionType.VALIDATION_ONLY

    @classmethod
    def calculate_task_risk(
        cls,
        action_type: TaskActionType,
        category: TaskCategory,
        change_significance: ChangeSignificance,
        caller_distance: int = 0,
        has_signature_change: bool = False,
    ) -> str:
        """Calculate granular risk for an individual upgrade task.

        - Breaking public API / signature -> HIGH
        - Direct incompatible caller -> HIGH
        - Indirect downstream validation -> MEDIUM
        - Test-only validation -> MEDIUM or LOW
        - Documentation / comment-only -> LOW
        - Trivial typo / no action -> LOW
        """
        if (
            action_type in (TaskActionType.NO_ACTION, TaskActionType.LOW_PRIORITY_REVIEW)
            or category == TaskCategory.DOCUMENTATION_CONFIG
            or change_significance
            in (
                ChangeSignificance.MINOR_CHANGE,
                ChangeSignificance.NO_ACTION_REQUIRED,
            )
        ):
            return "LOW"

        if category == TaskCategory.INTEGRATION_TEST:
            return "MEDIUM" if has_signature_change else "LOW"

        if action_type == TaskActionType.VALIDATION_ONLY:
            return "MEDIUM"

        # REQUIRED_CHANGE
        if change_significance == ChangeSignificance.MAJOR_CHANGE:
            if (
                has_signature_change
                or category == TaskCategory.CONTRACT_API
                or caller_distance <= 1
            ):
                return "HIGH"
            return "MEDIUM"

        if change_significance == ChangeSignificance.MODERATE_CHANGE:
            return "MEDIUM"

        return "LOW"

    @classmethod
    def explain_topological_order(
        cls,
        categories_present: set[TaskCategory] | list[Any] | None = None,
        has_cycles: bool = False,
    ) -> str:
        """Provide a clear, human-readable explanation of why this sequence is ordered,
        grounded in the actual dependency graph.
        """
        if not categories_present:
            return "No upgrade tasks requiring dependency ordering."

        # If passed a list of SequencedNodes / nodes with components and dependencies
        if (
            isinstance(categories_present, list)
            and categories_present
            and hasattr(categories_present[0], "component")
        ):
            nodes = categories_present
            lines: list[str] = ["Why this order?"]
            for node in nodes:
                step = getattr(node, "step_number", 0)
                comp = getattr(node, "component", "")
                short_name = comp.split("::")[-1] if "::" in comp else comp
                deps = getattr(node, "dependencies", [])
                act_type = getattr(node, "action_type", None)
                cat = getattr(node, "category", None)

                if not deps:
                    if cat == TaskCategory.CONTRACT_API:
                        lines.append(
                            f"{step}. {short_name} defines/changes the root callable contract."
                        )
                    elif cat == TaskCategory.DATA_MAPPING:
                        lines.append(
                            f"{step}. {short_name} defines underlying database persistence schema."
                        )
                    else:
                        lines.append(
                            f"{step}. {short_name} changes the core callable contract / logic."
                        )
                else:
                    dep_names = [d.split("::")[-1] if "::" in d else d for d in deps]
                    deps_str = ", ".join(dep_names)
                    if act_type == TaskActionType.VALIDATION_ONLY:
                        lines.append(
                            f"{step}. {short_name} is downstream and requires validation "
                            "after direct caller updates."
                        )
                    elif cat == TaskCategory.INTEGRATION_TEST:
                        lines.append(
                            f"{step}. {short_name} validates {deps_str} once changes complete."
                        )
                    else:
                        lines.append(
                            f"{step}. {short_name} directly consumes {deps_str} "
                            "and must adapt to the updated contract."
                        )

            if has_cycles or any(getattr(n, "is_circular", False) for n in nodes):
                lines.append(
                    "Note: Circular dependencies detected and batched into co-dependent groups."
                )

            return "\n".join(lines)

        cats = (
            categories_present if isinstance(categories_present, set) else set(categories_present)
        )
        has_contract = TaskCategory.CONTRACT_API in cats
        has_data = TaskCategory.DATA_MAPPING in cats
        has_core = TaskCategory.CORE_LOGIC in cats
        has_ui = TaskCategory.CLIENT_UI in cats
        has_test = TaskCategory.INTEGRATION_TEST in cats

        if has_data and has_core:
            base = (
                "The planner executes schema and data model updates first, "
                "followed by core business logic consumers, and integration test validation."
            )
        elif has_contract and (has_core or has_ui):
            base = (
                "The planner updates the changed API/contract first, then its direct consumers, "
                "followed by indirectly affected components and finally validation/tests."
            )
        elif has_ui and has_core:
            base = (
                "Core backend services are updated first to stabilize data delivery, "
                "followed by client/UI presentations and end-to-end tests."
            )
        elif has_core and has_test:
            base = (
                "The modified implementation is updated first, followed by dependent callers, "
                "and finally test suites to verify system integrity."
            )
        else:
            base = (
                "Components are sequenced from root contracts and dependencies "
                "down to dependent callers and validation suites."
            )

        if has_cycles:
            base += (
                " Circular dependencies were detected and batched into co-dependent "
                "execution groups via Tarjan's SCC algorithm."
            )
        return base

    @classmethod
    def is_callable_contract_change(cls, diff_snippet: str) -> bool:
        """Detect whether diff snippet modifies function/method signature or contract."""
        if not diff_snippet:
            return False
        import re

        code_lines = []
        for line in diff_snippet.splitlines():
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
                stripped = line[1:].strip()
                if stripped and not stripped.startswith(("#", "//", "/*", "*", '"""', "'''")):
                    code_lines.append(line)

        code_text = "\n".join(code_lines)
        if not code_text:
            return False

        if re.search(r"^\s*[-+]\s*(async\s+def\b|def\b)", code_text, re.MULTILINE):
            return True
        if re.search(r"^\s*[-+].*->\s*[a-zA-Z_]", code_text, re.MULTILINE):
            return True
        if re.search(r"^\s*[-+]\s*raise\s+[a-zA-Z_]", code_text, re.MULTILINE):
            return True
        return False

    @classmethod
    def is_whitespace_or_formatting_diff(cls, diff_snippet: str) -> bool:
        """Detect if diff is whitespace-only or indentation/formatting-only."""
        if not diff_snippet or not diff_snippet.strip():
            return True

        added: list[str] = []
        removed: list[str] = []
        for raw in diff_snippet.splitlines():
            if raw.startswith("+") and not raw.startswith("+++"):
                added.append(raw[1:])
            elif raw.startswith("-") and not raw.startswith("---"):
                removed.append(raw[1:])

        if not added and not removed:
            return True

        # All lines added or removed are whitespace or empty
        if all(not line.strip() for line in added) and all(not line.strip() for line in removed):
            return True

        # If stripped lines are identical (formatting/indentation changes only)
        added_stripped = [line.strip() for line in added if line.strip()]
        removed_stripped = [line.strip() for line in removed if line.strip()]
        if added_stripped == removed_stripped:
            return True

        return False

    @classmethod
    def is_documentation_diff(cls, diff_snippet: str) -> bool:
        """Deterministically detect if a diff patch contains only comments or documentation."""
        if not diff_snippet or not diff_snippet.strip():
            return False

        changed_lines: list[str] = []
        for raw in diff_snippet.splitlines():
            if (raw.startswith("+") and not raw.startswith("+++")) or (
                raw.startswith("-") and not raw.startswith("---")
            ):
                line = raw[1:].strip()
                if line:
                    changed_lines.append(line)

        if not changed_lines:
            return True

        import re

        # Keywords that indicate executable code statements in Python (case-sensitive)
        code_stmt_pattern = re.compile(
            r"^\s*(async\s+def\b|def\b|class\b|return\b|raise\b|import\b|from\s+\w+\s+import|assert\b|yield\b|del\b|pass\b|break\b|continue\b)"
        )
        block_pattern = re.compile(r"^\s*(if|elif|else|while|for|with|try|except|finally)\b.*:\s*$")
        assign_pattern = re.compile(
            r"^[a-zA-Z_]\w*(\s*,\s*[a-zA-Z_]\w*)*\s*(\+=|-=|\*=|/=|%=|:=|=)(?!=)"
        )
        call_stmt_pattern = re.compile(r"^[a-zA-Z_]\w*(\.[a-zA-Z_]\w*)*\s*\(.*?\)\s*$")
        decorator_pattern = re.compile(r"^\s*@[a-zA-Z_]\w*")

        docstring_headers = {
            "args:",
            "arguments:",
            "parameters:",
            "params:",
            "returns:",
            "return:",
            "raises:",
            "raise:",
            "yields:",
            "yield:",
            "attributes:",
            "examples:",
            "example:",
            "note:",
            "notes:",
            "see also:",
            "references:",
            "-------",
            "=======",
            "~~~~~~~",
        }

        for line in changed_lines:
            # 1. Full line comments and docstring quote markers
            if line.startswith(
                ("#", "//", "/*", "*/", "*", '"""', "'''", ".. ", ">>>", "...")
            ) or line.endswith(('"""', "'''")):
                continue

            # 2. Sphinx / RST directives and roles
            if re.search(r":[a-zA-Z_-]+:`", line) or line.startswith(
                (
                    ":param",
                    ":return",
                    ":type",
                    ":rtype",
                    ":data:",
                    ":raises:",
                    ":class:",
                    ":func:",
                    ":mod:",
                )
            ):
                continue

            # 3. Google/NumPy docstring section titles
            if line.lower() in docstring_headers or line.lower().rstrip(":") in docstring_headers:
                continue

            # 4. Check for executable code constructs
            if code_stmt_pattern.search(line):
                return False
            if block_pattern.search(line):
                return False
            if assign_pattern.search(line):
                return False
            if call_stmt_pattern.search(line):
                return False
            if decorator_pattern.search(line):
                return False

            # 5. Check if line contains assignment or comparison operators
            if any(
                op in line for op in ("+=", "-=", "*=", "/=", ":=", "==", "!=", "->", "<=", ">=")
            ):
                return False

            # 6. Check if line ends with colon or semicolon like code statements
            if line.endswith((":", ";", "{", "}")):
                return False

        return True

    @classmethod
    def classify_actionability(
        cls,
        diff_snippet: str = "",
        file_path: str = "",
        entity_name: str = "",
        entity_type: str = "function",
        category: TaskCategory | None = None,
        change_summary: str = "",
        has_callers: bool = False,
    ) -> Actionability:
        """Deterministically classify the actionability of a detected change.

        Returns one of:
            IGNORE: Whitespace, formatting, comment typos with no behavioral impact.
            INFORMATIONAL: Documentation, markdown, non-code configs not requiring code remediation.
            REVIEW: Test-only changes or changes where intent is ambiguous.
            UPGRADE: Meaningful contract, schema, logic, or caller-propagated changes.
        """
        # 1. Whitespace or Formatting changes
        if diff_snippet and cls.is_whitespace_or_formatting_diff(diff_snippet):
            return Actionability.IGNORE

        norm_path = file_path.replace("\\", "/").lower()
        is_doc_file = (
            norm_path.endswith(
                (".md", ".rst", ".txt", ".json", ".yaml", ".yml", ".toml", ".ini", ".env")
            )
            or "/docs/" in norm_path
            or norm_path.startswith("docs/")
        )

        # 2. Comment, docstring typo, or documentation-only diff
        if diff_snippet and cls.is_documentation_diff(diff_snippet):
            if is_doc_file:
                return Actionability.INFORMATIONAL
            return Actionability.IGNORE

        # 3. Standalone documentation or config file
        if is_doc_file or category == TaskCategory.DOCUMENTATION_CONFIG:
            return Actionability.INFORMATIONAL

        # 4. Tests
        is_test_file = (
            category == TaskCategory.INTEGRATION_TEST
            or norm_path.startswith(("tests/", "test/"))
            or "/tests/" in norm_path
            or "/test/" in norm_path
            or norm_path.endswith(("_test.py", "_test.ts", "_test.js"))
            or Path(norm_path).name.startswith("test_")
        )
        if is_test_file:
            return Actionability.REVIEW

        # 5. Default: Executable business logic, contract, data mapping, or handler
        return Actionability.UPGRADE

    @classmethod
    def is_documentation_only(
        cls,
        diff_snippet: str = "",
        file_path: str = "",
        category: TaskCategory | None = None,
        change_summary: str = "",
    ) -> bool:
        """Deterministically determine if a change is documentation/comment-only."""
        act = cls.classify_actionability(
            diff_snippet=diff_snippet,
            file_path=file_path,
            category=category,
            change_summary=change_summary,
        )
        return act in (Actionability.IGNORE, Actionability.INFORMATIONAL)

    @classmethod
    def classify(
        cls,
        entity_name: str,
        entity_type: str = "function",
        file_path: str = "",
        diff_snippet: str = "",
    ) -> TaskCategory:
        """Deterministically determine the architectural TaskCategory for an entity."""
        # 0. Check if diff is documentation-only
        if diff_snippet and cls.is_documentation_diff(diff_snippet):
            return TaskCategory.DOCUMENTATION_CONFIG

        normalized_path = file_path.replace("\\", "/").lower()
        lowered_name = entity_name.lower()
        lowered_type = entity_type.lower()

        # 1. Tests (check first to avoid test API mocks being classified as contracts)
        is_test_path = (
            normalized_path.startswith(("tests/", "test/"))
            or "/tests/" in normalized_path
            or "/test/" in normalized_path
            or normalized_path.endswith(("_test.py", "_test.ts", "_test.js"))
            or Path(normalized_path).name.startswith("test_")
        )
        if (
            lowered_type in ("test", "testunit", "testfunction", "testcase")
            or is_test_path
            or (not file_path and lowered_name.startswith(("test_", "test")))
        ):
            return TaskCategory.INTEGRATION_TEST

        # 2. Non-code Documentation & Config
        if (
            normalized_path.endswith(
                (".md", ".rst", ".txt", ".json", ".yaml", ".yml", ".toml", ".ini", ".env")
            )
            or "dockerfile" in normalized_path
            or "/docs/" in normalized_path
            or normalized_path.startswith("docs/")
            or "/.github/" in normalized_path
            or normalized_path.startswith(".github/")
        ):
            return TaskCategory.DOCUMENTATION_CONFIG

        # 3. Client & UI
        if (
            lowered_type in ("view", "page", "component", "ui", "template")
            or normalized_path.startswith(("frontend/", "client/", "ui/", "static/", "web/"))
            or any(
                p in normalized_path
                for p in (
                    "/frontend/",
                    "/client/",
                    "/ui/",
                    "/static/",
                    "/web/",
                    "/components/",
                    "/pages/",
                    "/templates/",
                )
            )
            or normalized_path.endswith(
                (".jsx", ".tsx", ".vue", ".svelte", ".html", ".css", ".scss", ".sass", ".less")
            )
        ):
            return TaskCategory.CLIENT_UI

        # 4. Contracts & Public APIs
        if (
            lowered_type in ("endpoint", "route", "api")
            or "/api/" in normalized_path
            or normalized_path.startswith("api/")
            or "/routes/" in normalized_path
            or "/endpoints/" in normalized_path
            or "/v1/" in normalized_path
            or "/v2/" in normalized_path
            or "contract" in normalized_path
            or "openapi" in normalized_path
            or lowered_name.endswith(("api", "endpoint", "route"))
        ):
            return TaskCategory.CONTRACT_API

        # 5. Data & Schema Mapping
        if (
            lowered_type in ("table", "database", "model", "schema")
            or "/models/" in normalized_path
            or normalized_path.startswith("models/")
            or "/schemas/" in normalized_path
            or normalized_path.startswith("schemas/")
            or "/alembic/" in normalized_path
            or normalized_path.startswith("alembic/")
            or "/migrations/" in normalized_path
            or normalized_path.startswith("migrations/")
            or "/database/" in normalized_path
            or normalized_path.startswith("database/")
            or normalized_path.endswith(("models.py", "schema.py", "entities.py"))
            or lowered_name.endswith(("model", "orm", "table", "schema", "record"))
        ):
            return TaskCategory.DATA_MAPPING

        # 6. Consumer / Handler
        if (
            lowered_type in ("worker", "task", "handler", "consumer", "webhook", "listener")
            or "/handlers/" in normalized_path
            or normalized_path.startswith("handlers/")
            or "/workers/" in normalized_path
            or normalized_path.startswith("workers/")
            or "/webhooks/" in normalized_path
            or normalized_path.startswith("webhooks/")
            or "/celery/" in normalized_path
            or normalized_path.startswith("celery/")
            or "/tasks/" in normalized_path
            or normalized_path.startswith("tasks/")
            or "/events/" in normalized_path
            or normalized_path.startswith("events/")
            or lowered_name.endswith(
                ("handler", "worker", "webhook", "consumer", "listener", "job")
            )
        ):
            return TaskCategory.CONSUMER_HANDLER

        # 7. Default: Core Domain Logic
        return TaskCategory.CORE_LOGIC

    @classmethod
    def get_tier_weight(cls, category: TaskCategory) -> int:
        """Return numeric sort weight for a category (lower runs earlier)."""
        return cls.TIER_WEIGHTS.get(category, 99)
