"""Unit tests for TRACE AI Assistant Synthesis Layer (F10)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

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
from trace.services.assistant.synthesis import (
    ASSISTANT_SYSTEM_PROMPT,
    DEFAULT_MODEL,
    OFFLINE_FALLBACK_MODEL,
    AssistantPromptBuilder,
    AssistantService,
    AssistantSynthesisService,
    DeterministicFallbackGenerator,
)


@pytest.fixture
def sample_bundle() -> CompactEvidenceBundle:
    """Create a populated CompactEvidenceBundle for testing."""
    proj_id = uuid4()
    run_id = uuid4()
    bundle = CompactEvidenceBundle(
        project_id=proj_id,
        analysis_run_id=run_id,
        matched_symbols=["api.routes.auth_handler", "auth_service.login"],
        graph_paths=[
            GraphNeighborEvidence(
                source_symbol="api.routes.auth_handler",
                target_symbol="auth_service.login",
                relationship_kind="CALLS",
                depth=1,
                file_path="src/api/routes.py",
            )
        ],
        total_graph_paths_count=1,
        risk_items=[
            RiskItemEvidence(
                symbol_name="auth_service.login",
                risk_level="HIGH",
                risk_score=82.5,
                factors=["breaking_signature_change", "high_fan_out_12"],
                recommendations=["Add integration regression tests for auth_handler"],
            )
        ],
        plan_steps=[
            PlanStepEvidence(
                task_id="TASK-001",
                title="Step 1: auth_service.login",
                step_number=1,
                tier="CORE_DOMAIN",
                component="auth_service.login",
                dependencies=[],
                status="PENDING",
                reason="Update method signature with required timeout param",
            ),
            PlanStepEvidence(
                task_id="TASK-004",
                title="Step 4: api.routes.auth_handler",
                step_number=4,
                tier="API_SURFACE",
                component="api.routes.auth_handler",
                dependencies=["1"],
                status="PENDING",
                reason="Update call site with timeout parameter",
            ),
        ],
        diff_hunks=[
            DiffHunkEvidence(
                symbol_name="auth_service.login",
                file_path="src/services/auth.py",
                change_type="MODIFIED",
                is_breaking=True,
                summary="Added timeout parameter to login signature",
            )
        ],
    )
    bundle.sources = AssistantRetrievalService.assemble_evidence_sources(bundle)
    return bundle


def test_prompt_formatting(sample_bundle: CompactEvidenceBundle):
    """T010: Test prompt builder formats anti-hallucination prompt and JSON evidence."""
    question = "Why is api.routes.auth_handler affected by this change?"
    messages = AssistantPromptBuilder.build_messages(question, sample_bundle)

    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == ASSISTANT_SYSTEM_PROMPT
    assert "expert software architecture peer" in messages[0]["content"]

    user_msg = messages[1]["content"]
    assert f"User Question: {question}" in user_msg
    assert "Available Project Context:" in user_msg
    assert "api.routes.auth_handler" in user_msg
    assert "auth_service.login" in user_msg
    assert "Provide a direct, helpful, and natural response." in user_msg


def test_deterministic_fallback(sample_bundle: CompactEvidenceBundle):
    """T012: Test deterministic markdown generation from evidence bundle."""
    question = "Explain the risk for auth_service.login"
    text = DeterministicFallbackGenerator.generate(question, sample_bundle)

    assert "🎯 Identified Target Entities" in text
    assert "`api.routes.auth_handler`" in text
    assert "🕸️ Dependency Graph Paths" in text
    assert "1-hop [CALLS]" in text
    assert "⚠️ Assessed Risk Breakdown" in text
    assert "HIGH" in text
    assert "82.5" in text
    assert "📋 Upgrade Plan Sequence & Tasks" in text
    assert "*(Generated via TRACE deterministic offline engine)*" in text


def test_plan_sequence_synthesis(sample_bundle: CompactEvidenceBundle):
    """T015: Test plan sequencing explanation between tasks."""
    question = "Why does Task 1 precede Task 4 in the upgrade plan?"
    text = DeterministicFallbackGenerator.generate(question, sample_bundle)

    assert "Upgrade Plan Sequence Rationale: Step 1 vs Step 4" in text
    assert "Preceding Task (Step 1)" in text
    assert "Subsequent Task (Step 4)" in text
    assert "prerequisite dependency" in text


def test_empty_state_fallback():
    """Test deterministic fallback handles empty evidence bundle cleanly."""
    bundle = CompactEvidenceBundle(project_id=uuid4(), analysis_run_id=None)
    text = DeterministicFallbackGenerator.generate("What is non_existent_symbol?", bundle)

    assert "No matching code symbols" in text
    assert "non_existent_symbol" in text


@pytest.mark.asyncio
async def test_openrouter_invocation(sample_bundle: CompactEvidenceBundle):
    """T011: Test OpenRouter LLM completion invocation with mocked HTTP client."""
    config = ApplicationConfig(
        openrouter_api_key=SecretStr("sk-test-key-12345"),
        llm_enable_external_calls=True,
        openrouter_model="mistralai/mistral-7b-instruct:free",
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "api.routes.auth_handler is affected because it directly calls auth_service.login."
                }
            }
        ]
    }

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.is_closed = False
    mock_client.post.return_value = mock_response

    service = AssistantSynthesisService(config=config, http_client=mock_client)
    answer, model = await service.synthesize("Why is auth_handler affected?", sample_bundle)

    assert "auth_handler is affected" in answer
    assert model == "mistralai/mistral-7b-instruct:free"
    mock_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_openrouter_transient_retry_and_fallback(sample_bundle: CompactEvidenceBundle):
    """T011 & T012: Test fallback when OpenRouter experiences transient 429 rate-limiting."""
    config = ApplicationConfig(
        openrouter_api_key=SecretStr("sk-test-key-12345"),
        llm_enable_external_calls=True,
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 429
    mock_response.request = MagicMock()
    mock_response.text = "Rate limit exceeded"

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.is_closed = False
    mock_client.post.return_value = mock_response

    service = AssistantSynthesisService(config=config, http_client=mock_client)
    answer, model = await service.synthesize("Why is auth_handler affected?", sample_bundle)

    assert model == OFFLINE_FALLBACK_MODEL
    assert "🕸️ Dependency Graph Paths" in answer


@pytest.mark.asyncio
async def test_assistant_service_ask(sample_bundle: CompactEvidenceBundle):
    """T013: Test end-to-end AssistantService.ask orchestrating retrieval and synthesis."""
    mock_retrieval = AsyncMock(spec=AssistantRetrievalService)
    mock_retrieval.retrieve.return_value = sample_bundle

    synthesis_service = AssistantSynthesisService(
        config=ApplicationConfig(llm_enable_external_calls=False)
    )

    orchestrator = AssistantService(
        retrieval_service=mock_retrieval,
        synthesis_service=synthesis_service,
    )

    request = AssistantQueryRequest(
        project_id=sample_bundle.project_id,
        analysis_run_id=sample_bundle.analysis_run_id,
        question="Why is api.routes.auth_handler affected?",
    )

    response = await orchestrator.ask(request)

    assert isinstance(response, AssistantQueryResponse)
    assert response.model_used == OFFLINE_FALLBACK_MODEL
    assert len(response.sources) > 0
    assert any(s.type == "graph" for s in response.sources)
    assert any(s.type == "risk" for s in response.sources)
    assert any(s.type == "plan" for s in response.sources)
    assert any(s.type == "diff" for s in response.sources)


@pytest.mark.asyncio
async def test_openrouter_sanitizes_thinking_scratchpad(sample_bundle: CompactEvidenceBundle):
    """Test that <think> tags and 'here is a thinking process' scratchpads are stripped."""
    config = ApplicationConfig(
        openrouter_api_key=SecretStr("sk-test-key-12345"),
        llm_enable_external_calls=True,
        openrouter_model="meta-llama/llama-3.3-70b-instruct:free",
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "<think>Let me analyze the dependencies.\nFirst auth_service.</think>\n\nHere's a thinking process:\nStep 1: check caller.\n\n# Architecture Analysis\n`auth_handler` calls `auth_service.login`."
                }
            }
        ]
    }

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.is_closed = False
    mock_client.post.return_value = mock_response

    service = AssistantSynthesisService(config=config, http_client=mock_client)
    answer, model = await service.synthesize("Why is auth_handler affected?", sample_bundle)

    assert "<think>" not in answer
    assert "</think>" not in answer
    assert "Here's a thinking process:" not in answer
    assert "# Architecture Analysis" in answer
    assert "`auth_handler` calls `auth_service.login`." in answer


@pytest.mark.asyncio
async def test_openrouter_sanitizes_thinking_process_split(sample_bundle: CompactEvidenceBundle):
    """Test that 'Analyze User Input:' and 'Final Answer:' parts are correctly extracted."""
    config = ApplicationConfig(
        openrouter_api_key=SecretStr("sk-test-key-12345"),
        llm_enable_external_calls=True,
        openrouter_model="meta-llama/llama-3.3-70b-instruct:free",
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "Analyze User Input:\n1. The user asks about dependencies.\n2. Checking graph.\n\nFinal Answer:\n`auth_handler` directly depends on `auth_service.login`."
                }
            }
        ]
    }

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.is_closed = False
    mock_client.post.return_value = mock_response

    service = AssistantSynthesisService(config=config, http_client=mock_client)
    answer, model = await service.synthesize("Why is auth_handler affected?", sample_bundle)

    assert "Analyze User Input:" not in answer
    assert "Final Answer:" not in answer
    assert "`auth_handler` directly depends on `auth_service.login`." in answer

