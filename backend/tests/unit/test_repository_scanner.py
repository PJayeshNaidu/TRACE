"""Unit tests for RepositoryScanner."""

from pathlib import Path
from trace.analysis.scanner import RepositoryScanner, ScanResult
from trace.domain.analysis import FileKind, FileStatus

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def sample_repo_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "sample_repo"


@pytest.fixture
def ignored_dirs_repo_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "ignored_dirs_repo"


def test_scanner_discovers_sample_repo_files(sample_repo_path: Path):
    """Verify scanning the sample repository categorizes files accurately."""
    scanner = RepositoryScanner()
    result = scanner.scan(sample_repo_path)

    assert isinstance(result, ScanResult)
    paths = {f.path for f in result.files}

    # Python files
    assert "app/__init__.py" in paths
    assert "app/main.py" in paths
    assert "app/config.py" in paths
    assert "app/models.py" in paths
    assert "app/services.py" in paths
    assert "app/tests/test_services.py" in paths

    # Manifests and docs
    assert "pyproject.toml" in paths
    assert "README.md" in paths

    # File kind assertions
    file_map = {f.path: f for f in result.files}
    assert file_map["app/main.py"].file_type == FileKind.PYTHON
    assert file_map["app/tests/test_services.py"].file_type == FileKind.TEST
    assert file_map["app/config.py"].file_type == FileKind.CONFIG
    assert file_map["README.md"].file_type == FileKind.DOCUMENTATION
    assert file_map["pyproject.toml"].file_type == FileKind.DEPENDENCY


def test_scanner_prunes_ignored_directories(ignored_dirs_repo_path: Path):
    """Verify default ignored directories (.venv, __pycache__) are pruned."""
    scanner = RepositoryScanner()
    result = scanner.scan(ignored_dirs_repo_path)

    paths = [f.path for f in result.files]
    assert "main.py" in paths

    for path in paths:
        assert ".venv" not in path
        assert "__pycache__" not in path


def test_scanner_custom_exclusion_patterns(sample_repo_path: Path):
    """Verify custom exclusion globs filter out matching files."""
    scanner = RepositoryScanner()
    result = scanner.scan(sample_repo_path, exclude_patterns=("app/tests/*", "*.md"))

    paths = {f.path for f in result.files}
    assert "README.md" not in paths
    assert "app/tests/test_services.py" not in paths
    assert "app/main.py" in paths


def test_scanner_handles_large_and_binary_files(tmp_path: Path):
    """Verify scanner handles binary files and oversized files safely."""
    # Create a small python file
    (tmp_path / "valid.py").write_text("x = 1\n", encoding="utf-8")

    # Create a binary file (containing null bytes)
    (tmp_path / "binary.dat").write_bytes(b"\x00\x01\x02\x03\x04")

    # Create an oversized file (>1MB)
    large_file = tmp_path / "large.py"
    large_file.write_bytes(b"a" * (1024 * 1024 + 10))

    scanner = RepositoryScanner(max_file_size_bytes=1024 * 1024)
    result = scanner.scan(tmp_path)

    file_map = {f.path: f for f in result.files}
    assert "valid.py" in file_map
    assert file_map["valid.py"].status == FileStatus.PARSED

    assert "large.py" in file_map
    assert file_map["large.py"].status == FileStatus.SKIPPED

    assert "binary.dat" in file_map
    assert file_map["binary.dat"].file_type == FileKind.OTHER


def test_scanner_source_root_detection(tmp_path: Path):
    """Verify detection of source root (e.g., src layout vs root)."""
    src_dir = tmp_path / "src" / "pkg"
    src_dir.mkdir(parents=True)
    (src_dir / "mod.py").write_text("def f(): pass\n", encoding="utf-8")

    scanner = RepositoryScanner()
    result = scanner.scan(tmp_path)

    assert result.source_root == "src"
