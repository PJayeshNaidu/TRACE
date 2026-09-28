# TRACE Environment Variables Reference

This document documents all configuration variables supported by TRACE. It is maintained in strict bidirectional synchronization with `.env.example` (FR-046).

---

## Configuration Variables Matrix

| Variable Name | Type | Required? | Default Value | Description |
|---|---|---|---|---|
| `DATABASE_URL` | String (Secret) | **Yes** | *None* | Asynchronous PostgreSQL connection URL with asyncpg scheme (`postgresql+asyncpg://...`). |
| `NEO4J_URI` | String | No | *None* | Neo4j Bolt/Neo4j protocol connection URI (`bolt://...` or `neo4j://...`). |
| `NEO4J_USERNAME` | String | No | `neo4j` | Username for Neo4j graph database authentication. |
| `NEO4J_PASSWORD` | String (Secret) | No | *None* | Password for Neo4j graph database authentication. |
| `OPENROUTER_API_KEY` | String (Secret) | No* | *None* | API key for OpenRouter LLM gateway. (*Required if `LLM_ENABLE_EXTERNAL_CALLS=true`). |
| `OPENROUTER_BASE_URL` | String | No | *None* | Optional override URL for OpenRouter API (defaults to `https://openrouter.ai/api/v1`). |
| `LLM_DEFAULT_MODEL` | String | No | `mistralai/mistral-7b-instruct:free` | Default free-tier LLM model identifier. Safe fallback when unset. |
| `LLM_REASONING_MODEL` | String | No | *None* | Optional model identifier for heavy reasoning tasks. |
| `LLM_FAST_MODEL` | String | No | *None* | Optional model identifier for low-latency tasks. |
| `LLM_FALLBACK_MODELS` | List[String] | No | `[]` | Comma-separated list of fallback model IDs to attempt sequentially. |
| `LLM_ENABLE_EXTERNAL_CALLS` | Boolean | No | `false` | Master switch enabling outbound API calls to LLM provider. |
| `LLM_ENABLE_EXTERNAL_TRANSMISSION` | Boolean | No | `false` | Security gate permitting outbound transmission of source code to external LLMs. |
| `VECTOR_STORE_URL` | String | No | *None* | Reserved for future vector database connection string (Phase 3A+). |
| `APP_ENV` | String | No | `development` | Operating environment (`development`, `test`, `production`). Controls JSON vs Console logging. |
| `LOG_LEVEL` | String | No | `INFO` | Standard log severity filter (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`). |

---

## Container Development Variables (Dev-Only)

These variables are consumed by Docker Compose and container initialization scripts, not by `ApplicationConfig` directly:

| Variable Name | Type | Purpose |
|---|---|---|
| `POSTGRES_USER` | String | Database superuser for local Docker PostgreSQL container initialization. |
| `POSTGRES_PASSWORD` | String | Superuser password for local Docker PostgreSQL container initialization. |
| `POSTGRES_DB` | String | Default database name created in local Docker PostgreSQL container. |

---

## Security and Credential Rules

1. **No Credentials in Version Control**: `.env` is explicitly listed in `.gitignore`. Real credentials must never be committed.
2. **Safe Placeholders**: `.env.example` must contain only safe placeholder values.
3. **Empty String Handling**: Supplying an empty string (`""`) for required variables (like `DATABASE_URL`) is treated as absent and triggers validation failure.
4. **Log Redaction**: All values associated with secret fields (`DATABASE_URL`, `NEO4J_PASSWORD`, `OPENROUTER_API_KEY`, passwords, tokens) are automatically redacted to `[REDACTED]` in log output.
