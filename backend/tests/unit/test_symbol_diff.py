"""Unit tests for SymbolDiffEngine and Breaking Change Detection."""

import uuid
from trace.analysis.symbol_diff import SymbolDiffEngine
from trace.domain.analysis import (
    APIEndpoint,
    Class,
    DecoratorDescriptor,
    Function,
    FunctionKind,
    Module,
    ParameterDescriptor,
    RepositoryAnalysis,
    SourceLocation,
)
from trace.domain.diff import (
    DiffHunk,
    FileChangeType,
    FileDiff,
    SymbolChangeKind,
)


from datetime import UTC, datetime


def _make_dummy_analysis(
    functions: list[Function] | None = None,
    classes: list[Class] | None = None,
    endpoints: list[APIEndpoint] | None = None,
    modules: list[Module] | None = None,
) -> RepositoryAnalysis:
    return RepositoryAnalysis(
        run_id=uuid.uuid4(),
        repository_id=uuid.uuid4(),
        analyzed_at=datetime.now(UTC),
        resolved_revision="1234567890123456789012345678901234567890",
        commit_hash="1234567890123456789012345678901234567890",
        files=(),
        modules=tuple(modules or ()),
        classes=tuple(classes or ()),
        functions=tuple(functions or ()),
        services=(),
        imports=(),
        calls=(),
        endpoints=tuple(endpoints or ()),
        configurations=(),
        database_references=(),
        tests=(),
        documentation=(),
        dependencies=(),
        relationships=(),
        diagnostics=(),
        summary={},
    )


def test_symbol_diff_deleted_file() -> None:
    """Symbols in deleted files are marked DELETED and BREAKING."""
    func = Function(
        name="old_func",
        qualified_name="app.old.old_func",
        module_name="app.old",
        enclosing_class=None,
        kind=FunctionKind.FUNCTION,
        parameters=(),
        return_type="int",
        decorators=(),
        docstring=None,
        location=SourceLocation(file_path="app/old.py", start_line=1, end_line=5),
    )
    base_analysis = _make_dummy_analysis(functions=[func])
    file_diff = FileDiff(
        old_path="app/old.py",
        new_path=None,
        change_type=FileChangeType.DELETED,
        insertions=0,
        deletions=5,
        hunks=(),
    )

    engine = SymbolDiffEngine()
    diffs = engine.compute_symbol_diffs([file_diff], base_analysis, None)

    assert len(diffs) == 1
    assert diffs[0].qualified_name == "app.old.old_func"
    assert diffs[0].change_kind == SymbolChangeKind.DELETED
    assert diffs[0].is_breaking is True


def test_symbol_diff_added_file() -> None:
    """Symbols in added files are marked ADDED."""
    func = Function(
        name="new_func",
        qualified_name="app.new.new_func",
        module_name="app.new",
        enclosing_class=None,
        kind=FunctionKind.FUNCTION,
        parameters=(ParameterDescriptor(name="x", type_annotation="int"),),
        return_type="str",
        decorators=(),
        docstring=None,
        location=SourceLocation(file_path="app/new.py", start_line=1, end_line=3),
    )
    target_analysis = _make_dummy_analysis(functions=[func])
    file_diff = FileDiff(
        old_path=None,
        new_path="app/new.py",
        change_type=FileChangeType.ADDED,
        insertions=3,
        deletions=0,
        hunks=(),
    )

    engine = SymbolDiffEngine()
    diffs = engine.compute_symbol_diffs([file_diff], None, target_analysis)

    assert len(diffs) == 1
    assert diffs[0].qualified_name == "app.new.new_func"
    assert diffs[0].change_kind == SymbolChangeKind.ADDED
    assert diffs[0].is_breaking is False
    assert "new_func(x: int) -> str" in (diffs[0].new_signature or "")


def test_symbol_diff_function_breaking_parameter_removed() -> None:
    """Removing a parameter is flagged as breaking."""
    old_func = Function(
        name="calculate",
        qualified_name="app.calc.calculate",
        module_name="app.calc",
        enclosing_class=None,
        kind=FunctionKind.FUNCTION,
        parameters=(
            ParameterDescriptor(name="a", type_annotation="int"),
            ParameterDescriptor(name="b", type_annotation="int"),
        ),
        return_type="int",
        decorators=(),
        docstring=None,
        location=SourceLocation(file_path="app/calc.py", start_line=10, end_line=15),
    )
    new_func = Function(
        name="calculate",
        qualified_name="app.calc.calculate",
        module_name="app.calc",
        enclosing_class=None,
        kind=FunctionKind.FUNCTION,
        parameters=(ParameterDescriptor(name="a", type_annotation="int"),),
        return_type="int",
        decorators=(),
        docstring=None,
        location=SourceLocation(file_path="app/calc.py", start_line=10, end_line=14),
    )

    base_analysis = _make_dummy_analysis(functions=[old_func])
    target_analysis = _make_dummy_analysis(functions=[new_func])

    file_diff = FileDiff(
        old_path="app/calc.py",
        new_path="app/calc.py",
        change_type=FileChangeType.MODIFIED,
        insertions=1,
        deletions=2,
        hunks=(DiffHunk(old_start=10, old_lines=5, new_start=10, new_lines=4),),
    )

    engine = SymbolDiffEngine()
    diffs = engine.compute_symbol_diffs([file_diff], base_analysis, target_analysis)

    assert len(diffs) == 1
    sym = diffs[0]
    assert sym.change_kind == SymbolChangeKind.MODIFIED
    assert sym.is_breaking is True
    assert "Parameter 'b' was removed" in (sym.breaking_reason or "")


def test_symbol_diff_function_added_optional_param_not_breaking() -> None:
    """Adding an optional parameter with default value is NOT breaking."""
    old_func = Function(
        name="greet",
        qualified_name="app.greet.greet",
        module_name="app.greet",
        enclosing_class=None,
        kind=FunctionKind.FUNCTION,
        parameters=(ParameterDescriptor(name="name", type_annotation="str"),),
        return_type="str",
        decorators=(),
        docstring=None,
        location=SourceLocation(file_path="app/greet.py", start_line=5, end_line=10),
    )
    new_func = Function(
        name="greet",
        qualified_name="app.greet.greet",
        module_name="app.greet",
        enclosing_class=None,
        kind=FunctionKind.FUNCTION,
        parameters=(
            ParameterDescriptor(name="name", type_annotation="str"),
            ParameterDescriptor(name="greeting", type_annotation="str", has_default=True, default_value='"Hello"'),
        ),
        return_type="str",
        decorators=(),
        docstring=None,
        location=SourceLocation(file_path="app/greet.py", start_line=5, end_line=11),
    )

    base_analysis = _make_dummy_analysis(functions=[old_func])
    target_analysis = _make_dummy_analysis(functions=[new_func])

    file_diff = FileDiff(
        old_path="app/greet.py",
        new_path="app/greet.py",
        change_type=FileChangeType.MODIFIED,
        insertions=2,
        deletions=1,
        hunks=(DiffHunk(old_start=5, old_lines=5, new_start=5, new_lines=6),),
    )

    engine = SymbolDiffEngine()
    diffs = engine.compute_symbol_diffs([file_diff], base_analysis, target_analysis)

    assert len(diffs) == 1
    sym = diffs[0]
    assert sym.change_kind == SymbolChangeKind.MODIFIED
    assert sym.is_breaking is False
    assert sym.breaking_reason is None


def test_symbol_diff_function_return_type_changed() -> None:
    """Changing function return type is flagged as breaking."""
    old_func = Function(
        name="get_count",
        qualified_name="app.db.get_count",
        module_name="app.db",
        enclosing_class=None,
        kind=FunctionKind.FUNCTION,
        parameters=(),
        return_type="int",
        decorators=(),
        docstring=None,
        location=SourceLocation(file_path="app/db.py", start_line=1, end_line=4),
    )
    new_func = Function(
        name="get_count",
        qualified_name="app.db.get_count",
        module_name="app.db",
        enclosing_class=None,
        kind=FunctionKind.FUNCTION,
        parameters=(),
        return_type="dict[str, int]",
        decorators=(),
        docstring=None,
        location=SourceLocation(file_path="app/db.py", start_line=1, end_line=4),
    )

    base_analysis = _make_dummy_analysis(functions=[old_func])
    target_analysis = _make_dummy_analysis(functions=[new_func])

    file_diff = FileDiff(
        old_path="app/db.py",
        new_path="app/db.py",
        change_type=FileChangeType.MODIFIED,
        insertions=1,
        deletions=1,
        hunks=(DiffHunk(old_start=1, old_lines=4, new_start=1, new_lines=4),),
    )

    engine = SymbolDiffEngine()
    diffs = engine.compute_symbol_diffs([file_diff], base_analysis, target_analysis)

    assert len(diffs) == 1
    assert diffs[0].is_breaking is True
    assert "Return type changed from 'int' to 'dict[str, int]'" in (diffs[0].breaking_reason or "")
