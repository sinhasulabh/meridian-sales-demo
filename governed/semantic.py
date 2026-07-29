"""Semantic layer (spec §7). Metric definitions live exactly once here.

No LLM, no DuckDB connection, no MCP — just the governed vocabulary that
`governed/engine.py` compiles into SQL. Nothing else in the codebase is
allowed to redefine what "attainment," "open pipeline," or "at risk" mean
(INV-4).
"""

from __future__ import annotations

OPEN_STAGES: tuple[str, ...] = ("Prospecting", "Discovery", "Proposal", "Negotiation")
CLOSED_WON = "Closed Won"
CLOSED_LOST = "Closed Lost"

Q1_2026_START = "2026-01-01"
Q1_2026_END = "2026-03-31"

DEFAULT_AT_RISK_THRESHOLD = 0.70

METRIC_DEFINITIONS: dict[str, str] = {
    "segment_attainment": (
        "Attainment = Σ Closed-Won deal_value in Q1 2026 for the segment "
        "÷ Σ quota_q1_2026 for that segment's reps. Open pipeline is "
        "reported separately and never counted toward attainment."
    ),
    "reps_at_risk": (
        "Per rep: Σ Closed-Won deal_value in Q1 2026 ÷ quota_q1_2026. "
        "A rep is flagged at-risk when this ratio is below the threshold "
        "(default 0.70)."
    ),
    "pipeline_value": (
        "Σ deal_value for deals in an open stage "
        f"({', '.join(OPEN_STAGES)}). Optional segment and close_date <= "
        "filters narrow the sum; with neither, this is total open pipeline."
    ),
    "deal_reason": (
        "Returns one account's stored loss_reason verbatim. If the deal is "
        "not Closed Lost, that is stated rather than a reason. If "
        "loss_reason is empty, the tool refuses rather than inferring a "
        "cause."
    ),
}
