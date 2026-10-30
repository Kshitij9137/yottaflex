"""Deterministic, zero-padded ID helpers.

IDs are pure functions of their inputs: no randomness, no clocks. Counters are
supplied by the caller in sorted order, which keeps generation reproducible.
"""
from __future__ import annotations

import re
from datetime import date

from .config import QUARTERS

_QUARTER = r"20\d{2}Q[1-4]"

PATTERNS: dict[str, re.Pattern[str]] = {
    "employee": re.compile(r"^EMP-\d{6}$"),
    "snapshot": re.compile(rf"^SNAP-EMP-\d{{6}}-{_QUARTER}$"),
    "survey": re.compile(r"^SURV-20\d{2}-\d{6}$"),
    "intervention": re.compile(r"^INT-20\d{2}-\d{6}$"),
    "outcome": re.compile(r"^OUT-EMP-\d{6}-20\d{2}$"),
    "role": re.compile(r"^ROLE-\d{3}$"),
    "team": re.compile(r"^TEAM-\d{4}$"),
    "band": re.compile(r"^BAND-\d{3}-20\d{2}$"),
    "workload": re.compile(rf"^WKL-EMP-\d{{6}}-{_QUARTER}$"),
    "promotion": re.compile(r"^PRM-\d{6}$"),
    "assignment": re.compile(r"^ASG-\d{6}$"),
    "ground_truth": re.compile(r"^GT-\d{6}$"),
}
_QUARTER_RE = re.compile(rf"^{_QUARTER}$")
_QUARTER_END = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}


def is_valid(kind: str, value: str) -> bool:
    """True if `value` matches the ID format for entity `kind`."""
    return bool(PATTERNS[kind].match(value))


def _counter(n: int, width: int, max_value: int | None = None) -> str:
    if isinstance(n, bool) or not isinstance(n, int):
        raise TypeError(f"counter must be int, got {type(n).__name__}")
    limit = max_value if max_value is not None else 10**width - 1
    if not 1 <= n <= limit:
        raise ValueError(f"counter {n} out of range 1..{limit}")
    return str(n).zfill(width)


def _require(kind: str, value: str) -> str:
    if not is_valid(kind, value):
        raise ValueError(f"invalid {kind} id: {value!r}")
    return value


def _year(year: int) -> str:
    if not 2000 <= year <= 2099:
        raise ValueError(f"year out of range: {year}")
    return str(year)


# --- Quarter helpers --------------------------------------------------------
def quarter_label(d: date) -> str:
    """date -> 'YYYYQn'."""
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def quarter_end(label: str) -> date:
    """'YYYYQn' -> last calendar day of that quarter."""
    if not _QUARTER_RE.match(label):
        raise ValueError(f"invalid quarter label: {label!r}")
    month, day = _QUARTER_END[int(label[-1])]
    return date(int(label[:4]), month, day)


def window_quarters() -> tuple[str, ...]:
    return QUARTERS


# --- ID builders ------------------------------------------------------------
def employee_id(n: int) -> str:
    return f"EMP-{_counter(n, 6)}"


def employee_number(emp_id: str) -> int:
    return int(_require("employee", emp_id).split("-")[1])


def snapshot_id(emp_id: str, quarter: str) -> str:
    _require("employee", emp_id)
    if not _QUARTER_RE.match(quarter):
        raise ValueError(f"invalid quarter label: {quarter!r}")
    return f"SNAP-{emp_id}-{quarter}"


def workload_id(emp_id: str, quarter: str) -> str:
    _require("employee", emp_id)
    if not _QUARTER_RE.match(quarter):
        raise ValueError(f"invalid quarter label: {quarter!r}")
    return f"WKL-{emp_id}-{quarter}"


def survey_id(year: int, n: int) -> str:
    return f"SURV-{_year(year)}-{_counter(n, 6)}"


def intervention_id(year: int, n: int) -> str:
    return f"INT-{_year(year)}-{_counter(n, 6)}"


def outcome_id(emp_id: str, year: int) -> str:
    _require("employee", emp_id)
    return f"OUT-{emp_id}-{_year(year)}"


def role_id(n: int) -> str:
    return f"ROLE-{_counter(n, 3)}"


def team_id(n: int) -> str:
    return f"TEAM-{_counter(n, 4)}"


def band_id(role: str, fy_start_year: int) -> str:
    _require("role", role)
    return f"BAND-{role.split('-')[1]}-{_year(fy_start_year)}"


def promotion_id(n: int) -> str:
    return f"PRM-{_counter(n, 6)}"


def assignment_id(n: int) -> str:
    return f"ASG-{_counter(n, 6)}"


def ground_truth_id(n: int) -> str:
    return f"GT-{_counter(n, 6)}"