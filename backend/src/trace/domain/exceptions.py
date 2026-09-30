"""Typed domain exception hierarchy for TRACE domain business errors.

Per Constitution §XIV, domain exceptions are pure Python classes decoupled
from any web framework or transport layer (FastAPI, HTTP status codes, etc.).
"""

import uuid
from typing import Any


class TraceDomainError(Exception):
    """Base exception for all TRACE business domain errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ProjectNotFoundError(TraceDomainError):
    """Raised when a requested project does not exist."""

    def __init__(self, project_id: uuid.UUID | str) -> None:
        self.project_id = str(project_id)
        super().__init__(
            message=f"Project with ID '{self.project_id}' was not found.",
            details={"project_id": self.project_id},
        )


class ProjectAlreadyExistsError(TraceDomainError):
    """Raised when attempting to create a project with a duplicate name."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(
            message=f"Project with name '{self.name}' already exists.",
            details={"name": self.name},
        )


class ProjectArchivedError(TraceDomainError):
    """Raised when an operation is attempted on an archived project."""

    def __init__(
        self,
        project_id: uuid.UUID | str,
        operation: str = "perform operation on",
    ) -> None:
        self.project_id = str(project_id)
        self.operation = operation
        msg = (
            f"Cannot {operation} archived project '{self.project_id}'. "
            "Reactivate the project first."
        )
        super().__init__(
            message=msg,
            details={"project_id": self.project_id, "operation": operation},
        )


class RepositoryNotFoundError(TraceDomainError):
    """Raised when a requested repository does not exist."""

    def __init__(self, repository_id: uuid.UUID | str) -> None:
        self.repository_id = str(repository_id)
        super().__init__(
            message=f"Repository with ID '{self.repository_id}' was not found.",
            details={"repository_id": self.repository_id},
        )


class DuplicateRepositoryError(TraceDomainError):
    """Raised when a repository location is already registered under the same project."""

    def __init__(self, project_id: uuid.UUID | str, location: str) -> None:
        self.project_id = str(project_id)
        self.location = location
        msg = (
            f"Repository location '{location}' is already registered "
            f"under project '{self.project_id}'."
        )
        super().__init__(
            message=msg,
            details={"project_id": self.project_id, "location": location},
        )


class RepositoryInUseError(TraceDomainError):
    """Raised when deleting a repository that is linked to analysis runs."""

    def __init__(
        self,
        repository_id: uuid.UUID | str,
        last_analysis_run_id: uuid.UUID | str | None = None,
        reason: str = "Repository is associated with existing analysis runs and cannot be deleted.",
    ) -> None:
        self.repository_id = str(repository_id)
        self.last_analysis_run_id = str(last_analysis_run_id) if last_analysis_run_id else None
        details = {"repository_id": self.repository_id}
        if self.last_analysis_run_id:
            details["last_analysis_run_id"] = self.last_analysis_run_id
        super().__init__(
            message=reason,
            details=details,
        )


class InvalidRepositoryLocationError(TraceDomainError):
    """Raised when a repository location is malformed, contains null bytes, or credentials."""

    def __init__(self, location: str, reason: str) -> None:
        self.location = location
        self.reason = reason
        super().__init__(
            message=f"Invalid repository location '{location}': {reason}",
            details={"location": location, "reason": reason},
        )


class UnsupportedRepositoryTypeError(TraceDomainError):
    """Raised when an unsupported repository type is specified."""

    def __init__(self, repo_type: str) -> None:
        self.repo_type = repo_type
        msg = f"Unsupported repository type '{repo_type}'. Allowed types are 'LOCAL' and 'REMOTE'."
        super().__init__(
            message=msg,
            details={"repo_type": repo_type},
        )


class RepositoryInaccessibleError(TraceDomainError):
    """Raised when a repository cannot be reached, accessed, or validated."""

    def __init__(self, location: str, reason: str) -> None:
        self.location = location
        self.reason = reason
        super().__init__(
            message=f"Repository at '{location}' is inaccessible: {reason}",
            details={"location": location, "reason": reason},
        )


class DatabasePersistenceError(TraceDomainError):
    """Raised when a database persistence operation fails unexpectedly."""

    def __init__(self, message: str, cause: Exception | None = None) -> None:
        self.cause = cause
        details: dict[str, Any] = {}
        if cause is not None:
            details["cause_type"] = type(cause).__name__
            details["cause_message"] = str(cause)
        super().__init__(message=message, details=details)


class AnalysisRunNotFoundError(TraceDomainError):
    """Raised when a requested analysis run does not exist."""

    def __init__(self, run_id: uuid.UUID | str) -> None:
        self.run_id = str(run_id)
        super().__init__(
            message=f"Analysis run with ID '{self.run_id}' was not found.",
            details={"run_id": self.run_id},
        )


class AnalysisExecutionError(TraceDomainError):
    """Raised when static analysis execution fails fatally."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message=message, details=details)


class InvalidAnalysisStateError(TraceDomainError):
    """Raised when an operation is invalid for the current analysis run state."""

    def __init__(self, run_id: uuid.UUID | str, current_status: str, operation: str) -> None:
        self.run_id = str(run_id)
        self.current_status = current_status
        self.operation = operation
        super().__init__(
            message=(
                f"Cannot {operation} analysis run '{self.run_id}' in status '{current_status}'."
            ),
            details={
                "run_id": self.run_id,
                "current_status": current_status,
                "operation": operation,
            },
        )
