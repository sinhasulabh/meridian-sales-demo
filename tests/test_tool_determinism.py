"""Tier A — hard deploy gate (spec §12). No LLM, no network.

Calls the actual MCP tool surface (mcp_server/server.py), not the raw
governed functions directly — this is what proves the MCP wrapping layer
didn't lose or mutate a figure on the way out. Gate rule: this file green,
or no deploy.
"""

import asyncio
from pathlib import Path

import pytest
import yaml

from mcp_server.server import mcp

CASES = yaml.safe_load((Path(__file__).parent / "golden_tool_evals.yaml").read_text())["cases"]


def _call(tool: str, args: dict) -> dict:
    result = asyncio.run(mcp.call_tool(tool, args))
    assert not result.is_error, f"{tool}({args}) returned a tool error: {result.content}"
    return result.structured_content


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_golden_case(case):
    payload = _call(case["tool"], case["args"])
    assert payload["stamp"] == case["expect_stamp"], payload

    for key, expected in case.get("expect_value", {}).items():
        actual = payload["value"].get(key)
        if isinstance(expected, float):
            assert actual == pytest.approx(expected), f"{key}: {actual} != {expected}"
        else:
            assert actual == expected, f"{key}: {actual!r} != {expected!r}"

    for key, forbidden in case.get("expect_not_value", {}).items():
        assert payload["value"].get(key) != forbidden, f"{key} leaked unscoped value {forbidden}"


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_determinism_same_call_twice_is_identical(case):
    first = _call(case["tool"], case["args"])
    second = _call(case["tool"], case["args"])
    assert first == second


def test_scoped_rep_cannot_retrieve_org_level_figure_by_any_phrasing():
    """The filter lives in query construction, not the prompt (§12)."""
    scoped = _call("get_segment_attainment", {"segment": "Enterprise", "viewer": "REP-02"})
    leadership = _call("get_segment_attainment", {"segment": "Enterprise", "viewer": "LEADERSHIP"})
    assert scoped["value"]["won"] != leadership["value"]["won"]
    assert scoped["value"]["won"] == 340_000


def test_every_receipt_carries_the_literal_executed_sql_or_is_static():
    for case in CASES:
        payload = _call(case["tool"], case["args"])
        sql = payload["receipt"]["sql"]
        assert sql, "receipt.sql must never be empty"


def test_ironbridge_receipt_shows_empty_field_not_a_reason():
    payload = _call("get_deal_reason", {"account_name": "Ironbridge", "viewer": "LEADERSHIP"})
    assert payload["stamp"] == "cannot_verify"
    assert "loss_reason" not in payload["value"]
    row = payload["receipt"]["rows"][0]
    assert row["deal_id"] == "OPP-008"
    assert not row["loss_reason"]
