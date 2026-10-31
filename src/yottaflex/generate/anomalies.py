"""Step 5: inject labelled edge cases into a *valid* baseline, and sample benign decoys.

Principles
- The baseline is generated first and is clean. This module only edits cells (or adds rows)
  that are then listed in the ground truth with the original values. Nothing else changes.
- Ground truth is returned separately and never written into any feature table.
- Decoys are untouched natural rows that look suspicious to a naive rule and must NOT be flagged.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .. import config, ids
from ..dates import months_between

ITEM_COLS = ["q_manager_support", "q_growth_opportunity", "q_workload_sustainable",
             "q_recognition", "q_intent_to_stay"]
TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


@dataclass(frozen=True)
class AnomalyRates:
    leak_late_recorded: float = 0.006     # of employees (late-recorded, revised row)
    leak_after_exit: float = 0.004        # of employees (snapshot dated after exit)
    missing_as_negative: float = 0.03     # of Skipped survey rows
    label_mismatch: float = 0.005         # of employees
    unreviewed_score: float = 0.10        # of Signal_Flagged interventions
    decoy: float = 0.03                   # of employees, per decoy type


def _py(v):
    if v is None or (not isinstance(v, (list, dict, str)) and pd.isna(v)):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d")
    return v


def _orig(**kw) -> str:
    return json.dumps({k: _py(v) for k, v in kw.items()}, separators=(",", ":"))


def _k(rate: float, base: int, pool: int, minimum: int = 1) -> int:
    return int(min(pool, max(minimum, round(rate * base))))


def _score(items: list) -> float | None:
    vals = [v for v in items if not pd.isna(v)]
    return round(100.0 * (float(np.mean(vals)) - 1.0) / 4.0, 1) if vals else None


def _workload_derived(hours: float, projects: int, oncall: int):
    ot = round(max(0.0, hours - 40.0) * 13.0, 1)
    idx = round(float(np.clip(100.0 * (0.55 * (hours - 35.0) / 20.0 + 0.30 * projects / 8.0
                                       + 0.15 * oncall / 20.0), 0.0, 100.0)), 1)
    return ot, idx, bool(idx >= 65.0)


def inject(tables: dict[str, pd.DataFrame], n_employees: int, rng: np.random.Generator,
           rates: AnomalyRates = AnomalyRates()) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    T = {k: v.copy() for k, v in tables.items()}
    O, S, SV, W = T["attrition_outcome"], T["tenure_snapshot"], T["engagement_survey"], T["workload_snapshot"]
    gt: list[dict] = []
    used_emp: set[str] = set()

    def add(issue, sub, entity, rid, field, orig, decision, injected, desc):
        gt.append({"issue_type": issue, "issue_subtype": sub, "entity": entity, "record_id": rid,
                   "field": field, "original_value": orig, "expected_decision": decision,
                   "is_injected": injected, "description": desc})

    sv_pos = pd.Series(np.arange(len(SV)), index=SV["snapshot_id"])
    w_pos = pd.Series(np.arange(len(W)), index=W["snapshot_id"])

    # ------------------------------------------------------------------
    # 1a. future_information_leak / late_recorded_row
    # ------------------------------------------------------------------
    windows = [(pd.Timestamp(config.CUTOFFS[k]), pd.Timestamp(config.HORIZON_ENDS[k]))
               for k in ("train", "validation", "test")]
    snap_at = S[S["snapshot_date"].isin([c for c, _ in windows])].set_index(["employee_id", "snapshot_date"])["snapshot_id"]
    pool = []
    # employees with interventions are excluded: their engagement_delta is derived from these surveys,
    # and editing a survey would silently make that derived value stale
    has_intervention = set(T["intervention"]["employee_id"])
    for emp, x in O.loc[O["final_status"] == "Exited_Voluntary", ["employee_id", "termination_date"]].itertuples(index=False):
        if emp in has_intervention:
            continue
        for c, h in windows:
            if c < x <= h and (emp, c) in snap_at.index:
                pool.append((emp, c, x, snap_at[(emp, c)]))
    pool = [pool[i] for i in rng.permutation(len(pool))]
    n_late = _k(rates.leak_late_recorded, n_employees, len(pool))
    for emp, c, x, sid in pool[:n_late]:
        used_emp.add(emp)
        gap = int((x - c).days)
        rec = max(c + pd.Timedelta(days=1), x - pd.Timedelta(days=int(rng.integers(1, 15)))) if gap >= 2 else c + pd.Timedelta(days=1)
        rec_s = (rec + pd.Timedelta(hours=12)).strftime(TS_FMT)
        i = int(sv_pos[sid])
        has_score = pd.notna(SV.at[i, "engagement_score"])
        if has_score and rng.random() < 0.5:
            old_items = [SV.at[i, col] for col in ITEM_COLS]
            new_items = [pd.NA if pd.isna(v) else int(rng.integers(1, 3)) for v in old_items]
            orig = _orig(**dict(zip(ITEM_COLS, old_items)), engagement_score=SV.at[i, "engagement_score"],
                         recorded_at=SV.at[i, "recorded_at"])
            for col, v in zip(ITEM_COLS, new_items):
                SV.at[i, col] = v
            SV.at[i, "engagement_score"] = _score(new_items)
            SV.at[i, "recorded_at"] = rec_s
            add("future_information_leak", "late_recorded_row", "engagement_survey", SV.at[i, "survey_id"],
                ", ".join([*ITEM_COLS, "engagement_score", "recorded_at"]), orig, "flag", True,
                "Survey for a quarter at or before the cutoff was revised and recorded after the cutoff, "
                "after the employee's exit decision. Using it as a feature leaks the outcome.")
        else:
            j = int(w_pos[sid])
            hrs = round(float(60.0 + 5.0 * rng.random()), 1)
            ot, idx, high = _workload_derived(hrs, int(W.at[j, "active_project_count"]), int(W.at[j, "on_call_days"]))
            orig = _orig(avg_weekly_hours=W.at[j, "avg_weekly_hours"], overtime_hours_quarter=W.at[j, "overtime_hours_quarter"],
                         workload_index=W.at[j, "workload_index"], high_load_flag=W.at[j, "high_load_flag"],
                         recorded_at=W.at[j, "recorded_at"])
            W.at[j, "avg_weekly_hours"], W.at[j, "overtime_hours_quarter"] = hrs, ot
            W.at[j, "workload_index"], W.at[j, "high_load_flag"] = idx, high
            W.at[j, "recorded_at"] = rec_s
            add("future_information_leak", "late_recorded_row", "workload_snapshot", W.at[j, "workload_id"],
                "avg_weekly_hours, overtime_hours_quarter, workload_index, high_load_flag, recorded_at", orig, "flag", True,
                "Workload for a quarter at or before the cutoff was revised and recorded after the cutoff, "
                "after the employee's exit decision. Using it as a feature leaks the outcome.")

    # ------------------------------------------------------------------
    # 1b. future_information_leak / snapshot_after_exit (new rows)
    # ------------------------------------------------------------------
    last_idx = S.groupby("employee_id")["snapshot_date"].idxmax()
    last = S.loc[last_idx].set_index("employee_id")
    ex = O[(O["final_status"] != "Active") & O["termination_date"].notna() & ~O["employee_id"].isin(used_emp)]
    cand = []
    for emp, x in ex[["employee_id", "termination_date"]].itertuples(index=False):
        q = config.QUARTERS.index(last.at[emp, "snapshot_quarter"]) + 1
        if q < len(config.QUARTERS) and pd.Timestamp(ids.quarter_end(config.QUARTERS[q])) > x:
            cand.append((emp, q))
    cand = [cand[i] for i in rng.permutation(len(cand))]
    n_zomb = _k(rates.leak_after_exit, n_employees, len(cand))
    emp_tbl = T["employee"].set_index("employee_id")
    team_peak = T["team"].set_index("team_id")["planned_peak_quarter"]
    bands = T["compensation_band"]
    PH, A = T["promotion_history"], T["employee_team_assignment"]
    sv_year_max = SV["survey_id"].str.slice(5, 9).astype(int).to_frame("y").assign(
        c=SV["survey_id"].str.slice(10).astype(int)).groupby("y")["c"].max().to_dict()
    new_s, new_sv, new_w = [], [], []
    for emp, q in cand[:n_zomb]:
        used_emp.add(emp)
        lq, ql = last.loc[emp], config.QUARTERS[q]
        d1 = pd.Timestamp(ids.quarter_end(ql))
        hire = emp_tbl.at[emp, "hire_date"]
        promos = PH[(PH["employee_id"] == emp) & (PH["event_type"] == "Promotion") & (PH["effective_date"] <= d1)]["effective_date"]  # lateral moves do not reset the clock
        lp = promos.max() if len(promos) else hire
        ts = A[(A["employee_id"] == emp) & (A["effective_from"] <= d1)]["effective_from"].max()
        mo = lambda a: int(months_between(np.datetime64(a.date(), "D"), np.datetime64(d1.date(), "D")))
        b = bands[(bands["role_id"] == lq["role_id"]) & (bands["effective_from"] <= d1)
                  & (bands["effective_to"].isna() | (bands["effective_to"] >= d1))]
        sid = ids.snapshot_id(emp, ql)
        new_s.append({**lq.to_dict(), "snapshot_id": sid, "employee_id": emp, "snapshot_quarter": ql,
                      "snapshot_date": d1, "tenure_months": mo(hire), "months_since_last_promotion": mo(lp),
                      "months_in_current_team": mo(ts),
                      "compa_ratio": round(float(lq["base_salary_annual"]) / float(b["annual_mid"].iloc[0]), 3),
                      "transfer_in_quarter": False, "promotion_in_quarter": False,
                      "recorded_at": (d1 + pd.Timedelta(hours=18, minutes=int(rng.integers(0, 60)))).strftime(TS_FMT)})
        yr = int(d1.year); sv_year_max[yr] = sv_year_max.get(yr, 0) + 1
        new_sv.append({"survey_id": ids.survey_id(yr, sv_year_max[yr]), "employee_id": emp, "snapshot_id": sid,
                       "survey_date": d1, "response_status": "Skipped", **{c: pd.NA for c in ITEM_COLS},
                       "items_answered": 0, "engagement_score": np.nan,
                       "recorded_at": (d1 + pd.Timedelta(hours=19)).strftime(TS_FMT)})
        wl = W[(W["employee_id"] == emp) & (W["snapshot_id"] == lq["snapshot_id"])].iloc[0].to_dict()
        peak = int(team_peak[lq["team_id"]]) == int(ql[-1])
        ot, idx, high = _workload_derived(float(wl["avg_weekly_hours"]), int(wl["active_project_count"]), int(wl["on_call_days"]))
        new_w.append({**wl, "workload_id": ids.workload_id(emp, ql), "snapshot_id": sid, "planned_peak_flag": peak,
                      "overtime_hours_quarter": ot, "workload_index": idx, "high_load_flag": high,
                      "recorded_at": (d1 + pd.Timedelta(hours=18, minutes=int(rng.integers(60, 120)))).strftime(TS_FMT)})
        desc = ("Row exists for a quarter after the employee's termination date. Its existence reveals the "
                "outcome and it post-dates the event, so it must not feed features.")
        add("future_information_leak", "snapshot_after_exit", "tenure_snapshot", sid, "(inserted row)", None, "flag", True, desc)
        add("future_information_leak", "snapshot_after_exit", "engagement_survey", new_sv[-1]["survey_id"], "(inserted row)", None, "flag", True, desc)
        add("future_information_leak", "snapshot_after_exit", "workload_snapshot", new_w[-1]["workload_id"], "(inserted row)", None, "flag", True, desc)
    if new_s:
        T["tenure_snapshot"] = pd.concat([S, pd.DataFrame(new_s)[S.columns].astype(S.dtypes.to_dict())], ignore_index=True)
        T["engagement_survey"] = pd.concat([SV, pd.DataFrame(new_sv)[SV.columns].astype(SV.dtypes.to_dict())], ignore_index=True)
        T["workload_snapshot"] = pd.concat([W, pd.DataFrame(new_w)[W.columns].astype(W.dtypes.to_dict())], ignore_index=True)
        S, SV, W = T["tenure_snapshot"], T["engagement_survey"], T["workload_snapshot"]

    # ------------------------------------------------------------------
    # 2. missing_survey_as_negative
    # ------------------------------------------------------------------
    injected_ids = {g["record_id"] for g in gt}
    sk = SV[(SV["response_status"] == "Skipped") & SV["engagement_score"].isna()
            & ~SV["survey_id"].isin(injected_ids)]["survey_id"].to_numpy()
    sk = sk[rng.permutation(len(sk))]
    n_mn = _k(rates.missing_as_negative, int((SV["response_status"] == "Skipped").sum()), len(sk))
    pos = pd.Series(np.arange(len(SV)), index=SV["survey_id"])
    for sid in sk[:n_mn]:
        SV.at[int(pos[sid]), "engagement_score"] = 0.0
        add("missing_survey_as_negative", "skipped_scored_zero", "engagement_survey", sid, "engagement_score",
            _orig(engagement_score=None), "flag", True,
            "Survey was skipped, so the score must be null. A zero treats missing as the most negative answer.")

    # ------------------------------------------------------------------
    # 3. label_termination_mismatch
    # ------------------------------------------------------------------
    lab = O["voluntary_attrition_label"]
    pools = {
        "label_missing_exit": O.index[(lab == 1).fillna(False) & ~O["employee_id"].isin(used_emp)],
        "label_without_exit": O.index[(lab == 0).fillna(False) & (O["final_status"] == "Active") & ~O["employee_id"].isin(used_emp)],
        "label_outside_horizon": O.index[lab.isna() & (O["final_status"] == "Exited_Voluntary") & ~O["employee_id"].isin(used_emp)],
    }
    k_tot = max(3, round(rates.label_mismatch * n_employees))
    k1 = k2 = int(round(0.4 * k_tot)); k3 = max(1, k_tot - k1 - k2)
    new_label = {"label_missing_exit": 0, "label_without_exit": 1, "label_outside_horizon": 1}
    descs = {
        "label_missing_exit": "Voluntary exit inside the horizon, but the stored label says the employee stayed.",
        "label_without_exit": "Employee is still active, but the stored label says a voluntary exit occurred.",
        "label_outside_horizon": "Exit happened before the prediction cutoff (not scorable), but a label of 1 is stored.",
    }
    for (name, idxs), k in zip(pools.items(), (k1, k2, k3)):
        idxs = np.asarray(idxs)
        for i in idxs[rng.permutation(len(idxs))][:min(k, len(idxs))]:
            used_emp.add(O.at[i, "employee_id"])
            orig = O.at[i, "voluntary_attrition_label"]
            O.at[i, "voluntary_attrition_label"] = new_label[name]
            add("label_termination_mismatch", name, "attrition_outcome", O.at[i, "outcome_id"],
                "voluntary_attrition_label", _orig(voluntary_attrition_label=orig), "flag", True, descs[name])

    # ------------------------------------------------------------------
    # 4. unreviewed_individual_score
    # ------------------------------------------------------------------
    I = T["intervention"]
    sig = I.index[(I["trigger_source"] == "Signal_Flagged") & I["status"].isin(["Conducted", "Closed"])]
    n_sig_all = int((I["trigger_source"] == "Signal_Flagged").sum())
    n_ur = _k(rates.unreviewed_score, n_sig_all, len(sig), minimum=3)
    sig = np.asarray(sig)[rng.permutation(len(sig))][:n_ur]
    subs = ["no_explanation", "no_human_review", "no_explanation_no_review"]
    for r, i in enumerate(sig):
        sub = subs[r % 3]
        old = dict(signal_top_factors=I.at[i, "signal_top_factors"], review_status=I.at[i, "review_status"],
                   reviewed_by_employee_id=I.at[i, "reviewed_by_employee_id"], reviewed_date=I.at[i, "reviewed_date"])
        if sub in ("no_explanation", "no_explanation_no_review"):
            I.at[i, "signal_top_factors"] = None
        if sub in ("no_human_review", "no_explanation_no_review"):
            I.at[i, "review_status"] = "Pending"
            I.at[i, "reviewed_by_employee_id"] = None
            I.at[i, "reviewed_date"] = pd.NaT
        add("unreviewed_individual_score", sub, "intervention", I.at[i, "intervention_id"],
            "signal_top_factors, review_status, reviewed_by_employee_id, reviewed_date", _orig(**old), "flag", True,
            "An individual model score drove a conducted intervention without a plain-language explanation "
            "and/or a recorded human review.")

    # ------------------------------------------------------------------
    # Benign decoys: untouched natural rows that must NOT be flagged
    # ------------------------------------------------------------------
    injected_ids = {g["record_id"] for g in gt}
    n_dec = max(1, round(rates.decoy * n_employees))

    def sample(ids_):
        arr = np.asarray(ids_)
        return arr[rng.permutation(len(arr))][:n_dec]

    score_by_snap = SV.set_index("snapshot_id")["engagement_score"]
    wd = W[W["high_load_flag"] & W["planned_peak_flag"] & ~W["workload_id"].isin(injected_ids)
           & (W["snapshot_id"].map(score_by_snap) >= 70)]["workload_id"]
    for rid in sample(wd):
        add("benign_high_workload", "planned_peak_healthy_engagement", "workload_snapshot", rid, None, None,
            "do_not_flag", False,
            "High load during the team's planned peak quarter while engagement stays healthy. Expected and temporary.")

    As = A.sort_values(["employee_id", "effective_from"])
    nxt = As.groupby("employee_id")["effective_from"].shift(-1)
    term = As["employee_id"].map(O.set_index("employee_id")["termination_date"])
    closed = As[nxt.notna() & (term.isna() | (term > nxt + pd.Timedelta(days=180)))]["assignment_id"]
    for rid in sample(closed):
        add("benign_internal_transfer", "assignment_closed_by_transfer", "employee_team_assignment", rid, None, None,
            "do_not_flag", False,
            "Assignment ended because the employee moved to another team and stayed. A transfer is not attrition.")

    ms = SV[(SV["response_status"] == "Skipped") & SV["engagement_score"].isna()
            & ~SV["survey_id"].isin(injected_ids)]["survey_id"]
    for rid in sample(ms):
        add("benign_missing_survey", "skipped_null_score", "engagement_survey", rid, None, None, "do_not_flag", False,
            "Survey skipped and correctly stored as null. Missing is not a negative signal.")

    order = {k: i for i, k in enumerate(config.ISSUE_TYPES)}
    df = pd.DataFrame(gt)
    df = df.sort_values(by=["issue_type", "entity", "record_id"], key=lambda s: s.map(order) if s.name == "issue_type" else s,
                        kind="stable").reset_index(drop=True)
    df.insert(0, "gt_id", [ids.ground_truth_id(i + 1) for i in range(len(df))])
    return T, df