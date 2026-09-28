"""Unit tests for Repository domain entity, enums, and normalization logic."""

import uuid
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from pathlib import Path
from trace.domain.repository import (
    ConnectionValidationResult,
    Repository,
    RepositoryStatus,
    RepositoryType,
    normalize_location,
)

import pytest


def test_repository_enums() -> None:
    """RepositoryType and RepositoryStatus define exact required enum values."""
    assert RepositoryType.LOCAL == "LOCAL"
    assert RepositoryType.REMOTE == "REMOTE"

    assert RepositoryStatus.REGISTERED == "REGISTERED"
    assert RepositoryStatus.CONNECTED == "CONNECTED"
    assert RepositoryStatus.ERROR == "ERROR"


def test_repository_entity_immutability() -> None:
    """Repository entity is frozen and rejects attribute assignment."""
    repo = Repository(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        type=RepositoryType.LOCAL,
        location="/repos/my-repo",
        default_branch=None,
        status=RepositoryStatus.REGISTERED,
        last_error=None,
        last_validated_at=None,
        last_analysis_run_id=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    with pytest.raises(FrozenInstanceError):
        repo.status = RepositoryStatus.CONNECTED  # type: ignore[misc]


def test_connection_validation_result_defaults() -> None:
    """ConnectionValidationResult is frozen with sensible defaults."""
    res = ConnectionValidationResult(is_connected=True, detected_branch="main", latency_ms=15.2)
    assert res.is_connected is True
    assert res.detected_branch == "main"
    assert res.error_message is None
    assert res.latency_ms == 15.2


def test_normalize_location_local(tmp_path: Path) -> None:
    """Local path normalization resolves to canonical absolute path."""
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()
    normalized = normalize_location(str(repo_dir), RepositoryType.LOCAL)
    assert Path(normalized).is_absolute()
    assert "\\" not in normalized  # forward slashes


def test_normalize_location_remote_https() -> None:
    """Remote HTTPS URLs normalize scheme/host to lowercase, strip trailing .git and slashes."""
    raw = "HTTPS://GitHub.com/My-Org/My-Repo.git/"
    normalized = normalize_location(raw, RepositoryType.REMOTE)
    assert normalized == "https://github.com/My-Org/My-Repo"

    clean = "https://gitlab.com/group/subgroup/project"
    assert (
        normalize_location(clean, RepositoryType.REMOTE)
        == "https://gitlab.com/group/subgroup/project"
    )


def test_normalize_location_remote_scp() -> None:
    """SCP-style SSH URLs normalize host to lowercase, strip trailing .git and slashes."""
    raw = "git@GITHUB.COM:My-Org/My-Repo.git/"
    normalized = normalize_location(raw, RepositoryType.REMOTE)
    assert normalized == "git@github.com:My-Org/My-Repo"


def test_normalize_location_remote_ssh_protocol() -> None:
    """SSH protocol URLs normalize host to lowercase, strip trailing .git and slashes."""
    raw = "SSH://git@GITHUB.COM/My-Org/My-Repo.git/"
    normalized = normalize_location(raw, RepositoryType.REMOTE)
    assert normalized == "ssh://git@github.com/My-Org/My-Repo"


def test_normalize_location_invalid_type() -> None:
    """Unsupported repository type raises UnsupportedRepositoryTypeError."""
    from trace.domain.exceptions import UnsupportedRepositoryTypeError

    with pytest.raises(UnsupportedRepositoryTypeError):
        normalize_location("something", "INVALID")  # type: ignore[arg-type]


def test_normalize_location_fallbacks() -> None:
    """Test fallback paths when path resolution or urlsplit raises Exception."""
    from unittest.mock import patch

    with patch("os.path.abspath", side_effect=Exception("resolve failure")):
        res = normalize_location("relative/path", RepositoryType.LOCAL)
        assert res == "relative/path"

    with patch("urllib.parse.urlsplit", side_effect=Exception("parse failure")):
        res = normalize_location("https://github.com/fallback/repo.git/", RepositoryType.REMOTE)
        assert res == "https://github.com/fallback/repo"
