"""Assemble final tables from simulation output.

All derived columns are computed from source columns here (or in simulate.py with the
same helpers); nothing derived is drawn independently.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .. import config, ids, labels
from ..dates import D1, quarter_end_of
from .masters import HR_FAMILY, Workforce, build_teams, role_index
from .params import FACTOR_NAMES, SimParams
from .simulate import T, SimResult

QEND = np.array([np.datetime64(ids.quarter_end(q), "D") for q in config.QUARTERS])


def _ts(dates, minutes) -> pd.Series:
    """datetime64[D] + minutes -> ISO-8601 UTC strings."""
    t = np.asarray(dates, dtype="datetime64[m]") + np.asarray(minutes).astype(np.int64).astype("timedelta64[m]")
    return pd.Series(t.astype("datetime64[s]")).dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _cat(lst, key, dtype=None):
    arrs = [x[key] for x in lst if len(x[key])]
    if not arrs:
        return np.array([], dtype=dtype)
    return np.concatenate(arrs)


def _dt(arr) -> pd.Series:
    return pd.Series(pd.to_datetime(np.asarray(arr, dtype="datetime64[D]").astype("datetime64[ns]")))


def build_tables(wf: Workforce, roles: pd.DataFrame, bands: pd.DataFrame, sim: SimResult,
                 p: SimParams, post: np.random.Generator) -> dict[str, pd.DataFrame]:
    n = wf.n
    emp_ids = np.array([ids.employee_id(i + 1) for i in range(n)])
    role_ids = roles["role_id"].to_numpy()
    team_ids = np.array([ids.team_id(i + 1) for i in range(len(wf.team_family))])
    t = {"role": roles, "compensation_band": bands}

    # ---- Employee -------------------------------------------------------
    t["employee"] = pd.DataFrame({
        "employee_id": emp_ids,
        "hire_date": _dt(wf.hire),
        "initial_role_id": role_ids[role_index(wf.family, wf.init_level)],
        "employment_type": wf.employment_type,
        "recorded_at": _ts(wf.hire, 540 + wf.rec_minutes),
    })
    t["team"] = build_teams(wf, emp_ids)

    # ---- Snapshots (sorted by employee, quarter) --------------------------
    S = {k: _cat(sim.snaps, k) for k in sim.snaps[0] if k != "t"}
    tq = _cat_t(sim.snaps)
    order = np.lexsort((tq, S["emp"]))
    S = {k: v[order] for k, v in S.items()}
    tq = tq[order]
    m = len(order)
    sid = np.array([ids.snapshot_id(emp_ids[e], config.QUARTERS[q]) for e, q in zip(S["emp"], tq)])
    snap_date = QEND[tq]
    quarters = np.array(config.QUARTERS)[tq]
    t["tenure_snapshot"] = pd.DataFrame({
        "snapshot_id": sid, "employee_id": emp_ids[S["emp"]], "snapshot_quarter": quarters,
        "snapshot_date": _dt(snap_date), "role_id": role_ids[S["role_idx"]],
        "team_id": team_ids[S["team"]], "tenure_months": S["tenure"], "months_since_last_promotion": S["msp"],
        "months_in_current_team": S["mit"], "base_salary_annual": S["salary"],
        "compa_ratio": np.round(S["compa"], 3), "transfer_in_quarter": S["tr"],
        "promotion_in_quarter": S["promo"],
        "recorded_at": _ts(snap_date, 1080 + post.integers(0, 180, m)),
    })
    t["workload_snapshot"] = pd.DataFrame({
        "workload_id": [ids.workload_id(emp_ids[e], config.QUARTERS[q]) for e, q in zip(S["emp"], tq)],
        "employee_id": emp_ids[S["emp"]], "snapshot_id": sid,
        "avg_weekly_hours": S["hours"], "active_project_count": S["projects"], "on_call_days": S["oncall"],
        "planned_peak_flag": S["peak"],
        "overtime_hours_quarter": np.round(np.maximum(0.0, S["hours"] - 40.0) * 13.0, 1),
        "workload_index": S["widx"], "high_load_flag": S["high"],
        "recorded_at": _ts(snap_date, 1080 + post.integers(0, 180, m)),
    })
    # survey: status, items, derived score; counters restart each year
    status = np.where(S["skipped"], "Skipped", np.where(S["partial"], "Partial", "Responded"))
    sdate = S["survey_date"]
    items = pd.DataFrame(S["items"], columns=["q_manager_support", "q_growth_opportunity",
                                              "q_workload_sustainable", "q_recognition", "q_intent_to_stay"]
                         ).astype("Int64")
    score = pd.Series(S["score"]).where(S["n_ans"] > 0)
    year = pd.Series(sdate.astype("datetime64[Y]").astype(int) + 1970)
    counter = year.groupby(year).cumcount() + 1
    rec = np.minimum(sdate.astype("datetime64[m]") + (480 + post.integers(0, 600, m) + 1440 * post.integers(0, 3, m)
                                                    ).astype("timedelta64[m]"),
                     snap_date.astype("datetime64[m]") + np.timedelta64(1259, "m"))
    sv = pd.DataFrame({
        "survey_id": [ids.survey_id(int(y), int(c)) for y, c in zip(year, counter)],
        "employee_id": emp_ids[S["emp"]], "snapshot_id": sid, "survey_date": _dt(sdate),
        "response_status": status})
    sv = pd.concat([sv, items], axis=1)
    sv["items_answered"] = S["n_ans"]
    sv["engagement_score"] = score
    sv["recorded_at"] = pd.Series(rec.astype("datetime64[s]")).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    t["engagement_survey"] = sv

    # ---- Assignments (bridge, effective-dated) ----------------------------
    ev = pd.DataFrame({"emp": _cat(sim.assign, "emp", np.int64), "eff_from": _cat(sim.assign, "date", "datetime64[D]"),
                       "team": _cat(sim.assign, "team", np.int64), "reason": _cat(sim.assign, "reason", str)})
    first = pd.DataFrame({"emp": np.arange(n), "eff_from": wf.hire, "team": wf.team, "reason": "Hire"})
    a = pd.concat([first, ev], ignore_index=True).sort_values(["emp", "eff_from"], kind="stable").reset_index(drop=True)
    a["eff_from"] = pd.to_datetime(a["eff_from"].to_numpy(dtype="datetime64[D]").astype("datetime64[ns]"))
    nxt = a.groupby("emp")["eff_from"].shift(-1) - pd.Timedelta(days=1)
    exit_ts = pd.Series(pd.to_datetime(sim.exit_date.astype("datetime64[ns]")))
    last = nxt.isna()
    nxt[last] = exit_ts.iloc[a.loc[last, "emp"].to_numpy()].to_numpy()
    t["employee_team_assignment"] = pd.DataFrame({
        "assignment_id": [ids.assignment_id(i + 1) for i in range(len(a))],
        "employee_id": emp_ids[a["emp"].to_numpy()], "team_id": team_ids[a["team"].to_numpy()],
        "effective_from": a["eff_from"], "effective_to": nxt, "change_reason": a["reason"]})

    # ---- PromotionHistory ---------------------------------------------------
    pe, qe_ = wf.pre_events, sim.promo
    ph = pd.DataFrame({
        "emp": np.concatenate([pe["emp"], _cat(qe_, "emp", np.int64)]),
        "date": np.concatenate([pe["date"], _cat(qe_, "date", "datetime64[D]")]),
        "type": np.concatenate([np.full(len(pe["emp"]), "Promotion"), _cat(qe_, "type", str)]),
        "from_role": np.concatenate([pe["from_role"], _cat(qe_, "from_role", np.int64)]),
        "to_role": np.concatenate([pe["to_role"], _cat(qe_, "to_role", np.int64)]),
        "prior": np.concatenate([pe["prior"], _cat(qe_, "prior", np.int64)]),
        "new": np.concatenate([pe["new"], _cat(qe_, "new", np.int64)]),
    }).sort_values(["date", "emp"], kind="stable").reset_index(drop=True)
    pd_ = ph["date"].to_numpy(dtype="datetime64[D]")
    lag = pd_.astype("datetime64[m]") + (600 + 1440 * post.integers(0, 4, len(ph))).astype("timedelta64[m]")
    rec = np.minimum(lag, quarter_end_of(pd_).astype("datetime64[m]") + np.timedelta64(1259, "m"))
    t["promotion_history"] = pd.DataFrame({
        "promotion_id": [ids.promotion_id(i + 1) for i in range(len(ph))],
        "employee_id": emp_ids[ph["emp"].to_numpy()], "event_type": ph["type"],
        "effective_date": _dt(pd_), "from_role_id": role_ids[ph["from_role"].to_numpy()],
        "to_role_id": role_ids[ph["to_role"].to_numpy()],
        "prior_base_salary_annual": ph["prior"], "new_base_salary_annual": ph["new"],
        "salary_change_pct": np.round(100.0 * (ph["new"] / ph["prior"] - 1.0), 2),
        "recorded_at": pd.Series(rec.astype("datetime64[s]")).dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
    })

    # ---- AttritionOutcome -----------------------------------------------------
    status_f = np.array(config.FINAL_STATUSES)[sim.exit_type.astype(int)]
    reason = np.where(sim.exit_type == 1,
                      np.array(config.TERMINATION_REASONS)[np.maximum(sim.exit_reason, 0)], None)
    cutoff, hend = config.CUTOFFS["test"], config.HORIZON_ENDS["test"]
    tdate = _dt(sim.exit_date)
    rec_out = np.where(np.isnat(sim.exit_date), np.datetime64("2026-10-15", "D"),
                       sim.exit_date + post.integers(0, 31, n).astype("timedelta64[D]"))
    out = pd.DataFrame({
        "outcome_id": [ids.outcome_id(e, config.OUTCOME_YEAR) for e in emp_ids],
        "employee_id": emp_ids, "final_status": status_f, "termination_date": tdate,
        "termination_reason_category": reason,
        "prediction_cutoff_date": pd.Timestamp(cutoff), "horizon_end_date": pd.Timestamp(hend),
    })
    have = set(t["tenure_snapshot"].loc[t["tenure_snapshot"]["snapshot_date"] == pd.Timestamp(cutoff), "employee_id"])
    out["eligible_at_cutoff"] = out["employee_id"].isin(have)
    out["voluntary_attrition_label"] = labels.derive_label(
        out["final_status"], out["termination_date"], out["eligible_at_cutoff"], cutoff, hend)
    out["label_rule_version"] = config.LABEL_RULE_VERSION
    out["recorded_at"] = _ts(rec_out, 720)
    t["attrition_outcome"] = out

    t["intervention"] = _build_interventions(wf, sim, t, emp_ids, post)
    return {k: t[k] for k in ("role", "compensation_band", "employee", "team", "employee_team_assignment",
                              "tenure_snapshot", "engagement_survey", "workload_snapshot",
                              "promotion_history", "attrition_outcome", "intervention")}


def _cat_t(snaps):
    return np.concatenate([np.full(len(s["emp"]), s["t"], dtype=np.int64) for s in snaps])


def _build_interventions(wf, sim, t, emp_ids, post) -> pd.DataFrame:
    cols = ["intervention_id", "employee_id", "trigger_snapshot_id", "trigger_source", "intervention_type",
            "signal_score", "signal_top_factors", "review_status", "reviewed_by_employee_id", "reviewed_date",
            "proposed_date", "conducted_date", "closed_date", "status", "hazard_multiplier",
            "engagement_delta", "outcome_category", "left_within_2_quarters"]
    if not sim.iv:
        return pd.DataFrame(columns=cols)
    I = {k: np.concatenate([x[k] for x in sim.iv]) for k in sim.iv[0]}
    order = np.lexsort((I["emp"], I["proposed"].astype("datetime64[D]").astype(np.int64)))
    I = {k: v[order] for k, v in I.items()}
    k = len(order)
    eid = emp_ids[I["emp"]]
    ex = sim.exit_date[I["emp"]]
    # a follow-up cannot close after the person has left
    closed = np.where(~np.isnat(I["closed"]) & ~np.isnat(ex) & (I["closed"] > ex), np.datetime64("NaT", "D"), I["closed"])
    status = np.where((I["status"] == "Closed") & np.isnat(closed), "Conducted", I["status"])

    # reviewer: an HR partner employed on the review date
    hr = np.flatnonzero(wf.family == HR_FAMILY)
    reviewer = np.full(k, None, dtype=object)
    for j in np.flatnonzero(~np.isnat(I["reviewed"])):
        d = I["reviewed"][j]
        ok = hr[(wf.hire[hr] <= d) & (np.isnat(sim.exit_date[hr]) | (sim.exit_date[hr] > d))]
        if ok.size == 0:
            raise ValueError("no HR reviewer available; raise n_employees")
        reviewer[j] = emp_ids[ok[int(post.integers(0, ok.size))]]

    names = np.array(FACTOR_NAMES)
    factors = []
    for j in range(k):
        if I["src"][j] != 0:
            factors.append(None); continue
        c = I["contrib"][j]; top = np.argsort(-c, kind="stable")[:3]
        factors.append(json.dumps([{"factor": names[i], "contribution": round(float(c[i]), 3)}
                                   for i in top if c[i] > 0], separators=(",", ":")))

    year = pd.Series(I["proposed"].astype("datetime64[Y]").astype(int) + 1970)
    counter = year.groupby(year).cumcount() + 1
    qlab = np.array(config.QUARTERS)[I["t"]]
    df = pd.DataFrame({
        "intervention_id": [ids.intervention_id(int(y), int(c)) for y, c in zip(year, counter)],
        "employee_id": eid,
        "trigger_snapshot_id": [ids.snapshot_id(e, q) for e, q in zip(eid, qlab)],
        "trigger_source": np.array(config.TRIGGER_SOURCES)[I["src"]],
        "intervention_type": np.array(config.INTERVENTION_TYPES)[I["ity"]],
        "signal_score": np.round(I["score"], 4), "signal_top_factors": factors,
        "review_status": I["review_status"], "reviewed_by_employee_id": reviewer,
        "reviewed_date": _dt(I["reviewed"]), "proposed_date": _dt(I["proposed"]),
        "conducted_date": _dt(I["conducted"]), "closed_date": _dt(closed),
        "status": status, "hazard_multiplier": I["mult"],
    })

    # simulated outcomes, derived from surveys and exits
    sv = t["engagement_survey"]
    sv = sv[sv["engagement_score"].notna()][["employee_id", "survey_date", "engagement_score"]]
    sv = sv.sort_values(["employee_id", "survey_date"])
    groups = {key: (g["survey_date"].to_numpy(dtype="datetime64[D]"), g["engagement_score"].to_numpy())
              for key, g in sv.groupby("employee_id")}
    delta = np.full(k, np.nan)
    for j in range(k):
        c = I["conducted"][j]
        if np.isnat(c) or eid[j] not in groups:
            continue
        dts, sc = groups[eid[j]]
        pos = int(np.searchsorted(dts, c, side="right"))
        if pos > 0 and pos < len(dts):
            delta[j] = sc[pos:pos + 2].mean() - sc[pos - 1]
    df["engagement_delta"] = np.round(delta, 2)
    df["outcome_category"] = np.select([np.isnan(delta), delta >= 5, delta <= -5], ["Not_Applicable", "Improved", "Declined"], "No_Change")
    vol_exit = np.where(sim.exit_type[I["emp"]] == 1, ex, np.datetime64("NaT", "D"))
    cond = I["conducted"]
    left = (~np.isnat(vol_exit)) & ~np.isnat(cond) & (vol_exit > cond) & (vol_exit <= cond + np.timedelta64(182, "D"))
    df["left_within_2_quarters"] = pd.array(np.where(np.isnat(cond), None, left), dtype="boolean")
    return df