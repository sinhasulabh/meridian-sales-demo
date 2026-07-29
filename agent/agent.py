"""ADK LlmAgent on Claude (spec §9). The autonomous tier: may be wrong,
must be honest. Contains the only model in the system.

Tool wiring — demo default (spec §9): the governed functions are
registered directly as ADK `FunctionTool`s (the "simplest" option), in the
same process as the agent. No stdio/network hop. Swapping to the remote-MCP
production topology means pointing an `MCPToolset` at `mcp_server/server.py`
deployed over Streamable HTTP instead of the wrappers below — the governed
functions underneath are identical either way (§2.1).

INV-10, mechanically: each wrapper's signature takes `tool_context:
ToolContext` instead of `viewer: str`. ADK detects the `ToolContext`-typed
parameter and (a) excludes it from the JSON schema the LLM sees, and (b)
injects the real object at call time — so `viewer` never appears in the
model's function-calling schema at all. It cannot see it, set it, or be
prompt-injected into changing it. The wrapper reads the authenticated
viewer from session state, populated by `agent/server.py` from the UI's
login identity, and forwards it unchanged into the governed call.
"""

from __future__ import annotations

import os
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import ToolContext

from agent.prompts import SYSTEM_PROMPT
from governed import engine
from governed.models import LEADERSHIP

MODEL_ID = os.environ.get("MODEL_ID", "anthropic/claude-haiku-4-5-20251001")


def _viewer(tool_context: ToolContext) -> str:
    return tool_context.state.get("viewer", LEADERSHIP)


def get_segment_attainment(segment: str, tool_context: ToolContext) -> dict[str, Any]:
    """Q1 2026 closed-won attainment vs. quota for one segment.

    Args:
        segment: One of "Enterprise", "Mid-Market", "SMB".
    """
    return engine.get_segment_attainment(segment, _viewer(tool_context)).model_dump(mode="json")


def get_reps_at_risk(tool_context: ToolContext, threshold: float = 0.70) -> dict[str, Any]:
    """Reps whose Q1 2026 closed-won attainment is below `threshold`.

    Args:
        threshold: Attainment cutoff in [0.0, 1.0]. Defaults to 0.70.
    """
    return engine.get_reps_at_risk(threshold=threshold, viewer=_viewer(tool_context)).model_dump(
        mode="json"
    )


def get_pipeline_value(
    tool_context: ToolContext,
    segment: str | None = None,
    close_before: str | None = None,
) -> dict[str, Any]:
    """Sum of open-stage deal_value, optionally filtered.

    Args:
        segment: Optional segment filter.
        close_before: Optional ISO date; keeps deals with close_date <= this.
    """
    return engine.get_pipeline_value(
        segment=segment, close_before=close_before, viewer=_viewer(tool_context)
    ).model_dump(mode="json")


def get_deal_reason(account_name: str, tool_context: ToolContext) -> dict[str, Any]:
    """The stored loss_reason for one account, verbatim. Refuses if empty.

    Args:
        account_name: The account to look up.
    """
    return engine.get_deal_reason(account_name, _viewer(tool_context)).model_dump(mode="json")


def list_supported_questions() -> dict[str, Any]:
    """The governed capability set — what this system can and can't answer."""
    return engine.list_supported_questions().model_dump(mode="json")


root_agent = LlmAgent(
    model=LiteLlm(model=MODEL_ID),
    name="meridian_ci",
    description=(
        "Answers questions about Q1 2026 sales pipeline attainment, "
        "at-risk reps, open pipeline value, and deal-loss reasons using "
        "governed, deterministic tools."
    ),
    instruction=SYSTEM_PROMPT,
    tools=[
        get_segment_attainment,
        get_reps_at_risk,
        get_pipeline_value,
        get_deal_reason,
        list_supported_questions,
    ],
)
