# TRACE Repository Management and Code-Analysis Guide

This guide shows how to test TRACE with a real Git repository on Windows. It covers the complete workflow: preparing the database, starting the API, cloning a public repository locally, registering it, validating Git access, starting an analysis, and reviewing the results.

The examples use the public [HTTPX](https://github.com/encode/httpx) repository. TRACE's current analyzer works with a **local Git working directory**. A remote Git URL can be registered and validated, but it is not cloned automatically for code analysis.

## What You Need

- Windows PowerShell
- Python environment already installed for this project (`backend/.venv`)
- Git installed and available from PowerShell (`git --version`)
- PostgreSQL running with the connection configured in `backend/.env`

The backend folder contains the API. Repositories to analyze should be kept outside it, in the top-level `test-repos` folder. This keeps test inputs separate from TRACE source code.

```text
TRACE/
|-- backend/                 # TRACE API and database migrations
|-- frontend/                # Optional Streamlit analysis viewer
|-- test-repos/
|   `-- httpx/               # Repository being analyzed
`-- guide.md
```

## 1. Open the Backend Environment

Open PowerShell and change to the backend directory:

```powershell
cd "C:\Course Work\Course Tasks\TRACE\backend"
.\.venv\Scripts\Activate.ps1
```

The prompt should begin with `(trace)`.

> If PowerShell blocks script execution, run `Set-ExecutionPolicy -Scope Process Bypass` in that PowerShell session, then activate the environment again.

## 2. Apply Database Migrations

TRACE stores projects, repositories, and analysis runs in PostgreSQL. Before using the API, create or update the tables with Alembic migrations.

The application loads `DATABASE_URL` from `backend/.env`, but Alembic needs that value available in the active PowerShell session. For the default local configuration, run:

```powershell
$env:DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/trace"
alembic upgrade head
```

If your `backend/.env` uses a different PostgreSQL connection string, use that value in the first command instead.

Successful output should include:

```text
Context impl PostgresqlImpl.
Running upgrade ...
```

Do not rely on output containing `Context impl SQLiteImpl.` for this workflow: that means Alembic used its SQLite fallback and did **not** migrate the PostgreSQL database that the API uses. The SQLite file is harmless, but it will not create the tables needed by the running API.

## 3. Start the TRACE API

From the activated backend environment, start the server:

```powershell
uvicorn trace.main:app --host 127.0.0.1 --port 8000
```

Keep this terminal open. The API documentation is available at:

```text
http://127.0.0.1:8000/docs
```

`http://127.0.0.1:8000/` returning `404 Not Found` is normal; TRACE does not define a homepage route.

### Important Windows note

Use the command above **without** `--reload` when testing local repositories. On Windows, Uvicorn reload mode can use an event loop that cannot start the Git subprocess TRACE uses for repository validation. The symptom is a validation response with `is_connected: false` and a blank `Git local probe failed:` error.

## 4. Clone a Repository to Analyze

Leave the API running and open a second PowerShell terminal. Clone test repositories under the project-root `test-repos` directory:

```powershell
cd "C:\Course Work\Course Tasks\TRACE"
New-Item -ItemType Directory -Force .\test-repos
git clone --depth 1 https://github.com/encode/httpx.git .\test-repos\httpx
```

This creates the local Git repository at:

```text
C:\Course Work\Course Tasks\TRACE\test-repos\httpx
```

Confirm it is a usable Git working tree:

```powershell
git -C .\test-repos\httpx rev-parse --is-inside-work-tree
git -C .\test-repos\httpx branch --show-current
```

Expected output is `true` and the checked-out branch name (HTTPX currently uses `master`).

## 5. Create a TRACE Project

Open `http://127.0.0.1:8000/docs` in a browser.

1. Find **POST `/api/v1/projects`**.
2. Select **Try it out**.
3. Enter the request body:

   ```json
   {
     "name": "HTTPX Analysis Test",
     "description": "Testing TRACE repository management and static code analysis"
   }
   ```

4. Select **Execute**.

The response should be `201 Created`. Copy the returned `id`; it is the `project_id` used in the next step.

If you get an error saying `relation "projects" does not exist`, repeat [Step 2](#2-apply-database-migrations) and confirm it reports `PostgresqlImpl`.

## 6. Register the Local Repository

1. In `/docs`, find **POST `/api/v1/projects/{project_id}/repositories`**.
2. Select **Try it out**.
3. Paste your project UUID into the `project_id` field.
4. Enter this request body:

   ```json
   {
     "type": "LOCAL",
     "location": "C:\\Course Work\\Course Tasks\\TRACE\\test-repos\\httpx"
   }
   ```

5. Select **Execute**.

A `201 Created` response means registration worked. Copy the returned repository `id`; it is the `repository_id` for all following calls.

## 7. Validate Repository Access

1. Find **POST `/api/v1/repositories/{repository_id}/validate`**.
2. Paste the repository UUID into the path field.
3. Select **Execute**.

A successful response contains values like:

```json
{
  "repository_id": "...",
  "is_connected": true,
  "status": "CONNECTED",
  "detected_branch": "master"
}
```

If validation fails:

- Check that the path exactly matches the cloned folder.
- Confirm `test-repos/httpx/.git` exists.
- Run the API without `--reload`, as described in [Step 3](#3-start-the-trace-api).
- Confirm `git --version` works in PowerShell.

## 8. Trigger Repository Code Analysis

1. Find **POST `/api/v1/repositories/{repository_id}/analyze`**.
2. Paste the repository UUID.
3. Use this request body:

   ```json
   {
     "target_ref": "master",
     "exclude_patterns": [
       "docs/*",
       ".github/*"
     ]
   }
   ```

4. Select **Execute**.

TRACE responds with `202 Accepted` and an analysis run object. Copy its `id`; this is the `analysis_run_id`.

The analysis runs in the background. Its status progresses through `PENDING`, `IN_PROGRESS`, and then either `COMPLETED` or `FAILED`.

## 9. Check Analysis Status and Results

Replace `ANALYSIS_RUN_ID` in the following URLs with the UUID returned by the analyze request. Do not type the literal text `ANALYSIS_RUN_ID`; the API expects a UUID.

| Purpose | URL |
| --- | --- |
| Check status | `http://127.0.0.1:8000/api/v1/analyses/ANALYSIS_RUN_ID` |
| Summary metrics | `http://127.0.0.1:8000/api/v1/analyses/ANALYSIS_RUN_ID/summary` |
| Entities | `http://127.0.0.1:8000/api/v1/analyses/ANALYSIS_RUN_ID/entities?limit=200` |
| Relationships | `http://127.0.0.1:8000/api/v1/analyses/ANALYSIS_RUN_ID/relationships?limit=200` |
| Diagnostics | `http://127.0.0.1:8000/api/v1/analyses/ANALYSIS_RUN_ID/diagnostics?limit=100` |

You can paste those completed URLs into a browser, or use their corresponding `GET` endpoints in `/docs`.

After status reaches `COMPLETED`, inspect:

- **Summary**: totals for files, Python files, modules, classes, functions, relationships, and diagnostics.
- **Entities**: discovered code elements such as modules, classes, functions, dependencies, and tests.
- **Relationships**: structural links such as imports, calls, inheritance, and dependencies.
- **Diagnostics**: parser errors or warnings collected during scanning.

## 10. Test Repository Management Features

The same `/docs` interface lets you test repository-management behavior:

- **GET `/api/v1/projects`**: list projects.
- **GET `/api/v1/projects/{project_id}`**: view project details and repository count.
- **GET `/api/v1/projects/{project_id}/repositories`**: list repositories belonging to a project.
- **GET `/api/v1/repositories/{repository_id}`**: inspect repository status and metadata.
- **POST `/api/v1/projects/{project_id}/archive`**: archive an active project.
- **POST `/api/v1/projects/{project_id}/activate`**: reactivate an archived project.
- **DELETE `/api/v1/repositories/{repository_id}`**: delete an unanalysed repository.

Once a repository has an analysis run, deletion is intentionally rejected to preserve analysis history. That response is an expected behavior to test.

## Optional: Use the Streamlit Analysis Viewer

The Streamlit application displays analysis results, but it does not create projects or register repositories. Complete Steps 5 and 6 in `/docs` first.

From the project root, start it in another terminal:

```powershell
cd "C:\Course Work\Course Tasks\TRACE"
streamlit run frontend/app.py
```

Open the URL printed by Streamlit. Select the created project and registered repository, trigger an analysis, then inspect the metrics, entities, relationships, and diagnostics in the interface.

## Quick Success Checklist

- [ ] PostgreSQL migrations report `PostgresqlImpl`.
- [ ] API is running at `http://127.0.0.1:8000/docs` without `--reload`.
- [ ] The Git repository is cloned below `TRACE/test-repos`.
- [ ] Project creation returns `201 Created`.
- [ ] Repository registration returns `201 Created`.
- [ ] Repository validation returns `is_connected: true` and `status: CONNECTED`.
- [ ] Analysis returns `202 Accepted`.
- [ ] The analysis run reaches `COMPLETED`.
- [ ] Summary, entities, relationships, and diagnostics endpoints return results.
