"""Unit tests for nuanced risk analysis, docstring/comment delta inference, and risk scoring."""

import pytest
from trace.analysis.delta_inference import DeltaInferenceEngine
from trace.analysis.reasoner.heuristic import HeuristicRuleEngine
from trace.domain.impact import RiskLevel
from trace.services.impact import ImpactAnalysisService


def test_flask_docstring_typo_is_doc_only():
    """Verify that the Sphinx/RST docstring typo fix is correctly identified as doc-only."""
    engine = DeltaInferenceEngine()
    diff = (
        "-        :data:`.session`, :data:`g:, and :data:`.current_app` become available.\n"
        "+        :data:`.session`, :data:`g`, and :data:`.current_app` become available."
    )
    result = engine.infer_delta("request_context", diff, inbound_callers=("flask.app.Flask.wsgi_app",))
    assert result.is_doc_only is True
    assert result.is_signature_change is False
    assert result.is_return_change is False
    assert result.is_exception_change is False
    assert "Documentation / docstring updated" in result.change_summary
    assert "Documentation update only" in result.remediation_guidance


def test_comment_only_diff_is_doc_only():
    """Verify that single-line or block comment updates are identified as doc-only."""
    engine = DeltaInferenceEngine()
    diff = (
        "-    # Calculate tax for standard state\n"
        "+    # Calculate tax including municipal surcharge"
    )
    result = engine.infer_delta("calculate_tax", diff)
    assert result.is_doc_only is True
    assert result.is_signature_change is False


def test_executable_code_diff_is_not_doc_only():
    """Verify that executable body statements are NOT treated as doc-only."""
    engine = DeltaInferenceEngine()
    diff = (
        "-    return amount * 0.1\n"
        "+    return amount * 0.2"
    )
    result = engine.infer_delta("calculate_tax", diff)
    assert result.is_doc_only is False
    assert result.is_return_change is True


def test_signature_diff_is_not_doc_only():
    """Verify that callable signature updates are recognized as signature changes."""
    engine = DeltaInferenceEngine()
    diff = (
        "-def calculate_tax(amount: float) -> float:\n"
        "+def calculate_tax(amount: float, rate: float = 0.08) -> float:"
    )
    result = engine.infer_delta("calculate_tax", diff)
    assert result.is_doc_only is False
    assert result.is_signature_change is True


@pytest.mark.asyncio
async def test_heuristic_reasoner_doc_only():
    """Verify that HeuristicRuleEngine produces non-breaking justification for doc-only updates."""
    reasoner = HeuristicRuleEngine()
    summary = {
        "entity": "request_context",
        "entity_type": "function",
        "file": "src/flask/app.py",
        "lines_affected": (1505, 1511),
    }
    diff = (
        "-        :data:`.session`, :data:`g:, and :data:`.current_app` become available.\n"
        "+        :data:`.session`, :data:`g`, and :data:`.current_app` become available."
    )
    res = await reasoner.reason(
        entity_summary=summary,
        diff_snippet=diff,
        inbound_callers=("flask.app.Flask.test_request_context", "flask.app.Flask.wsgi_app"),
        downstream_files=("src/flask/app.py",),
    )
    assert res["is_doc_only"] is True
    assert "Upstream callers unaffected (cosmetic/documentation change)" in res["justification"]
    assert "Documentation/docstring for function `request_context`" in res["justification"]


def test_remediation_plan_for_doc_only():
    """Verify that doc-only changes produce documentation verification rather than code refactor steps."""
    engine = DeltaInferenceEngine()
    plan = engine.synthesize_remediation_plan(
        signature_changed_entities=[],
        deleted_files=[],
        inbound_callers=["flask.app.Flask.wsgi_app"],
        downstream_files=["src/flask/app.py"],
        is_doc_only_run=True,
    )
    assert len(plan) == 1
    assert plan[0].category == "Documentation Verification"
    assert "Verify documentation build" in plan[0].action_description


def test_evaluate_risk_doc_only_scores_low():
    """Verify that an all-doc-only run evaluates to RiskLevel.LOW even if callers exist in call graph."""
    service = ImpactAnalysisService(
        db_gateway=None,  # type: ignore
        git_provider=None,  # type: ignore
        artifact_store=None,  # type: ignore
    )
    level, factors = service._evaluate_risk(
        total_entities=1,
        signature_changes=0,
        total_callers=0,  # 0 callers at risk for doc-only
        deleted_files_count=0,
        deleted_code_files_count=0,
        deleted_non_code_files_count=0,
        is_all_doc_only=True,
    )
    assert level == RiskLevel.LOW
    assert len(factors) == 1
    assert factors[0].factor == "Documentation / Non-Executable Modification"
    assert factors[0].severity == "LOW"


def test_evaluate_risk_deleted_markdown_is_low():
    """Verify that deleting a non-code file (README.md) does NOT trigger high severity Module Deletion."""
    service = ImpactAnalysisService(
        db_gateway=None,  # type: ignore
        git_provider=None,  # type: ignore
        artifact_store=None,  # type: ignore
    )
    level, factors = service._evaluate_risk(
        total_entities=0,
        signature_changes=0,
        total_callers=0,
        deleted_files_count=1,
        deleted_code_files_count=0,
        deleted_non_code_files_count=1,
        is_all_doc_only=False,
    )
    assert level == RiskLevel.LOW
    assert factors[0].factor == "Non-Code Asset Deletion"
    assert factors[0].severity == "LOW"


def test_evaluate_risk_deleted_python_module_is_high():
    """Verify that deleting an actual code file (service.py) triggers high severity Code Module Deletion."""
    service = ImpactAnalysisService(
        db_gateway=None,  # type: ignore
        git_provider=None,  # type: ignore
        artifact_store=None,  # type: ignore
    )
    level, factors = service._evaluate_risk(
        total_entities=0,
        signature_changes=0,
        total_callers=0,
        deleted_files_count=1,
        deleted_code_files_count=1,
        deleted_non_code_files_count=0,
        is_all_doc_only=False,
    )
    assert level == RiskLevel.HIGH
    assert factors[0].factor == "Code Module Deletion"
    assert factors[0].severity == "HIGH"


def test_evaluate_risk_executable_callers_triggers_high():
    """Verify that executable modifications with >=2 callers trigger HIGH risk."""
    service = ImpactAnalysisService(
        db_gateway=None,  # type: ignore
        git_provider=None,  # type: ignore
        artifact_store=None,  # type: ignore
    )
    level, factors = service._evaluate_risk(
        total_entities=1,
        signature_changes=0,
        total_callers=3,
        deleted_files_count=0,
        deleted_code_files_count=0,
        deleted_non_code_files_count=0,
        is_all_doc_only=False,
    )
    assert level == RiskLevel.HIGH
    assert any(f.factor == "Multi-Hop Caller Dependency" for f in factors)
