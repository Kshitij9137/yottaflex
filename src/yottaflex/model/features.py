"""As-of feature building.

Rule: a feature for cutoff C may only use rows with snapshot_date <= C that were recorded by the end of day C
(`recorded_at <= C 23:59:59Z`). `naive=True` deliberately breaks this (the classic "latest value" join) so the
leak audit and the leak ladder have something real to catch.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..validate.schema import SCHEMA, coerce

FEATURES = [
    "last_engagement", "engagement_drop", "engagement_mean_4q", "low_engagement_gap", "never_responded",
    "surveys_skipped_4q", "workload_index", "high_load_quarters_4q", "nonpeak_overload_streak", "planned_peak_now",
    "months_since_last_promotion", "stagnation_months", "compa_ratio", "pay_gap", "tenure_months", "new_joiner",
    "months_in_current_team", "level", "recent_transfer", "recent_promotion", "recent_intervention",
]
PROVENANCE = ["src_max_recorded_at", "src_max_date"]
NEUTRAL_ENGAGEMENT = 60.0      # "no survey yet" is neutral, never negative
STAGNATION_GRACE = 36


def typed_tables(raw: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    return {name: coerce(raw[name], SCHEMA[name])[0] for name in SCHEMA}


def cutoff_end(cutoff) -> pd.Timestamp:
    return pd.Timestamp(cutoff) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)


def build_panel(T: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """One row per snapshot, joined to its survey and workload rows, each with its own recorded_at."""
    S, SV, W, R = T["tenure_snapshot"], T["engagement_survey"], T["workload_snapshot"], T["role"]
    P = S[["snapshot_id", "employee_id", "snapshot_date", "role_id", "tenure_months", "months_since_last_promotion",
           "months_in_current_team", "compa_ratio", "transfer_in_quarter", "promotion_in_quarter", "recorded_at"]
          ].rename(columns={"recorded_at": "s_rec"})
    P["level"] = P["role_id"].map(R.set_index("role_id")["level"]).astype("float64")
    P = P.merge(SV[["snapshot_id", "response_status", "engagement_score", "recorded_at"]]
                .rename(columns={"recorded_at": "sv_rec"}), on="snapshot_id", how="left")
    P = P.merge(W[["snapshot_id", "workload_index", "high_load_flag", "planned_peak_flag", "recorded_at"]]
                .rename(columns={"recorded_at": "w_rec"}), on="snapshot_id", how="left")
    for c in ("transfer_in_quarter", "promotion_in_quarter", "high_load_flag", "planned_peak_flag"):
        P[c] = P[c].fillna(False).astype(bool)
    return P.sort_values(["employee_id", "snapshot_date"], kind="stable").reset_index(drop=True)


def _last_valid(Q: pd.DataFrame, valid: pd.Series, col: str, nth: int) -> pd.Series:
    V = Q[valid]
    k = V.groupby("employee_id").cumcount(ascending=False)
    return V[k == nth].set_index("employee_id")[col]


def features_at(P: pd.DataFrame, I: pd.DataFrame, cutoff, *, naive: bool = False, future_count: bool = False,
                check_recorded: bool = True, sanitize: bool = True) -> pd.DataFrame:
    """Feature table for one cutoff, indexed by employee_id, for employees who have a snapshot at the cutoff.

    Production settings are the defaults. The switches exist only so the leak ladder can switch a defence off:
    naive = latest-value join over all rows; check_recorded = enforce recorded_at <= cutoff;
    sanitize = never turn a skipped survey into a score.
    """
    C, end = pd.Timestamp(cutoff), cutoff_end(cutoff)
    pop = P.loc[(P["snapshot_date"] == C) & (P["s_rec"] <= end), "employee_id"].unique()
    Q = P[P["employee_id"].isin(pop)].copy()
    if not naive:
        Q = Q[(Q["snapshot_date"] <= C) & ((Q["s_rec"] <= end) | (not check_recorded))]
    open_gate = naive or not check_recorded
    sv_av = pd.Series(True, index=Q.index) if open_gate else (Q["sv_rec"] <= end)
    w_av = pd.Series(True, index=Q.index) if open_gate else (Q["w_rec"] <= end)
    Q["k"] = Q.groupby("employee_id").cumcount(ascending=False)      # 0 = latest row used

    # --- engagement. Missing is missing: a skipped survey never becomes a score -------------------------------
    score = Q["engagement_score"] if (naive or not sanitize) else Q["engagement_score"].where((Q["response_status"] != "Skipped") & sv_av)
    if not naive and not sanitize:
        score = score.where(sv_av)
    valid = score.notna()
    Q["_score"] = score
    last = _last_valid(Q, valid, "_score", 0)
    prev = _last_valid(Q, valid, "_score", 1)
    last4 = Q[(Q["k"] < 4) & valid].groupby("employee_id")["_score"].mean()
    skipped4 = ((Q["k"] < 4) & (Q["response_status"] == "Skipped") & sv_av).groupby(Q["employee_id"]).sum()

    # --- workload ----------------------------------------------------------------------------------------------
    wv = w_av & Q["workload_index"].notna()
    w_last = Q[wv].groupby("employee_id").tail(1).set_index("employee_id")
    high4 = ((Q["k"] < 4) & Q["high_load_flag"] & w_av).groupby(Q["employee_id"]).sum()
    code = np.where(w_av & Q["high_load_flag"] & ~Q["planned_peak_flag"], 1, np.where(w_av & ~Q["high_load_flag"], 0, 2))
    Q["_code"] = code
    Q["_j"] = Q.groupby("employee_id").cumcount()
    wide = Q.pivot(index="employee_id", columns="_j", values="_code")
    streak = pd.Series(0.0, index=wide.index)
    for j in wide.columns:                                            # same semantics as the generator's counter
        c = wide[j]
        streak = np.where(c == 1, streak + 1, np.where(c == 0, 0.0, streak))
        streak = pd.Series(streak, index=wide.index)

    base = Q[Q["k"] == 0].set_index("employee_id")
    recent = Q[Q["k"] < 2].groupby("employee_id")[["transfer_in_quarter", "promotion_in_quarter"]].any()

    # --- interventions conducted by the cutoff -----------------------------------------------------------------
    Ic = I[I["conducted_date"].notna()]
    Ic = Ic if naive else Ic[Ic["conducted_date"] <= C]
    window = Ic if naive else Ic[Ic["conducted_date"] > C - pd.Timedelta(days=182)]
    rec_int = window.groupby("employee_id").size()

    F = pd.DataFrame(index=base.index)
    F["never_responded"] = last.reindex(F.index).isna().astype(float)
    F["last_engagement"] = last.reindex(F.index).fillna(NEUTRAL_ENGAGEMENT)
    pr = prev.reindex(F.index)
    F["engagement_drop"] = (pr - last.reindex(F.index)).clip(lower=0).fillna(0.0)
    F["engagement_mean_4q"] = last4.reindex(F.index).fillna(F["last_engagement"])
    F["low_engagement_gap"] = (NEUTRAL_ENGAGEMENT - F["last_engagement"]).clip(lower=0)
    F["surveys_skipped_4q"] = skipped4.reindex(F.index).fillna(0).astype(float)
    F["workload_index"] = w_last["workload_index"].reindex(F.index).astype(float)
    F["workload_index"] = F["workload_index"].fillna(F["workload_index"].median())
    F["high_load_quarters_4q"] = high4.reindex(F.index).fillna(0).astype(float)
    F["nonpeak_overload_streak"] = streak.reindex(F.index).fillna(0.0)
    F["planned_peak_now"] = w_last["planned_peak_flag"].reindex(F.index).fillna(False).astype(float)
    F["months_since_last_promotion"] = base["months_since_last_promotion"].astype(float)
    F["stagnation_months"] = (F["months_since_last_promotion"] - STAGNATION_GRACE).clip(0, 24) * (base["level"] < 5)
    F["compa_ratio"] = base["compa_ratio"].astype(float)
    F["pay_gap"] = (0.95 - F["compa_ratio"]).clip(0, 0.30)
    F["tenure_months"] = base["tenure_months"].astype(float)
    F["new_joiner"] = (F["tenure_months"] < 12).astype(float)
    F["months_in_current_team"] = base["months_in_current_team"].astype(float)
    F["level"] = base["level"].astype(float)
    F["recent_transfer"] = recent["transfer_in_quarter"].reindex(F.index).fillna(False).astype(float)
    F["recent_promotion"] = recent["promotion_in_quarter"].reindex(F.index).fillna(False).astype(float)
    F["recent_intervention"] = (rec_int.reindex(F.index).fillna(0) > 0).astype(float)
    cols = list(FEATURES)
    if future_count:                                                  # a deliberate, blatant leak for the demo
        F["future_snapshots"] = (P[P["employee_id"].isin(F.index) & (P["snapshot_date"] > C)]
                                 .groupby("employee_id").size().reindex(F.index).fillna(0).astype(float))
        cols.append("future_snapshots")

    # --- provenance: the latest recorded_at / date among the rows actually used ----------------------------------
    used = Q[["s_rec"]].copy()
    used["rec"] = pd.concat([Q["s_rec"], Q["sv_rec"].where(sv_av), Q["w_rec"].where(w_av)], axis=1).max(axis=1)
    F["src_max_recorded_at"] = used["rec"].groupby(Q["employee_id"]).max().reindex(F.index)
    dates = Q["snapshot_date"].groupby(Q["employee_id"]).max()
    if len(window):
        dates = pd.concat([dates, window.groupby("employee_id")["conducted_date"].max()], axis=1).max(axis=1)
    F["src_max_date"] = dates.reindex(F.index)
    return F[cols + PROVENANCE]
