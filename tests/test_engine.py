"""Metric unit tests vs. known figures (spec Appendix A). No LLM, no MCP.

These pin the governed tier to ground truth. If a future change to
`governed/engine.py` or the underlying CSVs moves one of these numbers,
this file — not a hard-coded constant somewhere in app logic — is what
catches it.
"""

from governed.engine import (
    get_deal_reason,
    get_pipeline_value,
    get_reps_at_risk,
    get_segment_attainment,
    list_supported_questions,
)
from governed.models import LEADERSHIP, Stamp


def test_enterprise_attainment():
    r = get_segment_attainment("Enterprise", LEADERSHIP)
    assert r.stamp == Stamp.ASSUMPTION
    assert r.value["won"] == 2_050_000
    assert r.value["quota"] == 3_500_000
    assert r.value["attainment_pct"] == 58.6
    assert r.value["open_pipeline"] == 2_775_000


def test_mid_market_attainment():
    r = get_segment_attainment("Mid-Market", LEADERSHIP)
    assert r.stamp == Stamp.ASSUMPTION
    assert r.value["won"] == 1_100_000
    assert r.value["quota"] == 1_950_000
    assert r.value["attainment_pct"] == 56.4


def test_smb_attainment():
    r = get_segment_attainment("SMB", LEADERSHIP)
    assert r.stamp == Stamp.ASSUMPTION
    assert r.value["won"] == 275_000
    assert r.value["quota"] == 470_000
    assert r.value["attainment_pct"] == 58.5


def test_reps_at_risk_default_threshold():
    r = get_reps_at_risk(viewer=LEADERSHIP)
    assert r.stamp == Stamp.ASSUMPTION
    assert r.value["total_reps"] == 10
    assert r.value["at_risk_count"] == 7

    by_name = {row["rep_name"]: row["attainment_pct"] for row in r.value["reps"]}
    expected = {
        "Kevin Marsh": 34.6,
        "Ryan Cole": 38.6,
        "Marcus Rivera": 40.0,
        "Tom Bradley": 44.0,
        "Sarah Chen": 57.8,
        "James Okafor": 60.0,
        "Danielle Torres": 64.6,
        "Priya Patel": 74.7,
        "Lisa Park": 76.0,
        "Aisha Williams": 86.7,
    }
    assert by_name == expected

    at_risk_names = {row["rep_name"] for row in r.value["reps"] if row["at_risk"]}
    assert at_risk_names == {
        "Kevin Marsh",
        "Ryan Cole",
        "Marcus Rivera",
        "Tom Bradley",
        "Sarah Chen",
        "James Okafor",
        "Danielle Torres",
    }


def test_pipeline_value_close_before_q1_end():
    r = get_pipeline_value(close_before="2026-03-31", viewer=LEADERSHIP)
    assert r.stamp == Stamp.ASSUMPTION
    assert r.value["pipeline_value"] == 1_301_000


def test_pipeline_value_total_unfiltered_is_verified():
    r = get_pipeline_value(viewer=LEADERSHIP)
    assert r.stamp == Stamp.VERIFIED
    assert r.value["pipeline_value"] == 4_311_000


def test_pipeline_value_enterprise_segment_context_figure():
    r = get_pipeline_value(segment="Enterprise", viewer=LEADERSHIP)
    assert r.stamp == Stamp.ASSUMPTION
    assert r.value["pipeline_value"] == 2_775_000


def test_ironbridge_refuses_without_inventing_a_reason():
    r = get_deal_reason("Ironbridge", LEADERSHIP)
    assert r.stamp == Stamp.CANNOT_VERIFY
    assert r.value["found"] is True
    assert "loss_reason" not in r.value
    assert r.receipt.rows[0]["deal_id"] == "OPP-008"
    assert r.receipt.rows[0]["loss_reason"] in (None, "")


def test_fulcrum_returns_stored_reason():
    r = get_deal_reason("Fulcrum Enterprises", LEADERSHIP)
    assert r.stamp == Stamp.VERIFIED
    assert r.value["loss_reason"] == "Competitor - Salesforce"
    assert r.receipt.rows[0]["deal_id"] == "OPP-009"


def test_deal_reason_unknown_account_is_cannot_verify_not_error():
    r = get_deal_reason("Definitely Not A Real Company", LEADERSHIP)
    assert r.stamp == Stamp.CANNOT_VERIFY
    assert r.value["found"] is False


def test_deal_reason_open_deal_states_current_stage():
    r = get_deal_reason("Stratford Dynamics", LEADERSHIP)
    assert r.stamp == Stamp.VERIFIED
    assert r.value["stage"] != "Closed Lost"
    assert "loss reason" in r.answer_template.lower()


def test_determinism_same_call_same_result():
    r1 = get_segment_attainment("Enterprise", LEADERSHIP)
    r2 = get_segment_attainment("Enterprise", LEADERSHIP)
    assert r1 == r2


def test_receipt_sql_is_the_literal_parameterized_query():
    r = get_segment_attainment("Enterprise", LEADERSHIP)
    assert "?" in r.receipt.sql
    assert "segment" in r.receipt.sql.lower()


def test_list_supported_questions():
    r = list_supported_questions()
    assert r.stamp == Stamp.VERIFIED
    tools = {q["tool"] for q in r.value["supported"]}
    assert tools == {
        "get_segment_attainment",
        "get_reps_at_risk",
        "get_pipeline_value",
        "get_deal_reason",
    }
