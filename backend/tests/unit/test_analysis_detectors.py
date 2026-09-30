"""Unit tests for specialized pattern detectors."""

from pathlib import Path
from trace.analysis.analyzer import AnalysisContext, PythonCodeAnalyzer
from trace.analysis.detectors import (
    APIDetector,
    ConfigDetector,
    DatabaseDetector,
    DependencyDetector,
    DocumentationDetector,
    ServiceDetector,
    TestDetector,
)
from trace.domain.analysis import (
    DatabaseOperationKind,
    DocumentationKind,
    RelationshipKind,
)

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def sample_repo_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "sample_repo"


def test_service_detector(sample_repo_path: Path):
    """Verify ServiceDetector finds service classes and methods."""
    detector = ServiceDetector()
    analyzer = PythonCodeAnalyzer(detectors=(detector,))
    from uuid import uuid4

    context = AnalysisContext(
        run_id=uuid4(), repository_id=uuid4(), working_tree_path=sample_repo_path
    )
    result = analyzer.analyze(context)

    svc_names = {s.name for s in result.services}
    assert "BaseService" in svc_names
    assert "ItemService" in svc_names

    item_service = next(s for s in result.services if s.name == "ItemService")
    assert "create_item" in item_service.methods
    assert "get_items" in item_service.methods


def test_api_detector(sample_repo_path: Path):
    """Verify APIDetector extracts FastAPI route endpoints and EXPOSES relationships."""
    detector = APIDetector()
    analyzer = PythonCodeAnalyzer(detectors=(detector,))
    from uuid import uuid4

    context = AnalysisContext(
        run_id=uuid4(), repository_id=uuid4(), working_tree_path=sample_repo_path
    )
    result = analyzer.analyze(context)

    routes = {(e.http_method, e.path) for e in result.endpoints}
    assert ("GET", "/items") in routes
    assert ("POST", "/items") in routes

    exposes_rels = [
        r for r in result.relationships if r.relationship_type == RelationshipKind.EXPOSES
    ]
    assert len(exposes_rels) >= 2


def test_config_detector(sample_repo_path: Path):
    """Verify ConfigDetector detects configuration and environment settings."""
    detector = ConfigDetector()
    analyzer = PythonCodeAnalyzer(detectors=(detector,))
    from uuid import uuid4

    context = AnalysisContext(
        run_id=uuid4(), repository_id=uuid4(), working_tree_path=sample_repo_path
    )
    result = analyzer.analyze(context)

    keys = {c.key_name for c in result.configurations}
    assert "DATABASE_URL" in keys or "database_url" in keys

    configured_by = [
        r
        for r in result.relationships
        if r.relationship_type in {RelationshipKind.CONFIGURED_BY, RelationshipKind.READS}
    ]
    assert len(configured_by) >= 1


def test_database_detector(sample_repo_path: Path):
    """Verify DatabaseDetector identifies ORM models and operations."""
    detector = DatabaseDetector()
    analyzer = PythonCodeAnalyzer(detectors=(detector,))
    from uuid import uuid4

    context = AnalysisContext(
        run_id=uuid4(), repository_id=uuid4(), working_tree_path=sample_repo_path
    )
    result = analyzer.analyze(context)

    entities = {d.target_entity for d in result.database_references}
    assert "items" in entities or "ItemOrm" in entities

    model_decls = [
        d
        for d in result.database_references
        if d.operation == DatabaseOperationKind.MODEL_DECLARATION
    ]
    assert len(model_decls) >= 1


def test_test_detector(sample_repo_path: Path):
    """Verify TestDetector detects test functions and TESTED_BY links."""
    detector = TestDetector()
    analyzer = PythonCodeAnalyzer(detectors=(detector,))
    from uuid import uuid4

    context = AnalysisContext(
        run_id=uuid4(), repository_id=uuid4(), working_tree_path=sample_repo_path
    )
    result = analyzer.analyze(context)

    test_names = {t.test_name for t in result.tests}
    assert "test_service_initialization" in test_names
    assert "test_create_item" in test_names

    tested_by_rels = [
        r for r in result.relationships if r.relationship_type == RelationshipKind.TESTED_BY
    ]
    assert len(tested_by_rels) >= 1
    assert any("ItemService" in r.source_identifier for r in tested_by_rels)


def test_documentation_detector(sample_repo_path: Path):
    """Verify DocumentationDetector extracts docstrings and README.md."""
    detector = DocumentationDetector()
    analyzer = PythonCodeAnalyzer(detectors=(detector,))
    from uuid import uuid4

    context = AnalysisContext(
        run_id=uuid4(), repository_id=uuid4(), working_tree_path=sample_repo_path
    )
    result = analyzer.analyze(context)

    md_docs = [d for d in result.documentation if d.doc_type == DocumentationKind.MARKDOWN_FILE]
    assert len(md_docs) >= 1
    assert any(d.title == "README.md" for d in md_docs)

    inline_docs = [
        d for d in result.documentation if d.doc_type == DocumentationKind.INLINE_DOCSTRING
    ]
    assert len(inline_docs) >= 1


def test_dependency_detector(sample_repo_path: Path):
    """Verify DependencyDetector extracts external dependencies from pyproject.toml."""
    detector = DependencyDetector()
    analyzer = PythonCodeAnalyzer(detectors=(detector,))
    from uuid import uuid4

    context = AnalysisContext(
        run_id=uuid4(), repository_id=uuid4(), working_tree_path=sample_repo_path
    )
    result = analyzer.analyze(context)

    pkgs = {d.package_name for d in result.dependencies}
    assert "fastapi" in pkgs
    assert "pydantic" in pkgs
    assert "sqlalchemy" in pkgs

    depends_on = [
        r for r in result.relationships if r.relationship_type == RelationshipKind.DEPENDS_ON
    ]
    assert len(depends_on) >= 3
