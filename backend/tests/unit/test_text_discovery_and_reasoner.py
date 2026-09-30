"""Unit tests for text discovery and dual-track heuristic/LLM reasoner."""

import pytest
from trace.analysis.reasoner.heuristic import HeuristicRuleEngine
from trace.analysis.reasoner.llm import OpenRouterLlmReasoner
from trace.analysis.text_discovery import TextDiscoveryEngine


def test_text_discovery_engine(tmp_path):
    """Verify word-boundary discovery in non-code files."""
    engine = TextDiscoveryEngine()

    # Create dummy files
    deploy_yaml = tmp_path / "deploy.yaml"
    deploy_yaml.write_text("task:\n  handler: calculate_tax\n  retries: 3", encoding="utf-8")

    readme_md = tmp_path / "README.md"
    readme_md.write_text("Call calculate_tax to compute tax.", encoding="utf-8")

    source_py = tmp_path / "payments.py"
    source_py.write_text("def calculate_tax(): pass", encoding="utf-8")

    matches = engine.find_text_references(
        working_tree_path=tmp_path,
        entity_name="calculate_tax",
        source_file_path="payments.py",
    )

    assert "deploy.yaml" in matches
    assert "README.md" in matches
    assert "payments.py" not in matches  # Self-reference excluded


@pytest.mark.asyncio
async def test_heuristic_rule_engine():
    """Verify deterministic heuristic reasoner outputs structured explanation."""
    engine = HeuristicRuleEngine()

    summary = {
        "entity": "calculate_tax",
        "entity_type": "function",
        "file": "payments.py",
        "lines_affected": (10, 15),
    }
    snippet = "-def calculate_tax(x):\n+def calculate_tax(x, y=1):"

    res = await engine.reason(
        entity_summary=summary,
        diff_snippet=snippet,
        inbound_callers=("checkout",),
        downstream_files=("payments.py", "deploy.yaml"),
    )

    assert "signature" in res["change_summary"].lower()
    assert "checkout" in res["remediation_guidance"].lower()
    assert "payments.py" in res["justification"]


@pytest.mark.asyncio
async def test_openrouter_fallback_on_invalid_key():
    """Verify OpenRouterLlmReasoner falls back gracefully to heuristics when offline or invalid key."""
    reasoner = OpenRouterLlmReasoner(api_key="invalid_test_key", timeout_seconds=1.0)

    summary = {
        "entity": "calculate_tax",
        "entity_type": "function",
        "file": "payments.py",
        "lines_affected": (10, 15),
    }
    snippet = "-def calculate_tax(x):\n+def calculate_tax(x, y=1):"

    # Should not raise exception; falls back to heuristic engine
    res = await reasoner.reason(
        entity_summary=summary,
        diff_snippet=snippet,
        inbound_callers=("checkout",),
        downstream_files=("payments.py",),
    )

    assert "change_summary" in res
    assert "remediation_guidance" in res
    assert "justification" in res
