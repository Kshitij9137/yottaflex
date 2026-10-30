from datetime import date

import pytest

from yottaflex import config, ids


def test_brief_examples_match_exactly():
    assert ids.employee_id(1) == "EMP-000001"
    assert ids.snapshot_id("EMP-000001", "2026Q1") == "SNAP-EMP-000001-2026Q1"
    assert ids.survey_id(2026, 1) == "SURV-2026-000001"
    assert ids.intervention_id(2026, 1) == "INT-2026-000001"
    assert ids.outcome_id("EMP-000001", 2026) == "OUT-EMP-000001-2026"


def test_other_ids_and_patterns():
    assert ids.role_id(3) == "ROLE-003"
    assert ids.team_id(12) == "TEAM-0012"
    assert ids.band_id("ROLE-003", 2025) == "BAND-003-2025"
    assert ids.workload_id("EMP-000010", "2025Q4") == "WKL-EMP-000010-2025Q4"
    assert ids.promotion_id(7) == "PRM-000007"
    assert ids.assignment_id(8) == "ASG-000008"
    assert ids.ground_truth_id(9) == "GT-000009"
    for kind, value in {
        "employee": ids.employee_id(10_000),
        "snapshot": ids.snapshot_id("EMP-010000", "2025Q2"),
        "survey": ids.survey_id(2025, 70_000),
        "intervention": ids.intervention_id(2025, 12),
        "outcome": ids.outcome_id("EMP-010000", 2026),
        "workload": ids.workload_id("EMP-010000", "2025Q2"),
    }.items():
        assert ids.is_valid(kind, value)


def test_ids_are_deterministic_and_zero_padded():
    assert ids.employee_id(42) == ids.employee_id(42)
    assert len(ids.employee_id(1)) == len("EMP-000001")
    assert ids.employee_number("EMP-000042") == 42


@pytest.mark.parametrize("bad", [0, -1, 1_000_000])
def test_employee_counter_bounds(bad):
    with pytest.raises(ValueError):
        ids.employee_id(bad)


def test_rejects_wrong_types_and_formats():
    with pytest.raises(TypeError):
        ids.employee_id("1")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        ids.employee_id(True)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ids.snapshot_id("EMP-1", "2026Q1")
    with pytest.raises(ValueError):
        ids.snapshot_id("EMP-000001", "2026Q5")
    assert not ids.is_valid("employee", "EMP-12345")


def test_quarter_helpers():
    assert ids.quarter_label(date(2025, 3, 31)) == "2025Q1"
    assert ids.quarter_label(date(2024, 10, 1)) == "2024Q4"
    assert ids.quarter_end("2026Q1") == date(2026, 3, 31)
    assert ids.quarter_end("2024Q4") == date(2024, 12, 31)


def test_window_is_24_months_of_8_quarters():
    assert len(config.QUARTERS) == 8
    assert ids.quarter_label(config.WINDOW_START) == config.QUARTERS[0]
    assert ids.quarter_label(config.WINDOW_END) == config.QUARTERS[-1]
    assert ids.quarter_end(config.QUARTERS[-1]) == config.WINDOW_END


def test_temporal_split_is_leak_free():
    order = ["train", "validation", "test"]
    for a, b in zip(order, order[1:]):
        # earlier labels are fully observed before the next cutoff
        assert config.HORIZON_ENDS[a] <= config.CUTOFFS[b]
        assert config.CUTOFFS[a] < config.CUTOFFS[b]
    for name in order:
        assert config.CUTOFFS[name] < config.HORIZON_ENDS[name]
        assert config.CUTOFFS[name] >= config.WINDOW_START
    assert config.HORIZON_ENDS["test"] <= config.WINDOW_END
    # cutoffs sit on quarter ends
    for d in config.CUTOFFS.values():
        assert ids.quarter_end(ids.quarter_label(d)) == d


def test_attrition_target_inside_allowed_bounds():
    lo, hi = config.TOTAL_ATTRITION_BOUNDS
    assert lo <= config.TARGET_VOLUNTARY_ATTRITION <= hi