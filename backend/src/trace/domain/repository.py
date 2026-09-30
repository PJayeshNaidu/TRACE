"""Pure domain entity, value objects, and normalization logic for Git repositories.

Per Constitution §XIV, domain entities contain zero framework, database, or I/O imports.
"""

import os
import re
import urllib.parse
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path


class RepositoryType(StrEnum):
    """Supported repository types in TRACE."""

    LOCAL = "LOCAL"
    REMOTE = "REMOTE"


class RepositoryStatus(StrEnum):
    """Operational connectivity status of a registered repository."""

    REGISTERED = "REGISTERED"
    CONNECTED = "CONNECTED"
    ERROR = "ERROR"


@dataclass(frozen=True)
class ConnectionValidationResult:
    """Diagnostic result of a non-destructive repository connectivity check."""

    is_connected: bool
    detected_branch: str | None = None
    error_message: str | None = None
    latency_ms: float = 0.0


@dataclass(frozen=True)
class Repository:
    """Immutable TRACE repository domain entity."""

    id: uuid.UUID
    project_id: uuid.UUID
    type: RepositoryType
    location: str
    default_branch: str | None
    status: RepositoryStatus
    last_error: str | None
    last_validated_at: datetime | None
    last_analysis_run_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


def normalize_location(location: str, repo_type: RepositoryType) -> str:
    """Normalize a repository location for deterministic comparison and uniqueness.

    - LOCAL: Converts to absolute canonical filesystem path with forward slashes.
    - REMOTE: Normalizes scheme and host to lowercase, strips trailing slashes and '.git'.

    Args:
        location: Raw input location string.
        repo_type: RepositoryType enum (LOCAL or REMOTE).

    Returns:
        Canonical normalized location string.
    """
    cleaned = location.strip()
    if repo_type == RepositoryType.LOCAL:
        # Resolve path to canonical absolute representation
        local_path = Path(cleaned)
        try:
            return Path(os.path.abspath(local_path.expanduser())).as_posix()
        except Exception:
            return local_path.as_posix()
    elif repo_type == RepositoryType.REMOTE:
        # Remote repository URL normalization
        # Check for SCP-style SSH syntax: [user@]host:path/to/repo[.git]
        scp_match = re.match(r"^([^@/:]+@)?([^:]+):(.+)$", cleaned)
        if scp_match and not cleaned.lower().startswith(("http://", "https://", "ssh://")):
            user_prefix = scp_match.group(1) or ""
            host = scp_match.group(2).lower()
            subpath = scp_match.group(3).strip("/")
            if subpath.endswith(".git"):
                subpath = subpath[:-4]
            return f"{user_prefix}{host}:{subpath}"

        try:
            parsed = urllib.parse.urlsplit(cleaned)
            scheme = parsed.scheme.lower()
            netloc = parsed.netloc.lower()
            url_path = parsed.path.rstrip("/")
            if url_path.endswith(".git"):
                url_path = url_path[:-4]
            # Reconstruct normalized URL
            normalized = urllib.parse.urlunsplit(
                (scheme, netloc, url_path, parsed.query, parsed.fragment)
            )
            return str(normalized).rstrip("/")
        except Exception:
            # Fallback string stripping
            s = cleaned.rstrip("/")
            if s.endswith(".git"):
                s = s[:-4]
            return s
    else:
        from trace.domain.exceptions import UnsupportedRepositoryTypeError

        raise UnsupportedRepositoryTypeError(str(repo_type))
