"""Unit tests verifying secret redaction and structured context binding in logs."""

from trace.core.logging import configure_logging

import pytest
import structlog


def test_logging_redaction_replaces_secrets(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify SecretRedactingProcessor redacts sensitive keys before JSON rendering."""
    configure_logging(app_env="test", log_level="INFO")
    logger = structlog.get_logger("test.redaction")
    logger.info(
        "User login event",
        api_key="real-secret-123",
        password="my-secret-password",
        openrouter_api_key="sk-or-v1-secret",
    )
    captured = capsys.readouterr()
    log_text = captured.out

    assert "[REDACTED]" in log_text
    assert "real-secret-123" not in log_text
    assert "my-secret-password" not in log_text
    assert "sk-or-v1-secret" not in log_text


def test_structured_contextvars_binding(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify named context fields (project_id, analysis_run_id) bind and render in JSON logs."""
    configure_logging(app_env="test", log_level="INFO")
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        project_id="proj-123",
        analysis_run_id="run-456",
        agent_name="CodeAnalyzer",
        stage="ast_parse",
    )

    logger = structlog.get_logger("test.context")
    logger.info("Analyzing repository")
    captured = capsys.readouterr()
    log_text = captured.out

    assert '"project_id": "proj-123"' in log_text
    assert '"analysis_run_id": "run-456"' in log_text
    assert '"agent_name": "CodeAnalyzer"' in log_text
    assert '"stage": "ast_parse"' in log_text

    structlog.contextvars.clear_contextvars()
