"""Phase 2 sanity tests on a small dataset (the same generator as the 10k run)."""
import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from yottaflex import config, ids, labels
from yottaflex.dates import months_between
from yottaflex.generate import generate_dataset
from yottaflex.generate.masters import MIN_EMPLOYEES

N = 600


@pytest.fixture(scope="module")
def ds():
    return generate_dataset(N, config.SEED, inject_anomalies=False)   # clean baseline


@pytest.fixture(scope="module")
def injected_ds():
    return generate_dataset(N, config.SEED, inject_anomalies=True)


@pytest.fixture(scope="module")
def T(ds):
    return ds.tables


def _digest(tables):
    h = hashlib.sha256()
    for name in sorted(tables):
        h.update(tables[name].to_csv(index=False, lineterminator="\n", date_format="%Y-%m-%d",
                                     float_format="%.10g").encode())
    return h.hexdigest()


def test_same_seed_is_reproducible(ds):
    assert _digest(generate_dataset(N, config.SEED, inject_anomalies=False).tables) == _digest(ds.tables)


def test_different_seed_changes_data(ds):
    assert _digest(generate_dataset(N, config.SEED + 1, inject_anomalies=False).tables) != _digest(ds.tables)


def test_scale_guard():
    with pytest.raises(ValueError):
        generate_dataset(MIN_EMPLOYEES - 1)


def test_row_counts_and_masters(T):
    assert len(T["employee"]) == N
    assert len(T["role"]) == 35 and len(T["compensation_band"]) == 105
    assert len(T["attrition_outcome"]) == N                       # 1:1 with employee
    assert (T["tenure_snapshot"].groupby("employee_id").size() >= 1).all()
    assert len(T["tenure_snapshot"]) == len(T["engagement_survey"]) == len(T["workload_snapshot"])


def test_primary_keys_unique_and_well_formed(T):
    kinds = {"role": "role", "compensation_band": "band", "employee": "employee", "team": "team",
             "employee_team_assignment": "assignment", "tenure_snapshot": "snapshot",
             "engagement_survey": "survey", "workload_snapshot": "workload",
             "promotion_history": "promotion", "attrition_outcome": "outcome", "intervention": "intervention"}
    for table, kind in kinds.items():
        pk = T[table].iloc[:, 0]
        assert pk.is_unique, table
        assert all(ids.is_valid(kind, v) for v in pk), table


def test_foreign_keys_resolve(T):
    E, S, R, TM = T["employee"], T["tenure_snapshot"], T["role"], T["team"]
    assert E["initial_role_id"].isin(R["role_id"]).all()
    assert TM["manager_employee_id"].isin(E["employee_id"]).all()
    assert S["employee_id"].isin(E["employee_id"]).all() and S["role_id"].isin(R["role_id"]).all()
    assert S["team_id"].isin(TM["team_id"]).all()
    for child in ("engagement_survey", "workload_snapshot"):
        c = T[child]
        assert c["snapshot_id"].is_unique and c["snapshot_id"].isin(S["snapshot_id"]).all()
    I = T["intervention"]
    assert I["trigger_snapshot_id"].isin(S["snapshot_id"]).all()
    assert I["reviewed_by_employee_id"].dropna().isin(E["employee_id"]).all()
    assert T["promotion_history"]["to_role_id"].isin(R["role_id"]).all()


def test_attrition_within_documented_bounds(ds):
    m = ds.meta
    assert abs(m["voluntary_attrition_rate"] - config.TARGET_VOLUNTARY_ATTRITION) < 0.015
    lo, hi = config.TOTAL_ATTRITION_BOUNDS
    assert lo <= m["voluntary_attrition_rate"] + m["involuntary_attrition_rate"] <= hi


def test_derived_values_reconcile(T):
    S = T["tenure_snapshot"].merge(T["employee"][["employee_id", "hire_date"]], on="employee_id")
    got = months_between(S["hire_date"].to_numpy("datetime64[D]"), S["snapshot_date"].to_numpy("datetime64[D]"))
    assert (got == S["tenure_months"].to_numpy()).all()
    W = T["workload_snapshot"]
    assert np.allclose(W["overtime_hours_quarter"], np.maximum(0, W["avg_weekly_hours"] - 40) * 13, atol=0.06)
    idx = np.clip(100 * (0.55 * (W["avg_weekly_hours"] - 35) / 20 + 0.30 * W["active_project_count"] / 8
                         + 0.15 * W["on_call_days"] / 20), 0, 100)
    assert np.allclose(W["workload_index"], idx, atol=0.06)
    assert (W["high_load_flag"] == (W["workload_index"] >= 65)).all()
    SV = T["engagement_survey"]
    items = SV[["q_manager_support", "q_growth_opportunity", "q_workload_sustainable",
                "q_recognition", "q_intent_to_stay"]].astype(float)
    assert (items.notna().sum(axis=1) == SV["items_answered"]).all()
    expect = 100 * (items.mean(axis=1) - 1) / 4
    ok = SV["engagement_score"].notna()
    assert np.allclose(SV.loc[ok, "engagement_score"], expect[ok], atol=0.06)
    P = T["promotion_history"]
    assert np.allclose(P["salary_change_pct"], 100 * (P["new_base_salary_annual"] / P["prior_base_salary_annual"] - 1), atol=0.006)


def test_missing_surveys_are_null_not_negative(T):
    SV = T["engagement_survey"]
    sk = SV["response_status"] == "Skipped"
    assert 0.10 < sk.mean() < 0.30
    assert SV.loc[sk, "engagement_score"].isna().all()
    assert SV.loc[sk, "items_answered"].eq(0).all()
    assert SV.loc[SV["response_status"] == "Responded", "items_answered"].eq(5).all()


def test_lifecycle_and_date_ordering(T):
    S, O = T["tenure_snapshot"], T["attrition_outcome"].set_index("employee_id")
    last = S.groupby("employee_id")["snapshot_date"].max()
    first = S.groupby("employee_id")["snapshot_date"].min()
    term = O["termination_date"].reindex(last.index)
    gone = term.notna()
    assert (last[gone] < term[gone]).all() and (first[gone] < term[gone]).all()
    exited = O["final_status"] != "Active"
    assert O.loc[exited, "termination_date"].notna().all() and O.loc[~exited, "termination_date"].isna().all()
    assert O.loc[O["final_status"] != "Exited_Voluntary", "termination_reason_category"].isna().all()
    A = T["employee_team_assignment"].sort_values(["employee_id", "effective_from"])
    assert (A["effective_to"].dropna() >= A.loc[A["effective_to"].notna(), "effective_from"]).all()
    prev_end = A.groupby("employee_id")["effective_to"].shift(1)
    nxt = A["effective_from"]
    cont = prev_end.notna()
    assert ((prev_end[cont] + pd.Timedelta(days=1)) == nxt[cont]).all()       # contiguous, no overlap
    assert (A.groupby("employee_id").head(1)["change_reason"] == "Hire").all()


def test_label_is_derived_from_termination_facts(T):
    O, S = T["attrition_outcome"], T["tenure_snapshot"]
    again = labels.labels_for_cutoff(O, S, config.CUTOFFS["test"], config.HORIZON_ENDS["test"])
    stored = O.set_index("employee_id")["voluntary_attrition_label"]
    pd.testing.assert_series_equal(again.astype("Int64"), stored.astype("Int64"), check_names=False)
    assert (stored == 1).sum() > 0


def test_baseline_has_no_future_information(T):
    for name in ("tenure_snapshot", "workload_snapshot"):
        rec = pd.to_datetime(T[name]["recorded_at"]).dt.tz_localize(None).dt.normalize()
        assert (rec <= T["tenure_snapshot"]["snapshot_date"]).all()
    S = T["tenure_snapshot"].set_index("snapshot_id")
    SV = T["engagement_survey"]
    rec = pd.to_datetime(SV["recorded_at"]).dt.tz_localize(None).dt.normalize()
    assert (rec <= SV["snapshot_id"].map(S["snapshot_date"])).all()


def test_interventions_respect_review_and_lifecycle(T):
    I = T["intervention"]
    sig = I[I["trigger_source"] == "Signal_Flagged"]
    assert len(I) > 0 and len(sig) > 0
    assert sig["signal_score"].between(0, 1).all()
    assert sig["signal_top_factors"].notna().all()
    assert all(json.loads(s) for s in sig["signal_top_factors"])
    assert (sig["review_status"] != "Not_Required").all()
    done = sig[sig["status"].isin(["Conducted", "Closed"])]
    assert (done["review_status"] == "Approved").all() and done["reviewed_by_employee_id"].notna().all()
    assert I.loc[I["trigger_source"] != "Signal_Flagged", "review_status"].eq("Not_Required").all()
    hr = T["employee"].merge(T["role"], left_on="initial_role_id", right_on="role_id").set_index("employee_id")["job_family"]
    rev = I["reviewed_by_employee_id"].dropna()
    assert (rev.map(hr) == "People_HR").all()
    assert (I["reviewed_date"].dropna() >= I.loc[I["reviewed_date"].notna(), "proposed_date"]).all()
    c = I[I["conducted_date"].notna()]
    assert (c["conducted_date"] > c["proposed_date"]).all()
    assert (c["hazard_multiplier"] < 1.0).any() and (I.loc[I["conducted_date"].isna(), "hazard_multiplier"] == 1.0).all()
    O = T["attrition_outcome"].set_index("employee_id")["termination_date"]
    term = c["employee_id"].map(O)
    assert (c["conducted_date"] <= term.fillna(pd.Timestamp("2100-01-01"))).all()


def test_benign_and_exception_cases_exist(T):
    W, A, SV = T["workload_snapshot"], T["employee_team_assignment"], T["engagement_survey"]
    assert (W["high_load_flag"] & W["planned_peak_flag"]).sum() > 0     # benign planned peaks
    assert (A["change_reason"] != "Hire").sum() > 0                      # internal transfers
    assert (SV["response_status"] == "Skipped").sum() > 0                # missing surveys
    assert (T["promotion_history"]["event_type"] == "Lateral_Move").sum() > 0


def test_no_sensitive_columns_present(T):
    banned = {"age", "gender", "ethnicity", "religion", "caste", "nationality", "disability",
              "marital_status", "home_location", "pin_code", "name"}
    for name, df in T.items():
        assert not banned & {c.lower() for c in df.columns}, name


def test_injected_ground_truth_matches_changed_and_inserted_rows(injected_ds):
    tables, baseline, truth = injected_ds.tables, injected_ds.baseline, injected_ds.ground_truth
    assert truth is not None
    assert truth["gt_id"].is_unique
    assert set(truth["expected_decision"]) == {"flag", "do_not_flag"}
    assert set(truth["issue_type"]) == set(config.ISSUE_TYPES)
    assert (truth["expected_decision"] == truth["is_injected"].map(
        {True: "flag", False: "do_not_flag"})).all()

    for row in truth.itertuples(index=False):
        table = tables[row.entity]
        primary_key = table.columns[0]
        current = table.set_index(primary_key).loc[row.record_id]
        original_table = baseline[row.entity]
        original_keys = set(original_table[primary_key])
        if row.is_injected and row.field == "(inserted row)":
            assert row.record_id not in original_keys
            assert row.record_id in set(table[primary_key])
        elif row.is_injected:
            assert row.record_id in original_keys
            original = json.loads(row.original_value)
            assert set(original) == set(row.field.split(", "))
            before = original_table.set_index(primary_key).loc[row.record_id]
            changed = False
            for field, value in original.items():
                baseline_value = before[field]
                if pd.isna(baseline_value):
                    assert value is None
                elif isinstance(baseline_value, pd.Timestamp):
                    assert value == str(baseline_value.date())
                else:
                    assert value == baseline_value
                current_value = current[field]
                changed |= (pd.isna(baseline_value) and not pd.isna(current_value))
                changed |= (not pd.isna(baseline_value) and pd.isna(current_value))
                if not pd.isna(baseline_value) and not pd.isna(current_value):
                    changed |= current_value != baseline_value
            assert changed, f"ground-truth row does not describe a change: {row}"
        else:
            assert not row.field
            assert pd.isna(row.original_value)
            before = original_table.set_index(primary_key).loc[row.record_id]
            pd.testing.assert_series_equal(current, before, check_names=False, check_dtype=False)