"""Unified Git diff parser producing structured FileDiff and DiffHunk domain objects."""

import re
from trace.domain.diff import DiffHunk, FileChangeType, FileDiff

# Regex for diff file header: diff --git a/path b/path
DIFF_HEADER_RE = re.compile(r"^diff --git a/(.*?) b/(.*?)$")
# Regex for hunk header: @@ -old_start,old_lines +new_start,new_lines @@ header_text
HUNK_HEADER_RE = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: ?(.*))?$"
)


class GitDiffParser:
    """Parses standard Unified Git Diff output into structured domain models."""

    def parse(self, diff_text: str) -> list[FileDiff]:
        """Parse raw unified diff text into a list of FileDiff instances.

        Args:
            diff_text: Raw stdout string from `git diff`.

        Returns:
            List of structured FileDiff objects.
        """
        if not diff_text or not diff_text.strip():
            return []

        file_diffs: list[FileDiff] = []
        lines = diff_text.splitlines()
        i = 0
        n = len(lines)

        while i < n:
            line = lines[i]
            match = DIFF_HEADER_RE.match(line)
            if not match:
                i += 1
                continue

            old_path = match.group(1).strip()
            new_path = match.group(2).strip()
            change_type = FileChangeType.MODIFIED
            is_new = False
            is_deleted = False
            is_renamed = False
            hunks: list[DiffHunk] = []
            insertions = 0
            deletions = 0

            i += 1
            # Parse header metadata lines until first hunk header @@ or next diff --git
            while i < n and not lines[i].startswith("diff --git"):
                sub_line = lines[i]
                if sub_line.startswith("new file mode"):
                    change_type = FileChangeType.ADDED
                    is_new = True
                elif sub_line.startswith("deleted file mode"):
                    change_type = FileChangeType.DELETED
                    is_deleted = True
                elif sub_line.startswith("rename from"):
                    is_renamed = True
                    change_type = FileChangeType.RENAMED
                elif sub_line.startswith("rename to"):
                    new_path = sub_line.removeprefix("rename to").strip()
                elif sub_line.startswith("--- /dev/null"):
                    change_type = FileChangeType.ADDED
                    is_new = True
                elif sub_line.startswith("+++ /dev/null"):
                    change_type = FileChangeType.DELETED
                    is_deleted = True
                elif sub_line.startswith("@@"):
                    # Start of hunks for this file
                    break
                i += 1

            # Parse all hunks for current file
            current_hunk_kwargs: dict[str, int | str] | None = None
            current_hunk_lines: list[str] = []

            def flush_hunk() -> None:
                nonlocal current_hunk_kwargs, current_hunk_lines
                if current_hunk_kwargs is not None:
                    hunks.append(
                        DiffHunk(
                            old_start=int(current_hunk_kwargs["old_start"]),
                            old_lines=int(current_hunk_kwargs["old_lines"]),
                            new_start=int(current_hunk_kwargs["new_start"]),
                            new_lines=int(current_hunk_kwargs["new_lines"]),
                            header=str(current_hunk_kwargs["header"]),
                            content="\n".join(current_hunk_lines),
                        )
                    )
                    current_hunk_kwargs = None
                    current_hunk_lines = []

            while i < n and not lines[i].startswith("diff --git"):
                sub_line = lines[i]
                hunk_match = HUNK_HEADER_RE.match(sub_line)
                if hunk_match:
                    flush_hunk()
                    old_start = int(hunk_match.group(1))
                    old_lines = int(hunk_match.group(2)) if hunk_match.group(2) is not None else 1
                    new_start = int(hunk_match.group(3))
                    new_lines = int(hunk_match.group(4)) if hunk_match.group(4) is not None else 1
                    header_text = (hunk_match.group(5) or "").strip()

                    current_hunk_kwargs = {
                        "old_start": old_start,
                        "old_lines": old_lines,
                        "new_start": new_start,
                        "new_lines": new_lines,
                        "header": header_text,
                    }
                else:
                    if current_hunk_kwargs is not None:
                        current_hunk_lines.append(sub_line)
                    if sub_line.startswith("+") and not sub_line.startswith("+++"):
                        insertions += 1
                    elif sub_line.startswith("-") and not sub_line.startswith("---"):
                        deletions += 1

                i += 1

            flush_hunk()

            if is_new:
                actual_old_path = None
                actual_new_path = new_path
            elif is_deleted:
                actual_old_path = old_path
                actual_new_path = None
            else:
                actual_old_path = old_path
                actual_new_path = new_path

            file_diffs.append(
                FileDiff(
                    old_path=actual_old_path,
                    new_path=actual_new_path,
                    change_type=change_type,
                    insertions=insertions,
                    deletions=deletions,
                    hunks=tuple(hunks),
                )
            )

        return file_diffs
