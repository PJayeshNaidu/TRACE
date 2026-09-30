"""Unit tests for the TRACE domain exception hierarchy."""

import uuid
from trace.domain.exceptions import (
    DatabasePersistenceError,
    DuplicateRepositoryError,
    InvalidRepositoryLocationError,
    ProjectAlreadyExistsError,
    ProjectArchivedError,
    ProjectNotFoundError,
    RepositoryInaccessibleError,
    RepositoryInUseError,
    RepositoryNotFoundError,
    TraceDomainError,
    UnsupportedRepositoryTypeError,
)


def test_domain_error_base() -> None:
    """Base domain error contains message and details dictionary."""
    err = TraceDomainError("Domain failure", {"key": "val"})
    assert isinstance(err, Exception)
    assert str(err) == "Domain failure"
    assert err.message == "Domain failure"
    assert err.details == {"key": "val"}


def test_project_not_found_error() -> None:
    """ProjectNotFoundError stores project_id and produces formatted message."""
    p_id = uuid.uuid4()
    err = ProjectNotFoundError(p_id)
    assert isinstance(err, TraceDomainError)
    assert str(p_id) in err.message
    assert err.details["project_id"] == str(p_id)


def test_project_already_exists_error() -> None:
    """ProjectAlreadyExistsError stores project name and details."""
    err = ProjectAlreadyExistsError("Core Project")
    assert isinstance(err, TraceDomainError)
    assert "Core Project" in err.message
    assert err.details["name"] == "Core Project"


def test_project_archived_error() -> None:
    """ProjectArchivedError captures project ID and operation."""
    p_id = uuid.uuid4()
    err = ProjectArchivedError(p_id, operation="register repository to")
    assert isinstance(err, TraceDomainError)
    assert "register repository to" in err.message
    assert str(p_id) in err.message
    assert err.details["project_id"] == str(p_id)


def test_repository_not_found_error() -> None:
    """RepositoryNotFoundError captures repository ID."""
    r_id = uuid.uuid4()
    err = RepositoryNotFoundError(r_id)
    assert isinstance(err, TraceDomainError)
    assert str(r_id) in err.message
    assert err.details["repository_id"] == str(r_id)


def test_duplicate_repository_error() -> None:
    """DuplicateRepositoryError captures project ID and location."""
    p_id = uuid.uuid4()
    err = DuplicateRepositoryError(p_id, "/repos/my-repo")
    assert isinstance(err, TraceDomainError)
    assert "/repos/my-repo" in err.message
    assert str(p_id) in err.message
    assert err.details["project_id"] == str(p_id)
    assert err.details["location"] == "/repos/my-repo"


def test_repository_in_use_error() -> None:
    """RepositoryInUseError captures repository ID and rejection reason."""
    r_id = uuid.uuid4()
    err = RepositoryInUseError(r_id)
    assert isinstance(err, TraceDomainError)
    assert "analysis runs" in err.message
    assert err.details["repository_id"] == str(r_id)


def test_invalid_repository_location_error() -> None:
    """InvalidRepositoryLocationError captures location and rejection reason."""
    err = InvalidRepositoryLocationError("https://u:p@github.com/r", "embedded credentials")
    assert isinstance(err, TraceDomainError)
    assert "embedded credentials" in err.message
    assert err.details["location"] == "https://u:p@github.com/r"
    assert err.details["reason"] == "embedded credentials"


def test_unsupported_repository_type_error() -> None:
    """UnsupportedRepositoryTypeError captures type string."""
    err = UnsupportedRepositoryTypeError("SVN")
    assert isinstance(err, TraceDomainError)
    assert "SVN" in err.message
    assert err.details["repo_type"] == "SVN"


def test_repository_inaccessible_error() -> None:
    """RepositoryInaccessibleError captures location and failure diagnostic."""
    err = RepositoryInaccessibleError("/nonexistent", "Path does not exist")
    assert isinstance(err, TraceDomainError)
    assert "/nonexistent" in err.message
    assert "Path does not exist" in err.message
    assert err.details["reason"] == "Path does not exist"


def test_database_persistence_error() -> None:
    """DatabasePersistenceError captures cause exception info."""
    cause = RuntimeError("connection drop")
    err = DatabasePersistenceError("Failed to persist", cause=cause)
    assert isinstance(err, TraceDomainError)
    assert err.cause is cause
    assert err.details["cause_type"] == "RuntimeError"
    assert err.details["cause_message"] == "connection drop"
