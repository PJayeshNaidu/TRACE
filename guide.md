# TRACE User & Developer Guide

Welcome to **TRACE** (Transformation Risk Analysis & Change Evaluation).

This guide walks you through setting up and using the complete TRACE stack: **Project & Repository Management (F01)**, **Deterministic AST Code Analysis (F02)**, and the **Neo4j Projected Dependency Graph (F03)** with our interactive Streamlit Observatory.

---

## 🚀 Quick Start with Docker Compose (Recommended)

The easiest way to start the entire TRACE platform (PostgreSQL, Neo4j, FastAPI Backend, and Streamlit Frontend) is with Docker Compose.

### 1. Ensure `.env` Exists
Make sure a `.env` file exists at the root of `TRACE`:
```powershell
Copy-Item .env.example .env
```

### 2. Start All Services
```powershell
docker compose up -d
```

This starts:
| Service | URL / Port | Description |
|---|---|---|
| **Streamlit Observatory** | [http://localhost:8501](http://localhost:8501) | Full interactive web UI (Analysis & Visual Graph) |
| **FastAPI Swagger Docs** | [http://localhost:8000/docs](http://localhost:8000/docs) | Interactive REST API documentation |
| **Neo4j Browser** | [http://localhost:7474](http://localhost:7474) | Graph visualizer (User: `neo4j` / Password: `password`) |
| **PostgreSQL** | `localhost:5432` | Relational database (`postgres`/`postgres`) |

---

## 🛠️ Alternative: Running Locally without Docker

If you prefer running services directly on Windows with Python `uv`:

### 1. Start PostgreSQL & Neo4j
```powershell
docker compose up -d postgres neo4j
```

### 2. Apply Database Migrations (PostgreSQL)
```powershell
cd c:\TRACE\backend
$env:DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/trace"
uv run alembic upgrade head
```

### 3. Start Backend API
```powershell
uv run uvicorn trace.main:app --host 127.0.0.1 --port 8000
```

### 4. Start Streamlit Frontend
```powershell
cd c:\TRACE
uv run --with streamlit streamlit run frontend/app.py
```

---

## 🔬 Complete End-to-End Workflow

### Step 1: Create a Project
Open the Streamlit UI at [http://localhost:8501](http://localhost:8501) (or use Swagger `/docs`):
- In the sidebar, expand **➕ Create New Project**.
- Enter **Project Name** (e.g. `TRACE-Core` or `HTTPX-Project`).
- Click **Create Project**.

---

### Step 2: Register a Repository

You can analyze either **Remote Public/Private Git Repositories** or **Local Directory Paths**:

#### Option A: Remote Git Repository (.git URL) — *Auto-Cloned*
- Under **➕ Register Repository**, select **`🌐 Remote Git Repo`**.
- Enter any cloneable URL:
  - `https://github.com/encode/httpx.git`
  - `https://github.com/psf/requests.git`
  - `https://github.com/pallets/flask.git`
- Branch: `HEAD` (or `main` / `master`).
- Click **Register Repository**.

#### Option B: Local Directory Path
- Select **`📁 Local Path`**.
- Enter `/workspace` (if using Docker) or `C:\TRACE` (if running locally on host).
- Click **Register Repository**.

---

### Step 3: Trigger Static Code Analysis & Graph Build

1. Select your registered repository from the dropdown.
2. Enter optional exclude patterns (e.g. `tests/*, docs/*`).
3. Click **🚀 Analyze Repository**.

**What happens behind the scenes:**
1. **F01**: Validates connectivity and resolves the Git commit SHA.
2. **F02**: Clones the repo (if remote) and deterministically parses all Python files via AST, extracting:
   - Modules, Classes, Functions/Methods, API Endpoints, Database Models, Services, Test Targets, and External Dependencies.
   - Discovers structural relationships (`IMPORTS`, `CALLS`, `EXTENDS`, `EXPOSES`, etc.).
3. **F03**: Automatically constructs the **Neo4j Projected Dependency Graph** linking the complete architectural hierarchy (`DEFINES`, `CALLS`, `IMPORTS`, `EXPOSES`).

---

## 🌐 Exploring the Dependency Graph

### 1. In-App Modern Force-Directed Canvas (Streamlit)
Navigate to the **`🌐 Dependency Graph (Neo4j)`** tab in Streamlit:
- **🌌 Obsidian Neon UI**: Glowing node particle network with Google Fonts (**Inter** & **JetBrains Mono**).
- **🔍 Symbol Search**: Type any function or class (e.g. `AnalysisService`) to auto-zoom and focus on it.
- **🏷️ Filter Pills**: Click category pills (🟣 Modules, 🔵 Classes, 🟢 Functions, 🟠 Endpoints, 🔴 Database, 🟡 Packages) to filter and isolate specific component types.
- **📱 HUD Inspector**: Click on any node circle to open the slide-in drawer showing exact file location, line number, and connection counts.
- **🎮 Navigation Controls**: Zoom in/out, fit to screen, or toggle physics simulation.

---

### 2. Advanced Cypher Queries in Neo4j Browser
Open [http://localhost:7474](http://localhost:7474) (Login: `neo4j` / `password`):

#### View Full Connected Codebase:
```cypher
MATCH (source)-[rel]->(target)
RETURN source, rel, target
LIMIT 100
```

#### View Module & Class Architecture:
```cypher
MATCH (m:Module)-[r:DEFINES|IMPORTS]->(child)
RETURN m, r, child
LIMIT 50
```

#### Trace Function Call Hierarchy:
```cypher
MATCH (caller:Function)-[r:CALLS]->(callee:Function)
RETURN caller, r, callee
LIMIT 50
```

#### Blast Radius / Impact Analysis (Who depends on X?):
```cypher
MATCH path = (upstream)-[:CALLS|DEPENDS_ON*1..3]->(target {name: "get_analysis_service"})
RETURN path
```

---

## 📡 REST API Reference Summary

Interactive Swagger UI available at `http://localhost:8000/docs`:

| Area | Method | Endpoint | Description |
|---|---|---|---|
| **Health** | `GET` | `/health` | Postgres & Neo4j connectivity check |
| **Projects** | `POST` | `/api/v1/projects` | Create a new project |
| | `GET` | `/api/v1/projects` | List all projects |
| **Repositories**| `POST` | `/api/v1/projects/{p_id}/repositories` | Register local or remote git repo |
| | `POST` | `/api/v1/repositories/{r_id}/validate` | Probe repository connection |
| **Analysis** | `POST` | `/api/v1/repositories/{r_id}/analyze` | Trigger asynchronous AST analysis |
| | `GET` | `/api/v1/analyses/{run_id}` | Check analysis run status |
| | `GET` | `/api/v1/analyses/{run_id}/summary` | Get summary metrics & file counts |
| | `GET` | `/api/v1/analyses/{run_id}/entities` | List discovered code symbols |
| | `GET` | `/api/v1/analyses/{run_id}/relationships`| List discovered structural links |
| **Graph (F03)** | `POST` | `/api/v1/analyses/{run_id}/graph/build` | Trigger/rebuild Neo4j graph |
| | `GET` | `/api/v1/analyses/{run_id}/graph/nodes` | List projected graph nodes |
| | `GET` | `/api/v1/analyses/{run_id}/graph/relationships`| List graph edges |
| | `GET` | `/api/v1/analyses/{run_id}/graph/dependents/{node_id}` | Find upstream dependents (impact) |
| | `GET` | `/api/v1/analyses/{run_id}/graph/dependencies/{node_id}` | Find downstream dependencies |

---

## 🧪 Running Unit & Integration Tests

```powershell
cd c:\TRACE\backend
uv run --extra dev pytest -v
```
Runs the complete test suite including graph projection, AST extraction, and service unit tests.
