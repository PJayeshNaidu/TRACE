# TRACE Local Development Setup Guide

## 1. Prerequisites

Before setting up TRACE, ensure the following software is installed on your workstation:
- **Python**: `>= 3.12` (Python 3.12, 3.13, or 3.14)
- **uv**: Fast Python package and environment manager (`>= 0.4.0`)
- **Docker & Docker Compose**: Compose Spec v2 compatible container engine (optional for native local dev, required for full compose stack)

---

## 2. Native Development Setup (Quickstart)

### Step 1: Clone and Navigate to Backend
```bash
git clone <repo-url>
cd TRACE/backend
```

### Step 2: Install Dependencies via uv
Install production and development dependencies in an isolated virtual environment:
```bash
uv sync --extra dev
```

### Step 3: Configure Environment Variables
Copy the template configuration file:
```bash
cp .env.example .env
```
Open `.env` and fill in the required variables (specifically `DATABASE_URL`):
```ini
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/trace
APP_ENV=development
LOG_LEVEL=INFO
LLM_ENABLE_EXTERNAL_CALLS=false
LLM_ENABLE_EXTERNAL_TRANSMISSION=false
```

### Step 4: Run Database Migrations
Apply the baseline schema using Alembic:
```bash
uv run alembic upgrade head
```

### Step 5: Start the Backend Application
Start the FastAPI server with live reloading enabled:
```bash
uv run uvicorn trace.main:app --reload --host 0.0.0.0 --port 8000
```

### Step 6: Verify System Health
In a separate terminal, probe the health check endpoint:
```bash
curl -s http://localhost:8000/health
```

#### Expected Response (Healthy):
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "services": {
    "postgres": {
      "status": "reachable"
    },
    "neo4j": {
      "status": "not_configured"
    }
  }
}
```
*(Note: Neo4j reports `"not_configured"` when `NEO4J_URI` is omitted; this is normal and does not degrade health in Phase 0).*

---

## 3. Docker Compose Development Stack

To run the complete local environment (FastAPI backend + PostgreSQL 16 + Neo4j 5) in containers:

### Step 1: Start Stack in Dependency Order
From the repository root:
```bash
docker compose up --build
```
Docker Compose starts PostgreSQL and Neo4j first, waits for their native container healthchecks to pass (`condition: service_healthy`), and only then starts the backend service.

#### Expected Console Health Progression:
```text
[+] Running 3/3
 ✔ Container trace-postgres  Healthy
 ✔ Container trace-neo4j     Healthy
 ✔ Container trace-backend   Started
```

### Step 2: Verify Health via Container Network
```bash
curl -s http://localhost:8000/health
```

#### Expected Output with All Services Running:
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "services": {
    "postgres": {
      "status": "reachable"
    },
    "neo4j": {
      "status": "reachable"
    }
  }
}
```

### Step 3: Tear Down Environment
```bash
docker compose down -v
```
