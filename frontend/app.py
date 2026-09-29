"""TRACE Static Code Analysis Evaluation Observatory (Streamlit Dashboard).

This dashboard provides an evaluation interface to trigger, observe, and inspect
TRACE Phase 2 (F02) repository code analysis runs via REST API endpoints.
Completely decoupled from backend internal domain and database models.
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

try:
    import streamlit as st
except ImportError:
    st = None  # type: ignore[assignment]


def make_api_request(
    url: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: float = 10.0,
) -> tuple[int, dict[str, Any] | None]:
    """Execute a HTTP JSON request using standard library urllib."""
    data_bytes = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status_code = resp.status
            body = resp.read().decode("utf-8")
            return status_code, json.loads(body) if body else None
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8")
        try:
            return err.code, json.loads(body) if body else None
        except Exception:
            return err.code, {"error": body}
    except Exception as exc:
        return 0, {"error": str(exc)}


def run_app() -> None:
    """Main Streamlit application flow."""
    if st is None:
        print("Streamlit is not installed in the current environment.")
        return

    st.set_page_config(
        page_title="TRACE Code Intelligence Observatory",
        page_icon="🔬",
        layout="wide",
    )

    st.title("🔬 TRACE Code Intelligence Observatory")
    st.caption("Phase 2 (F02) — Deterministic Static Code Analysis & Structural Intelligence")

    # Sidebar configuration
    st.sidebar.header("Configuration & Connectivity")
    api_url = st.sidebar.text_input(
        "TRACE API Base URL",
        value=os.environ.get("TRACE_API_URL", "http://127.0.0.1:8000/api/v1"),
    )

    health_url = api_url.rsplit("/api/v1", 1)[0] + "/health"
    status_code, health_data = make_api_request(health_url)
    if status_code == 200:
        st.sidebar.success("Backend API Connected")
    else:
        st.sidebar.warning(f"Backend API Offline ({status_code})")

    # Fetch projects
    projects_code, projects_data = make_api_request(f"{api_url}/projects")
    projects_list = projects_data.get("items", []) if projects_code == 200 and projects_data else []

    if not projects_list:
        st.info("No projects found or backend API is unreachable. Register a project first.")
        return

    project_map = {f"{p['name']} ({p['id'][:8]}...)": p["id"] for p in projects_list}
    selected_project_name = st.sidebar.selectbox("Select Project", options=list(project_map.keys()))
    selected_project_id = project_map[selected_project_name]

    # Fetch repositories for selected project
    repos_code, repos_data = make_api_request(f"{api_url}/projects/{selected_project_id}/repositories")
    repos_list = repos_data.get("items", []) if repos_code == 200 and repos_data else []

    if not repos_list:
        st.warning("No repositories registered for this project.")
        return

    repo_map = {f"{r['location']} [{r['type']}]": r["id"] for r in repos_list}
    selected_repo_name = st.sidebar.selectbox("Select Repository", options=list(repo_map.keys()))
    selected_repo_id = repo_map[selected_repo_name]

    # Analysis Control Panel
    st.subheader("Repository Analysis Control")
    col1, col2, col3 = st.columns([2, 2, 1])

    with col1:
        target_ref = st.text_input("Target Ref / Commit SHA (optional)", value="HEAD")
    with col2:
        exclude_patterns_str = st.text_input("Exclude Patterns (comma-separated)", value="tests/*, docs/*")
    with col3:
        st.write("")
        st.write("")
        trigger_btn = st.button("🚀 Analyze Repository", type="primary", use_container_width=True)

    if trigger_btn:
        patterns = [p.strip() for p in exclude_patterns_str.split(",") if p.strip()]
        trigger_payload = {"target_ref": target_ref or None, "exclude_patterns": patterns}
        trigger_code, trigger_res = make_api_request(
            f"{api_url}/repositories/{selected_repo_id}/analyze",
            method="POST",
            payload=trigger_payload,
        )

        if trigger_code == 202 and trigger_res:
            run_id = trigger_res["id"]
            st.session_state["active_run_id"] = run_id
            st.success(f"Analysis triggered! Run ID: `{run_id}`")
        else:
            st.error(f"Failed to trigger analysis: {trigger_res}")

    active_run_id = st.session_state.get("active_run_id")

    # Polling & Display Section
    if active_run_id:
        st.divider()
        st.subheader(f"Analysis Run: `{active_run_id}`")

        status_placeholder = st.empty()
        poll_count = 0
        run_status = "PENDING"
        run_record: dict[str, Any] = {}

        while poll_count < 30 and run_status in ("PENDING", "IN_PROGRESS"):
            status_code, run_res = make_api_request(f"{api_url}/analyses/{active_run_id}")
            if status_code == 200 and run_res:
                run_record = run_res
                run_status = run_record.get("status", "UNKNOWN")
                status_placeholder.info(f"Analysis Status: **{run_status}** (polling...)")
                if run_status in ("COMPLETED", "FAILED"):
                    break
            time.sleep(1.0)
            poll_count += 1

        if run_status == "COMPLETED":
            status_placeholder.success(
                f"Analysis **COMPLETED** in {run_record.get('duration_ms', 0):.1f} ms | Commit: `{run_record.get('commit_hash', 'N/A')}`"
            )

            # Summary Metrics
            sum_code, sum_data = make_api_request(f"{api_url}/analyses/{active_run_id}/summary")
            metrics = sum_data.get("metrics", {}) if sum_code == 200 and sum_data else {}

            m1, m2, m3, m4, m5, m6 = st.columns(6)
            m1.metric("Total Files", metrics.get("total_files", 0))
            m2.metric("Python Files", metrics.get("python_files", 0))
            m3.metric("Modules", metrics.get("modules", 0))
            m4.metric("Classes", metrics.get("classes", 0))
            m5.metric("Functions", metrics.get("functions", 0))
            m6.metric("Endpoints", metrics.get("endpoints", 0))

            m7, m8, m9, m10, m11, m12 = st.columns(6)
            m7.metric("Services", metrics.get("services", 0))
            m8.metric("Database Refs", metrics.get("database_models", 0))
            m9.metric("Test Targets", metrics.get("test_functions", 0))
            m10.metric("Dependencies", metrics.get("external_dependencies", 0))
            m11.metric("Relationships", metrics.get("total_relationships", 0))
            m12.metric("Diagnostics", metrics.get("diagnostics_count", 0))

            # Exploration Tabs
            tab_entities, tab_relationships, tab_diagnostics = st.tabs(
                ["🧩 Discovered Entities", "🔗 Structural Relationships", "⚠️ Diagnostics"]
            )

            with tab_entities:
                ent_code, ent_data = make_api_request(f"{api_url}/analyses/{active_run_id}/entities?limit=200")
                items = ent_data.get("items", []) if ent_code == 200 and ent_data else []
                if items:
                    st.dataframe(items, use_container_width=True)
                else:
                    st.info("No entities found.")

            with tab_relationships:
                rel_code, rel_data = make_api_request(f"{api_url}/analyses/{active_run_id}/relationships?limit=200")
                rels = rel_data.get("items", []) if rel_code == 200 and rel_data else []
                if rels:
                    st.dataframe(rels, use_container_width=True)
                else:
                    st.info("No relationships found.")

            with tab_diagnostics:
                diag_code, diag_data = make_api_request(f"{api_url}/analyses/{active_run_id}/diagnostics?limit=100")
                diags = diag_data.get("items", []) if diag_code == 200 and diag_data else []
                if diags:
                    st.dataframe(diags, use_container_width=True)
                else:
                    st.success("Clean analysis: 0 diagnostics or syntax errors encountered.")

        elif run_status == "FAILED":
            status_placeholder.error(f"Analysis FAILED: {run_record.get('error_message')}")


if __name__ == "__main__":
    run_app()
