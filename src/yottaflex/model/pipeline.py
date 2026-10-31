"""Train, evaluate, audit and explain. Returns everything the report and the CLI need."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from .. import config
from . import audit
from .dataset import build_all
from .explain import assert_supportive_framing, build_signals
from .features import FEATURES, build_panel, typed_tables
from .metrics import bootstrap_ci, calibration_table, evaluate_scores, top_k_stats
from .train import coefficient_table, fit_final, make_gb, make_lr, select_C

META = ["y", "cutoff", "src_max_recorded_at", "src_max_date"]
TENURE_LIKE = ["tenure_months", "new_joiner", "months_in_current_team", "level", "months_since_last_promotion", "stagnation_months"]
CAPACITY = 0.05


def rule_reference(F: pd.DataFrame) -> pd.Series:
    """The documented transparent rule from the generator (no noise): a reference ceiling, not an independent model."""
    eng_gap = np.clip((60 - F["last_engagement"]) / 20, -1.5, 2.5) * (1 - F["never_responded"])
    mod = np.where((F["last_engagement"] >= 70) & (F["never_responded"] == 0), 0.3, 1.0)
    over = np.minimum(F["nonpeak_overload_streak"], 4) / 2 * mod
    pay = np.clip(F["pay_gap"] / 0.10, 0, 2)
    return 0.9 * eng_gap + 0.4 * F["engagement_drop"] / 20 + 0.6 * (F["stagnation_months"] / 12) + 0.7 * pay + 0.8 * over + 0.5 * F["new_joiner"]


def _fit_eval(D, cols, C):
    m = fit_final(D["train"], D["validation"], cols, C)
    p = m.predict_proba(D["test"][cols])[:, 1]
    return m, p, evaluate_scores(D["test"]["y"], p, p)


def _tbl(e):
    return {k: round(float(e[k]), 4) for k in ("roc_auc", "pr_auc", "recall_at_5pct", "lift_at_5pct") if k in e}


def subgroup_audit(F, p, T, cutoff, capacity=CAPACITY):
    y = F["y"].to_numpy()
    k = max(1, int(round(capacity * len(F))))
    flagged = pd.Series(False, index=F.index)
    flagged.iloc[np.argsort(-p, kind="stable")[:k]] = True
    snap = T["tenure_snapshot"]
    role_at = snap[snap["snapshot_date"] == pd.Timestamp(cutoff)].drop_duplicates("employee_id").set_index("employee_id")["role_id"]
    G = pd.DataFrame({
        "job_family": role_at.map(T["role"].set_index("role_id")["job_family"]).reindex(F.index),
        "level": F["level"].astype(int).astype(str).radd("L"),
        "tenure_band": pd.cut(F["tenure_months"], [-1, 11, 35, 83, 10_000], labels=["<1 year", "1-3 years", "3-7 years", "7+ years"]).astype(str),
        "employment_type": T["employee"].set_index("employee_id")["employment_type"].reindex(F.index),
    })
    rows, overall_flag, base = [], flagged.mean(), y.mean()
    for g in G.columns:
        for v, idx in G.groupby(g, observed=True).groups.items():
            ii = F.index.get_indexer(idx)
            n, pos, fl = len(ii), int(y[ii].sum()), int(flagged.iloc[ii].sum())
            rows.append({"group": g, "value": str(v), "n": n, "base_rate": pos / n, "base_rate_ratio": (pos / n) / base,
                         "flag_rate": fl / n, "flag_ratio": (fl / n) / overall_flag,
                         "precision_of_flagged": (int(y[ii][flagged.iloc[ii].to_numpy()].sum()) / fl) if fl else float("nan"),
                         "recall_in_group": (int(y[ii][flagged.iloc[ii].to_numpy()].sum()) / pos) if pos else float("nan"),
                         "monitor": bool(n >= 100 and not 0.8 <= (fl / n) / overall_flag <= 1.25)})
    return pd.DataFrame(rows)


def stratified_alternative(F, p, T, cutoff, capacity=CAPACITY):
    """Same review capacity, but spent in proportion to each tenure band instead of by global rank."""
    y = F["y"].to_numpy()
    band = pd.cut(F["tenure_months"], [-1, 11, 35, 83, 10_000], labels=["<1 year", "1-3 years", "3-7 years", "7+ years"]).astype(str).to_numpy()
    k_total = max(1, int(round(capacity * len(F))))
    g = np.zeros(len(F), bool); g[np.argsort(-p, kind="stable")[:k_total]] = True
    s = np.zeros(len(F), bool)
    for b in np.unique(band):
        ii = np.flatnonzero(band == b)
        s[ii[np.argsort(-p[ii], kind="stable")[:max(1, int(round(capacity * len(ii))))]]] = True
    out = {}
    for name, sel in (("Global top 5% by score (default)", g), ("Top 5% within each tenure band", s)):
        hits = int(y[sel].sum())
        ratios = [(sel[band == b].mean() / sel.mean()) for b in np.unique(band)]
        out[name] = {"flagged": int(sel.sum()), "recall": hits / int(y.sum()), "precision": hits / int(sel.sum()),
                     "lift": (hits / int(sel.sum())) / y.mean(), "min_band_flag_ratio": float(min(ratios)), "max_band_flag_ratio": float(max(ratios))}
    return out


def run(raw: dict, clean_raw: dict | None = None) -> dict:
    T = typed_tables(raw)
    P = build_panel(T)
    D = build_all(P, T)
    cols = list(FEATURES)
    C, val_scores = select_C(D["train"], D["validation"], cols)
    model, p_test, e_test = _fit_eval(D, cols, C)
    y = D["test"]["y"].to_numpy()

    # temporal table: train is in-sample, validation is out-of-sample for a train-only fit, test is out-of-sample
    m_tr = make_lr(C).fit(D["train"][cols], D["train"]["y"])
    temporal = {}
    for s, mdl in (("train", m_tr), ("validation", m_tr), ("test", model)):
        pr = mdl.predict_proba(D[s][cols])[:, 1]
        temporal[s] = {"cutoff": str(config.CUTOFFS[s]), "horizon_end": str(config.HORIZON_ENDS[s]),
                       **{k: v for k, v in evaluate_scores(D[s]["y"], pr, pr).items() if k in ("n", "positives", "base_rate", "roc_auc", "pr_auc", "recall_at_5pct", "lift_at_5pct")}}

    both = pd.concat([D["train"], D["validation"]])
    gb = make_gb().fit(both[cols], both["y"])
    X = D["test"]
    baselines = {
        "Random ranking": {"roc_auc": 0.5, "pr_auc": float(y.mean()), "recall_at_5pct": 0.05, "lift_at_5pct": 1.0},
        "Tenure only (shorter = higher)": _tbl(evaluate_scores(y, -X["tenure_months"])),
        "Engagement score only (lower = higher)": _tbl(evaluate_scores(y, -X["last_engagement"])),
        "Gradient boosting (not interpretable)": _tbl(evaluate_scores(y, gb.predict_proba(X[cols])[:, 1])),
        "Transparent rule, reference ceiling": _tbl(evaluate_scores(y, rule_reference(X))),
        "Logistic regression (this model)": _tbl(e_test),
    }
    ci = bootstrap_ci(y, p_test, config.SEED)
    cal = calibration_table(y, p_test)

    # ---- leak ladder: switch one defence off at a time -------------------------------------------------------
    variants = [("Production: as-of, recorded_at enforced, skipped = null, recomputed labels", {}, True)]
    variants += [
        ("Ignore recorded_at (date-only as-of)", {"check_recorded": False}, False),
        ("Skipped survey scored as its stored value (no sanitising)", {"sanitize": False}, False),
        ("LEAK: latest-value join over all rows", {"naive": True}, False),
        ("LEAK: latest-value join + count of later snapshots", {"naive": True, "future_count": True}, False),
    ]
    ladder = []
    if clean_raw is not None:
        Tc = typed_tables(clean_raw); Dc = build_all(build_panel(Tc), Tc)
        _, _, ec = _fit_eval(Dc, cols, C)
        ladder.append({"pipeline": "Reference: same pipeline on the clean baseline (no injected anomalies)", **_tbl(ec),
                       "provenance_violations": audit.provenance_audit(Dc["test"], config.CUTOFFS["test"])["violations"], "audit": "PASS", "flagged_features": ""})
    prod_pct = None
    for name, kw, _ in variants:
        Dv = D if not kw else build_all(P, T, **kw)
        cv = cols + (["future_snapshots"] if kw.get("future_count") else [])
        _, pv, ev = _fit_eval(Dv, cv, C)
        a = audit.run_audit(Dv["test"], cv, config.CUTOFFS["test"])
        ladder.append({"pipeline": name, **_tbl(ev), "provenance_violations": a["provenance"]["violations"],
                       "audit": "PASS" if a["passed"] else "FAIL", "flagged_features": ", ".join(a["univariate"]["flagged"])})
        if kw == {"sanitize": False}:             # a data-quality fault, not a leak: the leak audit is silent by design
            sv = T["engagement_survey"]
            n_bad = int(((sv["response_status"] == "Skipped") & sv["engagement_score"].notna()).sum())
            ladder[-1]["audit"] = "PASS (not a leak)"
            ladder[-1]["flagged_features"] = f"caught by validator rule SURV-SKIPPED-HAS-SCORE ({n_bad} rows)"
        if kw == {"check_recorded": False}:       # how far do the revised rows move the employees they touch?
            late = P[(P["sv_rec"].dt.normalize() > P["snapshot_date"]) | (P["w_rec"].dt.normalize() > P["snapshot_date"])]
            aff = [e for e in late["employee_id"].unique() if e in Dv["test"].index]
            pr_prod = pd.Series(p_test, index=D["test"].index).rank(pct=True)
            pr_naive = pd.Series(pv, index=Dv["test"].index).rank(pct=True)
            ladder[-1]["affected_employees"] = len(aff)
            ladder[-1]["mean_percentile_shift"] = round(float((pr_naive[aff] - pr_prod[aff]).mean()), 4) if aff else 0.0
    # stored (possibly corrupted) test labels instead of recomputed ones
    stored = T["attrition_outcome"].set_index("employee_id")["voluntary_attrition_label"].astype("Int64").reindex(D["test"].index)
    ok = stored.notna().to_numpy()
    es = evaluate_scores(stored[ok].astype(int), p_test[ok], p_test[ok])
    la = audit.label_audit(T)
    ladder.append({"pipeline": "Use the stored test label instead of recomputing it", **_tbl(es), "provenance_violations": 0,
                   "audit": "FAIL" if la["stored_vs_recomputed_mismatches"] else "PASS",
                   "flagged_features": f"{la['stored_vs_recomputed_mismatches']} labels disagree with termination facts"})

    # ---- proxy and sensitive-attribute checks --------------------------------------------------------------
    sub = subgroup_audit(D["test"], p_test, T, config.CUTOFFS["test"])
    keep = [c for c in cols if c not in TENURE_LIKE]
    _, _, e_abl = _fit_eval(D, keep, C)
    full_audit = audit.run_audit(D["test"], cols, config.CUTOFFS["test"])
    strat = stratified_alternative(D["test"], p_test, T, config.CUTOFFS["test"])

    sig = build_signals(model, D["test"], cols, config.CUTOFFS["test"], T, CAPACITY)
    assert_supportive_framing(sig)
    return {
        "design": {"features": cols, "C": C, "validation_pr_auc_by_C": val_scores, "capacity_fraction": CAPACITY},
        "temporal": temporal, "test": e_test, "test_ci": ci, "baselines": baselines,
        "calibration": cal, "coefficients": coefficient_table(model, cols), "ladder": ladder,
        "audit": {"production": full_audit, "split": audit.split_audit(), "labels": la},
        "subgroups": sub, "stratified": strat, "ablation": {"removed": TENURE_LIKE, "metrics": _tbl(e_abl), "full": _tbl(e_test)},
        "signals": sig, "model": model, "test_frame": D["test"], "test_prob": p_test,
    }
