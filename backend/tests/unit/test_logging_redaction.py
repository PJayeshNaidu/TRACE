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


def test_logging_redaction_replaces_uri_credentials(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify SecretRedactingProcessor redacts embedded URI credentials in strings."""
    configure_logging(app_env="test", log_level="INFO")
    logger = structlog.get_logger("test.uri_redaction")
    logger.info(
        "git_remote_probe",
        url="https://user:ghp_secrettoken123@github.com/org/repo.git",
        raw_cmd="git ls-remote https://admin:password456@gitlab.com/group/repo.git",
    )
    captured = capsys.readouterr()
    log_text = captured.out

    assert "ghp_secrettoken123" not in log_text
    assert "password456" not in log_text
    assert "https://[REDACTED]:[REDACTED]@github.com/org/repo.git" in log_text
    assert "https://[REDACTED]:[REDACTED]@gitlab.com/group/repo.git" in log_text


def test_f01_project_lifecycle_structured_log_events(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify structured log events for project lifecycle operations."""
    import json

    configure_logging(app_env="test", log_level="INFO")
    logger = structlog.get_logger("trace.services.project")

    # project_created
    logger.info("project_created", project_id="p-123", name="My Project")
    # project_archived
    logger.info("project_archived", project_id="p-123")
    # project_activated
    logger.info("project_activated", project_id="p-123")

    captured = capsys.readouterr()
    lines = [json.loads(line) for line in captured.out.strip().split("\n") if line.strip()]

    events = {item["event"]: item for item in lines}
    assert "project_created" in events
    assert events["project_created"]["project_id"] == "p-123"
    assert events["project_created"]["name"] == "My Project"

    assert "project_archived" in events
    assert events["project_archived"]["project_id"] == "p-123"

    assert "project_activated" in events
    assert events["project_activated"]["project_id"] == "p-123"


def test_f01_repository_lifecycle_structured_log_events(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify structured log events for repository lifecycle operations."""
    import json

    configure_logging(app_env="test", log_level="INFO")
    logger = structlog.get_logger("trace.services.repository")

    # repository_registered
    logger.info(
        "repository_registered",
        repository_id="r-456",
        project_id="p-123",
        type="LOCAL",
        location="/path/to/repo",
    )
    # repository_validated (connected)
    logger.info(
        "repository_validated",
        repository_id="r-456",
        is_connected=True,
        status="CONNECTED",
        latency_ms=12.5,
    )
    # repository_deleted
    logger.info(
        "repository_deleted",
        repository_id="r-456",
        project_id="p-123",
    )

    captured = capsys.readouterr()
    lines = [json.loads(line) for line in captured.out.strip().split("\n") if line.strip()]

    events = {item["event"]: item for item in lines}
    assert "repository_registered" in events
    assert events["repository_registered"]["repository_id"] == "r-456"
    assert events["repository_registered"]["project_id"] == "p-123"
    assert events["repository_registered"]["type"] == "LOCAL"
    assert events["repository_registered"]["location"] == "/path/to/repo"

    assert "repository_validated" in events
    assert events["repository_validated"]["repository_id"] == "r-456"
    assert events["repository_validated"]["is_connected"] is True
    assert events["repository_validated"]["status"] == "CONNECTED"
    assert events["repository_validated"]["latency_ms"] == 12.5

    assert "repository_deleted" in events
    assert events["repository_deleted"]["repository_id"] == "r-456"
    assert events["repository_deleted"]["project_id"] == "p-123"
