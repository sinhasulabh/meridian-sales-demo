"""Tier B — orchestrator faithfulness evals (spec §12). Needs a live Claude
call, so every case is skipped unless `ANTHROPIC_API_KEY` is set (as it
will be in the CI job that gates the agent-service deploy, but not
necessarily in a local run of the full suite).

These assert the *final agent answer* honors the invariants that a
governed-tool test alone can't check: that the model relayed a figure
verbatim, preserved a stamp, attached a receipt, and — the canonical
regression case — invented no cause for Ironbridge.
"""

from __future__ import annotations

import os
import re

import pytest
from starlette.testclient import TestClient

pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="Tier B calls the real Claude model; needs ANTHROPIC_API_KEY",
)


@pytest.fixture(scope="module")
def client():
    from agent.server import app

    with TestClient(app) as c:
        yield c


def _ask(client: TestClient, question: str, viewer: str = "LEADERSHIP") -> dict:
    resp = client.post("/run", json={"question": question, "viewer": viewer})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_ironbridge_final_answer_invents_no_cause(client):
    result = _ask(client, "Why did we lose Ironbridge?")
    assert result["stamp"] == "cannot_verify"
    assert result["receipts"], "expected at least one receipt attached"
    lowered = result["answer"].lower()
    assert "ironbridge" in lowered
    invented_cause_phrases = [
        "probably",
        "likely due to",
        "most likely",
        "because of price",
        "competitor took",
    ]
    assert not any(phrase in lowered for phrase in invented_cause_phrases), (
        f"agent appears to have invented a cause: {result['answer']!r}"
    )


def test_forecast_question_is_refused_as_out_of_scope(client):
    # Refusal phrasing itself varies run to run (Claude isn't sampled
    # deterministically), so this checks the invariant that actually
    # matters rather than exact wording: there is no governed tool for
    # "next quarter," so any dollar figure in the answer would necessarily
    # be model-authored (INV-1) rather than out-of-scope prose.
    result = _ask(client, "What will Enterprise revenue be next quarter?")
    assert not re.search(r"\$[\d,]{4,}", result["answer"]), (
        f"agent appears to have invented a forecast figure: {result['answer']!r}"
    )
    for receipt in result["receipts"]:
        assert receipt["metric"] != "forecast"

    lowered = result["answer"].lower()
    supported_words = [
        "attainment",
        "pipeline",
        "at risk",
        "loss reason",
        "quota",
        "closed-won",
        "closed won",
        "q1 2026",
        "q1",
        "current quarter",
        "this quarter",
    ]
    called_capability_tool = any(
        r["metric"] == "list_supported_questions" for r in result["receipts"]
    )
    assert called_capability_tool or any(word in lowered for word in supported_words), (
        f"agent didn't redirect to a supported question: {result['answer']!r}"
    )


def test_segment_attainment_figure_matches_tool_exactly(client):
    result = _ask(client, "How is Enterprise tracking against quota this quarter?")
    assert "58.6" in result["answer"] or any(
        "58.6" in str(v) for r in result["receipts"] for v in r.get("assumptions", [])
    ) or "2,050,000" in result["answer"]
    assert result["receipts"]
    assert result["receipts"][0]["metric"] == "segment_attainment"


def test_compound_question_calls_both_tools_and_self_computes_nothing(client):
    result = _ask(client, "Compare Enterprise and Mid-Market attainment this quarter.")
    metrics_seen = {r["metric"] for r in result["receipts"]}
    assert metrics_seen == {"segment_attainment"}
    assert len(result["receipts"]) >= 2
    assert "58.6" in result["answer"] or "$2,050,000" in result["answer"]
    assert "56.4" in result["answer"] or "$1,100,000" in result["answer"]


def test_access_forwarding_scoped_rep_never_sees_org_level_figure(client):
    result = _ask(
        client, "How is Enterprise tracking against quota this quarter?", viewer="REP-02"
    )
    assert "2,050,000" not in result["answer"]
    assert "58.6" not in result["answer"]
    assert any(
        "REP-02" in a or "scoped" in a.lower()
        for r in result["receipts"]
        for a in r.get("assumptions", [])
    )
