"""Unit tests for Python AST parsing, symbol extraction, and PythonCodeAnalyzer."""

from pathlib import Path
from trace.analysis.analyzer import AnalysisContext, PythonCodeAnalyzer
from trace.analysis.extractor import SymbolExtractor, derive_module_qualified_name
from trace.analysis.parser import PythonAstParser
from trace.domain.analysis import (
    CallResolutionStatus,
    DiagnosticSeverity,
    FunctionKind,
    RelationshipKind,
)
from uuid import uuid4

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def sample_repo_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "sample_repo"


@pytest.fixture
def syntax_error_repo_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "syntax_error_repo"


def test_derive_module_qualified_name():
    """Verify dot-separated module qualified names and package flags."""
    assert derive_module_qualified_name("app/main.py") == ("app.main", False)
    assert derive_module_qualified_name("app/__init__.py") == ("app", True)
    assert derive_module_qualified_name("src/pkg/mod.py", source_root="src") == ("pkg.mod", False)
    assert derive_module_qualified_name("src/pkg/__init__.py", source_root="src") == ("pkg", True)


def test_ast_parser_handles_valid_and_syntax_error(syntax_error_repo_path: Path):
    """Verify AST parser parses valid code and generates diagnostics on syntax error."""
    parser = PythonAstParser()

    # Valid file
    valid_file = syntax_error_repo_path / "valid.py"
    tree, diag = parser.parse_file(valid_file, rel_path="valid.py")
    assert tree is not None
    assert diag is None

    # Broken file with deliberate syntax error
    broken_file = syntax_error_repo_path / "broken.py"
    tree, diag = parser.parse_file(broken_file, rel_path="broken.py")
    assert tree is None
    assert diag is not None
    assert diag.file_path == "broken.py"
    assert diag.severity == DiagnosticSeverity.ERROR
    assert diag.code == "SYNTAX_ERROR"
    assert diag.line is not None


def test_symbol_extractor_classes_and_functions():
    """Verify class, method, function, parameter, decorator, and import extraction."""
    code = """
import os
from app.models import ItemOrm

@decorator(param="val")
class MyService(BaseService):
    \"\"\"MyService docstring.\"\"\"

    def __init__(self, name: str = "default") -> None:
        self.name = name

    def execute(self) -> str:
        self.ping()
        return "done"

    def ping(self) -> str:
        return "pong"

def standalone_func(x: int, *args, **kwargs) -> int:
    \"\"\"Standalone function doc.\"\"\"
    return x * 2
"""
    parser = PythonAstParser()
    tree, diag = parser.parse_source(code, filename="service.py")
    assert tree is not None

    extractor = SymbolExtractor(internal_packages={"app"})
    extracted = extractor.extract(tree, file_path="app/service.py", total_lines=25)

    # Module
    assert extracted.module.qualified_name == "app.service"
    assert not extracted.module.is_package

    # Classes
    assert len(extracted.classes) == 1
    cls = extracted.classes[0]
    assert cls.name == "MyService"
    assert cls.qualified_name == "app.service.MyService"
    assert cls.parent_classes == ("BaseService",)
    assert cls.docstring == "MyService docstring."
    assert len(cls.decorators) == 1
    assert cls.decorators[0].name == "decorator"

    # EXTENDS relationship
    extends_rels = [
        r for r in extracted.relationships if r.relationship_type == RelationshipKind.EXTENDS
    ]
    assert len(extends_rels) == 1
    assert extends_rels[0].source_identifier == "app.service.MyService"
    assert extends_rels[0].target_identifier == "BaseService"

    # Functions & Methods
    func_names = [f.name for f in extracted.functions]
    assert "__init__" in func_names
    assert "execute" in func_names
    assert "ping" in func_names
    assert "standalone_func" in func_names

    standalone = next(f for f in extracted.functions if f.name == "standalone_func")
    assert standalone.kind == FunctionKind.FUNCTION
    assert standalone.docstring == "Standalone function doc."
    assert len(standalone.parameters) == 3
    assert standalone.parameters[0].name == "x"
    assert standalone.parameters[0].type_annotation == "int"
    assert standalone.parameters[1].name == "*args"
    assert standalone.parameters[2].name == "**kwargs"
    assert standalone.return_type == "int"

    # Calls
    execute_calls = [
        c for c in extracted.calls if c.caller_qualified_name == "app.service.MyService.execute"
    ]
    assert len(execute_calls) >= 1
    ping_call = next(c for c in execute_calls if c.callee_expression == "self.ping")
    assert ping_call.resolution_status == CallResolutionStatus.RESOLVED_INTERNAL
    assert ping_call.resolved_target == "app.service.MyService.ping"


def test_python_code_analyzer_full_analysis(sample_repo_path: Path):
    """Verify PythonCodeAnalyzer execution on the sample repository."""
    analyzer = PythonCodeAnalyzer()
    context = AnalysisContext(
        run_id=uuid4(),
        repository_id=uuid4(),
        working_tree_path=sample_repo_path,
        resolved_revision="1234567890123456789012345678901234567890",
    )

    result = analyzer.analyze(context)

    assert result.run_id == context.run_id
    assert result.repository_id == context.repository_id
    assert result.resolved_revision == context.resolved_revision
    assert len(result.files) >= 5
    assert len(result.modules) >= 5

    module_names = {m.qualified_name for m in result.modules}
    assert "app" in module_names
    assert "app.main" in module_names
    assert "app.config" in module_names
    assert "app.models" in module_names
    assert "app.services" in module_names

    class_names = {c.name for c in result.classes}
    assert "BaseService" in class_names
    assert "ItemService" in class_names
    assert "ItemOrm" in class_names

    func_names = {f.name for f in result.functions}
    assert "create_item" in func_names
    assert "get_items" in func_names
    assert "list_items" in func_names

    # Check 100% of entities have valid coordinates
    for m in result.modules:
        assert m.location.start_line >= 1
        assert m.location.end_line >= m.location.start_line
    for c in result.classes:
        assert c.location.start_line >= 1
        assert c.location.end_line >= c.location.start_line
    for f in result.functions:
        assert f.location.start_line >= 1
        assert f.location.end_line >= f.location.start_line

    # Verify specialized detector outputs integrated cleanly
    assert len(result.services) >= 1
    assert any(s.name == "ItemService" for s in result.services)

    assert len(result.endpoints) >= 1
    assert any(e.path == "/items" for e in result.endpoints)

    assert len(result.configurations) >= 1
    assert any(c.key_name == "DATABASE_URL" for c in result.configurations)

    assert len(result.database_references) >= 1
    assert any(d.target_entity == "items" for d in result.database_references)

    assert len(result.tests) >= 1
    assert any(t.test_name == "test_create_item" for t in result.tests)

    assert len(result.documentation) >= 1
    assert any(d.file_path == "README.md" for d in result.documentation)

    assert len(result.dependencies) >= 1
    assert any(dep.package_name == "fastapi" for dep in result.dependencies)

    assert len(result.relationships) >= 5
    rel_types = {r.relationship_type for r in result.relationships}
    assert RelationshipKind.EXPOSES in rel_types
    assert RelationshipKind.CONFIGURED_BY in rel_types
    assert RelationshipKind.DOCUMENTED_BY in rel_types
    assert RelationshipKind.DEPENDS_ON in rel_types
