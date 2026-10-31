"""Phase 4 tests: the validator passes clean data, fails broken data, and scores the detectors."""
import inspect

import numpy as np
import pandas as pd
import pytest

from yottaflex import config
from yottaflex.generate import generate_dataset
from yottaflex.generate.__main__ import main as generate_main
from yottaflex.validate import evaluate, passed, rules, run_rules
from yottaflex.validate.__main__ import main as validate_main
from yottaflex.validate.evaluate import INJECTED_TYPES


@pytest.fixture(scope="module")
def clean():
    return generate_dataset(600, config.SEED, inject_anomalies=False).tables


@pytest.fixture(scope="module")
def injected():
    return generate_dataset(1000, config.SEED)


def failing(tables):
    return {r.rule_id for r in run_rules(tables)[1] if r.n_violations}


# ---------------------------------------------------------------- positive results
def test_clean_baseline_passes_every_rule(clean):
    assert failing(clean) == set()


def test_injected_data_is_fully_explained_and_detectors_are_exact(injected):
    ctx, results, flagged = run_rules(injected.tables)
    ev = evaluate(ctx, results, flagged, injected.ground_truth)
    assert ev["unexplained_violations"] == 0, ev["unexplained_violations_by_rule"]
    assert ev["injected_records_not_flagged_by_any_rule"] == 0
    assert ev["gt_records_missing_from_tables"] == 0
    assert ev["decoys_flagged_by_any_rule"] == 0 and ev["decoys_total"] > 0
    assert {d["issue_type"] for d in ev["detectors"]} == set(INJECTED_TYPES)
    assert all(d["precision"] == 1.0 and d["recall"] == 1.0 for d in ev["detectors"])
    assert all(s["recall"] == 1.0 for s in ev["subtypes"])
    assert passed([], ev)
    for n in ev["naive_rules"]:                       # the shortcut rules fall into every decoy trap
        assert n["share_of_decoys_wrongly_flagged"] == 1.0 and n["our_detectors_flag_these_decoys"] == 0


def test_detectors_are_rule_based_and_never_see_the_ground_truth(clean):
    from yottaflex.validate.schema import SCHEMA
    assert "ground_truth" not in SCHEMA                       # the feature-side schema has no ground truth
    ctx = rules.Ctx(clean)
    assert set(ctx.T) == set(SCHEMA)                           # rules only ever see the data tables
    assert {r.maps_to for r in rules.RULES if r.maps_to} == set(INJECTED_TYPES)
    assert "gt" not in inspect.signature(rules.Rule).parameters


def test_rule_count_and_ids_are_unique():
    ids_ = [r.rule_id for r in rules.RULES]
    assert len(ids_) == len(set(ids_)) >= 150


# ---------------------------------------------------------------- mutation tests
def _first(df, mask):
    return df.index[mask][0]


def m_dup_pk(T):
    T["employee"] = pd.concat([T["employee"], T["employee"].iloc[[0]]], ignore_index=True)


def m_bad_format(T):
    T["employee"].at[0, "employee_id"] = "EMP-12"


def m_orphan_fk(T):
    T["tenure_snapshot"].at[0, "role_id"] = "ROLE-999"


def m_enum(T):
    T["employee"].at[0, "employment_type"] = "Intern"


def m_range(T):
    T["workload_snapshot"].at[0, "avg_weekly_hours"] = 99.0


def m_required(T):
    T["employee"].at[0, "hire_date"] = pd.NaT


def m_type(T):
    T["employee"]["hire_date"] = T["employee"]["hire_date"].astype(str)
    T["employee"].at[0, "hire_date"] = "not-a-date"


def m_promo_before_hire(T):
    P, E = T["promotion_history"], T["employee"].set_index("employee_id")
    P.at[0, "effective_date"] = E.at[P.at[0, "employee_id"], "hire_date"] - pd.Timedelta(days=5)


def m_intervention_order(T):
    I = T["intervention"]; i = _first(I, I["conducted_date"].notna())
    I.at[i, "conducted_date"] = I.at[i, "proposed_date"] - pd.Timedelta(days=1)


def m_tenure(T):
    T["tenure_snapshot"].at[3, "tenure_months"] += 1


def m_compa(T):
    T["tenure_snapshot"].at[3, "compa_ratio"] += 0.05


def m_msp(T):
    T["tenure_snapshot"].at[3, "months_since_last_promotion"] += 2


def m_mit(T):
    T["tenure_snapshot"].at[3, "months_in_current_team"] += 2


def m_workload(T):
    T["workload_snapshot"].at[0, "workload_index"] += 5


def m_score(T):
    V = T["engagement_survey"]; i = _first(V, V["response_status"] == "Responded")
    V.at[i, "engagement_score"] += 10


def m_terminate_early(T):
    O = T["attrition_outcome"]; i = _first(O, O["final_status"] != "Active")
    O.at[i, "termination_date"] = pd.Timestamp(config.WINDOW_START) + pd.Timedelta(days=1)


def m_assignment_gap(T):
    A = T["employee_team_assignment"]; i = _first(A, A["change_reason"] != "Hire")
    A.at[i, "effective_from"] += pd.Timedelta(days=3)


def m_status(T):
    I = T["intervention"]; i = _first(I, I["status"] == "Conducted")
    I.at[i, "status"] = "Closed"


def m_dup_natural(T):
    S = T["tenure_snapshot"]; row = S.iloc[[0]].copy(); row["snapshot_id"] = "SNAP-EMP-999999-2025Q1"
    T["tenure_snapshot"] = pd.concat([S, row], ignore_index=True)


def m_drop_survey(T):
    T["engagement_survey"] = T["engagement_survey"].iloc[1:].reset_index(drop=True)


def m_skipped_score(T):
    V = T["engagement_survey"]; V.at[_first(V, V["response_status"] == "Skipped"), "engagement_score"] = 0.0


def m_reviewer(T):
    I, E, R = T["intervention"], T["employee"], T["role"]
    fam = E.set_index("employee_id")["initial_role_id"].map(R.set_index("role_id")["job_family"])
    i = _first(I, I["reviewed_by_employee_id"].notna())
    I.at[i, "reviewed_by_employee_id"] = fam.index[(fam != "People_HR").to_numpy()][0]


def m_label(T):
    O = T["attrition_outcome"]; i = _first(O, O["voluntary_attrition_label"] == 0)
    O.at[i, "voluntary_attrition_label"] = 1


def m_late(T):
    V, S = T["engagement_survey"], T["tenure_snapshot"].set_index("snapshot_id")
    d = S.at[V.at[0, "snapshot_id"], "snapshot_date"] + pd.Timedelta(days=40)
    V.at[0, "recorded_at"] = d.strftime("%Y-%m-%dT%H:%M:%SZ")


def m_salary_jump(T):
    S = T["tenure_snapshot"]; i = _first(S, S["snapshot_quarter"] == "2025Q3")
    S.at[i, "base_salary_annual"] = int(S.at[i, "base_salary_annual"] * 1.5)


def m_chain(T):
    P = T["promotion_history"]; P.at[0, "from_role_id"] = "ROLE-001" if P.at[0, "from_role_id"] != "ROLE-001" else "ROLE-002"


def m_peak(T):
    W = T["workload_snapshot"]; W.at[0, "planned_peak_flag"] = not W.at[0, "planned_peak_flag"]


def m_manager(T):
    E, R, TM = T["employee"], T["role"], T["team"]
    low = E.merge(R, left_on="initial_role_id", right_on="role_id")
    never_promoted = ~low["employee_id"].isin(T["promotion_history"]["employee_id"])   # still level 1 at window start
    new = low.loc[(low["level"] == 1) & never_promoted & (low["hire_date"] < pd.Timestamp(config.WINDOW_START)), "employee_id"].iloc[0]
    TM.at[0, "manager_employee_id"] = new


def m_flag(T):
    S = T["tenure_snapshot"]; S.at[0, "transfer_in_quarter"] = not S.at[0, "transfer_in_quarter"]


def m_band_mid(T):
    T["compensation_band"].at[0, "annual_mid"] += 1000


def m_hazard(T):
    I = T["intervention"]; I.at[_first(I, I["conducted_date"].isna()), "hazard_multiplier"] = 0.8


MUTATIONS = [
    (m_dup_pk, "KEY-PK-UNIQUE:employee"), (m_bad_format, "KEY-PK-FORMAT:employee"),
    (m_orphan_fk, "FK:tenure_snapshot.role_id"), (m_enum, "SCH-ENUM:employee"),
    (m_range, "SCH-RANGE:workload_snapshot"), (m_required, "SCH-REQUIRED:employee"),
    (m_type, "SCH-TYPE:employee"), (m_promo_before_hire, "DATE-PROMOTION-EMPLOYMENT"),
    (m_intervention_order, "DATE-INTERVENTION-ORDER"), (m_tenure, "RECON-TENURE"),
    (m_compa, "RECON-COMPA"), (m_msp, "RECON-MONTHS-SINCE-PROMOTION"), (m_mit, "RECON-MONTHS-IN-TEAM"),
    (m_workload, "RECON-WORKLOAD"), (m_score, "RECON-SURVEY-SCORE"),
    (m_terminate_early, "LIFE-SNAPSHOT-AFTER-EXIT"), (m_assignment_gap, "DATE-ASSIGNMENT"),
    (m_status, "LIFE-INTERVENTION-TRANSITIONS"), (m_dup_natural, "DUP-NATURAL:tenure_snapshot"),
    (m_drop_survey, "CARD-SNAPSHOT-SURVEY-1TO1"), (m_skipped_score, "SURV-SKIPPED-HAS-SCORE"),
    (m_reviewer, "LIFE-REVIEWER"), (m_label, "RECON-LABEL"), (m_late, "TIME-LATE-RECORDED:engagement_survey"),
    (m_salary_jump, "RECON-SALARY-STEP"), (m_chain, "RECON-PROMOTION-CHAIN"), (m_peak, "RECON-PEAK-FLAG"),
    (m_manager, "LIFE-MANAGER"), (m_flag, "RECON-SNAPSHOT-FLAGS"), (m_band_mid, "RECON-BAND-MID"),
    (m_hazard, "LIFE-INTERVENTION-TRANSITIONS"),
]


@pytest.mark.parametrize("mutator,expected", MUTATIONS, ids=[m.__name__ for m, _ in MUTATIONS])
def test_validator_catches_a_single_injected_fault(clean, mutator, expected):
    T = {k: v.copy() for k, v in clean.items()}
    mutator(T)
    assert expected in failing(T), f"{mutator.__name__} was not caught by {expected}"


def test_mutation_leaves_original_untouched(clean):
    assert failing(clean) == set()


# ---------------------------------------------------------------- end to end on exported files
@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    d = tmp_path_factory.mktemp("export")
    assert generate_main(["--n-employees", "600", "--out", str(d)]) == 0
    return d


def test_cli_validates_exported_csv_and_report_is_deterministic(exported, tmp_path):
    r1, r2 = tmp_path / "a.md", tmp_path / "b.md"
    assert validate_main(["--data", str(exported), "--report", str(r1), "--json", str(tmp_path / "a.json")]) == 0
    assert validate_main(["--data", str(exported), "--report", str(r2)]) == 0
    assert r1.read_bytes() == r2.read_bytes()
    text = r1.read_text()
    assert "**Overall: PASS**" in text and "Benign decoys flagged by any rule | 0 of" in text


def test_cli_fails_when_exported_data_is_tampered(exported, tmp_path):
    import shutil
    d = tmp_path / "tampered"; shutil.copytree(exported, d)
    f = d / "attrition_outcome.csv"
    df = pd.read_csv(f, dtype=str, keep_default_na=False, na_values=[""])
    i = df.index[df["voluntary_attrition_label"] == "0"][0]
    df.at[i, "voluntary_attrition_label"] = "1"       # an unlabelled change: not in the ground truth
    df.to_csv(f, index=False, lineterminator="\n")
    assert validate_main(["--data", str(d), "--no-baseline"]) == 1


def test_clean_export_validates_without_ground_truth(tmp_path):
    assert generate_main(["--n-employees", "600", "--no-inject", "--out", str(tmp_path)]) == 0
    assert not (tmp_path / "ground_truth.csv").exists()
    assert validate_main(["--data", str(tmp_path)]) == 0


def test_ground_truth_pointing_at_a_missing_record_fails(injected):
    ctx, results, flagged = run_rules(injected.tables)
    gt = injected.ground_truth.copy()
    gt.loc[0, "record_id"] = "SURV-2099-999999"
    ev = evaluate(ctx, results, flagged, gt)
    assert ev["gt_records_missing_from_tables"] >= 1 and not passed([], ev)