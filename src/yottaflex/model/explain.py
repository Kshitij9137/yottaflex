"""Plain-language explanations and the supportive-signal output (never an employment decision)."""
from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd

from .features import FEATURES

THEMES = {
    "Engagement": ["last_engagement", "engagement_drop", "engagement_mean_4q", "low_engagement_gap"],
    "Workload": ["workload_index", "high_load_quarters_4q", "nonpeak_overload_streak", "planned_peak_now"],
    "Career progression": ["months_since_last_promotion", "stagnation_months", "recent_promotion", "level"],
    "Pay position": ["compa_ratio", "pay_gap"],
    "New joiner": ["tenure_months", "new_joiner"],
    "Team and role change": ["months_in_current_team", "recent_transfer"],
    "Recent support": ["recent_intervention"],
    "Survey participation": ["never_responded", "surveys_skipped_4q"],   # context only: never shown as a reason
}
NOT_A_REASON = {"Survey participation", "Recent support"}
TOPICS = {
    "Engagement": "Check in on how work feels right now and what would help",
    "Workload": "Review workload and priorities together",
    "Career progression": "Talk about growth path and promotion timeline",
    "Pay position": "Review pay position against the band with HR",
    "New joiner": "Follow up on onboarding and offer a mentor",
    "Team and role change": "Ask how the recent team or role change is going",
}
USE_NOTE = ("Supportive signal to prioritise a conversation. It is not an employment decision and must not be used "
            "for promotion, pay, performance or termination decisions.")
BANNED_PHRASES = ("terminate", "dismiss", "fire ", "layoff", "lay off", "demote", "performance improvement plan",
                  "will leave", "is going to quit", "replace")
REVIEW_STATUSES = ("Pending_Review", "Reviewed_Conversation_Held", "Reviewed_No_Action")


def _lr(model):
    return model.named_steps["standardscaler"], model.named_steps["logisticregression"]


def contributions(model, X: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Per-employee, per-feature contribution to the log-odds relative to the average employee."""
    sc, lr = _lr(model)
    z = (X[cols].to_numpy() - sc.mean_) / sc.scale_
    return pd.DataFrame(z * lr.coef_[0], index=X.index, columns=cols)


def theme_contributions(contrib: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({t: contrib[[c for c in fs if c in contrib.columns]].sum(axis=1) for t, fs in THEMES.items()})


def _detail(theme: str, r: pd.Series, avg: dict) -> str:
    if theme == "Engagement":
        s = f"Latest engagement score is {r['last_engagement']:.0f}/100 (average {avg['last_engagement']:.0f})"
        return s + (f", down {r['engagement_drop']:.0f} points since the previous survey" if r["engagement_drop"] >= 5 else "")
    if theme == "Workload":
        if r["nonpeak_overload_streak"] >= 1:
            return f"Workload index above 65 in {r['nonpeak_overload_streak']:.0f} consecutive non-peak quarter(s)"
        if r["high_load_quarters_4q"] >= 1:
            return f"High workload in {r['high_load_quarters_4q']:.0f} of the last 4 quarters"
        return f"Workload index is {r['workload_index']:.0f}/100 (average {avg['workload_index']:.0f})"
    if theme == "Career progression":
        return f"{r['months_since_last_promotion']:.0f} months since the last promotion"
    if theme == "Pay position":
        return f"Pay is {r['compa_ratio'] * 100:.0f}% of the band midpoint"
    if theme == "New joiner":
        return f"Joined {r['tenure_months']:.0f} months ago; first-year employees leave more often"
    if theme == "Team and role change":
        return "Moved teams recently" if r["recent_transfer"] else f"{r['months_in_current_team']:.0f} months in the current team"
    return theme


def explain(model, X: pd.DataFrame, cols: list[str], avg: dict, top: int = 3, min_contrib: float = 0.05) -> pd.DataFrame:
    tc = theme_contributions(contributions(model, X, cols))
    reasons = tc.drop(columns=list(NOT_A_REASON))
    rows = []
    for emp, r in X.iterrows():
        t = reasons.loc[emp].sort_values(ascending=False)
        t = t[t > min_contrib].head(top)
        items = [{"factor": k, "contribution": round(float(v), 3), "detail": _detail(k, r, avg)} for k, v in t.items()]
        rows.append({"employee_id": emp, "factors": items})
    return pd.DataFrame(rows).set_index("employee_id")


def context_notes(r: pd.Series) -> str:
    n = []
    if r["planned_peak_now"] >= 1:
        n.append("Planned workload peak this quarter (temporary, not counted as overload)")
    if r["recent_transfer"] >= 1:
        n.append("Moved teams recently")
    if r["new_joiner"] >= 1:
        n.append("New joiner (first year)")
    if r["never_responded"] >= 1 or r["surveys_skipped_4q"] >= 2:
        n.append("Few recent survey responses (a missing survey is not a negative signal)")
    if r["recent_intervention"] >= 1:
        n.append("A retention conversation was already held in the last 6 months")
    return "; ".join(n)


def build_signals(model, F: pd.DataFrame, cols: list[str], cutoff, T: dict, capacity_frac: float = 0.05,
                  model_version: str = "lr-v1") -> pd.DataFrame:
    """Priority list for HR partners: the top `capacity_frac` of scorable employees, each with reasons and a reviewer slot."""
    p = pd.Series(model.predict_proba(F[cols])[:, 1], index=F.index)
    order = p.sort_values(ascending=False, kind="stable")
    k = max(1, int(round(capacity_frac * len(order))))
    top = order.index[:k]
    avg = F[cols].mean().to_dict()
    ex = explain(model, F.loc[top], cols, avg)
    snap = T["tenure_snapshot"]
    team_of = snap[snap["snapshot_date"] == pd.Timestamp(cutoff)].drop_duplicates("employee_id").set_index("employee_id")["team_id"]
    mgr = team_of.map(T["team"].set_index("team_id")["manager_employee_id"])
    E, R, O = T["employee"].set_index("employee_id"), T["role"].set_index("role_id"), T["attrition_outcome"].set_index("employee_id")
    fam = E["initial_role_id"].map(R["job_family"])
    c = pd.Timestamp(cutoff)
    hr = sorted(e for e in fam.index[fam == "People_HR"]
                if E.at[e, "hire_date"] <= c and (pd.isna(O.at[e, "termination_date"]) or O.at[e, "termination_date"] > c))
    out = []
    for i, emp in enumerate(top):
        f = ex.at[emp, "factors"]
        topic = TOPICS.get(f[0]["factor"], "Open, supportive check-in") if f else "Open, supportive check-in"
        text = "; ".join(f"{j + 1}) {x['detail']}" for j, x in enumerate(f)) or "No single factor stands out; discuss openly"
        out.append({
            "scoring_cutoff": c.strftime("%Y-%m-%d"), "employee_id": emp, "rank": i + 1,
            "signal_score": round(float(p[emp]), 4), "signal_band": "Elevated",
            "top_factors_text": text, "factors_json": json.dumps(f, separators=(",", ":")),
            "context_notes": context_notes(F.loc[emp]), "suggested_conversation_topic": topic,
            "manager_employee_id": mgr.get(emp), "assigned_hr_partner_id": hr[i % len(hr)] if hr else None,
            "review_status": "Pending_Review", "reviewed_by_employee_id": "", "reviewed_date": "",
            "human_review_required": True, "automated_action_allowed": False,
            "use_note": USE_NOTE, "model_version": model_version, "explanation_complete": bool(f),
        })
    return pd.DataFrame(out)


def assert_supportive_framing(sig: pd.DataFrame) -> None:
    """Hard guard: no score leaves the system without an explanation, a reviewer slot and the supportive framing."""
    problems = []
    if not sig["human_review_required"].all():
        problems.append("human_review_required must be True on every row")
    if sig["automated_action_allowed"].any():
        problems.append("automated_action_allowed must be False on every row")
    if (sig["top_factors_text"].fillna("").str.strip() == "").any():
        problems.append("a row has no plain-language explanation")
    if not sig["review_status"].isin(REVIEW_STATUSES).all():
        problems.append("unknown review_status")
    pending = sig["review_status"] == "Pending_Review"
    if (sig.loc[pending, "reviewed_by_employee_id"].fillna("") != "").any():
        problems.append("a pending row already names a reviewer")
    if (sig.loc[~pending, "reviewed_by_employee_id"].fillna("") == "").any():
        problems.append("a reviewed row has no reviewer")
    if sig["assigned_hr_partner_id"].isna().any():
        problems.append("a row has no assigned HR partner")
    if not sig["use_note"].str.contains("not an employment decision").all():
        problems.append("framing note missing")
    for r in sig["factors_json"]:
        if not isinstance(json.loads(r), list):
            problems.append("factors_json is not a list"); break
    text = " ".join(sig["top_factors_text"].fillna("") + " " + sig["suggested_conversation_topic"].fillna("")).lower()
    bad = [w for w in BANNED_PHRASES if re.search(re.escape(w), text)]
    if bad:
        problems.append(f"decision-style wording found: {bad}")
    if problems:
        raise ValueError("signals violate the supportive-signal contract: " + "; ".join(problems))
