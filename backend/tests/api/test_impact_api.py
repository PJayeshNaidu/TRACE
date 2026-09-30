"""API integration tests for F05 Impact Analysis and Risk Evaluation endpoints."""

import subprocess
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from trace.api.analyses.router import get_artifact_store, get_code_analyzer
from trace.api.health.router import get_db_gateway
from trace.api.impact.router import get_impact_service
from trace.api.repositories.router import get_git_provider
from trace.domain.project import ProjectStatus
from trace.domain.repository import RepositoryStatus, RepositoryType
from trace.infrastructure.database.gateway import InMemoryDatabaseGateway
from trace.infrastructure.database.models import ProjectOrm, RepositoryOrm
from trace.infrastructure.git.adapters.subprocess import SubprocessGitProvider
from trace.infrastructure.storage.artifact_store import FileArtifactStore
from trace.main import create_app
from trace.services.impact import ImpactAnalysisService


@pytest.fixture
def sample_git_repo(tmp_path: Path) -> Path:
    """Create a temporary real git repo with two commits on main."""
    repo_dir = tmp_path / "impact_test_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo_dir)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo_dir), "config", "user.name", "Impact Tester"], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "config", "user.email", "impact@trace.io"], check=True)

    # Initial commit: tax.py and checkout.py
    tax_file = repo_dir / "tax.py"
    tax_file.write_text("def calculate_tax(amount: float) -> float:\n    return amount * 0.1\n")

    checkout_file = repo_dir / "checkout.py"
    checkout_file.write_text("from tax import calculate_tax\n\ndef checkout(subtotal: float) -> float:\n    return subtotal + calculate_tax(subtotal)\n")

    subprocess.run(["git", "-C", str(repo_dir), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "commit", "-m", "feat: initial tax and checkout"], check=True)

    # Second commit: modify calculate_tax signature
    tax_file.write_text("def calculate_tax(amount: float, rate: float = 0.08) -> float:\n    return amount * rate\n")
    subprocess.run(["git", "-C", str(repo_dir), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "commit", "-m", "refactor: add rate param to calculate_tax"], check=True)

    return repo_dir


@pytest.fixture
async def setup_impact_repo(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    sample_git_repo: Path,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Insert active project and connected repo into test database."""
    async with in_memory_db_gateway.session() as session:
        proj_id = uuid.uuid4()
        repo_id = uuid.uuid4()
        now = datetime.now(UTC)

        proj = ProjectOrm(
            id=proj_id,
            name="Impact Test Project",
            status=ProjectStatus.ACTIVE.value,
            created_at=now,
            updated_at=now,
        )
        session.add(proj)

        repo = RepositoryOrm(
            id=repo_id,
            project_id=proj_id,
            location=str(sample_git_repo),
            type=RepositoryType.LOCAL.value,
            status=RepositoryStatus.CONNECTED.value,
            default_branch="main",
            created_at=now,
            updated_at=now,
        )
        session.add(repo)
        await session.commit()

        return proj_id, repo_id


@pytest.mark.asyncio
async def test_evaluate_impact_endpoint(
    in_memory_db_gateway: InMemoryDatabaseGateway,
    setup_impact_repo: tuple[uuid.UUID, uuid.UUID],
    sample_git_repo: Path,
    tmp_path: Path,
):
    """Verify POST /api/v1/impact/evaluate returns the complete 4-key JSON payload."""
    _, repo_id = setup_impact_repo
    app = create_app()

    artifact_store = FileArtifactStore(base_path=str(tmp_path / "artifacts"))
    git_provider = SubprocessGitProvider()

    app.dependency_overrides[get_db_gateway] = lambda: in_memory_db_gateway
    app.dependency_overrides[get_git_provider] = lambda: git_provider
    app.dependency_overrides[get_artifact_store] = lambda: artifact_store

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "repository_id": str(repo_id),
            "base_ref": "HEAD~1",
            "target_ref": "HEAD",
            "llm_config": {"enabled": False},
        }
        resp = await client.post("/api/v1/impact/evaluate", json=payload)
        assert resp.status_code == 201

        data = resp.json()
        assert "analysis_metadata" in data
        assert "impact_analysis" in data
        assert "dependency_graph" in data
        assert "risk_analysis" in data

        meta = data["analysis_metadata"]
        assert meta["total_changed_entities"] >= 1
        assert meta["reasoning_mode"] == "HEURISTIC"

        impact = data["impact_analysis"]
        assert len(impact["detailed_impacts"]) >= 1
        entity_impact = impact["detailed_impacts"][0]
        assert "calculate_tax" in entity_impact["entity"]
        assert "diff_snippet" in entity_impact
        assert "remediation_guidance" in entity_impact

        # Verify risk analysis and remediation plan
        risk = data["risk_analysis"]
        assert "risk_level" in risk
        assert len(risk["actionable_remediation_plan"]) >= 1

        # Test GET /api/v1/impact/{id}
        analysis_id = meta["analysis_id"]
        get_resp = await client.get(f"/api/v1/impact/{analysis_id}")
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert get_data["analysis_metadata"]["analysis_id"] == analysis_id
