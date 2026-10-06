"""Unit tests for TaskSynthesizer."""

from __future__ import annotations

from trace.analysis.planner.task_synthesizer import TaskSynthesizer
from trace.domain.plan import TaskCategory
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_synthesize_modified_entity_metadata() -> None:
    raw_impact = {
        "change_summary": "Signature modified",
        "justification": "Parameter renamed from id to transaction_id",
        "remediation_guidance": "Update callers to pass transaction_id",
        "diff_snippet": "- def pay(id):\n+ def pay(transaction_id):",
        "lines_affected": [10, 15],
    }

    reason, expected_changes, required_tests, evidence = TaskSynthesizer.synthesize_task_metadata(
        component="PaymentAPI.pay",
        category=TaskCategory.CONTRACT_API,
        component_type="endpoint",
        file_path="src/api/payment.py",
        raw_impact=raw_impact,
    )

    assert "Signature modified" in reason
    assert "transaction_id" in reason
    assert "Update callers to pass transaction_id" in expected_changes
    assert evidence.diff_snippet == raw_impact["diff_snippet"]
    assert evidence.lines_affected == (10, 15)
    assert evidence.file_path == "src/api/payment.py"
    assert "tests/test_payment.py" in required_tests


def test_synthesize_caller_at_risk_metadata() -> None:
    caller_info = {
        "distance": 2,
        "target_entity": "PaymentAPI.pay",
        "call_chain": ("CheckoutService.checkout", "OrderService.place_order", "PaymentAPI.pay"),
    }

    reason, expected_changes, required_tests, evidence = TaskSynthesizer.synthesize_task_metadata(
        component="CheckoutService.checkout",
        category=TaskCategory.CORE_LOGIC,
        component_type="method",
        file_path="src/services/checkout.py",
        caller_info=caller_info,
    )

    assert "Transitive caller at depth 2" in reason
    assert "PaymentAPI.pay" in reason
    assert "Verify indirect integration with 'PaymentAPI.pay'" in expected_changes
    assert evidence.call_chain == caller_info["call_chain"]


def test_synthesize_direct_caller_metadata() -> None:
    caller_info = {
        "distance": 1,
        "target_entity": "PaymentAPI.pay",
        "call_chain": ("OrderService.place_order", "PaymentAPI.pay"),
    }

    reason, expected_changes, required_tests, evidence = TaskSynthesizer.synthesize_task_metadata(
        component="OrderService.place_order",
        category=TaskCategory.CORE_LOGIC,
        component_type="method",
        file_path="src/services/order.py",
        caller_info=caller_info,
    )

    assert "Direct caller" in reason
    assert "PaymentAPI.pay" in reason
    assert "Audit direct call site of 'PaymentAPI.pay'" in expected_changes
    assert "src/services/order.py" in expected_changes
    assert "tests/test_order.py" in required_tests


def test_synthesize_documentation_only_metadata() -> None:
    flask_doc_diff = """
- :data:`.session`, :data:`g:`, and :data:`.current_app` become available.
+ :data:`.session`, :data:`g`, and :data:`.current_app` become available.
"""
    raw_impact = {
        "change_summary": "Internal function execution statements updated.",
        "justification": "Internal calculation logic altered.",
        "remediation_guidance": "Run test suite.",
        "diff_snippet": flask_doc_diff,
        "lines_affected": [120, 122],
    }

    reason, expected_changes, required_tests, evidence = TaskSynthesizer.synthesize_task_metadata(
        component="src/flask/app.py::test_request_context",
        category=TaskCategory.CORE_LOGIC,
        component_type="function",
        file_path="src/flask/app.py",
        raw_impact=raw_impact,
    )

    # Documentation-only changes must NOT describe calculation/behavior logic changes
    assert "Documentation or comment-only update" in reason
    assert "No executable logic" in reason
    assert "calculation logic altered" not in reason
    assert "Review docstring / documentation updates" in expected_changes
    assert required_tests == []


def test_synthesize_test_only_metadata() -> None:
    raw_impact = {
        "change_summary": "Updated test assertions",
        "justification": "Verifies new error code",
        "remediation_guidance": "Run tests",
        "diff_snippet": "+ assert res.status_code == 400",
        "lines_affected": [50, 52],
    }

    reason, expected_changes, required_tests, evidence = TaskSynthesizer.synthesize_task_metadata(
        component="tests/test_auth.py::test_login_failure",
        category=TaskCategory.INTEGRATION_TEST,
        component_type="function",
        file_path="tests/test_auth.py",
        raw_impact=raw_impact,
    )

    assert "Test suite or fixture modified" in reason
    assert "Execute test suite 'tests/test_auth.py'" in expected_changes
    assert "tests/test_auth.py" in required_tests


def test_generate_llm_refactoring_prompt() -> None:
    prompt_payload = TaskSynthesizer.generate_llm_refactoring_prompt(
        component="PaymentAPI.pay",
        category=TaskCategory.CONTRACT_API,
        component_type="endpoint",
        file_path="src/api/payment.py",
        heuristic_reason="Signature modified",
        heuristic_changes="Update callers",
        diff_snippet="+ def pay(transaction_id):",
        callers=["CheckoutService.checkout"],
    )

    messages = prompt_payload["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert "PaymentAPI.pay" in messages[1]["content"]
    assert "CheckoutService.checkout" in messages[1]["content"]


def test_parse_llm_enrichment_success_and_markdown_cleaning() -> None:
    # 1. Plain JSON
    raw_1 = (
        '{"refined_reason": "Breaking parameter change", '
        '"detailed_expected_changes": "Adopt kwargs", '
        '"recommended_tests": ["tests/test_pay.py"]}'
    )
    res_1 = TaskSynthesizer.parse_llm_enrichment(raw_1)
    assert res_1 is not None
    assert res_1["reason"] == "Breaking parameter change"
    assert res_1["expected_changes"] == "Adopt kwargs"
    assert res_1["recommended_tests"] == ["tests/test_pay.py"]

    # 2. Markdown fenced JSON
    raw_2 = (
        '```json\n{"refined_reason": "Fenced output", "detailed_expected_changes": "Fix it"}\n```'
    )
    res_2 = TaskSynthesizer.parse_llm_enrichment(raw_2)
    assert res_2 is not None
    assert res_2["reason"] == "Fenced output"

    # 3. Invalid JSON
    raw_3 = "Not JSON output"
    res_3 = TaskSynthesizer.parse_llm_enrichment(raw_3)
    assert res_3 is None


@pytest.mark.asyncio
async def test_enrich_task_with_openrouter_success() -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": (
                        '{"refined_reason": "AI enriched reason", '
                        '"detailed_expected_changes": "AI enriched changes", '
                        '"recommended_tests": ["tests/test_ai.py"]}'
                    )
                }
            }
        ]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        reason, changes, tests, ai_review = await TaskSynthesizer.enrich_task_with_openrouter(
            component="PaymentAPI.pay",
            category=TaskCategory.CONTRACT_API,
            component_type="endpoint",
            file_path="src/api/payment.py",
            heuristic_reason="Base reason",
            heuristic_changes="Base changes",
            api_key="sk-test-key",
        )

        assert reason == "AI enriched reason"
        assert changes == "AI enriched changes"
        assert tests == ["tests/test_ai.py"]
        assert ai_review is not None


@pytest.mark.asyncio
async def test_enrich_task_with_openrouter_fallback_on_error() -> None:
    # Test network failure / timeout fallback
    with patch("httpx.AsyncClient.post", side_effect=Exception("Connection timed out")):
        reason, changes, tests, ai_review = await TaskSynthesizer.enrich_task_with_openrouter(
            component="PaymentAPI.pay",
            category=TaskCategory.CONTRACT_API,
            component_type="endpoint",
            file_path="src/api/payment.py",
            heuristic_reason="Base reason",
            heuristic_changes="Base changes",
            api_key="sk-test-key",
        )

        # Must fall back gracefully to heuristic base
        assert reason == "Base reason"
        assert changes == "Base changes"
        assert tests is None
        assert ai_review is None
