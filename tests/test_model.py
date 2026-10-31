"""Phase 5 tests: as-of correctness, leak audit, faithful explanations, and the supportive-signal contract."""
import hashlib
import inspect
import json

import numpy as np
import pandas as pd
import pytest

from yottaflex import config
from yottaflex.generate import generate_dataset
from yottaflex.generate.__main__ import main as generate_main
from yottaflex.model import audit, dataset, explain, features, pipeline
from yottaflex.model.__main__ import main as model_main
from yottaflex.model.explain import THEMES, NOT_A_REASON, assert_supportive_framing, contributions
from yottaflex.model.features import FEATURES, build_panel, features_at, typed_tables

N = 1000


@pytest.fixture(scope="module")
def inj():
    return generate_dataset(N, config.SEED)


@pytest.fixture(scope="module")
def clean():
    return generate_dataset(N, config.SEED, inject_anomalies=False)


@pytest.fixture(scope="module")
def prep(inj):
    T = typed_tables(inj.tables)
    return T, build_panel(T)


@pytest.fixture(scope="module")
def R(inj, clean):
    return pipeline.run(inj.tables, clean.tables)


# ------------------------------------------------------------------ as-of correctness
def test_production_features_use_nothing_from_after_the_cutoff(prep):
    T, P = prep
    for split in dataset.SPLITS:
        D = dataset.build_split(P, T, split)
        a = audit.provenance_audit(D, config.CUTOFFS[split])
        assert a["violations"] == 0 and a["rows"] == len(D)


def test_recorded_at_gate_excludes_revised_rows_and_nothing_else(prep):
    T, P = prep
    C = config.CUTOFFS["test"]
    prod = features_at(P, T["intervention"], C)
    loose = features_at(P, T["intervention"], C, check_recorded=False)
    cols = FEATURES
    differs = (prod[cols] != loose[cols]).any(axis=1)
    late = P[(P["sv_rec"].dt.normalize() > P["snapshot_date"]) | (P["w_rec"].dt.normalize() > P["snapshot_date"])]["employee_id"]
    assert differs.sum() > 0 and set(prod.index[differs]) <= set(late)
    pd.testing.assert_frame_equal(prod.loc[~differs, cols], loose.loc[~differs, cols])


def test_skipped_surveys_never_become_scores(prep):
    T, P = prep
    hit = 0
    for split in dataset.SPLITS:
        C = config.CUTOFFS[split]
        a = features_at(P, T["intervention"], C)
        b = features_at(P, T["intervention"], C, sanitize=False)
        hit += int(((b["last_engagement"] == 0) & (a["last_engagement"] != 0)).sum())
    assert hit > 0                                          # the defence is doing real work on this data
    assert features.NEUTRAL_ENGAGEMENT == 60.0


def test_people_who_left_before_the_cutoff_are_never_scored(prep):
    T, P = prep
    O = T["attrition_outcome"].set_index("employee_id")
    for split in dataset.SPLITS:
        C = pd.Timestamp(config.CUTOFFS[split])
        D = dataset.build_split(P, T, split)
        gone = O.index[O["termination_date"].notna() & (O["termination_date"] <= C)]
        assert not set(D.index) & set(gone)


def test_labels_follow_termination_facts_and_the_temporal_split(prep):
    T, P = prep
    O = T["attrition_outcome"].set_index("employee_id")
    for split in dataset.SPLITS:
        C, H = pd.Timestamp(config.CUTOFFS[split]), pd.Timestamp(config.HORIZON_ENDS[split])
        D = dataset.build_split(P, T, split)
        assert (D["cutoff"] == C).all()
        t = O["termination_date"].reindex(D.index)
        expect = ((O["final_status"].reindex(D.index) == "Exited_Voluntary") & (t > C) & (t <= H)).astype(int)
        assert (D["y"] == expect).all()
        assert not (O["final_status"].reindex(D.index).eq("Exited_Involuntary") & (t > C) & (t <= H)).any()
    assert audit.split_audit()["ok"]


# ------------------------------------------------------------------ leak audit
def test_audit_passes_production_and_catches_each_leak(R):
    L = {x["pipeline"]: x for x in R["ladder"]}
    prod = next(v for k, v in L.items() if k.startswith("Production"))
    assert prod["audit"] == "PASS" and prod["provenance_violations"] == 0
    date_only = L["Ignore recorded_at (date-only as-of)"]
    assert date_only["audit"] == "FAIL" and date_only["provenance_violations"] > 0 and date_only["affected_employees"] > 0
    assert date_only["mean_percentile_shift"] > 0                      # revised rows push leavers up
    naive = L["LEAK: latest-value join over all rows"]
    assert naive["audit"] == "FAIL" and naive["provenance_violations"] > 0.5 * R["test"]["n"]
    future = L["LEAK: latest-value join + count of later snapshots"]
    assert future["audit"] == "FAIL" and "future_snapshots" in future["flagged_features"]
    assert future["pr_auc"] > 0.9 and future["pr_auc"] > 5 * prod["pr_auc"]   # the inflation is visible
    stored = L["Use the stored test label instead of recomputing it"]
    assert stored["audit"] == "FAIL" and "disagree" in stored["flagged_features"]


def test_production_matches_clean_baseline_so_defences_work(R):
    L = {x["pipeline"]: x for x in R["ladder"]}
    ref = next(v for k, v in L.items() if k.startswith("Reference"))
    prod = next(v for k, v in L.items() if k.startswith("Production"))
    assert abs(ref["roc_auc"] - prod["roc_auc"]) < 0.03


def test_name_and_forbidden_column_audit():
    assert audit.forbidden_audit(FEATURES)["ok"]
    assert not audit.forbidden_audit(["gender", "last_engagement"])["ok"]
    assert not audit.forbidden_audit(["age_years"])["ok"]
    assert audit.forbidden_audit(["engagement_mean_4q", "manager_support"])["ok"]       # 'age' inside a word is fine
    assert not audit.forbidden_audit(["termination_date"])["ok"]
    assert not audit.forbidden_audit(["issue_type"])["ok"]


def test_univariate_audit_flags_a_perfect_separator():
    y = pd.Series([0] * 50 + [1] * 50)
    X = pd.DataFrame({"honest": np.random.default_rng(0).random(100), "leaky": y * 10 + 1})
    assert list(audit.univariate_audit(X, y, ["honest", "leaky"])["flagged"]) == ["leaky"]


def test_model_code_never_touches_the_ground_truth():
    for mod in (features, dataset, explain, pipeline, audit):
        assert "ground_truth" not in inspect.getsource(mod), mod.__name__


# ------------------------------------------------------------------ explanations
def test_explanations_are_faithful_to_the_model(R):
    m, F = R["model"], R["test_frame"]
    cols = R["design"]["features"]
    contrib = contributions(m, F, cols)
    lr = m.named_steps["logisticregression"]
    assert np.allclose(contrib.sum(axis=1) + lr.intercept_[0], m.decision_function(F[cols]), atol=1e-9)


def test_signals_are_complete_reviewable_and_supportive(R, inj):
    sig, T = R["signals"], typed_tables(inj.tables)
    assert_supportive_framing(sig)
    k = len(sig)
    assert abs(k - round(0.05 * R["test"]["n"])) <= 1
    assert list(sig["rank"]) == list(range(1, k + 1)) and sig["signal_score"].is_monotonic_decreasing
    assert (sig["top_factors_text"].str.strip() != "").all() and sig["explanation_complete"].all()
    assert sig["human_review_required"].all() and not sig["automated_action_allowed"].any()
    assert (sig["review_status"] == "Pending_Review").all() and (sig["reviewed_by_employee_id"].fillna("") == "").all()
    E, Ro, O = T["employee"].set_index("employee_id"), T["role"].set_index("role_id"), T["attrition_outcome"].set_index("employee_id")
    fam = sig["assigned_hr_partner_id"].map(E["initial_role_id"]).map(Ro["job_family"])
    assert (fam == "People_HR").all()
    c = pd.Timestamp(config.CUTOFFS["test"])
    assert (sig["assigned_hr_partner_id"].map(E["hire_date"]) <= c).all()
    assert (sig["assigned_hr_partner_id"].map(O["termination_date"]).isna() | (sig["assigned_hr_partner_id"].map(O["termination_date"]) > c)).all()
    assert sig["manager_employee_id"].isin(E.index).all()
    themes = {f["factor"] for row in sig["factors_json"] for f in json.loads(row)}
    assert themes <= set(THEMES) - NOT_A_REASON                         # survey participation is never a reason
    assert "Survey participation" not in themes
    assert (sig["scoring_cutoff"] == "2026-03-31").all()


@pytest.mark.parametrize("mutate,needle", [
    (lambda s: s.assign(human_review_required=False), "human_review_required"),
    (lambda s: s.assign(automated_action_allowed=True), "automated_action_allowed"),
    (lambda s: s.assign(top_factors_text=""), "explanation"),
    (lambda s: s.assign(use_note="Score for ranking"), "framing"),
    (lambda s: s.assign(top_factors_text="1) Likely to terminate soon"), "decision-style wording"),
    (lambda s: s.assign(reviewed_by_employee_id="EMP-000001"), "pending row already names a reviewer"),
    (lambda s: s.assign(review_status="Reviewed_No_Action"), "reviewed row has no reviewer"),
    (lambda s: s.assign(assigned_hr_partner_id=None), "HR partner"),
    (lambda s: s.assign(review_status="Auto_Approved"), "review_status"),
])
def test_contract_guard_rejects_unsafe_outputs(R, mutate, needle):
    with pytest.raises(ValueError, match=needle):
        assert_supportive_framing(mutate(R["signals"].copy()))


# ------------------------------------------------------------------ design claims
def test_benign_cases_are_not_learned_as_risk(R):
    c = R["coefficients"].set_index("feature")["coefficient"]
    assert abs(c["planned_peak_now"]) < 0.15 and abs(c["recent_transfer"]) < 0.15
    assert c["surveys_skipped_4q"] < 0.15                    # skipping a survey is not a risk factor
    assert c["last_engagement"] < 0 and c["nonpeak_overload_streak"] > 0 and c["stagnation_months"] > 0


def test_results_are_reported_with_uncertainty_and_baselines(R):
    t, ci = R["test"], R["test_ci"]
    assert 0.5 < t["roc_auc"] < 0.95 and t["base_rate"] < 0.1
    for k, (lo, hi) in ci.items():
        assert lo < t[k] < hi
    assert {"Random ranking", "Gradient boosting (not interpretable)", "Logistic regression (this model)"} <= set(R["baselines"])
    assert len(R["calibration"]) == 10


def test_proportional_selection_evens_out_bands(R):
    s = R["stratified"]["Top 5% within each tenure band"]
    assert 0.8 <= s["min_band_flag_ratio"] <= s["max_band_flag_ratio"] <= 1.25
    assert not R["subgroups"].empty and {"monitor", "flag_ratio", "base_rate_ratio"} <= set(R["subgroups"].columns)


def test_pipeline_is_deterministic(inj, R):
    again = pipeline.run(inj.tables)
    h = lambda d: hashlib.sha256(d.to_csv(index=False).encode()).hexdigest()
    assert h(again["signals"]) == h(R["signals"])


# ------------------------------------------------------------------ end to end
def test_cli_end_to_end_and_report_is_deterministic(tmp_path):
    data = tmp_path / "data"
    assert generate_main(["--n-employees", "600", "--out", str(data)]) == 0
    r1, r2 = tmp_path / "a.md", tmp_path / "b.md"
    assert model_main(["--data", str(data), "--out", str(tmp_path / "m1"), "--report", str(r1)]) == 0
    assert model_main(["--data", str(data), "--out", str(tmp_path / "m2"), "--report", str(r2)]) == 0
    assert r1.read_bytes() == r2.read_bytes()
    for f in ("retention_signals.csv", "coefficients.csv", "subgroup_audit.csv", "model_metrics.json"):
        assert (tmp_path / "m1" / f).exists()
    assert (tmp_path / "m1" / "retention_signals.csv").read_bytes() == (tmp_path / "m2" / "retention_signals.csv").read_bytes()
    assert json.loads((tmp_path / "m1" / "model_metrics.json").read_text())["audit"]["production"]["passed"] is True
    text = r1.read_text()
    assert "not an employment decision" in text and "## 5. Leak audit and the leak ladder" in text
