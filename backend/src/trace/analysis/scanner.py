"""Deterministic repository scanner with directory pruning and file classification."""

import fnmatch
from dataclasses import dataclass
from pathlib import Path
from trace.domain.analysis import AnalyzedFile, FileKind, FileStatus

DEFAULT_IGNORED_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".coverage",
        ".tox",
        ".nox",
        ".eggs",
        "build",
        "dist",
        "node_modules",
        ".idea",
        ".vscode",
    }
)

DEFAULT_MAX_FILE_SIZE_BYTES = 1024 * 1024  # 1 MB


@dataclass(frozen=True)
class ScanResult:
    """Outcome of repository scanning traversal."""

    files: tuple[AnalyzedFile, ...]
    python_files: tuple[Path, ...]
    source_root: str | None = None


class RepositoryScanner:
    """Scans repository working trees, applying exclusion rules and classifying files."""

    def __init__(
        self,
        ignored_dirs: frozenset[str] = DEFAULT_IGNORED_DIRS,
        max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
    ) -> None:
        self._ignored_dirs = ignored_dirs
        self._max_file_size_bytes = max_file_size_bytes

    def is_binary(self, file_path: Path) -> bool:
        """Check if file appears to be binary using null-byte detection."""
        try:
            with open(file_path, "rb") as f:
                chunk = f.read(1024)
                return b"\x00" in chunk
        except Exception:
            return True

    def classify_file(self, rel_path: str, is_bin: bool) -> FileKind:
        """Classify a file into FileKind based on naming patterns."""
        if is_bin:
            return FileKind.OTHER

        lower_path = rel_path.lower()
        file_name = Path(rel_path).name.lower()

        # Dependencies
        if file_name in {"pyproject.toml", "setup.py", "setup.cfg", "pipfile", "pipfile.lock"} or (
            file_name.startswith("requirements") and file_name.endswith(".txt")
        ):
            return FileKind.DEPENDENCY

        # Documentation
        if (
            file_name.startswith(("readme", "contributing", "changelog", "architecture", "license"))
            or "/docs/" in lower_path
            or lower_path.startswith("docs/")
            or file_name.endswith((".md", ".rst"))
        ):
            return FileKind.DOCUMENTATION

        # Tests
        if (
            file_name.startswith("test_")
            or file_name.endswith("_test.py")
            or "/tests/" in lower_path
            or "/test/" in lower_path
            or lower_path.startswith(("tests/", "test/"))
        ):
            return FileKind.TEST

        # Config
        if (
            file_name in {"config.py", "settings.py", "conf.py"}
            or "config" in file_name
            or file_name.endswith((".ini", ".yaml", ".yml", ".toml", ".json", ".env"))
        ):
            return FileKind.CONFIG

        # Python
        if file_name.endswith((".py", ".pyw")):
            return FileKind.PYTHON

        return FileKind.OTHER

    def scan(
        self,
        root_path: Path | str,
        exclude_patterns: tuple[str, ...] = (),
    ) -> ScanResult:
        """Traverse the repository directory deterministically.

        Args:
            root_path: Filesystem path to repository root.
            exclude_patterns: User-supplied glob patterns to skip.

        Returns:
            ScanResult containing classified files, candidate Python paths,
            and detected source root.
        """
        root = Path(root_path).resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"Repository root directory does not exist: {root}")

        analyzed_files: list[AnalyzedFile] = []
        candidate_python_files: list[Path] = []

        # Detect source root
        src_path = root / "src"
        source_root: str | None = None
        if src_path.is_dir():
            # Check if src has any python files
            if any(src_path.glob("**/*.py")):
                source_root = "src"

        # Walk directory with early pruning
        for entry in sorted(root.rglob("*")):
            # Skip directories from file inventory
            if entry.is_dir():
                continue

            # Check if any parent part matches ignored dirs
            rel_parts = entry.relative_to(root).parts
            if any(part in self._ignored_dirs for part in rel_parts[:-1]):
                continue

            rel_posix = entry.relative_to(root).as_posix()

            # Check custom exclude patterns
            if any(
                fnmatch.fnmatch(rel_posix, pat) or fnmatch.fnmatch(entry.name, pat)
                for pat in exclude_patterns
            ):
                continue

            # Symlink safety check: target must remain inside root
            if entry.is_symlink():
                try:
                    resolved = entry.resolve()
                    if not resolved.is_relative_to(root):
                        # Symlink escapes repository root - skip
                        continue
                except Exception:
                    continue

            # Check file size
            try:
                size_bytes = entry.stat().st_size
            except OSError:
                size_bytes = 0

            is_bin = self.is_binary(entry) if size_bytes > 0 else False
            file_kind = self.classify_file(rel_posix, is_bin)

            if size_bytes > self._max_file_size_bytes:
                status = FileStatus.SKIPPED
            else:
                status = FileStatus.PARSED

            analyzed_file = AnalyzedFile(
                path=rel_posix,
                file_type=file_kind,
                size_bytes=size_bytes,
                status=status,
                is_generated=False,
            )
            analyzed_files.append(analyzed_file)

            if (
                file_kind in {FileKind.PYTHON, FileKind.TEST, FileKind.CONFIG}
                and entry.suffix in {".py", ".pyw"}
                and status == FileStatus.PARSED
            ):
                candidate_python_files.append(entry)

        return ScanResult(
            files=tuple(analyzed_files),
            python_files=tuple(candidate_python_files),
            source_root=source_root,
        )
