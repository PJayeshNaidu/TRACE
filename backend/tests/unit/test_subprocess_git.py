"""Unit and fixture tests for SubprocessGitProvider."""

import subprocess
from pathlib import Path
from trace.domain.repository import ConnectionValidationResult, RepositoryType
from trace.infrastructure.git.adapters.subprocess import SubprocessGitProvider
from trace.infrastructure.git.provider import GitProvider
from unittest.mock import AsyncMock, patch

import pytest


def test_subprocess_git_provider_satisfies_protocol() -> None:
    """SubprocessGitProvider conforms to runtime-checkable GitProvider Protocol."""
    provider = SubprocessGitProvider()
    assert isinstance(provider, GitProvider)


@pytest.mark.asyncio
async def test_validate_local_valid_standard_repo(tmp_path: Path) -> None:
    """validate_local reports connected and detects active branch for standard repo."""
    repo_dir = tmp_path / "valid_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo_dir)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "config", "user.name", "Test User"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo_dir), "config", "user.email", "test@example.com"],
        check=True,
    )
    (repo_dir / "README.md").write_text("# Test Repo")
    subprocess.run(["git", "-C", str(repo_dir), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "commit", "-m", "Initial commit"], check=True)

    provider = SubprocessGitProvider()
    result = await provider.validate_local(repo_dir)

    assert result.is_connected is True
    assert result.detected_branch == "main"
    assert result.error_message is None
    assert result.latency_ms >= 0


@pytest.mark.asyncio
async def test_validate_local_bare_repository(tmp_path: Path) -> None:
    """validate_local recognizes bare repository as valid Git repository."""
    bare_dir = tmp_path / "bare_repo.git"
    subprocess.run(["git", "init", "--bare", str(bare_dir)], check=True, capture_output=True)

    provider = SubprocessGitProvider()
    result = await provider.validate_local(bare_dir)

    assert result.is_connected is True
    assert result.error_message is None


@pytest.mark.asyncio
async def test_validate_local_detached_head_no_fallback(tmp_path: Path) -> None:
    """validate_local returns detected_branch=None when HEAD is detached (no fallback)."""
    repo_dir = tmp_path / "detached_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo_dir)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "config", "user.name", "Test User"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo_dir), "config", "user.email", "test@example.com"],
        check=True,
    )
    (repo_dir / "file.txt").write_text("hello")
    subprocess.run(["git", "-C", str(repo_dir), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "commit", "-m", "Commit 1"], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "checkout", "--detach"], check=True)

    provider = SubprocessGitProvider()
    result = await provider.validate_local(repo_dir)

    assert result.is_connected is True
    assert result.detected_branch is None


@pytest.mark.asyncio
async def test_validate_local_nonexistent_and_non_git(tmp_path: Path) -> None:
    """validate_local reports is_connected=False for missing or non-git folders."""
    provider = SubprocessGitProvider()

    # Missing directory
    missing_dir = tmp_path / "does_not_exist"
    res1 = await provider.validate_local(missing_dir)
    assert res1.is_connected is False
    assert "does not exist" in (res1.error_message or "")

    # Non-git directory
    plain_dir = tmp_path / "plain_folder"
    plain_dir.mkdir()
    res2 = await provider.validate_local(plain_dir)
    assert res2.is_connected is False
    assert "Not a valid Git repository" in (res2.error_message or "")


@pytest.mark.asyncio
async def test_validate_local_timeout(tmp_path: Path) -> None:
    """validate_local handles command timeout gracefully."""
    repo_dir = tmp_path / "timeout_repo"
    repo_dir.mkdir()
    (repo_dir / ".git").mkdir()

    provider = SubprocessGitProvider(timeout_seconds=0.01)
    with patch.object(provider, "_run_command", side_effect=TimeoutError()):
        result = await provider.validate_local(repo_dir)
        assert result.is_connected is False
        assert "timed out" in (result.error_message or "")


@pytest.mark.asyncio
async def test_validate_remote_success_with_symref() -> None:
    """validate_remote parses symref from ls-remote output (mocked)."""
    provider = SubprocessGitProvider()
    mock_stdout = "ref: refs/heads/develop\tHEAD\n8f4b919a2ef44f01b8d923ef8902b4d1\tHEAD\n"
    with patch.object(provider, "_run_command", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (0, mock_stdout, "")
        result = await provider.validate_remote("https://github.com/org/repo")

    assert result.is_connected is True
    assert result.detected_branch == "develop"
    assert result.error_message is None


@pytest.mark.asyncio
async def test_validate_remote_success_without_symref_no_fallback() -> None:
    """validate_remote leaves detected_branch as None if no symref present (no fallback)."""
    provider = SubprocessGitProvider()
    mock_stdout = "8f4b919a2ef44f01b8d923ef8902b4d1\tHEAD\n"
    with patch.object(provider, "_run_command", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (0, mock_stdout, "")
        result = await provider.validate_remote("https://github.com/org/repo")

    assert result.is_connected is True
    assert result.detected_branch is None


@pytest.mark.asyncio
async def test_validate_remote_failure_diagnostics() -> None:
    """validate_remote captures exit code and stderr on failure (mocked)."""
    provider = SubprocessGitProvider()
    with patch.object(provider, "_run_command", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (
            128,
            "",
            "fatal: repository 'https://github.com/private/repo' not found",
        )
        result = await provider.validate_remote("https://github.com/private/repo")

    assert result.is_connected is False
    assert "not found" in (result.error_message or "")


@pytest.mark.asyncio
async def test_validate_remote_timeout() -> None:
    """validate_remote returns is_connected=False on timeout."""
    provider = SubprocessGitProvider(timeout_seconds=0.01)
    with patch.object(provider, "_run_command", side_effect=TimeoutError()):
        result = await provider.validate_remote("https://github.com/org/repo")
        assert result.is_connected is False
        assert "timed out" in (result.error_message or "")


@pytest.mark.asyncio
async def test_list_remote_references_and_detect_default_branch() -> None:
    """list_remote_references extracts ref names; detect_default_branch dispatches."""
    provider = SubprocessGitProvider()
    mock_out = (
        "8f4b919a\trefs/heads/main\n1a2b3c4d\trefs/heads/feature\n9e8d7c6b\trefs/tags/v1.0.0\n"
    )
    with patch.object(provider, "_run_command", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (0, mock_out, "")
        refs = await provider.list_remote_references("https://github.com/org/repo")

    assert refs == ["refs/heads/main", "refs/heads/feature", "refs/tags/v1.0.0"]

    with patch.object(
        provider,
        "validate_remote",
        return_value=ConnectionValidationResult(
            is_connected=True, detected_branch="main", latency_ms=1.0
        ),
    ):
        branch = await provider.detect_default_branch(
            "https://github.com/org/repo", RepositoryType.REMOTE
        )
        assert branch == "main"

    with patch.object(
        provider,
        "validate_local",
        return_value=ConnectionValidationResult(
            is_connected=True, detected_branch="develop", latency_ms=1.0
        ),
    ):
        branch = await provider.detect_default_branch(Path("/some/path"), RepositoryType.LOCAL)
        assert branch == "develop"


@pytest.mark.asyncio
async def test_validate_local_timeout_and_unexpected_exception(tmp_path: Path) -> None:
    """validate_local returns is_connected=False on timeout and unexpected errors."""
    repo_dir = tmp_path / "timeout_repo"
    repo_dir.mkdir()
    (repo_dir / ".git").mkdir()

    provider = SubprocessGitProvider(timeout_seconds=0.01)
    with patch.object(provider, "_run_command", side_effect=TimeoutError()):
        result = await provider.validate_local(repo_dir)
        assert result.is_connected is False
        assert "timed out" in (result.error_message or "")

    with patch.object(provider, "_run_command", side_effect=RuntimeError("disk read failure")):
        result = await provider.validate_local(repo_dir)
        assert result.is_connected is False
        assert "disk read failure" in (result.error_message or "")


@pytest.mark.asyncio
async def test_validate_remote_unexpected_exception_and_error_exit() -> None:
    """validate_remote handles unexpected exceptions and nonzero exit codes."""
    provider = SubprocessGitProvider()
    with patch.object(provider, "_run_command", side_effect=RuntimeError("network pipe broken")):
        result = await provider.validate_remote("https://github.com/org/broken")
        assert result.is_connected is False
        assert "network pipe broken" in (result.error_message or "")

    with patch.object(provider, "_run_command", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (1, "", "unknown git error")
        result = await provider.validate_remote("https://github.com/org/err")
        assert result.is_connected is False
        assert "unknown git error" in (result.error_message or "")


@pytest.mark.asyncio
async def test_run_command_timeout_kill() -> None:
    """_run_command kills process and raises TimeoutError when timeout expires."""

    # Call git with a command that takes longer than 0.001s, e.g. sleep via git or a tiny timeout
    provider = SubprocessGitProvider(timeout_seconds=0.0001)
    # Trigger timeout on git ls-remote or rev-parse
    with pytest.raises(TimeoutError):
        await provider._run_command(
            ["ls-remote", "https://192.0.2.1/test.git"],
            timeout_seconds=0.0001,
        )


@pytest.mark.asyncio
async def test_get_diff_branches_and_commits(tmp_path: Path) -> None:
    """get_diff, list_branches, and list_commits work correctly on real git repository."""
    repo_dir = tmp_path / "diff_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo_dir)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo_dir), "config", "user.name", "Diff Author"], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "config", "user.email", "author@trace.io"], check=True)

    # Initial commit on main
    file1 = repo_dir / "calculator.py"
    file1.write_text("def add(a: int, b: int) -> int:\n    return a + b\n")
    subprocess.run(["git", "-C", str(repo_dir), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "commit", "-m", "feat: initial add function"], check=True)

    # Create feature branch
    subprocess.run(["git", "-C", str(repo_dir), "checkout", "-b", "feature/multiply"], check=True)
    file1.write_text("def add(a: int, b: int) -> int:\n    return a + b\n\ndef multiply(a: int, b: int) -> int:\n    return a * b\n")
    subprocess.run(["git", "-C", str(repo_dir), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "commit", "-m", "feat: add multiply function"], check=True)

    provider = SubprocessGitProvider()

    # 1. list_branches
    branches = await provider.list_branches(repo_dir)
    assert "main" in branches
    assert "feature/multiply" in branches

    # 2. list_commits
    commits = await provider.list_commits(repo_dir, branch="feature/multiply", limit=10)
    assert len(commits) == 2
    assert commits[0].message == "feat: add multiply function"
    assert "Diff Author" in commits[0].author
    assert commits[1].message == "feat: initial add function"

    # 3. get_diff
    diff_text = await provider.get_diff(repo_dir, base_ref="main", target_ref="feature/multiply")
    assert "calculator.py" in diff_text
    assert "+def multiply(a: int, b: int) -> int:" in diff_text

