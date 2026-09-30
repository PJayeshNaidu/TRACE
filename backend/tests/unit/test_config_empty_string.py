"""Unit tests specifically exercising empty-string-as-absent validation with env isolation."""

from trace.core.config import ApplicationConfig

import pytest
from pydantic import ValidationError


def test_empty_string_required_database_url_raises_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DATABASE_URL="" supplied directly raises ValidationError with field named."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError) as exc_info:
        ApplicationConfig(_env_file=None, database_url="")
    assert "database_url" in str(exc_info.value).lower()


def test_empty_string_optional_neo4j_uri_treated_as_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """NEO4J_URI="" supplied directly is treated as None without error."""
    monkeypatch.delenv("NEO4J_URI", raising=False)
    cfg = ApplicationConfig(
        _env_file=None,
        database_url="postgresql+asyncpg://user:pass@localhost:5432/trace",
        neo4j_uri="",
    )
    assert cfg.neo4j_uri is None


def test_explicit_whitespace_treated_as_absent() -> None:
    """Whitespace-only strings in optional fields are treated as None."""
    cfg = ApplicationConfig(
        _env_file=None,
        database_url="postgresql+asyncpg://user:pass@localhost:5432/trace",
        neo4j_uri="   ",
        neo4j_username="   ",
    )
    assert cfg.neo4j_uri is None
    assert cfg.neo4j_username is None
