# Agent service — demo topology: governed tools co-located in-process
# (spec §2.1, §16.1). Runs agent/server.py (to_a2a + /run + /healthz) under
# uvicorn. Non-root, uv-managed, no secrets baked in — ANTHROPIC_API_KEY is
# injected at runtime from Secret Manager.

FROM python:3.12-slim AS base

RUN groupadd -r app && useradd -r -g app app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /srv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY governed/ ./governed/
COPY agent/ ./agent/
COPY data/ ./data/

RUN uv sync --frozen --no-dev

ENV PATH="/srv/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PORT=8080

USER app
EXPOSE 8080

CMD ["uvicorn", "agent.server:app", "--host", "0.0.0.0", "--port", "8080"]
