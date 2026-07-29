"""The agent service's ASGI app (spec §9, §11A, §16).

Built on top of `to_a2a(root_agent)` so this single process is reachable
two ways from one Cloud Run deployable:

  * A2A — the auto-generated agent card + JSON-RPC endpoint, for other
    agents (`to_a2a`'s own routes, mounted at app construction).
  * The UI's run endpoint — `POST /run {question, viewer, session_id?}`
    -> `{answer, stamp, receipts[], session_id}`, the bespoke contract the
    thin React client speaks (§11A). This is *not* one of ADK's generic
    dev-server routes (those are `adk web`, dev-only, §9) — it's a small
    endpoint we add directly so the response shape carries stamps and
    receipts the way the UI needs to render them.

CORS is locked to `UI_ORIGIN` (§13.2); the Anthropic key is read only
here, via `LiteLlm` inside `agent/agent.py` — the UI and MCP server never
see it.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from agent.agent import root_agent
from governed.models import Stamp

APP_NAME = "meridian_ci"
UI_ORIGIN = os.environ.get("UI_ORIGIN", "http://localhost:5173")

_session_service = InMemorySessionService()
_runner = Runner(agent=root_agent, app_name=APP_NAME, session_service=_session_service)

_STAMP_PRECEDENCE = {
    Stamp.CANNOT_VERIFY.value: 0,
    Stamp.ASSUMPTION.value: 1,
    Stamp.VERIFIED.value: 2,
}


async def _ensure_session(user_id: str, session_id: str, viewer: str) -> None:
    existing = await _session_service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    if existing is None:
        await _session_service.create_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id, state={"viewer": viewer}
        )


async def run_endpoint(request: Request) -> JSONResponse:
    body = await request.json()
    question = (body.get("question") or "").strip()
    viewer = (body.get("viewer") or "").strip()
    session_id = body.get("session_id") or str(uuid.uuid4())

    if not question:
        return JSONResponse({"error": "question is required"}, status_code=400)
    if not viewer:
        return JSONResponse({"error": "viewer is required"}, status_code=400)

    # user_id scopes ADK sessions; a viewer's own identity is a natural key
    # and keeps one rep's sessions from ever being listed under another's.
    await _ensure_session(user_id=viewer, session_id=session_id, viewer=viewer)

    tool_results: list[dict[str, Any]] = []
    answer_text = ""

    async for event in _runner.run_async(
        user_id=viewer,
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text=question)]),
        state_delta={"viewer": viewer},
    ):
        if not event.content or not event.content.parts:
            continue
        for part in event.content.parts:
            response = part.function_response.response if part.function_response else None
            if isinstance(response, dict):
                tool_results.append(response)
        if event.is_final_response():
            text_parts = [p.text for p in event.content.parts if p.text]
            if text_parts:
                answer_text = "".join(text_parts)

    receipts = [tr["receipt"] for tr in tool_results if "receipt" in tr]
    if tool_results:
        overall_stamp = min(
            (tr.get("stamp", Stamp.CANNOT_VERIFY.value) for tr in tool_results),
            key=lambda s: _STAMP_PRECEDENCE.get(s, 0),
        )
    else:
        overall_stamp = Stamp.CANNOT_VERIFY.value

    return JSONResponse(
        {
            "answer": answer_text or "I wasn't able to produce an answer for that.",
            "stamp": overall_stamp,
            "receipts": receipts,
            "session_id": session_id,
        }
    )


async def livez(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


app = to_a2a(root_agent, port=int(os.environ.get("PORT", 8080)))
app.add_route("/run", run_endpoint, methods=["POST"])
# Named /livez, not /healthz: on Cloud Run's *.run.app domains, GFE (the
# edge in front of the container) reserves /healthz for its own internal
# health-checking convention and never forwards it to the app — it 404s
# before reaching us regardless of what route we register. /livez isn't
# reserved and reaches the container normally. Cloud Run's own container
# probe is plain TCP here (no --startup-probe httpGet configured), so this
# endpoint is purely for our own external observability, not deploy gating.
app.add_route("/livez", livez, methods=["GET"])
app.add_middleware(
    CORSMiddleware,
    allow_origins=[UI_ORIGIN],
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)
