"""Cross-module text reference discovery across non-code and configuration repository files."""

from __future__ import annotations

import re
from pathlib import Path

# File extensions to scan for cross-module text references
TARGET_EXTENSIONS: set[str] = {
    ".yaml",
    ".yml",
    ".json",
    ".md",
    ".rst",
    ".toml",
    ".ini",
    ".env",
    ".cfg",
    ".txt",
    ".sh",
    ".dockerfile",
}

# Directories to ignore
IGNORED_DIRS: set[str] = {
    ".git",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "venv",
    ".trace",
    "storage",
    "dist",
    "build",
}


class TextDiscoveryEngine:
    """Discovers textual references to code symbols in non-code and config files using word boundaries."""

    def find_text_references(
        self,
        working_tree_path: Path | str,
        entity_name: str,
        source_file_path: str,
        max_files: int = 15,
    ) -> list[str]:
        """Scan workspace for word-boundary matches of entity_name outside source_file_path."""
        root = Path(working_tree_path).resolve()
        if not root.exists() or not entity_name:
            return []

        # Strip qualified name to core identifier if dotted
        identifier = entity_name.split(".")[-1]
        if len(identifier) < 3:
            # Skip very short identifiers to avoid false positive explosions
            return []

        pattern = re.compile(rf"\b{re.escape(identifier)}\b")
        matching_files: list[str] = []

        try:
            for path in root.rglob("*"):
                if not path.is_file():
                    continue

                # Skip ignored directories
                parts = set(path.parts)
                if parts.intersection(IGNORED_DIRS):
                    continue

                # Only inspect targeted non-code extensions or files without extension
                ext = path.suffix.lower()
                name = path.name.lower()
                if ext not in TARGET_EXTENSIONS and "dockerfile" not in name:
                    continue

                rel_path = path.relative_to(root).as_posix()
                # Skip the entity's own source file
                if rel_path == source_file_path:
                    continue

                try:
                    content = path.read_text(encoding="utf-8", errors="ignore")
                    if pattern.search(content):
                        matching_files.append(rel_path)
                        if len(matching_files) >= max_files:
                            break
                except Exception:
                    continue
        except Exception:
            pass

        return matching_files
