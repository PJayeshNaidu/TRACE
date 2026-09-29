"""Tests verifying CodeAnalyzer protocol abstraction, replaceability, and AST isolation."""

import ast
import uuid
from datetime import UTC, datetime
from pathlib import Path
from trace.analysis.analyzer import AnalysisContext, CodeAnalyzer
from trace.domain.analysis import (
    AnalysisRelationship,
    AnalysisStatus,
    AnalyzedFile,
    Class,
    EntityKind,
    FileKind,
    FileStatus,
    Function,
    FunctionKind,
    Module,
    RelationshipKind,
    RepositoryAnalysis,
    SourceLocation,
)
from trace.domain.project import ProjectStatus
from trace.domain.repository import RepositoryType
from trace.infrastructure.database.gateway import InMemoryDatabaseGateway
from trace.infrastructure.database.models import ProjectOrm, RepositoryOrm
from trace.infrastructure.storage.artifact_store import FileArtifactStore
from trace.services.analysis import AnalysisService
from unittest.mock import MagicMock

import pytest


class StubTypeScriptAnalyzer:
    """A test double implementing CodeAnalyzer for TypeScript, proving language decoupling."""

    @property
    def supported_language(self) -> str:
        return "typescript"

    def analyze(self, context: AnalysisContext) -> RepositoryAnalysis:
        loc = SourceLocation(file_path="src/index.ts", start_line=1, end_line=10)
        file = AnalyzedFile(
            path="src/index.ts",
            file_type=FileKind.OTHER,
            size_bytes=256,
            status=FileStatus.PARSED,
        )
        mod = Module(
            qualified_name="src.index",
            file_path="src/index.ts",
            is_package=False,
            docstring="TS Entrypoint",
            location=loc,
        )
        cls = Class(
            name="TypeScriptService",
            qualified_name="src.index.TypeScriptService",
            module_name="src.index",
            parent_classes=(),
            decorators=(),
            docstring="TypeScript service",
            location=loc,
        )
        fn = Function(
            name="process",
            qualified_name="src.index.TypeScriptService.process",
            module_name="src.index",
            enclosing_class="TypeScriptService",
            kind=FunctionKind.METHOD,
            parameters=(),
            return_type="Promise<void>",
            decorators=(),
            docstring=None,
            location=loc,
        )
        rel = AnalysisRelationship(
            source_type=EntityKind.CLASS,
            source_identifier="src.index.TypeScriptService",
            relationship_type=RelationshipKind.EXTENDS,
            target_type=EntityKind.CLASS,
            target_identifier="BaseService",
            evidence_location=loc,
        )

        return RepositoryAnalysis(
            run_id=context.run_id,
            repository_id=context.repository_id,
            analyzed_at=datetime.now(UTC),
            files=(file,),
            modules=(mod,),
            classes=(cls,),
            functions=(fn,),
            services=(),
            imports=(),
            calls=(),
            endpoints=(),
            configurations=(),
            database_references=(),
            tests=(),
            documentation=(),
            dependencies=(),
            relationships=(rel,),
            diagnostics=(),
            summary={
                "total_files": 1,
                "python_files": 0,
                "total_modules": 1,
                "total_classes": 1,
                "total_functions": 1,
                "total_relationships": 1,
                "total_diagnostics": 0,
            },
            resolved_revision=context.resolved_revision,
            commit_hash=context.resolved_revision,
        )


def test_code_analyzer_protocol_conformance() -> None:
    """Verify that StubTypeScriptAnalyzer conforms to CodeAnalyzer Protocol via isinstance check."""
    stub = StubTypeScriptAnalyzer()
    assert isinstance(stub, CodeAnalyzer)
    assert stub.supported_language == "typescript"


@pytest.mark.asyncio
async def test_analysis_service_with_pluggable_analyzer(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    stub_git_provider: MagicMock,
    tmp_path: Path,
) -> None:
    """Verify AnalysisService executes with any CodeAnalyzer without Python assumptions."""
    async with in_memory_db_gateway.session() as session:
        proj_id = uuid.uuid4()
        repo_id = uuid.uuid4()
        now = datetime.now(UTC)

        proj = ProjectOrm(
            id=proj_id,
            name="TS Project",
            description="TypeScript project",
            status=ProjectStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        repo = RepositoryOrm(
            id=repo_id,
            project_id=proj_id,
            type=RepositoryType.LOCAL.value,
            location=str(tmp_path),
            default_branch="main",
            status="CONNECTED",
            created_at=now,
            updated_at=now,
        )
        session.add(proj)
        session.add(repo)
        await session.commit()

    store = FileArtifactStore(tmp_path / "artifacts")
    ts_analyzer = StubTypeScriptAnalyzer()

    service = AnalysisService(
        db_gateway=in_memory_db_gateway,
        analyzer=ts_analyzer,
        artifact_store=store,
        git_provider=stub_git_provider,
    )

    # Trigger and execute
    run = await service.trigger_analysis(repository_id=repo_id)
    await service.execute_analysis_task(analysis_run_id=run.id)

    # Assert completed run
    completed_run = await service.get_analysis_run(run.id)
    assert completed_run.status == AnalysisStatus.COMPLETED
    assert completed_run.total_classes == 1
    assert completed_run.total_functions == 1

    # Assert artifact retrieval works generically
    artifact = await service.get_analysis_artifact(run.id)
    assert len(artifact.classes) == 1
    assert artifact.classes[0].name == "TypeScriptService"
    assert len(artifact.relationships) == 1


def test_zero_ast_leakage_outside_analysis_package() -> None:
    """Audit codebase to ensure no standard library `ast` is imported outside `trace.analysis`."""
    backend_src = Path(__file__).parent.parent.parent / "src" / "trace"
    assert backend_src.is_dir(), f"Expected directory {backend_src}"

    ast_importing_files: list[str] = []

    for py_file in backend_src.rglob("*.py"):
        rel_to_trace = py_file.relative_to(backend_src).as_posix()

        # Parse source and inspect imports
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except Exception:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "ast" or alias.name.startswith("ast."):
                        ast_importing_files.append(rel_to_trace)
            elif isinstance(node, ast.ImportFrom):
                if node.module == "ast" or (node.module and node.module.startswith("ast.")):
                    ast_importing_files.append(rel_to_trace)

    # Every file importing ast MUST be under analysis/
    for file_path in ast_importing_files:
        assert file_path.startswith("analysis/"), (
            f"Constitutional Violation: `ast` module imported in '{file_path}'. "
            f"`ast` must remain strictly isolated inside `trace.analysis`."
        )
