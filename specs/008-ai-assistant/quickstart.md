# Quickstart & Validation Guide: Feature 008 — AI Assistant (TRACE F10)

**Feature Branch**: `008-ai-assistant` | **Date**: 2026-10-05 | **Spec Reference**: [spec.md](spec.md)

This guide provides step-by-step instructions for validating the **TRACE F10 AI Assistant** locally across automated test suites, backend REST APIs, and the Streamlit Observatory web interface.

---

## Prerequisites

1. **Active Python Environment** (Python 3.12+):
   ```powershell
   python --version
   ```
2. **Backend & Frontend Dependencies Installed**:
   ```powershell
   python -m pip install -e backend/
   python -m pip install streamlit pandas
   ```
3. **Environment Configuration (`.env`)**:
   ```env
   OPENROUTER_API_KEY=your_key_here  # Optional: omit for deterministic offline fallback mode
   LLM_DEFAULT_MODEL=mistralai/mistral-7b-instruct:free
   ```

---

## 1. Automated Test Suite Execution

Run unit and integration tests covering data contracts, retrieval logic, prompt synthesis, API routing, and deterministic fallback:

```powershell
pytest backend/tests/unit/test_assistant_retrieval.py backend/tests/unit/test_assistant_synthesis.py backend/tests/api/test_assistant_api.py -v
```

### Expected Test Results
- `test_extract_target_symbols`: Pass (correctly matches candidate AST symbols in query text).
- `test_cypher_subgraph_retrieval`: Pass (extracts 1-hop and 2-hop callers without hallucinated edges).
- `test_compact_evidence_token_budget`: Pass (pruned JSON stays strictly $< 1,500$ tokens).
- `test_deterministic_fallback_synthesis`: Pass (produces markdown evidence tables when LLM key is absent).
- `test_assistant_ask_api_endpoint`: Pass (returns HTTP 200 with typed `EvidenceSource` items).

---

## 2. Running the Backend & API Validation

Start the TRACE FastAPI backend server:

```powershell
python -m uvicorn trace.main:create_app --factory --host 0.0.0.0 --port 8000 --reload
```

### 2.1 Test Dependency Q&A (`POST /api/v1/assistant/ask`)
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/assistant/ask" -Method Post -ContentType "application/json" -Body (@{
    project_id = "YOUR_PROJECT_UUID"
    question = "Why is checkout_service affected by this change?"
} | ConvertTo-Json)
```

### 2.2 Test Risk Justification Q&A
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/assistant/ask" -Method Post -ContentType "application/json" -Body (@{
    project_id = "YOUR_PROJECT_UUID"
    question = "Why is component payment_processor classified as High Risk?"
} | ConvertTo-Json)
```

### 2.3 Test Plan Sequence Q&A
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/assistant/ask" -Method Post -ContentType "application/json" -Body (@{
    project_id = "YOUR_PROJECT_UUID"
    question = "Why does task 1 come before task 4 in the upgrade plan?"
} | ConvertTo-Json)
```

---

## 3. Streamlit Observatory Web UI Validation

Launch the Streamlit Observatory interface:

```powershell
python -m streamlit run frontend/app.py
```

### Visual & Interactive Checklist
1. **Neo-Brutalist Drawer / Tab**:
   - Open the **"🤖 AI Assistant (F10)"** tab in the Observatory dashboard.
   - Verify Neo-Brutalist styling: sharp 90° corners, 2px solid `#000000` borders, hard offset shadows.
2. **Intent Quick-Prompts**:
   - Click on one of the suggested query chips (e.g. *"Explain Blast Radius"*, *"Why High Risk?"*).
   - Verify the query runs immediately and displays the answer in a high-contrast response card.
3. **Inspectable Source Badges**:
   - Verify that every returned answer contains clickable source badges (`[GRAPH]`, `[RISK]`, `[PLAN]`, `[DIFF]`).
   - Click a badge to expand the structured evidence metadata.
4. **Canvas Isolation Guarantee**:
   - Navigate to the **"Dependency Graph"** tab and **"Version Analyzer"** tab.
   - Confirm that force-directed canvas dragging, node hovering, and physics simulations are 100% functional with zero regressions.
