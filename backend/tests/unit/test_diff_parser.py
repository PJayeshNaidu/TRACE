"""Unit tests for GitDiffParser."""

import pytest
from trace.analysis.diff_parser import GitDiffParser
from trace.domain.diff import FileChangeType


def test_parse_empty_diff() -> None:
    """Empty or whitespace diff string returns empty list."""
    parser = GitDiffParser()
    assert parser.parse("") == []
    assert parser.parse("   \n\t  ") == []


def test_parse_modified_file_single_hunk() -> None:
    """Parse standard modified file diff with insertion and deletion."""
    raw_diff = """diff --git a/src/trace/calc.py b/src/trace/calc.py
index 1234567..89abcdef 100644
--- a/src/trace/calc.py
+++ b/src/trace/calc.py
@@ -10,5 +10,6 @@ def add(a: int, b: int) -> int:
-    return a - b
+    return a + b
+    # bonus comment
"""
    parser = GitDiffParser()
    diffs = parser.parse(raw_diff)

    assert len(diffs) == 1
    file_diff = diffs[0]
    assert file_diff.old_path == "src/trace/calc.py"
    assert file_diff.new_path == "src/trace/calc.py"
    assert file_diff.change_type == FileChangeType.MODIFIED
    assert file_diff.insertions == 2
    assert file_diff.deletions == 1
    assert len(file_diff.hunks) == 1

    hunk = file_diff.hunks[0]
    assert hunk.old_start == 10
    assert hunk.old_lines == 5
    assert hunk.new_start == 10
    assert hunk.new_lines == 6
    assert "def add" in hunk.header


def test_parse_added_file() -> None:
    """Parse added new file."""
    raw_diff = """diff --git a/src/trace/service.py b/src/trace/service.py
new file mode 100644
index 0000000..89abcdef
--- /dev/null
+++ b/src/trace/service.py
@@ -0,0 +1,10 @@
+class PaymentService:
+    def process(self):
+        pass
"""
    parser = GitDiffParser()
    diffs = parser.parse(raw_diff)

    assert len(diffs) == 1
    file_diff = diffs[0]
    assert file_diff.old_path is None
    assert file_diff.new_path == "src/trace/service.py"
    assert file_diff.change_type == FileChangeType.ADDED
    assert file_diff.insertions == 3
    assert file_diff.deletions == 0
    assert len(file_diff.hunks) == 1
    assert file_diff.hunks[0].new_start == 1
    assert file_diff.hunks[0].new_lines == 10


def test_parse_deleted_file() -> None:
    """Parse deleted file."""
    raw_diff = """diff --git a/src/trace/old.py b/src/trace/old.py
deleted file mode 100644
index 89abcdef..0000000
--- a/src/trace/old.py
+++ /dev/null
@@ -1,5 +0,0 @@
-class Obsolete:
-    pass
"""
    parser = GitDiffParser()
    diffs = parser.parse(raw_diff)

    assert len(diffs) == 1
    file_diff = diffs[0]
    assert file_diff.old_path == "src/trace/old.py"
    assert file_diff.new_path is None
    assert file_diff.change_type == FileChangeType.DELETED
    assert file_diff.deletions == 2
    assert file_diff.insertions == 0


def test_parse_renamed_file() -> None:
    """Parse renamed file."""
    raw_diff = """diff --git a/src/trace/legacy.py b/src/trace/modern.py
similarity index 98%
rename from src/trace/legacy.py
rename to src/trace/modern.py
index 1234567..89abcdef 100644
--- a/src/trace/legacy.py
+++ b/src/trace/modern.py
@@ -1 +1 @@
-def legacy_func(): pass
+def modern_func(): pass
"""
    parser = GitDiffParser()
    diffs = parser.parse(raw_diff)

    assert len(diffs) == 1
    file_diff = diffs[0]
    assert file_diff.old_path == "src/trace/legacy.py"
    assert file_diff.new_path == "src/trace/modern.py"
    assert file_diff.change_type == FileChangeType.RENAMED
    assert file_diff.insertions == 1
    assert file_diff.deletions == 1
    assert len(file_diff.hunks) == 1
    assert file_diff.hunks[0].old_lines == 1
    assert file_diff.hunks[0].new_lines == 1


def test_parse_multi_file_multi_hunk_diff() -> None:
    """Parse multiple files with multiple hunks in one unified diff."""
    raw_diff = """diff --git a/src/app/a.py b/src/app/a.py
index 1111111..2222222 100644
--- a/src/app/a.py
+++ b/src/app/a.py
@@ -5,3 +5,4 @@
 def func_a():
+    print("hunk 1")
@@ -20,2 +21,3 @@
 def func_b():
+    print("hunk 2")
diff --git a/src/app/b.py b/src/app/b.py
new file mode 100644
--- /dev/null
+++ b/src/app/b.py
@@ -0,0 +1,2 @@
+def func_c():
+    return True
"""
    parser = GitDiffParser()
    diffs = parser.parse(raw_diff)

    assert len(diffs) == 2
    assert diffs[0].new_path == "src/app/a.py"
    assert len(diffs[0].hunks) == 2
    assert diffs[1].new_path == "src/app/b.py"
    assert diffs[1].change_type == FileChangeType.ADDED
