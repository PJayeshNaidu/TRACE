"""Objective automated verification of docstrings and field descriptions for public interfaces."""

from trace.api.health.schemas import HealthStatus, ServiceStatus
from trace.core.config import ApplicationConfig
from trace.infrastructure.database.gateway import DatabaseGateway
from trace.infrastructure.graph.gateway import GraphGateway
from trace.infrastructure.llm.config import LLMConfig, ModelConfig
from trace.infrastructure.llm.provider import LLMProvider
from trace.infrastructure.llm.response import (
    ConfigurationError,
    ProviderError,
    Success,
    TimeoutError,
    TokenUsage,
)


def test_llm_provider_docstrings() -> None:
    """Verify LLMProvider Protocol and its public methods have non-empty docstrings."""
    assert LLMProvider.__doc__ is not None
    assert len(LLMProvider.__doc__.strip()) > 0

    assert LLMProvider.complete.__doc__ is not None
    assert len(LLMProvider.complete.__doc__.strip()) > 0

    assert LLMProvider.embed.__doc__ is not None
    assert len(LLMProvider.embed.__doc__.strip()) > 0


def test_database_gateway_docstrings() -> None:
    """Verify DatabaseGateway Protocol and its public methods have non-empty docstrings."""
    assert DatabaseGateway.__doc__ is not None
    assert len(DatabaseGateway.__doc__.strip()) > 0

    assert DatabaseGateway.session.__doc__ is not None
    assert len(DatabaseGateway.session.__doc__.strip()) > 0

    assert DatabaseGateway.health_check.__doc__ is not None
    assert len(DatabaseGateway.health_check.__doc__.strip()) > 0


def test_graph_gateway_docstrings() -> None:
    """Verify GraphGateway Protocol and its public methods have non-empty docstrings."""
    assert GraphGateway.__doc__ is not None
    assert len(GraphGateway.__doc__.strip()) > 0

    assert GraphGateway.health_check.__doc__ is not None
    assert len(GraphGateway.health_check.__doc__.strip()) > 0


def test_application_config_field_descriptions() -> None:
    """Verify ApplicationConfig and every one of its fields has a non-empty description."""
    assert ApplicationConfig.__doc__ is not None
    assert len(ApplicationConfig.__doc__.strip()) > 0

    for field_name, field_info in ApplicationConfig.model_fields.items():
        assert field_info.description is not None, f"Field '{field_name}' missing description"
        assert len(field_info.description.strip()) > 0


def test_health_schemas_field_descriptions() -> None:
    """Verify HealthStatus and ServiceStatus schemas and fields have non-empty descriptions."""
    assert HealthStatus.__doc__ is not None
    assert len(HealthStatus.__doc__.strip()) > 0
    for field_name, field_info in HealthStatus.model_fields.items():
        msg = f"HealthStatus field '{field_name}' missing description"
        assert field_info.description is not None, msg
        assert len(field_info.description.strip()) > 0

    assert ServiceStatus.__doc__ is not None
    assert len(ServiceStatus.__doc__.strip()) > 0
    for field_name, field_info in ServiceStatus.model_fields.items():
        msg = f"ServiceStatus field '{field_name}' missing description"
        assert field_info.description is not None, msg
        assert len(field_info.description.strip()) > 0


def test_llm_config_and_response_docstrings() -> None:
    """Verify LLMConfig, ModelConfig, and LLMResponse types have non-empty docstrings."""
    assert LLMConfig.__doc__ is not None
    assert len(LLMConfig.__doc__.strip()) > 0

    assert ModelConfig.__doc__ is not None
    assert len(ModelConfig.__doc__.strip()) > 0

    assert Success.__doc__ is not None
    assert len(Success.__doc__.strip()) > 0

    assert ConfigurationError.__doc__ is not None
    assert len(ConfigurationError.__doc__.strip()) > 0

    assert ProviderError.__doc__ is not None
    assert len(ProviderError.__doc__.strip()) > 0

    assert TimeoutError.__doc__ is not None
    assert len(TimeoutError.__doc__.strip()) > 0

    assert TokenUsage.__doc__ is not None
    assert len(TokenUsage.__doc__.strip()) > 0
