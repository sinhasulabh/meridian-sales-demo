"""Argument validation, viewer-scope resolution, and invariant post-checks.

Two distinct failure modes live here and must stay distinct:

* `GateValidationError` — the caller (agent) passed a bad argument. This is
  an objective, retriable signal (spec §9: "retry only on tool argument
  validation errors, at most once").
* Fail-closed access denial — the *data* is being withheld because the
  viewer identity didn't resolve. This is not a validation error; it is a
  normal `cannot_verify` result (INV-10), because raising here would leak
  the fact that the query was otherwise well-formed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from governed.models import LEADERSHIP, Segment


class GateValidationError(ValueError):
    """Raised when a tool argument fails validation against its enum/schema."""


def validate_segment(value: str | None) -> Segment | None:
    if value is None:
        return None
    try:
        return Segment(value)
    except ValueError as exc:
        allowed = ", ".join(s.value for s in Segment)
        raise GateValidationError(
            f"segment must be one of [{allowed}], got {value!r}"
        ) from exc


def validate_close_before(value: str | None) -> str | None:
    if value is None:
        return None
    import datetime

    try:
        datetime.date.fromisoformat(value)
    except ValueError as exc:
        raise GateValidationError(
            f"close_before must be an ISO date (YYYY-MM-DD), got {value!r}"
        ) from exc
    return value


def validate_account_name(value: str) -> str:
    if not value or not value.strip():
        raise GateValidationError("account_name must be a non-empty string")
    return value.strip()


def validate_threshold(value: float) -> float:
    if not (0.0 <= value <= 1.0):
        raise GateValidationError(f"threshold must be in [0.0, 1.0], got {value!r}")
    return value


# ── Access scoping (INV-10) ─────────────────────────────────────────────────

ViewerMode = Literal["leadership", "rep", "denied"]


@dataclass(frozen=True)
class ViewerScope:
    mode: ViewerMode
    rep_id: str | None = None

    @property
    def note(self) -> str | None:
        if self.mode == "rep":
            return (
                f"Scoped to your deals ({self.rep_id}); org-level figures "
                "are restricted to leadership."
            )
        if self.mode == "denied":
            return "Viewer identity did not resolve; access denied (fail closed)."
        return None


def resolve_viewer(viewer: str | None, known_rep_ids: frozenset[str]) -> ViewerScope:
    """Resolve the call-context `viewer` into an enforceable scope.

    Fails closed: anything that isn't exactly "LEADERSHIP" or a known
    rep_id denies access. Never defaults to unrestricted (INV-10).
    """
    if viewer is None:
        return ViewerScope(mode="denied")
    stripped = viewer.strip()
    if stripped == LEADERSHIP:
        return ViewerScope(mode="leadership")
    if stripped in known_rep_ids:
        return ViewerScope(mode="rep", rep_id=stripped)
    return ViewerScope(mode="denied")


def scope_predicate(scope: ViewerScope, column: str = "rep_id") -> tuple[str, list[str]]:
    """A SQL predicate fragment + bound params enforcing `scope`.

    Built adjacent to the rest of the parameterized SQL, never string-
    interpolated with model output, and unconditionally applied — the model
    never sees or chooses this fragment (INV-10).
    """
    if scope.mode == "rep":
        return f"AND {column} = ?", [scope.rep_id]
    return "", []


# ── Invariant post-check (INV-2 / INV-6) ────────────────────────────────────


def assert_sum_matches(
    value: float, rows: list[dict], key: str, *, tolerance: float = 0.01
) -> None:
    """The headline figure must equal the sum of the rows that produced it.

    Guards against the receipt and the figure silently drifting apart —
    the one thing that would make the receipt a lie.
    """
    row_sum = sum(row[key] for row in rows)
    if abs(row_sum - value) > tolerance:
        raise AssertionError(
            f"invariant violated: value={value} but sum(rows.{key})={row_sum}"
        )
