# Quickstart & Validation Guide: TRACE Phase 6 — F07: Upgrade Planner

**Feature**: [spec.md](spec.md) | [plan.md](plan.md) | [contracts/api.md](contracts/api.md)  
**Date**: 2026-10-01  

---

## 1. Prerequisites

Before validating F07, verify that the TRACE infrastructure is active:
```bash
# 1. Check container health
docker compose ps

# Expected output:
# trace-postgres  healthy
# trace-neo4j     healthy
# trace-backend   healthy
# trace-frontend  running
```

Verify backend health:
```bash
curl -s http://127.0.0.1:8000/health
# {"status":"ok","database":"connected","graph":"connected"}
```

---

## 2. End-to-End Validation Walkthrough

### Scenario A: Generating an Upgrade Plan from Impact Data

1. **Evaluate Impact & Risk (F05/F06)**:
   Ensure an impact analysis run exists for your repository. If you have an existing `impact_analysis_id`, you can reuse it. Otherwise, evaluate impact via API:
   ```bash
   curl -X POST http://127.0.0.1:8000/api/v1/impact/evaluate \
     -H "Content-Type: application/json" \
     -d '{
       "repository_id": "<REPO_ID>",
       "base_ref": "HEAD~1",
       "target_ref": "HEAD"
     }'
   ```
   Save the returned `analysis_metadata.analysis_id`.

2. **Generate the Upgrade Plan (F07)**:
   ```bash
   curl -X POST http://127.0.0.1:8000/api/v1/upgrade-plans/generate \
     -H "Content-Type: application/json" \
     -d '{
       "repository_id": "<REPO_ID>",
       "impact_analysis_id": "<ANALYSIS_ID>",
       "title": "Payment Migration Upgrade Plan"
     }'
   ```

   **Expected Result**:
   - HTTP status `201 Created`.
   - Returns full `UpgradePlanResponse` containing `tasks` strictly ordered by topological step numbers (`step_number: 1, 2, 3...`).
   - Every task has populated `component`, `reason`, `dependencies`, `expected_changes`, `required_tests`, `risk_level`, `status: "PENDING"`, and `evidence`.

---

### Scenario B: Inspecting Task Dependencies and Ordering

Retrieve the plan and verify topological sequencing:
```bash
curl -s http://127.0.0.1:8000/api/v1/upgrade-plans/<PLAN_ID> | jq '.tasks[] | {step: .step_number, category: .category, component: .component, deps: .dependencies}'
```

**Verification Checklist**:
- [ ] Tier 1 (`CONTRACT_API`) tasks appear before Tier 2 (`CORE_LOGIC`) tasks.
- [ ] Core services appear before downstream consumers (`CONSUMER_HANDLER`).
- [ ] Code modifications appear before test suites (`INTEGRATION_TEST`) and documentation (`DOCUMENTATION_CONFIG`).
- [ ] Any component $B$ that calls modified $A$ lists $A$ in its `.dependencies` array and has `step_number(B) > step_number(A)`.

---

### Scenario C: Interactive Task Status Transitions

1. **Mark First Task as In-Progress**:
   ```bash
   curl -X PATCH http://127.0.0.1:8000/api/v1/upgrade-plans/<PLAN_ID>/tasks/<TASK_1_ID> \
     -H "Content-Type: application/json" \
     -d '{"status": "IN_PROGRESS", "notes": "Auditing API route parameters"}'
   ```

2. **Complete the Task**:
   ```bash
   curl -X PATCH http://127.0.0.1:8000/api/v1/upgrade-plans/<PLAN_ID>/tasks/<TASK_1_ID> \
     -H "Content-Type: application/json" \
     -d '{"status": "COMPLETED", "notes": "Signature updated, parameters verified"}'
   ```

3. **Check Updated Progress Metrics**:
   ```bash
   curl -s http://127.0.0.1:8000/api/v1/upgrade-plans/<PLAN_ID> | jq '.summary_metrics'
   ```

   **Expected Output**:
   ```json
   {
     "total_tasks": 5,
     "completed_tasks": 1,
     "in_progress_tasks": 0,
     "pending_tasks": 4,
     "progress_percentage": 20.0
   }
   ```

---

### Scenario D: Streamlit Observatory UI Validation

1. Open your browser at `http://localhost:8501`.
2. Select your registered project and repository in the sidebar.
3. Navigate to the top-level tab: `"📋 Upgrade Planner (F07)"`.
4. Verify the following UI components:
   - **Progress Header**: Visual progress bar displaying `% Completed`, task counts, and risk badge.
   - **Filter Controls**: Filter by Status (`ALL`, `PENDING`, `COMPLETED`), Risk Level, or Category.
   - **Task Cards**: Each card displays Step Number, Category Tag, Component, Status Selectbox, and expandable details for Reason, Expected Changes, Required Tests, and Diff Evidence.
   - **Interactive Status Toggle**: Change a task from `PENDING` to `COMPLETED`; verify the card updates immediately and the progress bar reflects the new percentage without full page reload.

---

### Scenario E: Edge-Case Handling

1. **Circular Dependency Test**:
   - In a codebase with circular calls, verify the planner tags participating tasks with `is_circular: true`, emits a co-dependent batch warning, and terminates within $< 1.5\text{s}$ without crashing.
2. **Zero-Impact Test**:
   - Run plan generation against a commit range touching only whitespace or comments.
   - Verify the planner returns `total_tasks: 0`, `status: "COMPLETED"`, and `progress_percentage: 100.0`.
3. **Offline Fallback Test**:
   - Ensure `OPENROUTER_API_KEY` is empty or omit `llm_config`.
   - Run plan generation.
   - Verify the entire plan DAG, topological sequence, syntax delta instructions, and test references are generated with 100% fidelity using the offline heuristic engine.
