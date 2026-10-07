"""Unit tests for TRACE Assistant schemas and data contracts."""

import uuid
from pydantic import ValidationError
import pytest

from trace.schemas.assistant import (
    AssistantQueryRequest,
    AssistantQueryResponse,
    EvidenceSource,
)


def test_evidence_source_valid():
    """Verify EvidenceSource serialization and required fields."""
    src = EvidenceSource(
        type="graph",
        identifier="auth_service.login",
        summary="Direct 1-hop caller: api.routes.auth_handler -> auth_service.login",
        metadata={"depth": 1, "relationship": "CALLS"},
    )
    assert src.type == "graph"
    assert src.identifier == "auth_service.login"
    assert src.summary.startswith("Direct 1-hop")
    assert src.metadata["depth"] == 1

    d = src.model_dump()
    assert d["type"] == "graph"
    assert d["identifier"] == "auth_service.login"


def test_evidence_source_invalid_type():
    """Verify EvidenceSource rejects invalid type categories."""
    with pytest.raises(ValidationError):
        EvidenceSource(
            type="invalid_type",  # type: ignore[arg-type]
            identifier="x",
            summary="test",
        )


def test_assistant_query_request_valid():
    """Verify AssistantQueryRequest parses valid parameters."""
    proj_id = uuid.uuid4()
    run_id = uuid.uuid4()
    req = AssistantQueryRequest(
        project_id=proj_id,
        analysis_run_id=run_id,
        question="Why is checkout_service high risk?",
    )
    assert req.project_id == proj_id
    assert req.analysis_run_id == run_id
    assert req.question == "Why is checkout_service high risk?"


def test_assistant_query_request_validation_errors():
    """Verify AssistantQueryRequest enforces length limits and required fields."""
    proj_id = uuid.uuid4()

    # Too short question (< 3 chars)
    with pytest.raises(ValidationError):
        AssistantQueryRequest(project_id=proj_id, question="ab")

    # Missing project_id
    with pytest.raises(ValidationError):
        AssistantQueryRequest(question="Valid question here?")  # type: ignore[call-arg]


def test_assistant_query_response_serialization():
    """Verify AssistantQueryResponse serializes with sources and model attribution."""
    src = EvidenceSource(
        type="risk",
        identifier="checkout_service",
        summary="Risk Score 80: High Blast Radius",
        metadata={"score": 80.0},
    )
    resp = AssistantQueryResponse(
        answer="Checkout service is critical due to blast radius.",
        sources=[src],
        model_used="mistralai/mistral-7b-instruct:free",
    )
    assert resp.answer.startswith("Checkout service")
    assert len(resp.sources) == 1
    assert resp.sources[0].type == "risk"
    assert resp.model_used == "mistralai/mistral-7b-instruct:free"
