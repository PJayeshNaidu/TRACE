"""Centralized typed application configuration."""

import types
from typing import Any, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


class ApplicationConfig(BaseSettings):
    """Central typed settings for TRACE derived from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        def _patch_source(source: PydanticBaseSettingsSource) -> PydanticBaseSettingsSource:
            orig = getattr(source, "decode_complex_value", None)
            if orig is None:
                return source

            def custom_decode(self: Any, field_name: str, field: Any, value: Any) -> Any:
                if field_name == "llm_fallback_models" and isinstance(value, str):
                    val = value.strip()
                    if not val:
                        return []
                    if val.startswith("[") and val.endswith("]"):
                        try:
                            return orig(field_name, field, value)
                        except Exception:
                            pass
                    return [m.strip() for m in val.split(",") if m.strip()]
                return orig(field_name, field, value)

            source.decode_complex_value = types.MethodType(custom_decode, source)  # type: ignore[method-assign]
            return source

        return (
            init_settings,
            _patch_source(env_settings),
            _patch_source(dotenv_settings),
            file_secret_settings,
        )

    # Database (PostgreSQL)
    database_url: SecretStr = Field(
        ...,
        description="PostgreSQL async connection string (postgresql+asyncpg://...)",
    )

    # Graph Database (Neo4j)
    neo4j_uri: str | None = Field(
        default=None,
        description="Neo4j Bolt connection URI (bolt://...)",
    )
    neo4j_username: str | None = Field(
        default=None,
        description="Neo4j authentication username",
    )
    neo4j_password: SecretStr | None = Field(
        default=None,
        description="Neo4j authentication password",
    )

    # LLM Provider (OpenRouter)
    openrouter_api_key: SecretStr | None = Field(
        default=None,
        description="OpenRouter API key for external calls",
    )
    openrouter_base_url: str | None = Field(
        default=None,
        description="OpenRouter API base URL override",
    )
    llm_default_model: str = Field(
        default="mistralai/mistral-7b-instruct:free",
        description="Default free-tier LLM model identifier",
    )
    llm_reasoning_model: str | None = Field(
        default=None,
        description="Heavy reasoning LLM model identifier",
    )
    llm_fast_model: str | None = Field(
        default=None,
        description="Low-latency fast LLM model identifier",
    )
    llm_fallback_models: list[str] = Field(
        default_factory=list,
        description="Ordered list of fallback model identifiers",
    )

    # Infrastructure slots
    vector_store_url: str | None = Field(
        default=None,
        description="Vector store connection endpoint URL",
    )
    artifacts_dir: str = Field(
        default=".trace/artifacts",
        description="Filesystem directory for storing analysis run artifacts",
    )
    repo_analysis_dir: str = Field(
        default="repo_analysis",
        description="Filesystem directory for storing repository analysis JSON summaries",
    )

    # Environment and Observability
    app_env: Literal["development", "production", "test"] = Field(
        default="development",
        description="Application environment mode",
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging level threshold",
    )

    # Security Gates
    llm_enable_external_calls: bool = Field(
        default=False,
        description="Whether live external LLM calls are permitted",
    )
    llm_enable_external_transmission: bool = Field(
        default=False,
        description="Whether repository source code transmission to LLM is permitted",
    )

    # Git Subprocess Settings
    git_timeout_seconds: float = Field(
        default=10.0,
        gt=0.0,
        description="Timeout in seconds for Git subprocess operations",
    )
    git_binary_path: str = Field(
        default="git",
        description="Path to the system Git executable",
    )

    @field_validator("llm_fallback_models", mode="before")
    @classmethod
    def _parse_fallback_models(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            v_clean = v.strip()
            if not v_clean:
                return []
            return [m.strip() for m in v_clean.split(",") if m.strip()]
        if isinstance(v, list):
            return [str(m).strip() for m in v if str(m).strip()]
        return []

    @model_validator(mode="before")
    @classmethod
    def _treat_empty_strings_as_absent(cls, data: Any) -> Any:
        if isinstance(data, dict):
            cleaned = {}
            for k, v in data.items():
                if isinstance(v, str) and not v.strip():
                    # Empty string treated as absent
                    continue
                cleaned[k] = v
            return cleaned
        return data

    @model_validator(mode="after")
    def _validate_llm_call_prerequisites(self) -> "ApplicationConfig":
        if self.llm_enable_external_calls and not self.openrouter_api_key:
            raise ValueError(
                "OPENROUTER_API_KEY is required when LLM_ENABLE_EXTERNAL_CALLS is True"
            )
        return self
