FROM python:3.12-slim

# Install system dependencies and uv
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app/src:${PYTHONPATH}" \
    PATH="/root/.cargo/bin:${PATH}"

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml README.md ./

# Install production dependencies
RUN uv sync --frozen --no-dev --no-install-project 2>/dev/null || uv sync --no-dev --no-install-project

# Copy application source and alembic configuration
COPY src/ ./src/
COPY alembic.ini ./alembic.ini
COPY alembic/ ./alembic/

# Install the project itself
RUN uv sync --no-dev

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --retries=5 CMD curl -f http://localhost:8000/health || exit 1

CMD ["uv", "run", "uvicorn", "trace.main:app", "--host", "0.0.0.0", "--port", "8000"]
