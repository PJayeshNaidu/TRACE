"""Unit tests for ApplicationConfig and environment isolation."""

from trace.core.config import ApplicationConfig

import pytest
from pydantic import ValidationError


def test_valid_config_with_required_fields_only() -> None:
    """Config loads cleanly when all required fields are provided."""
    config = ApplicationConfig(
        _env_file=None,
        database_url="postgresql+asyncpg://user:pass@localhost:5432/trace",
    )
    assert (
        config.database_url.get_secret_value()
        == "postgresql+asyncpg://user:pass@localhost:5432/trace"
    )
    assert config.llm_default_model == "nvidia/nemotron-3.5-lightning:free"
    assert config.openrouter_model == "meta-llama/llama-3.3-70b-instruct:free"
    assert config.llm_enable_external_calls is False
    assert config.llm_enable_external_transmission is False
    assert config.app_env == "development"
    assert config.log_level == "INFO"
    assert config.neo4j_uri is None


def test_database_url_absent_raises_validation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing DATABASE_URL raises ValidationError naming the field."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError) as exc_info:
        ApplicationConfig(_env_file=None)
    assert "database_url" in str(exc_info.value).lower()


def test_empty_string_database_url_treated_as_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty string DATABASE_URL is treated as absent and raises ValidationError."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError) as exc_info:
        ApplicationConfig(_env_file=None, database_url="")
    assert "database_url" in str(exc_info.value).lower()


def test_empty_string_optional_fields_treated_as_none() -> None:
    """Empty string in optional fields is treated as None rather than invalid."""
    config = ApplicationConfig(
        _env_file=None,
        database_url="postgresql+asyncpg://user:pass@localhost:5432/trace",
        neo4j_uri="",
        neo4j_username="",
        neo4j_password="",
        openrouter_api_key="",
        llm_reasoning_model="",
        llm_fast_model="",
        llm_fallback_models="",
        vector_store_url="",
    )
    assert config.neo4j_uri is None
    assert config.neo4j_username is None
    assert config.neo4j_password is None
    assert config.openrouter_api_key is None
    assert config.llm_reasoning_model is None
    assert config.llm_fast_model is None
    assert config.llm_fallback_models == []
    assert config.vector_store_url is None


def test_llm_enable_external_transmission_defaults_to_false() -> None:
    """Transmission gate defaults to False (secure by default per FR-045)."""
    config = ApplicationConfig(
        _env_file=None,
        database_url="postgresql+asyncpg://user:pass@localhost:5432/trace",
    )
    assert config.llm_enable_external_transmission is False


def test_test_environment_isolation_from_ambient_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Constructed ApplicationConfig with _env_file=None is isolated from ambient host env."""
    # Set a hostile ambient env var
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://hostile:bad@hostile:5432/bad")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "hostile-model")

    # Pass explicit kwargs with _env_file=None
    isolated_config = ApplicationConfig(
        _env_file=None,
        database_url="postgresql+asyncpg://test:test@localhost:5432/test",
    )
    assert (
        isolated_config.database_url.get_secret_value()
        == "postgresql+asyncpg://test:test@localhost:5432/test"
    )

    # Also verify that deleting ambient env and passing kwargs succeeds
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("LLM_DEFAULT_MODEL", raising=False)
    clean_config = ApplicationConfig(
        _env_file=None,
        database_url="postgresql+asyncpg://clean:clean@localhost:5432/clean",
    )
    assert (
        clean_config.database_url.get_secret_value()
        == "postgresql+asyncpg://clean:clean@localhost:5432/clean"
    )


def test_fallback_models_comma_separated_parsing() -> None:
    """Comma-separated string of fallback models parses into list of strings."""
    config = ApplicationConfig(
        _env_file=None,
        database_url="postgresql+asyncpg://user:pass@localhost:5432/trace",
        llm_fallback_models="model1, model2, model3",
    )
    assert config.llm_fallback_models == ["model1", "model2", "model3"]


def test_llm_enable_external_calls_requires_api_key() -> None:
    """Enabling external LLM calls without an API key fails validation at startup."""
    with pytest.raises(ValidationError) as exc_info:
        ApplicationConfig(
            _env_file=None,
            database_url="postgresql+asyncpg://user:pass@localhost:5432/trace",
            llm_enable_external_calls=True,
            openrouter_api_key=None,
        )
    assert "openrouter_api_key" in str(exc_info.value).lower()


def test_git_execution_settings_defaults_and_overrides() -> None:
    """Git execution settings have safe defaults and accept valid overrides."""
    config_default = ApplicationConfig(
        _env_file=None,
        database_url="postgresql+asyncpg://user:pass@localhost:5432/trace",
    )
    assert config_default.git_timeout_seconds == 10.0
    assert config_default.git_binary_path == "git"

    config_custom = ApplicationConfig(
        _env_file=None,
        database_url="postgresql+asyncpg://user:pass@localhost:5432/trace",
        git_timeout_seconds=5.0,
        git_binary_path="/usr/bin/git",
    )
    assert config_custom.git_timeout_seconds == 5.0
    assert config_custom.git_binary_path == "/usr/bin/git"

    # Empty string should fall back to default
    config_empty = ApplicationConfig(
        _env_file=None,
        database_url="postgresql+asyncpg://user:pass@localhost:5432/trace",
        git_binary_path="",
    )
    assert config_empty.git_binary_path == "git"
