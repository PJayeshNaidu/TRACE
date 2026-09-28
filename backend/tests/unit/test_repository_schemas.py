"""Unit tests for Repository API request and response schemas and credential isolation."""

import uuid
from datetime import UTC, datetime
from trace.api.repositories.schemas import (
    RepositoryListResponse,
    RepositoryRegisterRequest,
    RepositoryResponse,
    ValidationReportResponse,
)
from trace.domain.repository import RepositoryStatus, RepositoryType

import pytest
from pydantic import ValidationError


def test_repository_register_valid_https() -> None:
    """RepositoryRegisterRequest accepts clean HTTPS Git URLs."""
    req = RepositoryRegisterRequest(
        type=RepositoryType.REMOTE,
        location="https://github.com/example-org/example-repo.git",
        default_branch="main",
    )
    assert req.type == RepositoryType.REMOTE
    assert req.location == "https://github.com/example-org/example-repo.git"
    assert req.default_branch == "main"


def test_repository_register_valid_ssh_scp() -> None:
    """RepositoryRegisterRequest accepts standard ambient SSH SCP-style URLs."""
    req = RepositoryRegisterRequest(
        type=RepositoryType.REMOTE,
        location="git@github.com:example-org/example-repo.git",
    )
    assert req.location == "git@github.com:example-org/example-repo.git"


def test_repository_register_valid_ssh_protocol() -> None:
    """RepositoryRegisterRequest accepts ssh:// URLs with ambient usernames."""
    req = RepositoryRegisterRequest(
        type=RepositoryType.REMOTE,
        location="ssh://git@github.com/example-org/example-repo.git",
    )
    assert req.location == "ssh://git@github.com/example-org/example-repo.git"


def test_repository_register_valid_local_path() -> None:
    """RepositoryRegisterRequest accepts local filesystem paths."""
    req = RepositoryRegisterRequest(
        type=RepositoryType.LOCAL,
        location="/home/user/workspace/repo",
    )
    assert req.location == "/home/user/workspace/repo"


def test_repository_register_rejects_embedded_credentials() -> None:
    """RepositoryRegisterRequest strictly rejects embedded credentials and tokens."""
    forbidden = [
        "https://user:token@github.com/org/repo",
        "https://user:password@host/repo",
        "https://token@github.com/org/repo",
        "http://secret_token@gitlab.com/group/repo",
        "git:secret@host:org/repo",
        "ssh://user:pass@host/repo.git",
    ]
    for url in forbidden:
        with pytest.raises(ValidationError) as exc_info:
            RepositoryRegisterRequest(type=RepositoryType.REMOTE, location=url)
        assert "must not contain embedded basic-auth credentials" in str(exc_info.value)


def test_repository_register_rejects_null_bytes_and_empty() -> None:
    """RepositoryRegisterRequest rejects null bytes and empty locations."""
    with pytest.raises(ValidationError) as exc_info:
        RepositoryRegisterRequest(type=RepositoryType.LOCAL, location="repo/\0/test")
    assert "null bytes" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
        RepositoryRegisterRequest(type=RepositoryType.LOCAL, location="   ")
    assert "cannot be empty" in str(exc_info.value)


def test_repository_response_and_list() -> None:
    """RepositoryResponse and RepositoryListResponse serialize correctly."""
    rid = uuid.uuid4()
    pid = uuid.uuid4()
    now = datetime.now(UTC)
    resp = RepositoryResponse(
        id=rid,
        project_id=pid,
        type=RepositoryType.REMOTE,
        location="https://github.com/org/repo",
        default_branch="main",
        status=RepositoryStatus.REGISTERED,
        last_error=None,
        last_validated_at=None,
        last_analysis_run_id=None,
        created_at=now,
        updated_at=now,
    )
    data = resp.model_dump(mode="json")
    assert data["id"] == str(rid)
    assert data["project_id"] == str(pid)
    assert data["status"] == "REGISTERED"

    list_resp = RepositoryListResponse(items=[resp], total=1)
    assert list_resp.total == 1
    assert len(list_resp.items) == 1


def test_validation_report_response() -> None:
    """ValidationReportResponse serializes probe metrics and status."""
    rid = uuid.uuid4()
    now = datetime.now(UTC)
    report = ValidationReportResponse(
        repository_id=rid,
        is_connected=True,
        status=RepositoryStatus.CONNECTED,
        detected_branch="main",
        error_message=None,
        latency_ms=125.5,
        validated_at=now,
    )
    data = report.model_dump(mode="json")
    assert data["repository_id"] == str(rid)
    assert data["is_connected"] is True
    assert data["status"] == "CONNECTED"
    assert data["latency_ms"] == 125.5
