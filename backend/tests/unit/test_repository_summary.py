"""Unit tests verifying repository analysis summary JSON generation per test.json schema."""

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from trace.analysis.analyzer import AnalysisContext, PythonCodeAnalyzer
from trace.analysis.summary import (
    build_repository_summary_payload,
    format_summary_filename,
    save_repository_summary_json,
)
from trace.api.health.router import get_db_gateway
from trace.api.repositories.router import get_git_provider
from trace.domain.project import ProjectStatus
from trace.domain.repository import RepositoryType
from trace.infrastructure.database.gateway import InMemoryDatabaseGateway
from trace.infrastructure.database.models import ProjectOrm, RepositoryOrm
from trace.infrastructure.storage.artifact_store import FileArtifactStore
from trace.main import create_app
from trace.services.analysis import AnalysisService
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def sample_repo_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "sample_repo"


@pytest.fixture
def test_json_schema() -> dict:
    # Try resolving test.json from project root
    candidates = [
        Path.cwd() / "test.json",
        Path.cwd().parent / "test.json",
        Path(__file__).resolve().parents[3] / "test.json",
    ]
    for c in candidates:
        if c.is_file():
            return json.loads(c.read_text(encoding="utf-8"))
    raise FileNotFoundError("test.json not found in candidate paths")


def test_summary_payload_strictly_matches_test_json_schema(
    sample_repo_path: Path,
    test_json_schema: dict,
):
    """Verify that build_repository_summary_payload produces exact schema matching test.json."""
    analyzer = PythonCodeAnalyzer()
    run_id = uuid.uuid4()
    repo_id = uuid.uuid4()

    context = AnalysisContext(
        run_id=run_id,
        repository_id=repo_id,
        working_tree_path=sample_repo_path,
        resolved_revision="1234567890123456789012345678901234567890",
    )
    analysis_result = analyzer.analyze(context)

    now = datetime.now(UTC)
    payload = build_repository_summary_payload(
        analysis_run_id=run_id,
        repository_id=repo_id,
        status="COMPLETED",
        started_at=now,
        completed_at=now,
        duration_ms=450.5,
        repo_name="sample_repo",
        repo_url="https://github.com/example/sample_repo.git",
        branch="main",
        commit_hash="1234567890123456789012345678901234567890",
        working_tree_path=sample_repo_path,
        artifact=analysis_result,
    )

    # 1. Top-level keys match
    assert set(payload.keys()) == set(test_json_schema.keys())

    # 2. schema_version
    assert payload["schema_version"] == "1.0.0"

    # 3. analysis_run section
    assert set(payload["analysis_run"].keys()) == set(test_json_schema["analysis_run"].keys())
    assert payload["analysis_run"]["analysis_run_id"] == str(run_id)
    assert payload["analysis_run"]["repository_id"] == str(repo_id)
    assert payload["analysis_run"]["status"] == "COMPLETED"
    assert isinstance(payload["analysis_run"]["duration_ms"], (int, float))
    assert payload["analysis_run"]["analyzer_version"] == "0.1.0"

    # 4. repository section
    assert set(payload["repository"].keys()) == set(test_json_schema["repository"].keys())
    assert payload["repository"]["name"] == "sample_repo"
    assert payload["repository"]["url"] == "https://github.com/example/sample_repo.git"
    assert payload["repository"]["default_branch"] == "main"

    # 5. version_control section
    assert set(payload["version_control"].keys()) == set(test_json_schema["version_control"].keys())
    cur_v = payload["version_control"]["current_version"]
    assert set(cur_v.keys()) == set(test_json_schema["version_control"]["current_version"].keys())
    assert cur_v["branch"] == "main"
    assert isinstance(payload["version_control"]["branches"], list)
    assert isinstance(payload["version_control"]["tags"], list)

    # 6. metrics section
    assert set(payload["metrics"].keys()) == set(test_json_schema["metrics"].keys())
    for k, v in payload["metrics"].items():
        assert isinstance(v, int), f"Metric {k} is not an integer: {v}"

    assert payload["metrics"]["total_files"] >= 5
    assert payload["metrics"]["python_files"] >= 4
    assert payload["metrics"]["classes"] >= 3
    assert payload["metrics"]["endpoints"] >= 1

    # 7. files section
    assert isinstance(payload["files"], list)
    assert len(payload["files"]) >= 5
    schema_file = test_json_schema["files"][0]
    for f in payload["files"]:
        assert set(f.keys()) == set(schema_file.keys())
        assert isinstance(f["size_bytes"], int)
        assert isinstance(f["line_count"], int)
        assert isinstance(f["is_test"], bool)
        assert isinstance(f["is_generated"], bool)

    # 8. python_files section
    assert isinstance(payload["python_files"], list)
    assert len(payload["python_files"]) > 0

    schema_file_item = test_json_schema["python_files"][0]
    for pf in payload["python_files"]:
        # Match all top-level keys in file entry
        assert set(pf.keys()) == set(schema_file_item.keys())
        assert set(pf["file"].keys()) == set(schema_file_item["file"].keys())
        assert set(pf["package"].keys()) == set(schema_file_item["package"].keys())

        # Check types
        assert isinstance(pf["file"]["size_bytes"], int)
        assert isinstance(pf["file"]["line_count"], int)
        assert isinstance(pf["file"]["hash"], str)

        # Check modules structure
        for m in pf["modules"]:
            assert set(m.keys()) == set(schema_file_item["modules"][0].keys())
            loc_keys = schema_file_item["modules"][0]["location"].keys()
            assert set(m["location"].keys()) == set(loc_keys)

        # Check classes structure
        for c in pf["classes"]:
            assert set(c.keys()) == set(schema_file_item["classes"][0].keys())
            loc_keys = schema_file_item["classes"][0]["location"].keys()
            assert set(c["location"].keys()) == set(loc_keys)
            for meth in c["methods"]:
                assert set(meth.keys()) == set(schema_file_item["classes"][0]["methods"][0].keys())

        # Check standalone functions structure
        for fn in pf["functions"]:
            assert set(fn.keys()) == set(schema_file_item["functions"][0].keys())
            loc_keys = schema_file_item["functions"][0]["location"].keys()
            assert set(fn["location"].keys()) == set(loc_keys)
            assert isinstance(fn["is_async"], bool)

        # Check methods structure
        for meth in pf["methods"]:
            assert set(meth.keys()) == set(schema_file_item["methods"][0].keys())
            loc_keys = schema_file_item["methods"][0]["location"].keys()
            assert set(meth["location"].keys()) == set(loc_keys)
            assert isinstance(meth["is_async"], bool)

        # Check endpoints structure
        for ep in pf["endpoints"]:
            assert set(ep.keys()) == set(schema_file_item["endpoints"][0].keys())
            loc_keys = schema_file_item["endpoints"][0]["location"].keys()
            assert set(ep["location"].keys()) == set(loc_keys)

        # Check database_models structure
        for db in pf["database_models"]:
            assert set(db.keys()) == set(schema_file_item["database_models"][0].keys())
            loc_keys = schema_file_item["database_models"][0]["location"].keys()
            assert set(db["location"].keys()) == set(loc_keys)

        # Check test_functions structure
        for tf in pf["test_functions"]:
            assert set(tf.keys()) == set(schema_file_item["test_functions"][0].keys())
            loc_keys = schema_file_item["test_functions"][0]["location"].keys()
            assert set(tf["location"].keys()) == set(loc_keys)

        # Check imports structure
        for imp in pf["imports"]:
            assert set(imp.keys()) == set(schema_file_item["imports"][0].keys())
            loc_keys = schema_file_item["imports"][0]["location"].keys()
            assert set(imp["location"].keys()) == set(loc_keys)
            assert "line" in imp["location"]

        # Check calls structure
        for cl in pf["calls"]:
            assert set(cl.keys()) == set(schema_file_item["calls"][0].keys())
            loc_keys = schema_file_item["calls"][0]["location"].keys()
            assert set(cl["location"].keys()) == set(loc_keys)
            assert "line" in cl["location"]

        # Check dependencies structure
        for dep in pf["dependencies"]:
            assert set(dep.keys()) == set(schema_file_item["dependencies"][0].keys())

        # Check relationships structure
        for rel in pf["relationships"]:
            assert set(rel.keys()) == set(schema_file_item["relationships"][0].keys())
            src_keys = schema_file_item["relationships"][0]["source"].keys()
            tgt_keys = schema_file_item["relationships"][0]["target"].keys()
            assert set(rel["source"].keys()) == set(src_keys)
            assert set(rel["target"].keys()) == set(tgt_keys)
            assert "line" in rel["location"]

    # 9. Top-level external_dependencies
    assert isinstance(payload["external_dependencies"], list)

    # 10. Top-level relationships
    assert isinstance(payload["relationships"], list)
    if payload["relationships"]:
        schema_rel = test_json_schema["relationships"][0]
        for rel in payload["relationships"]:
            assert set(rel.keys()) == set(schema_rel.keys())

    # 11. Top-level dependency_graph
    assert set(payload["dependency_graph"].keys()) == set(
        test_json_schema["dependency_graph"].keys()
    )
    assert isinstance(payload["dependency_graph"]["nodes"], list)
    assert isinstance(payload["dependency_graph"]["edges"], list)

    # 12. Top-level changes
    assert set(payload["changes"].keys()) == set(test_json_schema["changes"].keys())

    # 13. Top-level architecture
    assert set(payload["architecture"].keys()) == set(test_json_schema["architecture"].keys())

    # 14. Top-level configuration
    assert set(payload["configuration"].keys()) == set(test_json_schema["configuration"].keys())

    # 15. Top-level diagnostics
    assert isinstance(payload["diagnostics"], list)


def test_format_summary_filename():
    """Verify nameofrepo-branchname.json formatting and sanitization."""
    assert format_summary_filename("flask", "main") == "flask-main.json"
    assert format_summary_filename("my-repo", "feature/login") == "my-repo-feature-login.json"
    assert (
        format_summary_filename("repo_with_underscores", "refs/heads/dev")
        == "repo_with_underscores-refs-heads-dev.json"
    )
    assert format_summary_filename("flask", None) == "flask.json"
    assert format_summary_filename("flask", "") == "flask.json"


def test_save_repository_summary_json(tmp_path: Path):
    """Verify saving repository summary JSON writes valid file and run_id alias."""
    payload = {
        "schema_version": "1.0.0",
        "analysis_run": {"status": "COMPLETED"},
        "repository": {"name": "sample_repo", "default_branch": "main"},
        "version_control": {"current_version": {"branch": "main", "commit_sha": "abc"}},
        "metrics": {},
        "files": [],
        "python_files": [],
    }
    run_id = uuid.uuid4()
    saved = save_repository_summary_json(
        summary_payload=payload,
        repo_name="sample_repo",
        output_dir=tmp_path,
        run_id=run_id,
        branch_name="main",
    )
    assert saved.exists()
    assert saved.name == "sample_repo-main.json"
    assert (tmp_path / f"{run_id}.json").exists()

    content = json.loads(saved.read_text(encoding="utf-8"))
    assert content["analysis_run"]["status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_execute_analysis_task_saves_repo_analysis_file(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    sample_repo_path: Path,
    tmp_path: Path,
):
    """Verify that execute_analysis_task saves the summary JSON in repo_analysis folder."""
    # 1. Setup project & repo
    async with in_memory_db_gateway.session() as session:
        proj_id = uuid.uuid4()
        session.add(
            ProjectOrm(
                id=proj_id,
                name="Test Project",
                status=ProjectStatus.ACTIVE,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        repo_id = uuid.uuid4()
        session.add(
            RepositoryOrm(
                id=repo_id,
                project_id=proj_id,
                type=RepositoryType.LOCAL.value,
                location=str(sample_repo_path),
                status="CONNECTED",
                default_branch="main",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        await session.commit()

    repo_analysis_dir = tmp_path / "repo_analysis"
    store = FileArtifactStore(tmp_path / "artifacts")
    stub_git = AsyncMock()
    stub_git.resolve_revision.return_value = "0000000000000000000000000000000000000000"
    stub_git.timeout_seconds = 10.0

    service = AnalysisService(
        db_gateway=in_memory_db_gateway,
        analyzer=PythonCodeAnalyzer(),
        artifact_store=store,
        git_provider=stub_git,
        repo_analysis_dir=repo_analysis_dir,
    )

    run = await service.trigger_analysis(repository_id=repo_id)
    await service.execute_analysis_task(analysis_run_id=run.id)

    # Check that repo_analysis has sample_repo-main.json
    expected_file = repo_analysis_dir / f"{sample_repo_path.name}-main.json"
    assert expected_file.exists(), f"Expected file {expected_file} was not created!"

    data = json.loads(expected_file.read_text(encoding="utf-8"))
    assert data["analysis_run"]["status"] == "COMPLETED"
    assert data["repository"]["name"] == sample_repo_path.name
    assert data["metrics"]["total_files"] >= 5


@pytest.mark.asyncio
async def test_get_analysis_summary_endpoints(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    sample_repo_path: Path,
    tmp_path: Path,
):
    """Verify /analyses/{id}/summary and /analyses/{id}/summary/file endpoints."""
    # 1. Setup project & repo
    async with in_memory_db_gateway.session() as session:
        proj_id = uuid.uuid4()
        session.add(
            ProjectOrm(
                id=proj_id,
                name="Test Project",
                status=ProjectStatus.ACTIVE,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        repo_id = uuid.uuid4()
        session.add(
            RepositoryOrm(
                id=repo_id,
                project_id=proj_id,
                type=RepositoryType.LOCAL.value,
                location=str(sample_repo_path),
                status="CONNECTED",
                default_branch="main",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        await session.commit()

    repo_analysis_dir = tmp_path / "repo_analysis"
    store = FileArtifactStore(tmp_path / "artifacts")
    stub_git = AsyncMock()
    stub_git.resolve_revision.return_value = "0000000000000000000000000000000000000000"
    stub_git.timeout_seconds = 10.0

    service = AnalysisService(
        db_gateway=in_memory_db_gateway,
        analyzer=PythonCodeAnalyzer(),
        artifact_store=store,
        git_provider=stub_git,
        repo_analysis_dir=repo_analysis_dir,
    )

    run = await service.trigger_analysis(repository_id=repo_id)
    await service.execute_analysis_task(analysis_run_id=run.id)

    # Setup FastAPI app
    app = create_app()
    app.dependency_overrides[get_db_gateway] = lambda: in_memory_db_gateway
    app.dependency_overrides[get_git_provider] = lambda: stub_git
    from trace.api.analyses.router import get_analysis_service, get_artifact_store

    app.dependency_overrides[get_artifact_store] = lambda: store
    app.dependency_overrides[get_analysis_service] = lambda: service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Test JSON summary
        resp = await client.get(f"/api/v1/analyses/{run.id}/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "COMPLETED"
        assert "analysis_run" in body
        assert "repository" in body
        assert "version_control" in body
        assert "files" in body
        assert "python_files" in body
        assert body["schema_version"] == "1.0.0"
        assert len(body["python_files"]) > 0
        assert body["summary_file_path"] is not None
        assert body["summary_file_path"].endswith(f"{sample_repo_path.name}-main.json")

        # Test File download
        file_resp = await client.get(f"/api/v1/analyses/{run.id}/summary/file")
        assert file_resp.status_code == 200
        assert file_resp.headers["content-type"] == "application/json"
        content_disp = file_resp.headers.get("content-disposition", "")
        assert f"{sample_repo_path.name}-main.json" in content_disp
        downloaded = file_resp.json()
        assert downloaded["repository"]["name"] == sample_repo_path.name
