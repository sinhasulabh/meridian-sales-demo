"""DuckDB load + governed executors (spec §7, §15).

No LLM. No MCP. No ADK. This module is importable and fully testable on
its own — that separability is the point of the trust architecture (§1.2).

Every public function here returns a `ToolResult` (value + stamp +
receipt). Model output never becomes SQL text: arguments are validated by
`governed.gates` first, and every query is parameterized.
"""

from __future__ import annotations

import datetime
import functools
import threading
from pathlib import Path
from typing import Any

import duckdb

from governed import gates, semantic
from governed.models import LEADERSHIP, Receipt, Stamp, ToolResult

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

_lock = threading.Lock()


@functools.lru_cache(maxsize=1)
def _connection() -> duckdb.DuckDBPyConnection:
    """One in-memory DuckDB connection, loaded once, reused for every call.

    Cached at module scope (spec §13.1: "cache the DuckDB connection/data
    load at MCP-server start"). Read-only usage after this point.
    """
    con = duckdb.connect(":memory:")
    con.execute(
        "CREATE TABLE reps AS SELECT * FROM read_csv_auto(?, header=true)",
        [str(DATA_DIR / "reps.csv")],
    )
    con.execute(
        "CREATE TABLE deals AS SELECT * FROM read_csv_auto(?, header=true)",
        [str(DATA_DIR / "deals.csv")],
    )
    return con


@functools.lru_cache(maxsize=1)
def _known_rep_ids() -> frozenset[str]:
    con = _connection()
    rows = con.execute("SELECT rep_id FROM reps").fetchall()
    return frozenset(r[0] for r in rows)


def _query(sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    """Execute parameterized SQL and return JSON-safe row dicts.

    Thread-guarded because a single shared DuckDB connection is not
    concurrency-safe across simultaneous tool calls.
    """
    with _lock:
        con = _connection()
        cursor = con.execute(sql, params or [])
        columns = [d[0] for d in cursor.description]
        raw_rows = cursor.fetchall()
    return [dict(zip(columns, _jsonify(row), strict=True)) for row in raw_rows]


def _jsonify(row: tuple) -> tuple:
    return tuple(
        v.isoformat() if isinstance(v, (datetime.date, datetime.datetime)) else v
        for v in row
    )


def _denied_result(metric: str, scope: gates.ViewerScope) -> ToolResult:
    return ToolResult(
        stamp=Stamp.CANNOT_VERIFY,
        value={},
        answer_template=(
            "I can't verify a viewer identity for this request, so no data "
            "is returned. Access fails closed by design."
        ),
        receipt=Receipt(
            metric=metric,
            definition=semantic.METRIC_DEFINITIONS.get(metric, ""),
            sql="-- not executed: viewer identity did not resolve (fail closed)",
            assumptions=[scope.note or ""],
            rows=[],
            row_count="0 rows — access denied.",
        ),
        interpretation={"intent": metric, "access": "denied"},
    )


# ── get_segment_attainment ──────────────────────────────────────────────────


def get_segment_attainment(segment: str, viewer: str) -> ToolResult:
    seg = gates.validate_segment(segment)
    scope = gates.resolve_viewer(viewer, _known_rep_ids())
    if scope.mode == "denied":
        return _denied_result("segment_attainment", scope)

    deals_pred, deals_params = gates.scope_predicate(scope, "rep_id")
    reps_pred, reps_params = gates.scope_predicate(scope, "rep_id")

    won_sql = (
        "SELECT * FROM deals WHERE segment = ? AND stage = 'Closed Won' "
        f"AND close_date BETWEEN ? AND ? {deals_pred};"
    )
    won_rows = _query(
        won_sql,
        [seg.value, semantic.Q1_2026_START, semantic.Q1_2026_END, *deals_params],
    )
    won = sum(r["deal_value"] for r in won_rows)

    quota_sql = f"SELECT * FROM reps WHERE segment = ? {reps_pred};"
    quota_rows = _query(quota_sql, [seg.value, *reps_params])
    quota = sum(r["quota_q1_2026"] for r in quota_rows)

    open_pred, open_params = gates.scope_predicate(scope, "rep_id")
    open_sql = (
        "SELECT * FROM deals WHERE segment = ? AND stage IN "
        f"({','.join('?' for _ in semantic.OPEN_STAGES)}) {open_pred};"
    )
    open_rows = _query(open_sql, [seg.value, *semantic.OPEN_STAGES, *open_params])
    open_pipeline = sum(r["deal_value"] for r in open_rows)

    gates.assert_sum_matches(won, won_rows, "deal_value")
    gates.assert_sum_matches(quota, quota_rows, "quota_q1_2026")

    attainment_pct = round(won / quota * 100, 1) if quota else 0.0

    assumptions = [
        '"This quarter" resolved to Q1 2026.',
        f"Closed-won basis; ${open_pipeline:,} open pipeline not counted.",
    ]
    if scope.note:
        assumptions.append(scope.note)

    who = f"{scope.rep_id}'s" if scope.mode == "rep" else segment
    answer_template = (
        f"{who} attainment is {attainment_pct}% of {'their' if scope.mode == 'rep' else 'its'} "
        f"Q1 2026 quota — ${won:,} of ${quota:,} across {len(quota_rows)} rep"
        f"{'s' if len(quota_rows) != 1 else ''}."
    )

    return ToolResult(
        stamp=Stamp.ASSUMPTION,
        value={
            "segment": seg.value,
            "attainment_pct": attainment_pct,
            "won": won,
            "quota": quota,
            "open_pipeline": open_pipeline,
        },
        answer_template=answer_template,
        receipt=Receipt(
            metric="segment_attainment",
            definition=semantic.METRIC_DEFINITIONS["segment_attainment"],
            sql=won_sql,
            assumptions=assumptions,
            rows=won_rows,
            row_count=(
                f"{len(won_rows)} closed-won deals summed; "
                f"{len(quota_rows)} rep quotas summed."
            ),
        ),
        interpretation={"intent": "segment_attainment", "segment": seg.value},
    )


# ── get_reps_at_risk ─────────────────────────────────────────────────────────


def get_reps_at_risk(
    threshold: float = semantic.DEFAULT_AT_RISK_THRESHOLD, viewer: str = LEADERSHIP
) -> ToolResult:
    threshold = gates.validate_threshold(threshold)
    scope = gates.resolve_viewer(viewer, _known_rep_ids())
    if scope.mode == "denied":
        return _denied_result("reps_at_risk", scope)

    pred, params = gates.scope_predicate(scope, "r.rep_id")
    sql = (
        "SELECT r.rep_id, r.rep_name, r.segment, r.quota_q1_2026, "
        "COALESCE(SUM(CASE WHEN d.stage = 'Closed Won' AND d.close_date "
        "BETWEEN ? AND ? THEN d.deal_value ELSE 0 END), 0) AS won "
        "FROM reps r LEFT JOIN deals d ON d.rep_id = r.rep_id "
        f"{pred} "
        "GROUP BY r.rep_id, r.rep_name, r.segment, r.quota_q1_2026 "
        "ORDER BY r.rep_id;"
    )
    rows = _query(sql, [semantic.Q1_2026_START, semantic.Q1_2026_END, *params])

    for r in rows:
        r["attainment_pct"] = round(r["won"] / r["quota_q1_2026"] * 100, 1)
        r["at_risk"] = (r["won"] / r["quota_q1_2026"]) < threshold

    at_risk_rows = [r for r in rows if r["at_risk"]]

    assumptions = [
        f"At-risk threshold set to {threshold:.0%}.",
        '"This quarter" resolved to Q1 2026; closed-won basis.',
    ]
    if scope.note:
        assumptions.append(scope.note)

    if scope.mode == "rep":
        answer_template = (
            f"{rows[0]['rep_name']} is at {rows[0]['attainment_pct']}% of quota "
            f"({'at risk' if rows[0]['at_risk'] else 'not at risk'} vs. the "
            f"{threshold:.0%} threshold)."
            if rows
            else "No data for this rep."
        )
    else:
        names = ", ".join(f"{r['rep_name']} ({r['attainment_pct']}%)" for r in at_risk_rows)
        answer_template = (
            f"{len(at_risk_rows)} of {len(rows)} reps are below the "
            f"{threshold:.0%} attainment threshold: {names}."
        )

    return ToolResult(
        stamp=Stamp.ASSUMPTION,
        value={
            "threshold": threshold,
            "total_reps": len(rows),
            "at_risk_count": len(at_risk_rows),
            "reps": rows,
        },
        answer_template=answer_template,
        receipt=Receipt(
            metric="reps_at_risk",
            definition=semantic.METRIC_DEFINITIONS["reps_at_risk"],
            sql=sql,
            assumptions=assumptions,
            rows=rows,
            row_count=f"{len(rows)} reps evaluated; {len(at_risk_rows)} below {threshold:.0%}.",
        ),
        interpretation={"intent": "reps_at_risk", "threshold": threshold},
    )


# ── get_pipeline_value ───────────────────────────────────────────────────────


def get_pipeline_value(
    segment: str | None = None,
    close_before: str | None = None,
    viewer: str = LEADERSHIP,
) -> ToolResult:
    seg = gates.validate_segment(segment)
    close_before = gates.validate_close_before(close_before)
    scope = gates.resolve_viewer(viewer, _known_rep_ids())
    if scope.mode == "denied":
        return _denied_result("pipeline_value", scope)

    conditions = [f"stage IN ({','.join('?' for _ in semantic.OPEN_STAGES)})"]
    params: list[Any] = list(semantic.OPEN_STAGES)

    if seg is not None:
        conditions.append("segment = ?")
        params.append(seg.value)
    if close_before is not None:
        conditions.append("close_date <= ?")
        params.append(close_before)

    scope_pred, scope_params = gates.scope_predicate(scope, "rep_id")
    where = " AND ".join(conditions)
    sql = f"SELECT * FROM deals WHERE {where} {scope_pred};"
    rows = _query(sql, [*params, *scope_params])
    total = sum(r["deal_value"] for r in rows)

    gates.assert_sum_matches(total, rows, "deal_value")

    filters_applied = seg is not None or close_before is not None
    is_scoped = scope.mode == "rep"
    stamp = Stamp.ASSUMPTION if (filters_applied or is_scoped) else Stamp.VERIFIED

    assumptions = []
    if seg is not None:
        assumptions.append(f"Filtered to segment = {seg.value}.")
    if close_before is not None:
        assumptions.append(f"Filtered to close_date <= {close_before}.")
    if scope.note:
        assumptions.append(scope.note)

    descriptor = []
    if seg is not None:
        descriptor.append(seg.value)
    if close_before is not None:
        descriptor.append(f"closing by {close_before}")
    label = f" ({', '.join(descriptor)})" if descriptor else ""
    answer_template = f"Open pipeline{label} is ${total:,} across {len(rows)} deals."

    return ToolResult(
        stamp=stamp,
        value={
            "pipeline_value": total,
            "deal_count": len(rows),
            "segment": seg.value if seg else None,
            "close_before": close_before,
        },
        answer_template=answer_template,
        receipt=Receipt(
            metric="pipeline_value",
            definition=semantic.METRIC_DEFINITIONS["pipeline_value"],
            sql=sql,
            assumptions=assumptions,
            rows=rows,
            row_count=f"{len(rows)} open deals summed.",
        ),
        interpretation={
            "intent": "pipeline_value",
            "segment": seg.value if seg else None,
            "close_before": close_before,
        },
    )


# ── get_deal_reason ──────────────────────────────────────────────────────────


def get_deal_reason(account_name: str, viewer: str) -> ToolResult:
    account_name = gates.validate_account_name(account_name)
    scope = gates.resolve_viewer(viewer, _known_rep_ids())
    if scope.mode == "denied":
        return _denied_result("deal_reason", scope)

    scope_pred, scope_params = gates.scope_predicate(scope, "rep_id")
    sql = f"SELECT * FROM deals WHERE LOWER(account_name) = LOWER(?) {scope_pred};"
    rows = _query(sql, [account_name, *scope_params])

    assumptions = [scope.note] if scope.note else []

    if not rows:
        return ToolResult(
            stamp=Stamp.CANNOT_VERIFY,
            value={"account_name": account_name, "found": False},
            answer_template=(
                f"No deal record for {account_name!r} was found"
                f"{' within your scope' if scope.mode == 'rep' else ''}."
            ),
            receipt=Receipt(
                metric="deal_reason",
                definition=semantic.METRIC_DEFINITIONS["deal_reason"],
                sql=sql,
                assumptions=assumptions,
                rows=[],
                row_count="0 matching records.",
            ),
            interpretation={"intent": "deal_reason", "account_name": account_name},
        )

    deal = rows[0]

    if deal["stage"] != semantic.CLOSED_LOST:
        return ToolResult(
            stamp=Stamp.VERIFIED,
            value={"account_name": account_name, "stage": deal["stage"], "found": True},
            answer_template=(
                f"{account_name} is not Closed Lost — its current stage is "
                f"{deal['stage']}, so there is no loss reason to report."
            ),
            receipt=Receipt(
                metric="deal_reason",
                definition=semantic.METRIC_DEFINITIONS["deal_reason"],
                sql=sql,
                assumptions=assumptions,
                rows=rows,
                row_count="1 matching deal record.",
            ),
            interpretation={"intent": "deal_reason", "account_name": account_name},
        )

    loss_reason = (deal.get("loss_reason") or "").strip()
    if not loss_reason:
        return ToolResult(
            stamp=Stamp.CANNOT_VERIFY,
            value={"account_name": account_name, "stage": deal["stage"], "found": True},
            answer_template=(
                f"{account_name} ({deal['deal_id']}) is Closed Lost, but "
                "loss_reason is empty in the source data. No cause is "
                "recorded, so none is reported."
            ),
            receipt=Receipt(
                metric="deal_reason",
                definition=semantic.METRIC_DEFINITIONS["deal_reason"],
                sql=sql,
                assumptions=assumptions,
                rows=rows,
                row_count="1 matching deal record; loss_reason empty.",
            ),
            interpretation={"intent": "deal_reason", "account_name": account_name},
        )

    return ToolResult(
        stamp=Stamp.VERIFIED,
        value={
            "account_name": account_name,
            "stage": deal["stage"],
            "loss_reason": loss_reason,
            "found": True,
        },
        answer_template=f"{account_name} was lost to: {loss_reason}.",
        receipt=Receipt(
            metric="deal_reason",
            definition=semantic.METRIC_DEFINITIONS["deal_reason"],
            sql=sql,
            assumptions=assumptions,
            rows=rows,
            row_count="1 matching deal record.",
        ),
        interpretation={"intent": "deal_reason", "account_name": account_name},
    )


# ── list_supported_questions ────────────────────────────────────────────────

SUPPORTED_QUESTIONS: list[dict[str, str]] = [
    {
        "tool": "get_segment_attainment",
        "example": "How is Enterprise tracking against quota this quarter?",
    },
    {
        "tool": "get_reps_at_risk",
        "example": "Which reps are at risk of missing quota?",
    },
    {
        "tool": "get_pipeline_value",
        "example": "What's our open pipeline closing before end of Q1?",
    },
    {
        "tool": "get_deal_reason",
        "example": "Why did we lose the Ironbridge deal?",
    },
]


def list_supported_questions() -> ToolResult:
    return ToolResult(
        stamp=Stamp.VERIFIED,
        value={"supported": SUPPORTED_QUESTIONS},
        answer_template=(
            "I can answer questions about segment attainment, reps at risk, "
            "open pipeline value, and stored loss reasons — nothing else."
        ),
        receipt=Receipt(
            metric="list_supported_questions",
            definition="Static capability manifest of the five governed tools.",
            sql="-- static manifest; no query executed",
            assumptions=[],
            rows=[],
            row_count="n/a — static manifest.",
        ),
        interpretation={"intent": "list_supported_questions"},
    )
