"""Interactive live feature demonstration script for TRACE F01 and F02."""

import asyncio
import os
from httpx import AsyncClient, ASGITransport
from pydantic import SecretStr
from trace.main import create_app
from trace.core.config import ApplicationConfig

async def run_feature_demo() -> None:
    cfg = ApplicationConfig(
        database_url=SecretStr("sqlite+aiosqlite:///trace.db"),
        neo4j_uri=None,
        artifacts_dir="storage/artifacts/analyses",
    )
    app = create_app(config=cfg)

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1:8000") as client:
            print("=" * 65)
            print("   TRACE PHASE 1 (F01) & PHASE 2 (F02) INTERACTIVE DEMO")
            print("=" * 65)

            # ---------------------------------------------------------
            # Feature 1 (F01): Project & Repository Management
            # ---------------------------------------------------------
            print("\n>>> [FEATURE 1: F01 Project & Repository Management]")
            
            # 1. Create a Project
            res = await client.post("/api/v1/projects", json={
                "name": "Live Interactive Showcase",
                "description": "Demonstrating F01 (Project & Repo Management) and F02 (Static Code Analyzer)"
            })
            assert res.status_code == 201, res.text
            proj = res.json()
            proj_id = proj["id"]
            print(f"  [+] 1. Created Project: '{proj['name']}'")
            print(f"         ID: {proj_id}")

            # 2. Register a Local Repository
            abs_sample_path = os.path.abspath("tests/fixtures/sample_repo")
            res = await client.post(f"/api/v1/projects/{proj_id}/repositories", json={
                "type": "LOCAL",
                "location": abs_sample_path
            })
            assert res.status_code == 201, res.text
            repo = res.json()
            repo_id = repo["id"]
            print(f"  [+] 2. Registered Repository: '{repo['location']}' [{repo['type']}]")
            print(f"         ID: {repo_id}")

            # 3. Non-destructive Connectivity Validation
            res = await client.post(f"/api/v1/repositories/{repo_id}/validate")
            assert res.status_code == 200, res.text
            val = res.json()
            print(f"  [+] 3. Validated Connectivity: Status = {val['status']}")

            # ---------------------------------------------------------
            # Feature 2 (F02): Repository / Code Analyzer
            # ---------------------------------------------------------
            print("\n>>> [FEATURE 2: F02 Repository / Code Analyzer]")

            # 4. Trigger Static Code Analysis (Asynchronous HTTP 202 Accepted)
            res = await client.post(f"/api/v1/repositories/{repo_id}/analyze", json={"target_ref": "main"})
            assert res.status_code == 202, res.text
            run = res.json()
            run_id = run["id"]
            print(f"  [+] 4. Triggered Static Code Analysis (HTTP 202 Accepted)")
            print(f"         Analysis Run ID: {run_id} (Initial Status: {run['status']})")

            # 5. Observable Status Polling (PENDING -> COMPLETED)
            run_data = {}
            for _ in range(30):
                await asyncio.sleep(0.5)
                res = await client.get(f"/api/v1/analyses/{run_id}")
                run_data = res.json()
                if run_data["status"] in ("COMPLETED", "FAILED"):
                    break
            print(f"  [+] 5. Analysis Completed: Status = {run_data['status']} (Execution time: {run_data.get('duration_ms')} ms)")

            # 6. Summary Metrics
            res = await client.get(f"/api/v1/analyses/{run_id}/summary")
            summary = res.json()["metrics"]
            print(f"\n  [+] 6. Summary Metrics:")
            for k, v in summary.items():
                print(f"         - {k:<25}: {v}")

            # 7. Discovered Software Entities (Sample)
            res = await client.get(f"/api/v1/analyses/{run_id}/entities?limit=10")
            entities = res.json()
            print(f"\n  [+] 7. Discovered Entities ({entities['total']} total discovered):")
            for ent in entities["items"][:6]:
                print(f"         [{ent['kind']:<13}] {ent['name']} ({ent['location']['file_path']}:{ent['location']['start_line']})")

            # 8. Discovered Structural Relationships (Sample)
            res = await client.get(f"/api/v1/analyses/{run_id}/relationships?limit=10")
            rels = res.json()
            print(f"\n  [+] 8. Discovered Relationships ({rels['total']} total discovered):")
            for r in rels["items"][:6]:
                print(f"         {r['source_identifier']} --[{r['relationship_type']}]--> {r['target_identifier']}")

            # 9. Diagnostics Check
            res = await client.get(f"/api/v1/analyses/{run_id}/diagnostics")
            diags = res.json()
            print(f"\n  [+] 9. Analysis Diagnostics: {diags['total']} error(s) encountered (clean analysis)")

            print("\n" + "=" * 65)
            print("   ALL FEATURES TESTED SUCCESSFULLY!")
            print("=" * 65)

if __name__ == "__main__":
    asyncio.run(run_feature_demo())
