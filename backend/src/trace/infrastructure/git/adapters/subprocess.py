"""Subprocess-based Git provider adapter implementing GitProvider protocol."""

import asyncio
import os
import re
from pathlib import Path
from time import perf_counter
from trace.core.config import ApplicationConfig
from trace.domain.repository import ConnectionValidationResult, RepositoryType

import structlog

logger = structlog.get_logger(__name__)


class SubprocessGitProvider:
    """Executes non-destructive Git probe operations using system Git CLI subprocesses."""

    def __init__(
        self,
        config: ApplicationConfig | None = None,
        binary_path: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        if config is not None:
            self.binary_path = binary_path or config.git_binary_path
            self.timeout_seconds = (
                timeout_seconds if timeout_seconds is not None else config.git_timeout_seconds
            )
        else:
            self.binary_path = binary_path or "git"
            self.timeout_seconds = timeout_seconds if timeout_seconds is not None else 10.0

    async def _run_command(
        self,
        args: list[str],
        timeout_seconds: float,
    ) -> tuple[int, str, str]:
        """Execute a git subprocess with terminal prompt disabled."""
        env = {
            **os.environ,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": "echo",
        }
        try:
            proc = await asyncio.create_subprocess_exec(
                self.binary_path,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        except FileNotFoundError:
            return (-1, "", f"Git binary '{self.binary_path}' not found in system PATH.")
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout_seconds,
            )
            return (
                proc.returncode if proc.returncode is not None else -1,
                stdout_b.decode("utf-8", errors="replace"),
                stderr_b.decode("utf-8", errors="replace"),
            )
        except TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            raise

    async def validate_local(self, path: Path) -> ConnectionValidationResult:
        """Validate accessibility, structure, and HEAD branch of a local Git repository."""
        start_time = perf_counter()
        if not path.exists() or not path.is_dir():
            latency_ms = (perf_counter() - start_time) * 1000
            return ConnectionValidationResult(
                is_connected=False,
                error_message=f"Path '{path}' does not exist or is not a directory.",
                latency_ms=round(latency_ms, 2),
            )

        try:
            dot_git = path / ".git"
            is_work_tree = False
            is_bare = False
            git_dir: str | None = None

            if dot_git.exists():
                rc_wt, out_wt, _ = await self._run_command(
                    [
                        "--git-dir",
                        str(dot_git),
                        "-C",
                        str(path),
                        "rev-parse",
                        "--is-inside-work-tree",
                    ],
                    timeout_seconds=self.timeout_seconds,
                )
                if rc_wt == 0 and out_wt.strip() == "true":
                    is_work_tree = True
                    git_dir = str(dot_git)

            if not is_work_tree:
                head_file = path / "HEAD"
                if head_file.exists():
                    rc_bare, out_bare, _ = await self._run_command(
                        ["--git-dir", str(path), "rev-parse", "--is-bare-repository"],
                        timeout_seconds=self.timeout_seconds,
                    )
                    if rc_bare == 0 and out_bare.strip() == "true":
                        is_bare = True
                        git_dir = str(path)

            if not is_work_tree and not is_bare:
                latency_ms = (perf_counter() - start_time) * 1000
                return ConnectionValidationResult(
                    is_connected=False,
                    error_message="Not a valid Git repository.",
                    latency_ms=round(latency_ms, 2),
                )

            # Probe default branch via symbolic-ref HEAD (no hardcoded fallback)
            rc_branch, out_branch, _ = await self._run_command(
                ["--git-dir", str(git_dir), "symbolic-ref", "--short", "HEAD"],
                timeout_seconds=self.timeout_seconds,
            )
            detected_branch = out_branch.strip() if rc_branch == 0 and out_branch.strip() else None

            latency_ms = (perf_counter() - start_time) * 1000
            return ConnectionValidationResult(
                is_connected=True,
                detected_branch=detected_branch,
                latency_ms=round(latency_ms, 2),
            )

        except TimeoutError:
            latency_ms = (perf_counter() - start_time) * 1000
            return ConnectionValidationResult(
                is_connected=False,
                error_message=f"Git local probe timed out after {self.timeout_seconds} seconds.",
                latency_ms=round(latency_ms, 2),
            )
        except Exception as exc:
            latency_ms = (perf_counter() - start_time) * 1000
            return ConnectionValidationResult(
                is_connected=False,
                error_message=f"Git local probe failed: {exc}",
                latency_ms=round(latency_ms, 2),
            )

    async def validate_remote(
        self,
        url: str,
        timeout_seconds: float = 10.0,
    ) -> ConnectionValidationResult:
        """Probe remote Git reachability without cloning code."""
        start_time = perf_counter()
        try:
            rc, stdout, stderr = await self._run_command(
                ["ls-remote", "--symref", url, "HEAD"],
                timeout_seconds=timeout_seconds,
            )
            latency_ms = (perf_counter() - start_time) * 1000
            if rc != 0:
                err_msg = stderr.strip() or f"Git remote probe failed with exit code {rc}."
                return ConnectionValidationResult(
                    is_connected=False,
                    error_message=err_msg,
                    latency_ms=round(latency_ms, 2),
                )

            # Parse symref: ref: refs/heads/<branch>\tHEAD (no fallback)
            match = re.search(r"ref:\s+refs/heads/([^\s]+)\s+HEAD", stdout)
            detected_branch = match.group(1) if match else None

            return ConnectionValidationResult(
                is_connected=True,
                detected_branch=detected_branch,
                latency_ms=round(latency_ms, 2),
            )
        except TimeoutError:
            latency_ms = (perf_counter() - start_time) * 1000
            return ConnectionValidationResult(
                is_connected=False,
                error_message=f"Git remote probe timed out after {timeout_seconds} seconds.",
                latency_ms=round(latency_ms, 2),
            )
        except Exception as exc:
            latency_ms = (perf_counter() - start_time) * 1000
            return ConnectionValidationResult(
                is_connected=False,
                error_message=f"Git remote probe failed: {exc}",
                latency_ms=round(latency_ms, 2),
            )

    async def detect_default_branch(
        self,
        location: str,
        repo_type: RepositoryType,
    ) -> str | None:
        """Resolve default branch name deterministically."""
        if repo_type == RepositoryType.LOCAL:
            res = await self.validate_local(Path(location))
        else:
            res = await self.validate_remote(location, timeout_seconds=self.timeout_seconds)
        return res.detected_branch if res.is_connected else None

    async def list_remote_references(
        self,
        url: str,
        timeout_seconds: float = 10.0,
    ) -> list[str]:
        """List remote branch and tag reference names."""
        rc, stdout, stderr = await self._run_command(
            ["ls-remote", "--heads", "--tags", url],
            timeout_seconds=timeout_seconds,
        )
        if rc != 0:
            raise RuntimeError(stderr.strip() or f"Git ls-remote failed with exit code {rc}.")

        refs: list[str] = []
        for line in stdout.strip().splitlines():
            parts = line.strip().split()
            if len(parts) >= 2:
                refs.append(parts[1])
        return refs

    async def resolve_revision(
        self,
        location: str | Path,
        ref: str = "HEAD",
    ) -> str | None:
        """Resolve a Git reference (e.g. branch, tag, HEAD) to a 40-character commit SHA."""
        path = Path(location)
        if not path.exists():
            return None
        rc, stdout, _ = await self._run_command(
            ["-C", str(path), "rev-parse", ref],
            timeout_seconds=self.timeout_seconds,
        )
        if rc == 0 and stdout.strip():
            sha = stdout.strip()
            if len(sha) == 40 and all(c in "0123456789abcdefABCDEF" for c in sha):
                return sha.lower()
        return None

    async def clone_or_checkout(
        self,
        url: str,
        destination: Path,
        target_ref: str | None = None,
        timeout_seconds: float = 180.0,
    ) -> Path:
        """Clone a remote Git repository or fetch and checkout the target ref."""
        dest = Path(destination).resolve()
        if (dest / ".git").exists():
            logger.info("Remote repository already cloned, fetching latest changes", path=str(dest))
            await self._run_command(
                ["-C", str(dest), "fetch", "--all", "--prune"],
                timeout_seconds=timeout_seconds,
            )
            if target_ref and target_ref != "HEAD":
                rc, _, _ = await self._run_command(
                    ["-C", str(dest), "checkout", target_ref],
                    timeout_seconds=timeout_seconds,
                )
                if rc != 0:
                    await self._run_command(
                        ["-C", str(dest), "checkout", f"origin/{target_ref}"],
                        timeout_seconds=timeout_seconds,
                    )
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            logger.info("Cloning remote Git repository", url=url, destination=str(dest))
            args = ["clone", url, str(dest)]
            if target_ref and target_ref != "HEAD":
                args = ["clone", "-b", target_ref, url, str(dest)]
            rc, stdout, stderr = await self._run_command(args, timeout_seconds=timeout_seconds)
            if rc != 0:
                # If clone -b failed (e.g. target_ref is a commit SHA), fallback to standard clone + checkout
                fallback_args = ["clone", url, str(dest)]
                rc, stdout, stderr = await self._run_command(fallback_args, timeout_seconds=timeout_seconds)
                if rc != 0:
                    raise RuntimeError(f"Git clone failed for {url}: {stderr.strip() or stdout.strip()}")
                if target_ref and target_ref != "HEAD":
                    await self._run_command(
                        ["-C", str(dest), "checkout", target_ref],
                        timeout_seconds=timeout_seconds,
                    )
        return dest
