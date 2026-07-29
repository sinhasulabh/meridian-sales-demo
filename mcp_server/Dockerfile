# Production-only artifact (spec §16.2): the governed MCP server split out
# as its own Cloud Run service, over Streamable HTTP. Not deployed in the
# 2-service demo topology (the demo co-locates governed tools in the agent
# process) — kept here so the promotion is a deploy/config change, not a
# rewrite.

FROM python:3.12-slim AS base

RUN groupadd -r app && useradd -r -g app app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /srv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY governed/ ./governed/
COPY mcp_server/ ./mcp_server/
COPY data/ ./data/

RUN uv sync --frozen --no-dev

ENV PATH="/srv/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    MCP_TRANSPORT=streamable-http \
    PORT=8080

USER app
EXPOSE 8080

CMD ["python", "-m", "mcp_server.server"]
