"""Unit tests for argument validation and access-scope resolution (INV-5, INV-10)."""

import pytest

from governed import gates
from governed.models import LEADERSHIP, Segment

KNOWN_REPS = frozenset({"REP-01", "REP-02", "REP-03"})


def test_validate_segment_accepts_known_values():
    assert gates.validate_segment("Enterprise") == Segment.ENTERPRISE
    assert gates.validate_segment("Mid-Market") == Segment.MID_MARKET
    assert gates.validate_segment(None) is None


def test_validate_segment_rejects_unknown_value():
    with pytest.raises(gates.GateValidationError):
        gates.validate_segment("Nonexistent")


def test_validate_close_before_rejects_non_iso_date():
    with pytest.raises(gates.GateValidationError):
        gates.validate_close_before("not-a-date")
    assert gates.validate_close_before("2026-03-31") == "2026-03-31"
    assert gates.validate_close_before(None) is None


def test_validate_account_name_rejects_blank():
    with pytest.raises(gates.GateValidationError):
        gates.validate_account_name("   ")
    assert gates.validate_account_name(" Acme ") == "Acme"


def test_validate_threshold_rejects_out_of_range():
    with pytest.raises(gates.GateValidationError):
        gates.validate_threshold(1.5)
    with pytest.raises(gates.GateValidationError):
        gates.validate_threshold(-0.1)
    assert gates.validate_threshold(0.7) == 0.7


# ── Access scoping (INV-10) ─────────────────────────────────────────────────


def test_resolve_viewer_leadership_is_unrestricted():
    scope = gates.resolve_viewer(LEADERSHIP, KNOWN_REPS)
    assert scope.mode == "leadership"
    predicate, params = gates.scope_predicate(scope)
    assert predicate == ""
    assert params == []


def test_resolve_viewer_known_rep_is_scoped():
    scope = gates.resolve_viewer("REP-02", KNOWN_REPS)
    assert scope.mode == "rep"
    assert scope.rep_id == "REP-02"
    predicate, params = gates.scope_predicate(scope)
    assert "rep_id" in predicate
    assert params == ["REP-02"]
    assert "REP-02" in scope.note


@pytest.mark.parametrize("viewer", ["UNKNOWN", "", "  ", None, "rep-02", "DROP TABLE deals;"])
def test_resolve_viewer_fails_closed_for_anything_else(viewer):
    scope = gates.resolve_viewer(viewer, KNOWN_REPS)
    assert scope.mode == "denied"
    predicate, params = gates.scope_predicate(scope)
    assert predicate == ""
    assert params == []


def test_assert_sum_matches_passes_on_consistent_data():
    gates.assert_sum_matches(30, [{"deal_value": 10}, {"deal_value": 20}], "deal_value")


def test_assert_sum_matches_raises_on_drift():
    with pytest.raises(AssertionError):
        gates.assert_sum_matches(999, [{"deal_value": 10}, {"deal_value": 20}], "deal_value")
