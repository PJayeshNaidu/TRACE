# Quickstart Validation Guide: TRACE Phase 2 — F02: Repository / Code Analyzer

**Feature Branch**: `003-repository-code-analyzer`  
**Date**: 2026-09-29  
**Spec Reference**: [spec.md](./spec.md)  
**Contracts Reference**: [contracts/](./contracts/)

---

## 1. Prerequisites & Environment Setup

Ensure the Python 3.12+ virtual environment is active and all required dependencies are installed:

```powershell
# Activate backend virtual environment
.\backend\.venv\Scripts\Activate.ps1

# Run database migrations to establish baseline + F01 + F02 schema
cd backend
alembic upgrade head
cd ..
```

---

## 2. Running Automated Tests

F02 includes unit tests, fixture-based static analysis tests, and integration API tests.

```powershell
# Run the complete deterministic test suite (Phase 0, F01, and F02)
pytest backend/tests -v -m "not integration"

# Run F02-specific unit and static analysis tests
pytest backend/tests/unit/test_python_code_analyzer.py -v
pytest backend/tests/unit/test_analysis_service.py -v
pytest backend/tests/unit/test_analysis_detectors.py -v

# Run F02 API contract tests
pytest backend/tests/api/test_analysis_api.py -v
```

Expected Outcome: All tests pass with zero network calls and zero external LLM invocations. Total test suite line and branch coverage exceeds 80%.

---

## 3. End-to-End Validation Scenario via REST API

### Scenario: Analyze a Real Connected Repository

#### Step 1: Start TRACE Backend API Server
```powershell
# In terminal 1:
cd backend
uvicorn trace.main:app --host 127.0.0.1 --port 8000 --reload
```

#### Step 2: Register a Repository (F01 Baseline)
```powershell
# Create project
$proj = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/v1/projects" `
    -ContentType "application/json" `
    -Body '{"name": "TRACE Testbed", "description": "F02 Analysis Validation"}'

$projId = $proj.id

# Register local repository (pointing to TRACE itself or a test fixture)
$repo = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/v1/projects/$projId/repositories" `
    -ContentType "application/json" `
    -Body '{"type": "LOCAL", "location": "tests/fixtures/sample_repo"}'

$repoId = $repo.id

# Validate connectivity
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/v1/repositories/$repoId/validate"
```

#### Step 3: Trigger F02 Static Analysis
```powershell
# Initiate analysis run (returns 202 Accepted with status PENDING)
$run = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/v1/repositories/$repoId/analyze" `
    -ContentType "application/json" `
    -Body '{"target_ref": "main"}'

$runId = $run.id
Write-Host "Triggered Run ID: $runId, Status: $($run.status)"
```

#### Step 4: Poll Status until Complete
```powershell
# Poll run status
do {
    Start-Sleep -Milliseconds 500
    $statusRes = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/api/v1/analyses/$runId"
    Write-Host "Current Status: $($statusRes.status)"
} while ($statusRes.status -in @("PENDING", "IN_PROGRESS"))

# Verify final status
$statusRes | Format-List id, status, total_files, python_files, total_classes, total_functions, total_relationships, duration_ms
```

#### Step 5: Inspect Discovered Software Intelligence
```powershell
# 1. Summary metrics
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/api/v1/analyses/$runId/summary" | ConvertTo-Json -Depth 5

# 2. Discovered API endpoints
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/api/v1/analyses/$runId/entities?kind=ENDPOINT" | ConvertTo-Json -Depth 5

# 3. Discovered structural relationships (CALLS, EXPOSES, etc.)
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/api/v1/analyses/$runId/relationships?relationship_type=CALLS" | ConvertTo-Json -Depth 5

# 4. Diagnostics & syntax warnings
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/api/v1/analyses/$runId/diagnostics" | ConvertTo-Json -Depth 5
```

---

## 4. Running the Streamlit Evaluation Interface

Launch the lightweight Streamlit evaluation dashboard to visually inspect analysis results:

```powershell
# In terminal 2:
streamlit run frontend/app.py
```

Features visible in the Streamlit UI:
1. Select Project and Repository.
2. Click **Analyze Repository** to dispatch F02 analysis.
3. Live polling indicator showing `PENDING` → `IN_PROGRESS` → `COMPLETED`.
4. Overview Cards: Total Files, Python Files, Modules, Classes, Functions, APIs, Tests, Dependencies.
5. Entity Explorer: Search and view discovered classes, methods, docstrings, and decorators.
6. Diagnostics Drawer: View any syntax errors or unresolved imports captured during repository scanning.
