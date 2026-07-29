# Meridian Commercial Intelligence

A trustworthy **agentic** system that answers natural-language questions about Q1 2026 sales
pipeline data. Autonomy — planning, language understanding, dialogue — lives in a Google ADK
orchestrator powered by **Anthropic Claude**. Every number it reports comes from a governed,
deterministic MCP tool server over DuckDB, returned *with the query and rows that produced it*.
A thin, executive-grade React client renders the answer with its confidence stamp and full
source trace.

Built against `REQUIREMENTS-v2.md` in this repo — that document is the full spec; this README
is the map and the honest account of what shipped.

## Table of contents

- [The trust thesis](#the-trust-thesis)
- [Why this design](#why-this-design)
- [Architecture](#architecture)
- [Running it locally](#running-it-locally)
- [The eval suite (what gates a deploy)](#the-eval-suite-what-gates-a-deploy)
- [Access control](#access-control)
- [A2A and calling the MCP tools directly](#a2a-and-calling-the-mcp-tools-directly)
- [Personalizing the UI](#personalizing-the-ui)
- [Deployment](#deployment)
- [Scope cuts](#scope-cuts)
- [What this proves, and what it doesn't](#what-this-proves-and-what-it-doesnt)
- [Versions](#versions)

## The trust thesis

A prior version of this tool lost executive confidence because a language model **produced**
numbers, and it produced wrong ones in public. Going agentic does not relax that — it relocates
the trust boundary to the tool contract and the orchestrator's system prompt, and it holds two
tiers apart:

```
┌────────────────────────────────────────────────────────────────┐
│  AUTONOMOUS TIER (may be wrong, must be honest)                 │
│  ADK orchestrator on Claude — NL understanding, planning,       │
│  dialogue. Contains an LLM. Bound by system-prompt invariants.  │
└────────────────────────────────────────────────────────────────┘
                       │ MCP tool calls (typed, validated)
                       ▼
┌────────────────────────────────────────────────────────────────┐
│  GOVERNED TIER (cannot be wrong, has NO LLM)                    │
│  governed/ = semantic layer + gates + DuckDB engine.             │
│  Pure deterministic compute. Returns value + stamp + receipt.   │
└────────────────────────────────────────────────────────────────┘
```

**The trusted tier contains no model at all.** `governed/` never imports `agent/`, never calls
an LLM, and is fully unit-testable on its own — that's `tests/test_engine.py` and
`tests/test_gates.py`, and neither needs a network connection or an API key.

Ten invariants (`REQUIREMENTS-v2.md` §1.1) hold this together. The two that matter most for
reading this codebase:

- **No model-authored numbers.** Every figure in an answer must appear verbatim in a tool
  result. The agent's system prompt (`agent/prompts.py`) makes this the first rule, and Tier B
  evals check the model actually followed it.
- **Abstention is terminal.** When data can't support an answer, a tool returns `cannot_verify`
  and that's the end of it — not a retry trigger, not a chance for the model to fill the gap.

### The Ironbridge case

The canonical regression test, at every layer: **"Why did we lose Ironbridge?"** `OPP-008` is
Closed Lost, Enterprise, $195,000 — and `loss_reason` is empty in the source data. The correct
answer is "the record exists, it was lost, and no reason was recorded." Nothing else.

- **Tool layer** (`governed/engine.py::get_deal_reason`): detects the empty field and returns
  `stamp: cannot_verify`, never a fabricated cause. Pinned by
  `test_ironbridge_refuses_without_inventing_a_reason` (Tier A).
- **Agent layer** (`agent/prompts.py`): the system prompt names this case explicitly and
  instructs the model to relay the refusal, never to supply a cause of its own. Pinned by
  `test_ironbridge_final_answer_invents_no_cause` (Tier B).
- **UI layer** (`ui/src/components/ConfidenceBadge.tsx`): renders the brick `cannot_verify`
  badge, and the source trace shows the actual row with its empty `loss_reason` field.

## Why this design

**Why ADK + MCP, on Claude, instead of one model doing everything?** Because the failure mode
this system exists to prevent — a model inventing a number — has to be *structurally*
impossible, not prompt-engineered away. Putting the governed tools behind MCP means the model
never sees a code path where it could compute a figure itself; it can only call a tool and
relay what comes back. The inner NL→spec translator from the prior version is **deleted, not
relocated** — ADK's native Claude function-calling *is* the translation layer now, and the
translation step never touches the numbers.

**Why DuckDB, given the data is 85 rows?** At this scale the engine choice is irrelevant to
performance, so it's made on the trust axis instead. DuckDB's receipt is an **executable,
portable `SELECT`** — an analyst can copy the string out of the source trace and run it against
the source CSVs to reconcile a figure by hand (INV-7: the SQL in the receipt is the literal
string that ran, never a reconstruction). The same SQL dialect scales to a real warehouse, so
the prototype and the production data layer are the same choice, not a migration waiting to
happen.

**How INV-8/INV-9 defend the boundary.** A governed tool being correct doesn't help if the model
is dishonest about what it returned — that's exactly the shape of the original failure, and it
can re-enter through the agent's mouth even with perfect tools underneath. Two mechanisms close
that gap:

- **INV-8 (stamp/figure fidelity):** the system prompt forbids upgrading `assumption` or
  `cannot_verify` into confident prose, and forbids introducing any number a tool didn't return.
- **INV-9 (receipt propagation):** every tool result's `receipt` travels with the agent's
  answer, through `agent/server.py`'s `/run` response, into the UI's source-trace panel. A
  figure three hops deep is still traceable back to the exact query that produced it.

## Architecture

### Code boundaries vs. deployment boundaries

The code is factored into three tiers regardless of how it's deployed — that's what makes MCP a
real seam rather than decoration:

```
meridian-agentic/
├── governed/       # GOVERNED TIER — no LLM, no ADK, no UI imports
│   ├── semantic.py     # metric definitions, defined exactly once
│   ├── engine.py       # DuckDB load + the 5 governed executors
│   ├── gates.py        # arg validation, access-scope resolution, invariant post-checks
│   └── models.py       # Pydantic ToolResult / Receipt (the envelope every tool returns)
├── mcp_server/      # wraps governed/ as MCP tools (FastMCP-equivalent MCPServer)
├── agent/           # ADK LlmAgent on Claude — the only LLM in the system
│   ├── agent.py         # tool wrappers (viewer injected via ToolContext, never LLM-visible)
│   ├── prompts.py       # the trust guardrail system prompt
│   └── server.py        # to_a2a() + the UI's /run endpoint, one ASGI app
├── ui/              # thin React (Vite) exec client — no business logic, no LLM key
├── data/            # deals.csv, reps.csv — the only source of truth
└── tests/           # Tier A (hard gate) + Tier B (faithfulness) evals
```

### Demo topology — 2 deployables

```
  Executives ──►  Thin React UI (nginx-on-Cloud-Run)         [deployable #1]
                       │ HTTPS → agent /run (CORS-locked)
                       ▼
  A2A peers ──►  ADK Agent service (LlmAgent on Claude)      [deployable #2]
                       │ governed tools attached IN-PROCESS as ADK FunctionTools
                       ▼  (in-process call — no network hop)
                 governed/ tier — no LLM
                       ▼
                 DuckDB (in-memory) over data/*.csv
```

The governed tools run **in the agent process** for the demo (`agent/agent.py` registers the
`governed/engine.py` functions directly as ADK `FunctionTool`s — the spec's "simplest" option).
`mcp_server/server.py` still exists as fully separate, independently-runnable code with no
import from `agent/` — it's just not the wiring the demo agent uses.

**Why co-located isn't a corner cut:** the governed functions underneath are identical either
way. Promoting to the production topology means changing `agent/agent.py`'s tool list from the
direct-`FunctionTool` wrappers to an `MCPToolset` pointed at a deployed `mcp_server/`, and
nothing in `governed/` changes. That's a wiring change, not a rewrite — which is the entire
point of having drawn the tier boundary before touching the deploy story.

### Production topology — 3 services

```
  UI (static) ──►  ADK Agent service ──MCP (Streamable HTTP, authed)──►  MCP Server service
```

`mcp_server/server.py` deploys as its own Cloud Run service (`mcp_server/Dockerfile`), reachable
over Streamable HTTP, independently callable by any MCP client — not just this agent. See
[Deployment](#deployment).

## Running it locally

### Governed tier + Tier A evals (no API key, no network)

```bash
uv sync
uv run pytest tests/test_engine.py tests/test_gates.py tests/test_tool_determinism.py -v
```

This is the hard gate. If it's not green, nothing downstream is trustworthy enough to run.

### The agent, locally

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export UI_ORIGIN=http://localhost:5173
uv run uvicorn agent.server:app --reload --port 8080
```

`agent/server.py` is one ASGI app exposing:

- `POST /run` — `{question, viewer, session_id?}` → `{answer, stamp, receipts[], session_id}`,
  the contract the React UI speaks.
- `GET /.well-known/agent-card.json` — the auto-generated A2A agent card (from `to_a2a()`).
- `GET /healthz`.

**Without a key**, the agent process will fail to make model calls — there is deliberately **no
LLM fallback for figures** (spec §13.5): if the model is unreachable, the intent is an honest
refusal, never a guessed number. To exercise the governed tools without any model, call
`mcp_server/server.py` directly (see below) or hit `governed/engine.py`'s functions from a
Python shell — both paths are model-free by construction.

Dev/debug alternative: `uv run adk web agent` gives ADK's own tool-call-chain visualizer. It is
**not** the executive-facing surface and isn't part of the demo — the React UI is.

### The MCP server, standalone

```bash
uv run python -m mcp_server.server                 # stdio (demo transport)
MCP_TRANSPORT=streamable-http uv run python -m mcp_server.server   # production transport
```

Any MCP client can call the five tools directly this way, with no agent in the loop. Every tool
requires `viewer` as an explicit argument here (`"LEADERSHIP"` or a `rep_id` like `"REP-02"`) —
unlike the agent's LLM-facing schema, this is the self-sufficient governed surface, so it has to
take the real argument (see [Access control](#access-control) for why the agent's version
doesn't).

### The UI, in dev

```bash
cd ui
npm install
npm run dev   # http://localhost:5173, expects the agent at http://localhost:8080
```

Set `VITE_AGENT_URL` (`ui/.env` or the shell) to point at a different agent instance. The UI
never holds the Anthropic key and never calls the MCP server directly (spec §11A) — it only
knows the agent's `/run` endpoint.

## The eval suite (what gates a deploy)

Two tiers, mirrored in `.github/workflows/deploy.yml`:

**Tier A — governed-tool determinism (hard deploy gate; no LLM, no network).**
`tests/test_engine.py`, `tests/test_gates.py`, `tests/test_tool_determinism.py`. Calls the
actual MCP tool surface (not just the raw functions) against `tests/golden_tool_evals.yaml`,
and asserts:

| Tool call | Stamp | Figure |
|---|---|---|
| `get_segment_attainment("Enterprise")` | assumption | **58.6%** ($2,050,000 / $3,500,000) |
| `get_segment_attainment("Mid-Market")` | assumption | **56.4%** ($1,100,000 / $1,950,000) |
| `get_segment_attainment("SMB")` | assumption | **58.5%** ($275,000 / $470,000) |
| `get_reps_at_risk()` | assumption | **7 of 10** below 70% |
| `get_pipeline_value(close_before="2026-03-31")` | assumption | **$1,301,000** |
| `get_pipeline_value()` | verified | **$4,311,000** |
| `get_deal_reason("Ironbridge")` | **cannot_verify** | refuses — `loss_reason` empty |
| `get_deal_reason("Fulcrum Enterprises")` | verified | **"Competitor - Salesforce"** |

Plus the access-scoping cases: a scoped rep (`viewer="REP-02"`) gets only their own contribution
(never the org-level figure, by any phrasing — the filter lives in query construction), an
unknown/blank viewer fails closed, and `LEADERSHIP` is unrestricted. Also asserted: calling any
tool twice with identical arguments returns byte-identical results (INV-6), and every receipt's
`sql` field is non-empty.

**Gate rule: this suite green, or no deploy.** It runs in ~1 second and needs nothing but `uv`.

**Tier B — orchestrator faithfulness (needs a live Claude call).**
`tests/test_agent_faithfulness.py`, skipped locally unless `ANTHROPIC_API_KEY` is set, and run
as its own CI job against `anthropic/claude-haiku-4-5-20251001` to keep cost down. Asserts the
*final agent answer* — not just the tool result — honors the invariants: no fabricated
Ironbridge cause, forecast questions refused as out-of-scope, a segment-attainment answer's
figure matches the tool's exactly, a compound comparison calls both tools and self-computes
nothing, and access forwarding holds (a scoped rep's final answer never contains the org-level
figure). A Tier B failure blocks the agent-service deploy.

## Access control

**Model: authenticate high, authorize low.** Identity is *claimed* at the UI's login screen
(no password — a stubbed claim, spec §11B); authorization is *enforced* in the governed tier as
a mandatory SQL predicate. The LLM is never in the access path.

Mechanically, in `agent/agent.py`: every tool wrapper takes `tool_context: ToolContext` instead
of `viewer: str`. ADK detects the `ToolContext`-typed parameter and (a) excludes it from the
JSON schema the model sees — confirmed by inspecting the generated function declarations, none
of which contain `viewer` — and (b) injects the real session object at call time. The wrapper
reads `tool_context.state["viewer"]`, populated by `agent/server.py` from the authenticated
login identity on every `/run` call, and forwards it unchanged into `governed/engine.py`. The
model cannot see it, set it, or be prompt-injected into changing it, because there is no
parameter for it to act on.

Enforcement, in `governed/gates.py::resolve_viewer` + `scope_predicate`: `"LEADERSHIP"` gets no
filter; a known `rep_id` gets `AND rep_id = ?` injected into every query the engine builds,
applied to both sides of a ratio (a scoped rep's segment attainment is *their own* won ÷ *their
own* quota, not their contribution to the segment total); anything else — unknown identity,
blank, a segment they don't belong to being asked about — **fails closed**: an empty
`cannot_verify` result, never full data. The applied scope is written into
`receipt.assumptions` (e.g. *"Scoped to your deals (REP-02); org-level figures are restricted
to leadership"*), so the access boundary is itself part of the auditable receipt.

**The honest stub:** the login screen's identity is unauthenticated and therefore spoofable —
anyone can type `REP-02` or `LEADERSHIP`. That is the deliberate simplification for this demo.
Swapping it for a real IdP that sets a verified `rep_id` claim changes only where `viewer`
originates (an auth middleware in front of `agent/server.py`'s `/run` endpoint instead of a
login form); it does not touch `resolve_viewer`, `scope_predicate`, or anything in
`governed/engine.py` — the same promote-without-rewrite pattern as the MCP seam.

## A2A and calling the MCP tools directly

`agent/server.py` builds its ASGI app from `google.adk.a2a.utils.agent_to_a2a.to_a2a(root_agent)`,
which auto-generates the agent card at `/.well-known/agent-card.json` and the A2A JSON-RPC
endpoint. Any A2A-aware peer (another ADK agent, Gemini Enterprise, a different framework
entirely) can discover the card and delegate pipeline questions without going through the React
UI at all.

To call the governed tools with no agent in the loop, run `mcp_server/server.py` (stdio or
Streamable HTTP per above) and connect any MCP client to it — `list_supported_questions` is a
reasonable first call to confirm the connection and see the capability set.

## Personalizing the UI

Everything client-specific lives in `ui/config.ts`: `BRANDING` (client name, title line, context
line, tagline), the stubbed `REP_ROSTER` login identities, and `SUGGESTED_QUESTIONS` (the chips,
including the dashed Ironbridge trap). `VITE_AGENT_URL` points the build at a specific agent
deployment. Re-skinning for a new engagement is editing this one file and rebuilding — no
component code changes.

## Deployment

CI (`.github/workflows/deploy.yml`) on push to `main`: `ruff` → **Tier A** → (in parallel) build
the UI bundle and run **Tier B** → build + push both container images → deploy. **No deploy if
Tier A fails**; a Tier B failure blocks the agent-service deploy specifically. Auth to GCP is
keyless (Workload Identity Federation) — no JSON key ever lives in this public repo.

- **Agent service:** `agent/Dockerfile`, non-root, `uv`-managed, runs
  `uvicorn agent.server:app`. `ANTHROPIC_API_KEY` is injected from Secret Manager at deploy time
  — it is never baked into the image and never present anywhere but this one service.
- **UI:** `ui/Dockerfile`, multi-stage (`npm run build` → static `nginx`), `VITE_AGENT_URL`
  passed as a build arg pointing at the deployed agent URL.
- **MCP server (production only):** `mcp_server/Dockerfile`, not deployed in the demo topology.
  Splitting it out is documented above under [Architecture](#architecture) and is a config
  change to `agent/agent.py`'s tool wiring, not a rewrite.

Enterprise alternative: deploy the agent to Vertex AI Agent Engine instead of raw Cloud Run for
managed scaling/registry.

## Scope cuts

Deliberate, not oversights (spec §5.2):

- Read-only. No write-back to any system of record.
- No auth/user management beyond Cloud Run IAM, MCP-server auth (production only), and the
  UI↔agent CORS lock — the login screen's identity is a stub, documented as one above.
- No forecasting, and no "why" beyond a stored `loss_reason` — the Ironbridge case is the
  canonical example of exactly the boundary this draws.
- Data ships as CSVs; no live warehouse connector.
- Exactly five governed metrics. Anything else is a navigational refusal via
  `list_supported_questions`, not an approximation.
- The UI is intentionally thin: ask, answer, verify. No dashboards, saved views, or exports.

## What this proves, and what it doesn't

**Proves:** that an LLM can sit in the planning/dialogue loop of a numbers-reporting tool
without ever being the source of a number — the governed tier is fully independent, unit-tested
without any model, and every figure the agent relays is traceable through a receipt back to an
executable SQL statement. That access control can be enforced without putting the model
anywhere near the enforcement path. That the trust properties survive an extra hop (agent → A2A
→ external caller, or agent → UI) because the receipt is carried as data, not re-derived at each
hop.

**Doesn't prove:** that Claude's tool-selection is perfect on arbitrary phrasing — Tier B checks
specific canonical and adversarial-ish questions, not exhaustive phrasing coverage. That the
login screen is a real authentication system — it isn't, by design, and the README says so
rather than letting the UI imply otherwise. That this scales past a demo dataset — DuckDB and
an in-memory 85-row load are the right choice *for this exercise specifically*, with an explicit
note about what changes (warehouse connection string, nothing else in the SQL) if it didn't.

## Versions

Pin exact versions at build time; re-verify against current docs before a real deployment.
Installed in this repo's `uv.lock` at the time of writing: `google-adk==2.5.0`,
`mcp==2.0.0` (its `FastMCP` is now `mcp.server.MCPServer` — same tool-decorator shape, see
`mcp_server/server.py`'s module docstring), `litellm==1.94.0`, `a2a-sdk` per `pyproject.toml`,
Python 3.12, React 18 + Vite 5. Default model: `anthropic/claude-haiku-4-5-20251001`
(`MODEL_ID` env var; set to `anthropic/claude-sonnet-5` for an exec demo). References:

- ADK ↔ MCP integration: https://google.github.io/adk-docs/tools/mcp-tools/
- ADK models (LiteLLM / Claude): https://google.github.io/adk-docs/
- Exposing an ADK agent via A2A: https://google.github.io/adk-docs/a2a/quickstart-exposing/
