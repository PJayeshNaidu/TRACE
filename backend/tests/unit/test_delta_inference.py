"""Unit tests for deterministic syntax delta inference and remediation planning."""

from trace.analysis.delta_inference import DeltaInferenceEngine


def test_delta_inference_signature_change():
    """Verify signature change detection from def lines."""
    engine = DeltaInferenceEngine()
    snippet = "-def calculate_tax(amount):\n+def calculate_tax(amount, rate=0.08):"
    delta = engine.infer_delta("calculate_tax", snippet, inbound_callers=("checkout",))

    assert delta.is_signature_change is True
    assert "signature" in delta.change_summary.lower()
    assert "audit all call sites" in delta.remediation_guidance.lower()


def test_delta_inference_return_change():
    """Verify return value semantics change detection."""
    engine = DeltaInferenceEngine()
    snippet = "-    return total\n+    return {'total': total, 'tax': tax}"
    delta = engine.infer_delta("calculate_tax", snippet, inbound_callers=("checkout",))

    assert delta.is_return_change is True
    assert "return" in delta.change_summary.lower()
    assert "upstream callers" in delta.remediation_guidance.lower()


def test_delta_inference_exception_change():
    """Verify exception flow change detection."""
    engine = DeltaInferenceEngine()
    snippet = "+    raise InvalidTaxRateError('Rate exceeds threshold')"
    delta = engine.infer_delta("calculate_tax", snippet, inbound_callers=("checkout",))

    assert delta.is_exception_change is True
    assert "exception" in delta.change_summary.lower()


def test_synthesize_remediation_plan():
    """Verify 4-step remediation plan synthesis."""
    engine = DeltaInferenceEngine()
    plan = engine.synthesize_remediation_plan(
        signature_changed_entities=["calculate_tax"],
        deleted_files=["legacy_math.py"],
        inbound_callers=["checkout", "invoice"],
        downstream_files=["deploy.yaml", "main.py"],
    )

    categories = [step.category for step in plan]
    assert "Contract Changes" in categories
    assert "Missing Modules" in categories
    assert "Direct Callers" in categories
    assert "Integration Validation" in categories
