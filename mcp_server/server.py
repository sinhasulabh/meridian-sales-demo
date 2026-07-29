"""FastMCP-equivalent MCP server wrapping `governed/` as tools (spec §10).

No LLM. Read-only data. Imports only from `governed/` — nothing from
`agent/` or `ui/`. This is the artifact that is independently callable by
any MCP client, and the one that gets split into its own Cloud Run service
in the production topology (§2.1, §16.2).

The installed `mcp` SDK (2.0.0) renamed `FastMCP` to `MCPServer`; the API
surface (`@mcp.tool()`, `mcp.run(transport=...)`) is the same shape the
spec describes. Pin/re-verify at build time per the spec's own note.

Transport: demo runs this over **stdio** (`python -m mcp_server.server`),
co-located in the agent container — no network hop, no auth needed.
Production runs it over **Streamable HTTP** as its own service
(`mcp.run(transport="streamable-http")`), see `Dockerfile` and §16.2.

Every tool takes `viewer` as an explicit, required argument: MCP tools
must be self-sufficient for any MCP client calling them directly (spec §4,
"MCP direct"). The ADK agent (agent/agent.py) does NOT expose `viewer` to
the LLM's function-calling schema — it injects it server-side via
ADK's ToolContext so the model is never in the access-control path
(INV-10). This server is the direct-callable governed surface; the agent
is a different caller that happens to keep the model blind to `viewer`.
"""

from __future__ import annotations

from typing import Any

from mcp.server import MCPServer

from governed import engine
from governed.models import ToolResult

mcp = MCPServer(
    name="meridian-commercial-intelligence",
    title="Meridian Commercial Intelligence",
    instructions=(
        "Governed, deterministic tools over Q1 2026 sales pipeline data. "
        "No tool here calls an LLM; every result carries a stamp "
        "(verified | assumption | cannot_verify) and a receipt with the "
        "exact SQL that ran. `viewer` is required on every call: "
        "'LEADERSHIP' for unrestricted access, or a rep_id (e.g. 'REP-02') "
        "to see only that rep's deals. Unknown/blank viewer fails closed."
    ),
)


def _dump(result: ToolResult) -> dict[str, Any]:
    return result.model_dump(mode="json")


@mcp.tool()
def get_segment_attainment(segment: str, viewer: str) -> dict[str, Any]:
    """Q1 2026 closed-won attainment vs. quota for one segment.

    Args:
        segment: One of "Enterprise", "Mid-Market", "SMB".
        viewer: "LEADERSHIP" or a rep_id (e.g. "REP-02"). Required.
    """
    return _dump(engine.get_segment_attainment(segment, viewer))


@mcp.tool()
def get_reps_at_risk(viewer: str, threshold: float = 0.70) -> dict[str, Any]:
    """Reps whose Q1 2026 closed-won attainment is below `threshold`.

    Args:
        viewer: "LEADERSHIP" or a rep_id. Required.
        threshold: Attainment cutoff in [0.0, 1.0]. Defaults to 0.70.
    """
    return _dump(engine.get_reps_at_risk(threshold=threshold, viewer=viewer))


@mcp.tool()
def get_pipeline_value(
    viewer: str, segment: str | None = None, close_before: str | None = None
) -> dict[str, Any]:
    """Sum of open-stage deal_value, optionally filtered.

    Args:
        viewer: "LEADERSHIP" or a rep_id. Required.
        segment: Optional segment filter.
        close_before: Optional ISO date; keeps deals with close_date <= this.
    """
    return _dump(
        engine.get_pipeline_value(segment=segment, close_before=close_before, viewer=viewer)
    )


@mcp.tool()
def get_deal_reason(account_name: str, viewer: str) -> dict[str, Any]:
    """The stored loss_reason for one account, verbatim. Refuses if empty.

    Args:
        account_name: The account to look up.
        viewer: "LEADERSHIP" or a rep_id. Required.
    """
    return _dump(engine.get_deal_reason(account_name, viewer))


@mcp.tool()
def list_supported_questions() -> dict[str, Any]:
    """The governed capability set — what this system can and can't answer."""
    return _dump(engine.list_supported_questions())


if __name__ == "__main__":
    import os

    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "streamable-http":
        mcp.run(
            transport="streamable-http",
            host="0.0.0.0",
            port=int(os.environ.get("PORT", 8080)),
        )
    else:
        mcp.run(transport="stdio")
