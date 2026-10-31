"""Validation rules (Step 8): keys, foreign keys, enums, dates, reconciliation, lifecycle, duplicates.

Every rule returns (ids_of_violating_rows, n_rows_checked). Rules never read the ground truth.
A rule may be tagged `maps_to=<issue_type>`: those rules are the anomaly detectors.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from .. import config, ids, labels
from ..dates import months_between
from ..generate.params import FACTOR_NAMES
from .schema import SCHEMA, coerce

WS, WE = pd.Timestamp(config.WINDOW_START), pd.Timestamp(config.WINDOW_END)
QEND = {q: pd.Timestamp(ids.quarter_end(q)) for q in config.QUARTERS}


@dataclass(frozen=True)
class Rule:
    rule_id: str
    category: str
    entity: str
    description: str
    fn: Callable
    maps_to: str | None = None


RULES: list[Rule] = []


def rule(rid, category, entity, description, maps_to=None):
    def deco(fn):
        RULES.append(Rule(rid, category, entity, description, fn, maps_to))
        return fn
    return deco


def _ids(df: pd.DataFrame, mask) -> list:
    m = pd.Series(np.asarray(mask, dtype=object), index=df.index)
    m = m.where(m.notna(), False).astype(bool)          # NA counts as "no violation" (no FutureWarning downcast)
    return df.loc[m, df.columns[0]].tolist()


def _months(a: pd.Series, b: pd.Series) -> pd.Series:
    ok = a.notna() & b.notna()
    out = pd.Series(np.nan, index=a.index)
    out[ok] = months_between(a[ok].to_numpy("datetime64[D]"), b[ok].to_numpy("datetime64[D]"))
    return out


def _asof(left, right, left_on, right_on, by, cols):
    L = left.dropna(subset=[left_on, by]).sort_values(left_on, kind="stable")
    R = right.dropna(subset=[right_on, by]).sort_values(right_on, kind="stable")
    return pd.merge_asof(L, R[[by, right_on, *cols]], left_on=left_on, right_on=right_on, by=by,
                         direction="backward", suffixes=("", "_r"))


class Ctx:
    """Typed tables plus a few cached joins shared by many rules."""

    def __init__(self, raw: dict[str, pd.DataFrame]):
        self.T, self.type_bad, self.col_problems = {}, {}, {}
        for name, cols in SCHEMA.items():
            typed, bad, prob = coerce(raw[name], cols)
            self.T[name], self.type_bad[name], self.col_problems[name] = typed, bad, prob
        T = self.T
        self.emp = T["employee"].drop_duplicates("employee_id").set_index("employee_id")
        self.out = T["attrition_outcome"].drop_duplicates("employee_id").set_index("employee_id")
        self.role = T["role"].drop_duplicates("role_id").set_index("role_id")
        self.team = T["team"].drop_duplicates("team_id").set_index("team_id")
        S = T["tenure_snapshot"]
        self.snap = S.drop_duplicates("snapshot_id").set_index("snapshot_id")
        self.hire = S["employee_id"].map(self.emp["hire_date"])
        self.term = S["employee_id"].map(self.out["termination_date"])
        self._cache = {}

    def cached(self, key, fn):
        if key not in self._cache:
            self._cache[key] = fn()
        return self._cache[key]

    @property
    def snap_assign(self):
        def f():
            A = self.T["employee_team_assignment"].rename(columns={
                "team_id": "a_team", "effective_from": "a_from", "effective_to": "a_to"})
            return _asof(self.T["tenure_snapshot"], A, "snapshot_date", "a_from", "employee_id", ["a_team", "a_to"])
        return self.cached("snap_assign", f)

    @property
    def snap_promo(self):
        def f():
            P = self.T["promotion_history"]
            P = P[P["event_type"] == "Promotion"].rename(columns={"effective_date": "last_promo"})
            return _asof(self.T["tenure_snapshot"], P, "snapshot_date", "last_promo", "employee_id", [])
        return self.cached("snap_promo", f)

    @property
    def snap_event(self):
        def f():
            P = self.T["promotion_history"].rename(columns={"effective_date": "ev_date", "to_role_id": "ev_role"})
            return _asof(self.T["tenure_snapshot"], P, "snapshot_date", "ev_date", "employee_id", ["ev_role"])
        return self.cached("snap_event", f)

    @property
    def snap_band(self):
        def f():
            B = self.T["compensation_band"].rename(columns={"effective_from": "b_from", "effective_to": "b_to"})
            return _asof(self.T["tenure_snapshot"], B, "snapshot_date", "b_from", "role_id", ["b_to", "annual_mid"])
        return self.cached("snap_band", f)


# ---------------------------------------------------------------------------
# Generated schema rules: one rule per (table, kind)
# ---------------------------------------------------------------------------
def _gen_schema_rules():
    for table, cols in SCHEMA.items():
        pk = cols[0]

        def columns(c, table=table):
            return ([f"{table}: {c.col_problems[table][0]}"] if c.col_problems[table] else []), 1
        rule(f"SCH-COLUMNS:{table}", "Schema", table, "Columns match the data dictionary (names, order)")(columns)

        def types(c, table=table):
            df = c.T[table]
            return df[df.columns[0]].iloc[c.type_bad[table]].tolist(), len(df)
        rule(f"SCH-TYPE:{table}", "Schema", table, "Every value parses as its declared type")(types)

        def required(c, table=table, cols=cols):
            df = c.T[table]
            need = [x.name for x in cols if x.req]
            return _ids(df, df[need].isna().any(axis=1)), len(df)
        rule(f"SCH-REQUIRED:{table}", "Schema", table, "Required fields are not null")(required)

        def enums(c, table=table, cols=cols):
            df = c.T[table]
            bad = pd.Series(False, index=df.index)
            for x in cols:
                if x.allowed is not None:
                    bad |= (df[x.name].notna() & ~df[x.name].isin(list(x.allowed))).fillna(False)
            return _ids(df, bad), len(df)
        rule(f"SCH-ENUM:{table}", "Schema", table, "Values are within the allowed enumerations")(enums)

        def ranges(c, table=table, cols=cols):
            df = c.T[table]
            bad = pd.Series(False, index=df.index)
            for x in cols:
                if x.lo is not None:
                    bad |= (df[x.name].astype("float64") < x.lo - 1e-9).fillna(False)
                if x.hi is not None:
                    bad |= (df[x.name].astype("float64") > x.hi + 1e-9).fillna(False)
            return _ids(df, bad), len(df)
        rule(f"SCH-RANGE:{table}", "Schema", table, "Numeric values are within documented ranges")(ranges)

        def uniq(c, table=table):
            df = c.T[table]
            return _ids(df, df[df.columns[0]].duplicated(keep="first")), len(df)
        rule(f"KEY-PK-UNIQUE:{table}", "Keys", table, "Primary key is unique")(uniq)

        def fmt(c, table=table, kind=pk.kind):
            df = c.T[table]
            ok = df[df.columns[0]].fillna("").astype(str).str.match(ids.PATTERNS[kind].pattern)
            return _ids(df, ~ok), len(df)
        rule(f"KEY-PK-FORMAT:{table}", "Keys", table, "Primary key matches the ID convention")(fmt)

        if table != "employee":  # employee has no attributes beyond the ID by design, so coincidences are legitimate
            def dup_row(c, table=table):
                df = c.T[table]
                return _ids(df, df.drop(columns=[df.columns[0]]).astype(str).duplicated(keep="first")), len(df)
            rule(f"DUP-ROW:{table}", "Duplicates", table, "No row repeats another row apart from its ID")(dup_row)

        for col in cols:
            if col.fk:
                def fk(c, table=table, col=col):
                    df = c.T[table]
                    parent = c.T[col.fk[0]][col.fk[1]]
                    return _ids(df, df[col.name].notna() & ~df[col.name].isin(parent)), int(df[col.name].notna().sum())
                rule(f"FK:{table}.{col.name}", "Foreign keys", table,
                     f"{col.name} exists in {col.fk[0]}.{col.fk[1]}")(fk)


_gen_schema_rules()

NATURAL = {
    "role": ["job_family", "level"], "compensation_band": ["role_id", "effective_from"],
    "employee_team_assignment": ["employee_id", "effective_from"], "tenure_snapshot": ["employee_id", "snapshot_quarter"],
    "promotion_history": ["employee_id", "effective_date", "event_type"],
    "intervention": ["employee_id", "trigger_snapshot_id"], "team": ["team_name"],
    "attrition_outcome": ["employee_id"], "engagement_survey": ["snapshot_id"], "workload_snapshot": ["snapshot_id"],
}
for _t, _k in NATURAL.items():
    def _nat(c, t=_t, k=_k):
        df = c.T[t]
        return _ids(df, df.duplicated(subset=k, keep="first")), len(df)
    rule(f"DUP-NATURAL:{_t}", "Duplicates", _t, f"No duplicate natural key {tuple(_k)}")(_nat)


# ---------------------------------------------------------------------------
# Keys that embed other fields
# ---------------------------------------------------------------------------
@rule("KEY-COMPOSITE:tenure_snapshot", "Keys", "tenure_snapshot", "snapshot_id = SNAP-<employee_id>-<quarter>")
def _(c):
    S = c.T["tenure_snapshot"]
    return _ids(S, S["snapshot_id"] != "SNAP-" + S["employee_id"].astype(str) + "-" + S["snapshot_quarter"].astype(str)), len(S)


@rule("KEY-COMPOSITE:workload_snapshot", "Keys", "workload_snapshot", "workload_id = WKL-<employee_id>-<quarter of its snapshot>")
def _(c):
    W = c.T["workload_snapshot"]
    q = W["snapshot_id"].map(c.snap["snapshot_quarter"])
    return _ids(W, W["workload_id"] != "WKL-" + W["employee_id"].astype(str) + "-" + q.astype(str)), len(W)


@rule("KEY-COMPOSITE:attrition_outcome", "Keys", "attrition_outcome", "outcome_id = OUT-<employee_id>-2026")
def _(c):
    O = c.T["attrition_outcome"]
    return _ids(O, O["outcome_id"] != "OUT-" + O["employee_id"].astype(str) + f"-{config.OUTCOME_YEAR}"), len(O)


@rule("KEY-COMPOSITE:compensation_band", "Keys", "compensation_band", "band_id = BAND-<role number>-<fiscal year start>")
def _(c):
    B = c.T["compensation_band"]
    exp = "BAND-" + B["role_id"].astype(str).str[5:] + "-" + B["effective_from"].dt.year.astype(str)
    return _ids(B, B["band_id"] != exp), len(B)


@rule("KEY-COMPOSITE:engagement_survey", "Keys", "engagement_survey", "survey_id year = year of survey_date")
def _(c):
    V = c.T["engagement_survey"]
    return _ids(V, V["survey_id"].astype(str).str[5:9] != V["survey_date"].dt.year.astype(str)), len(V)


@rule("KEY-COMPOSITE:intervention", "Keys", "intervention", "intervention_id year = year of proposed_date")
def _(c):
    I = c.T["intervention"]
    return _ids(I, I["intervention_id"].astype(str).str[4:8] != I["proposed_date"].dt.year.astype(str)), len(I)


@rule("KEY-COMPOSITE:role", "Keys", "role", "role_title = '<job_family> L<level>'")
def _(c):
    R = c.T["role"]
    return _ids(R, R["role_title"] != R["job_family"].astype(str) + " L" + R["level"].astype(str)), len(R)


# ---------------------------------------------------------------------------
# Cardinality and join consistency
# ---------------------------------------------------------------------------
def _count_rule(parent, pk, child, fk, rid, desc, exact=True):
    def fn(c):
        P = c.T[parent]
        n = c.T[child][fk].value_counts()
        cnt = P[pk].map(n).fillna(0)
        return _ids(P, (cnt != 1) if exact else (cnt < 1)), len(P)
    rule(rid, "Cardinality", parent, desc)(fn)


_count_rule("tenure_snapshot", "snapshot_id", "engagement_survey", "snapshot_id", "CARD-SNAPSHOT-SURVEY-1TO1", "Each snapshot has exactly one survey row")
_count_rule("tenure_snapshot", "snapshot_id", "workload_snapshot", "snapshot_id", "CARD-SNAPSHOT-WORKLOAD-1TO1", "Each snapshot has exactly one workload row")
_count_rule("employee", "employee_id", "attrition_outcome", "employee_id", "CARD-EMPLOYEE-OUTCOME-1TO1", "Each employee has exactly one outcome")
_count_rule("employee", "employee_id", "tenure_snapshot", "employee_id", "CARD-EMPLOYEE-SNAPSHOT", "Each employee has at least one snapshot", exact=False)
_count_rule("employee", "employee_id", "employee_team_assignment", "employee_id", "CARD-EMPLOYEE-ASSIGNMENT", "Each employee has at least one team assignment", exact=False)


@rule("CARD-CHILD-EMPLOYEE-CONSISTENT", "Cardinality", "engagement_survey",
      "Survey, workload and intervention rows agree with their snapshot on the employee")
def _(c):
    bad = []
    for t, col in (("engagement_survey", "snapshot_id"), ("workload_snapshot", "snapshot_id"), ("intervention", "trigger_snapshot_id")):
        df = c.T[t]
        own = df[col].map(c.snap["employee_id"])
        bad += _ids(df, own.notna() & (own != df["employee_id"]))
    return bad, sum(len(c.T[t]) for t in ("engagement_survey", "workload_snapshot", "intervention"))


# ---------------------------------------------------------------------------
# Conditional / lifecycle completeness rules
# ---------------------------------------------------------------------------
ITEMS = ["q_manager_support", "q_growth_opportunity", "q_workload_sustainable", "q_recognition", "q_intent_to_stay"]


@rule("COND-SURVEY", "Conditional rules", "engagement_survey",
      "Item count matches items_answered and response_status; answered surveys carry a score")
def _(c):
    V = c.T["engagement_survey"]
    n = V[ITEMS].notna().sum(axis=1)
    st = V["response_status"]
    bad = (n != V["items_answered"]) | ((st == "Responded") & (n != 5)) | ((st == "Partial") & ~n.between(3, 4)) | ((st == "Skipped") & (n != 0))
    bad |= (n > 0) & V["engagement_score"].isna()
    return _ids(V, bad), len(V)


@rule("SURV-SKIPPED-HAS-SCORE", "Conditional rules", "engagement_survey",
      "A skipped survey must have a null score (missing is never a negative score)", maps_to="missing_survey_as_negative")
def _(c):
    V = c.T["engagement_survey"]
    return _ids(V, (V["response_status"] == "Skipped") & V["engagement_score"].notna()), len(V)


@rule("COND-OUTCOME", "Conditional rules", "attrition_outcome",
      "termination_date iff exited; reason only for voluntary exits; cutoff and horizon are the documented constants")
def _(c):
    O = c.T["attrition_outcome"]
    exited = O["final_status"] != "Active"
    bad = (exited != O["termination_date"].notna())
    bad |= O["termination_reason_category"].notna() & (O["final_status"] != "Exited_Voluntary")
    bad |= O["prediction_cutoff_date"] != pd.Timestamp(config.CUTOFFS["test"])
    bad |= O["horizon_end_date"] != pd.Timestamp(config.HORIZON_ENDS["test"])
    return _ids(O, bad), len(O)


@rule("COND-INTERVENTION", "Conditional rules", "intervention",
      "Signal fields present iff Signal_Flagged; reviewer and review date iff reviewed; explanation is valid JSON")
def _(c):
    I = c.T["intervention"]
    sig = I["trigger_source"] == "Signal_Flagged"
    rv = I["review_status"].isin(["Approved", "Declined"])
    bad = (sig != I["signal_score"].notna()) | (sig != I["signal_top_factors"].notna())
    bad |= sig & (I["review_status"] == "Not_Required")
    bad |= ~sig & (I["review_status"] != "Not_Required")
    bad |= rv != I["reviewed_by_employee_id"].notna()
    bad |= I["reviewed_by_employee_id"].notna() != I["reviewed_date"].notna()

    def valid(s):
        if s is None or pd.isna(s):
            return True
        try:
            v = json.loads(s)
            return bool(v) and all(x.get("factor") in FACTOR_NAMES for x in v) and len(v) <= 3
        except Exception:
            return False
    bad |= ~I["signal_top_factors"].map(valid).astype(bool)
    return _ids(I, bad), len(I)


@rule("REVIEW-SIGNAL-UNEXPLAINED-OR-UNREVIEWED", "Conditional rules", "intervention",
      "A conducted individual signal needs an explanation, a human reviewer and Approved status",
      maps_to="unreviewed_individual_score")
def _(c):
    I = c.T["intervention"]
    done = (I["trigger_source"] == "Signal_Flagged") & I["status"].isin(["Conducted", "Closed"])
    bad = done & (I["signal_top_factors"].isna() | I["reviewed_by_employee_id"].isna() | (I["review_status"] != "Approved"))
    return _ids(I, bad), int(done.sum())


# ---------------------------------------------------------------------------
# Date ordering and temporal availability
# ---------------------------------------------------------------------------
@rule("DATE-SNAPSHOT-QUARTER", "Dates", "tenure_snapshot", "snapshot_date is the last day of snapshot_quarter and inside the window")
def _(c):
    S = c.T["tenure_snapshot"]
    return _ids(S, (S["snapshot_date"] != S["snapshot_quarter"].map(QEND)) | (S["snapshot_date"] < WS) | (S["snapshot_date"] > WE)), len(S)


@rule("DATE-SNAPSHOT-AFTER-HIRE", "Dates", "tenure_snapshot", "snapshot_date is on or after hire_date")
def _(c):
    S = c.T["tenure_snapshot"]
    return _ids(S, S["snapshot_date"] < c.hire), len(S)


@rule("DATE-SURVEY-WINDOW", "Dates", "engagement_survey", "survey_date is inside its snapshot quarter, after hire, not after the snapshot date")
def _(c):
    V = c.T["engagement_survey"]
    sd = V["snapshot_id"].map(c.snap["snapshot_date"])
    qs = sd.dt.to_period("Q").dt.start_time.astype("datetime64[ns]")
    hire = V["employee_id"].map(c.emp["hire_date"])
    return _ids(V, (V["survey_date"] > sd) | (V["survey_date"] < qs) | (V["survey_date"] < hire)), len(V)


@rule("DATE-RECORDED-AFTER-EVENT", "Dates", "employee", "recorded_at is not before the event it records")
def _(c):
    E, P, O, V = c.T["employee"], c.T["promotion_history"], c.T["attrition_outcome"], c.T["engagement_survey"]
    bad = []
    bad += _ids(E, E["recorded_at"].dt.normalize() < E["hire_date"])
    bad += _ids(P, P["recorded_at"].dt.normalize() < P["effective_date"])
    bad += _ids(O, O["termination_date"].notna() & (O["recorded_at"].dt.normalize() < O["termination_date"]))
    bad += _ids(V, V["recorded_at"].dt.normalize() < V["survey_date"])
    return bad, len(E) + len(P) + len(O) + len(V)


@rule("DATE-PROMOTION-EMPLOYMENT", "Dates", "promotion_history", "Role events fall during employment and inside the data window")
def _(c):
    P = c.T["promotion_history"]
    hire = P["employee_id"].map(c.emp["hire_date"]); term = P["employee_id"].map(c.out["termination_date"])
    return _ids(P, (P["effective_date"] < hire) | (P["effective_date"] > term.fillna(WE)) | (P["effective_date"] > WE)), len(P)


@rule("DATE-ASSIGNMENT", "Dates", "employee_team_assignment",
      "Assignments start at hire, never end before they start, are contiguous, and close on the termination date")
def _(c):
    A = c.T["employee_team_assignment"].sort_values(["employee_id", "effective_from"], kind="stable")
    g = A.groupby("employee_id")
    prev_to = g["effective_to"].shift(1)
    first = g.cumcount() == 0
    last = g.cumcount(ascending=False) == 0
    hire = A["employee_id"].map(c.emp["hire_date"]); term = A["employee_id"].map(c.out["termination_date"])
    bad = A["effective_to"].notna() & (A["effective_to"] < A["effective_from"])
    bad |= first & ((A["effective_from"] != hire) | (A["change_reason"] != "Hire"))
    bad |= ~first & ((A["change_reason"] == "Hire") | (prev_to.isna()) | (A["effective_from"] != prev_to + pd.Timedelta(days=1)))
    bad |= last & (A["effective_to"].fillna(pd.Timestamp("2100-01-01")) != term.fillna(pd.Timestamp("2100-01-01")))
    return _ids(A, bad), len(A)


@rule("DATE-BAND-VERSIONS", "Dates", "compensation_band", "Band versions per role are ordered, contiguous and the last one is open")
def _(c):
    B = c.T["compensation_band"].sort_values(["role_id", "effective_from"], kind="stable")
    g = B.groupby("role_id")
    prev_to = g["effective_to"].shift(1)
    first, last = g.cumcount() == 0, g.cumcount(ascending=False) == 0
    bad = B["effective_to"].notna() & (B["effective_to"] < B["effective_from"])
    bad |= ~first & (B["effective_from"] != prev_to + pd.Timedelta(days=1))
    bad |= last != B["effective_to"].isna()
    return _ids(B, bad), len(B)


@rule("DATE-OUTCOME-WINDOW", "Dates", "attrition_outcome",
      "termination_date is inside the window, after hire and after the first snapshot")
def _(c):
    O = c.T["attrition_outcome"]
    hire = O["employee_id"].map(c.emp["hire_date"])
    first = O["employee_id"].map(c.T["tenure_snapshot"].groupby("employee_id")["snapshot_date"].min())
    t = O["termination_date"]
    return _ids(O, t.notna() & ((t < WS) | (t > WE) | (t <= hire) | (t <= first))), int(t.notna().sum())


@rule("DATE-INTERVENTION-ORDER", "Dates", "intervention",
      "proposed <= reviewed <= conducted <= closed; proposed after its trigger snapshot; all inside employment and the window")
def _(c):
    I = c.T["intervention"]
    sd = I["trigger_snapshot_id"].map(c.snap["snapshot_date"]); term = I["employee_id"].map(c.out["termination_date"]).fillna(WE + pd.Timedelta(days=1))
    bad = I["proposed_date"] <= sd
    for a, b in (("proposed_date", "reviewed_date"), ("reviewed_date", "conducted_date"), ("conducted_date", "closed_date"), ("proposed_date", "conducted_date")):
        bad |= I[a].notna() & I[b].notna() & (I[b] < I[a])
    for col in ("reviewed_date", "conducted_date"):
        bad |= I[col].notna() & (I[col] > term)
    bad |= I["proposed_date"] > term
    for col in ("proposed_date", "reviewed_date", "conducted_date", "closed_date"):
        bad |= I[col].notna() & (I[col] > WE)
    return _ids(I, bad), len(I)


@rule("DATE-TEAM", "Dates", "team", "Teams are created before the window")
def _(c):
    T_ = c.T["team"]
    return _ids(T_, T_["created_date"] > WS), len(T_)


def _late(table, snap_col):
    def fn(c):
        df = c.T[table]
        day = df["snapshot_date"] if snap_col is None else df[snap_col].map(c.snap["snapshot_date"])
        return _ids(df, df["recorded_at"].dt.normalize() > day), len(df)
    return fn


for _t, _s in (("tenure_snapshot", None), ("engagement_survey", "snapshot_id"), ("workload_snapshot", "snapshot_id")):
    rule(f"TIME-LATE-RECORDED:{_t}", "Temporal availability", _t,
         "Row was recorded no later than the end of its own snapshot day (no back-filled or revised rows)",
         maps_to="future_information_leak")(_late(_t, _s))


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
@rule("LIFE-SNAPSHOT-AFTER-EXIT", "Lifecycle", "tenure_snapshot", "No snapshot exists on or after the termination date",
      maps_to="future_information_leak")
def _(c):
    S = c.T["tenure_snapshot"]
    return _ids(S, c.term.notna() & (S["snapshot_date"] >= c.term)), len(S)


def _child_after_exit(table):
    def fn(c):
        df = c.T[table]
        sd = df["snapshot_id"].map(c.snap["snapshot_date"]); term = df["employee_id"].map(c.out["termination_date"])
        return _ids(df, term.notna() & (sd >= term)), len(df)
    return fn


for _t in ("engagement_survey", "workload_snapshot"):
    rule(f"LIFE-CHILD-AFTER-EXIT:{_t}", "Lifecycle", _t, "No survey or workload row hangs off a post-exit snapshot",
         maps_to="future_information_leak")(_child_after_exit(_t))


@rule("LIFE-INTERVENTION-TRANSITIONS", "Lifecycle", "intervention",
      "Status is consistent with the stage dates and review state (Proposed -> Approved -> Conducted -> Closed, or Declined)")
def _(c):
    I = c.T["intervention"]
    s, rv = I["status"], I["review_status"]
    cond, clo = I["conducted_date"].notna(), I["closed_date"].notna()
    ok_review = rv.isin(["Approved", "Not_Required"])
    bad = ((s == "Declined") & ((rv != "Declined") | cond | clo))
    bad |= (s == "Proposed") & (cond | clo | rv.isin(["Approved", "Declined"]))
    bad |= (s == "Approved") & (~(rv == "Approved") | cond | clo)
    bad |= (s == "Conducted") & (~cond | clo | ~ok_review)
    bad |= (s == "Closed") & (~cond | ~clo | ~ok_review)
    bad |= (~s.isin(["Conducted", "Closed"])) & ((I["hazard_multiplier"] != 1.0))
    return _ids(I, bad), len(I)


@rule("LIFE-REVIEWER", "Lifecycle", "intervention", "The reviewer is an HR partner who is employed on the review date")
def _(c):
    I = c.T["intervention"]
    r = I["reviewed_by_employee_id"]
    fam = r.map(c.emp["initial_role_id"]).map(c.role["job_family"])
    hire = r.map(c.emp["hire_date"]); term = r.map(c.out["termination_date"])
    bad = r.notna() & ((fam != "People_HR") | (hire > I["reviewed_date"]) | (term.notna() & (term <= I["reviewed_date"])))
    return _ids(I, bad), int(r.notna().sum())


@rule("LIFE-MANAGER", "Lifecycle", "team", "Team manager was hired before the window, holds level >= 4 at window start, same family")
def _(c):
    T_ = c.T["team"].copy()
    m = T_.rename(columns={"manager_employee_id": "employee_id"})[["team_id", "employee_id", "job_family"]].copy()
    m["d"] = pd.Series([WS] * len(m), index=m.index).astype("datetime64[ns]")
    P = c.T["promotion_history"].rename(columns={"effective_date": "ev_date", "to_role_id": "ev_role"})
    a = _asof(m, P, "d", "ev_date", "employee_id", ["ev_role"])
    role = a["employee_id"].map(c.emp["initial_role_id"]).where(a["ev_role"].isna(), a["ev_role"])
    lvl, fam = role.map(c.role["level"]), role.map(c.role["job_family"])
    hire = a["employee_id"].map(c.emp["hire_date"])
    bad = (lvl < 4) | (fam != a["job_family"]) | (hire >= WS)
    return a.loc[bad.fillna(False).to_numpy(), "team_id"].tolist(), len(a)


@rule("LIFE-NO-INTERVENTION-AFTER-EXIT", "Lifecycle", "intervention", "No intervention is proposed after the employee has left")
def _(c):
    I = c.T["intervention"]
    term = I["employee_id"].map(c.out["termination_date"])
    return _ids(I, term.notna() & (I["proposed_date"] > term)), len(I)


# ---------------------------------------------------------------------------
# Arithmetic reconciliation (derived values recompute from source records)
# ---------------------------------------------------------------------------
@rule("RECON-TENURE", "Reconciliation", "tenure_snapshot", "tenure_months = whole months from hire_date to snapshot_date")
def _(c):
    S = c.T["tenure_snapshot"]
    return _ids(S, _months(c.hire, S["snapshot_date"]) != S["tenure_months"].astype("float64")), len(S)


@rule("RECON-MONTHS-SINCE-PROMOTION", "Reconciliation", "tenure_snapshot",
      "months_since_last_promotion recomputes from PromotionHistory (hire date if none)")
def _(c):
    m = c.snap_promo
    base = m["last_promo"].fillna(m["employee_id"].map(c.emp["hire_date"]))
    bad = _months(base, m["snapshot_date"]) != m["months_since_last_promotion"].astype("float64")
    return m.loc[bad.to_numpy(), "snapshot_id"].tolist(), len(m)


@rule("RECON-MONTHS-IN-TEAM", "Reconciliation", "tenure_snapshot", "months_in_current_team recomputes from EmployeeTeamAssignment")
def _(c):
    m = c.snap_assign
    bad = _months(m["a_from"], m["snapshot_date"]) != m["months_in_current_team"].astype("float64")
    return m.loc[bad.to_numpy(), "snapshot_id"].tolist(), len(m)


@rule("RECON-TEAM", "Reconciliation", "tenure_snapshot", "Snapshot team equals the assignment that covers snapshot_date")
def _(c):
    m = c.snap_assign
    covered = m["a_to"].isna() | (m["a_to"] >= m["snapshot_date"])
    bad = (m["a_team"] != m["team_id"]) | ~covered | m["a_team"].isna()
    return m.loc[bad.to_numpy(), "snapshot_id"].tolist(), len(m)


@rule("RECON-ROLE", "Reconciliation", "tenure_snapshot", "Snapshot role equals the latest role event (or the initial role)")
def _(c):
    m = c.snap_event
    exp = m["employee_id"].map(c.emp["initial_role_id"]).where(m["ev_role"].isna(), m["ev_role"])
    return m.loc[(exp != m["role_id"]).to_numpy(), "snapshot_id"].tolist(), len(m)


@rule("RECON-COMPA", "Reconciliation", "tenure_snapshot", "compa_ratio = base salary / band midpoint effective on snapshot_date")
def _(c):
    m = c.snap_band
    in_band = m["b_to"].isna() | (m["b_to"] >= m["snapshot_date"])
    exp = m["base_salary_annual"].astype("float64") / m["annual_mid"].astype("float64")
    bad = ~in_band | ((exp - m["compa_ratio"]).abs() > 0.0006)
    return m.loc[bad.fillna(True).to_numpy(), "snapshot_id"].tolist(), len(m)


@rule("RECON-SALARY-STEP", "Reconciliation", "tenure_snapshot",
      "Salary changes between snapshots only by an April merit step (0-10%) or to a role event's new salary")
def _(c):
    S = c.T["tenure_snapshot"].sort_values(["employee_id", "snapshot_date"], kind="stable").reset_index(drop=True)
    g = S.groupby("employee_id")
    S["prev_sal"], S["prev_date"] = g["base_salary_annual"].shift(1).astype("float64"), g["snapshot_date"].shift(1)
    P = c.T["promotion_history"].rename(columns={"effective_date": "ev_date", "new_base_salary_annual": "ev_new"})
    m = _asof(S, P, "snapshot_date", "ev_date", "employee_id", ["ev_new"])
    m = m[m["prev_sal"].notna()]
    in_int = m["ev_date"].notna() & (m["ev_date"] > m["prev_date"])
    cur = m["base_salary_annual"].astype("float64"); ratio = cur / m["prev_sal"]
    apr = pd.to_datetime(m["snapshot_date"].dt.year.astype(str) + "-04-01").astype("datetime64[ns]")
    cross = (m["prev_date"] < apr) & (m["snapshot_date"] >= apr)
    ok_event = (cur == m["ev_new"].astype("float64"))
    ok_merit = np.where(cross, (ratio >= 1 - 1e-9) & (ratio <= 1.10 + 1e-3), (ratio - 1).abs() < 1e-9)
    bad = np.where(in_int, ~ok_event, ~ok_merit)
    return m.loc[bad, "snapshot_id"].tolist(), len(m)


@rule("RECON-SNAPSHOT-FLAGS", "Reconciliation", "tenure_snapshot",
      "transfer_in_quarter and promotion_in_quarter match the assignment and promotion events in that quarter")
def _(c):
    S = c.T["tenure_snapshot"].drop_duplicates("snapshot_id").copy()
    S["qs"] = S["snapshot_date"].dt.to_period("Q").dt.start_time.astype("datetime64[ns]")
    A = c.T["employee_team_assignment"]; A = A[A["change_reason"] != "Hire"][["employee_id", "effective_from"]]
    P = c.T["promotion_history"]; P = P[P["event_type"] == "Promotion"][["employee_id", "effective_date"]]
    out = {}
    for name, ev, col in (("tr", A, "effective_from"), ("pr", P, "effective_date")):
        j = S[["snapshot_id", "employee_id", "qs", "snapshot_date"]].merge(ev, on="employee_id", how="inner")
        hit = j[(j[col] >= j["qs"]) & (j[col] <= j["snapshot_date"])]["snapshot_id"].unique()
        out[name] = S["snapshot_id"].isin(hit)
    bad = (out["tr"] != S["transfer_in_quarter"].fillna(False).astype(bool)) | (out["pr"] != S["promotion_in_quarter"].fillna(False).astype(bool))
    return _ids(S, bad.to_numpy()), len(S)


@rule("RECON-PEAK-FLAG", "Reconciliation", "workload_snapshot",
      "planned_peak_flag = (team.planned_peak_quarter == calendar quarter of the snapshot)")
def _(c):
    W = c.T["workload_snapshot"]
    team = W["snapshot_id"].map(c.snap["team_id"]); q = W["snapshot_id"].map(c.snap["snapshot_date"]).dt.quarter
    exp = team.map(c.team["planned_peak_quarter"]) == q
    return _ids(W, exp != W["planned_peak_flag"].fillna(False).astype(bool)), len(W)


@rule("RECON-WORKLOAD", "Reconciliation", "workload_snapshot", "overtime, workload_index and high_load_flag recompute from hours, projects and on-call days")
def _(c):
    W = c.T["workload_snapshot"]
    h, p, o = W["avg_weekly_hours"], W["active_project_count"].astype("float64"), W["on_call_days"].astype("float64")
    ot = (h - 40).clip(lower=0) * 13
    idx = (100 * (0.55 * (h - 35) / 20 + 0.30 * p / 8 + 0.15 * o / 20)).clip(0, 100)
    bad = ((ot - W["overtime_hours_quarter"]).abs() > 0.06) | ((idx - W["workload_index"]).abs() > 0.06)
    bad |= (W["workload_index"] >= 65) != W["high_load_flag"].fillna(False).astype(bool)
    return _ids(W, bad), len(W)


@rule("RECON-SURVEY-SCORE", "Reconciliation", "engagement_survey", "engagement_score = 100 x (mean of answered items - 1) / 4")
def _(c):
    V = c.T["engagement_survey"]
    mean = V[ITEMS].astype("float64").mean(axis=1)
    exp = 100 * (mean - 1) / 4
    ans = V[ITEMS].notna().any(axis=1)
    return _ids(V, ans & ((exp - V["engagement_score"]).abs() > 0.051)), int(ans.sum())


@rule("RECON-PROMOTION-PCT", "Reconciliation", "promotion_history", "salary_change_pct recomputes from salaries and sits in its documented range")
def _(c):
    P = c.T["promotion_history"]
    pct = 100 * (P["new_base_salary_annual"].astype("float64") / P["prior_base_salary_annual"].astype("float64") - 1)
    promo = P["event_type"] == "Promotion"
    bad = ((pct - P["salary_change_pct"]).abs() > 0.006)
    bad |= promo & ~pct.between(6 - 0.05, 20 + 0.05) | ~promo & ~pct.between(-0.05, 5 + 0.05)
    return _ids(P, bad), len(P)


@rule("RECON-PROMOTION-CHAIN", "Reconciliation", "promotion_history",
      "Each role event starts from the previous role; promotions go up one level in the same family; lateral moves keep the level")
def _(c):
    P = c.T["promotion_history"].sort_values(["employee_id", "effective_date"], kind="stable")
    prev_to = P.groupby("employee_id")["to_role_id"].shift(1)
    exp_from = prev_to.where(prev_to.notna(), P["employee_id"].map(c.emp["initial_role_id"]))
    lf, lt = P["from_role_id"].map(c.role["level"]), P["to_role_id"].map(c.role["level"])
    ff, ft = P["from_role_id"].map(c.role["job_family"]), P["to_role_id"].map(c.role["job_family"])
    promo = P["event_type"] == "Promotion"
    bad = (exp_from != P["from_role_id"]) | (promo & ((ff != ft) | (lt != lf + 1))) | (~promo & ((lt != lf) | (ff == ft)))
    return _ids(P, bad), len(P)


@rule("RECON-BAND-MID", "Reconciliation", "compensation_band", "annual_mid = (min + max) / 2 and min < mid < max")
def _(c):
    B = c.T["compensation_band"]
    return _ids(B, ((B["annual_min"] + B["annual_max"]) // 2 != B["annual_mid"]) | ~((B["annual_min"] < B["annual_mid"]) & (B["annual_mid"] < B["annual_max"]))), len(B)


def _eligible(c):
    O = c.T["attrition_outcome"]
    cut = pd.Timestamp(config.CUTOFFS["test"])
    have = set(c.T["tenure_snapshot"].loc[c.T["tenure_snapshot"]["snapshot_date"] == cut, "employee_id"])
    return O["employee_id"].isin(have) & ~(O["termination_date"].notna() & (O["termination_date"] <= cut))


@rule("RECON-ELIGIBLE", "Reconciliation", "attrition_outcome", "eligible_at_cutoff = employed with a snapshot on the cutoff date")
def _(c):
    O = c.T["attrition_outcome"]
    return _ids(O, _eligible(c) != O["eligible_at_cutoff"].fillna(False).astype(bool)), len(O)


@rule("RECON-LABEL", "Reconciliation", "attrition_outcome",
      "voluntary_attrition_label recomputes from final_status and termination_date with the single label function",
      maps_to="label_termination_mismatch")
def _(c):
    O = c.T["attrition_outcome"]
    again = labels.derive_label(O["final_status"], O["termination_date"], _eligible(c),
                                config.CUTOFFS["test"], config.HORIZON_ENDS["test"])
    stored = O["voluntary_attrition_label"].astype("Int64")
    same = (again == stored).fillna(False).astype(bool) | (again.isna() & stored.isna())
    return _ids(O, ~same), len(O)


@rule("RECON-INTERVENTION-DERIVED", "Reconciliation", "intervention",
      "hazard_multiplier, engagement_delta, outcome_category and left_within_2_quarters recompute from source records")
def _(c):
    I = c.T["intervention"]
    V = c.T["engagement_survey"]
    V = V[(V["response_status"] != "Skipped") & V["engagement_score"].notna()].sort_values(["employee_id", "survey_date"])
    groups = {k: (g["survey_date"].to_numpy("datetime64[D]"), g["engagement_score"].to_numpy()) for k, g in V.groupby("employee_id")}
    allowed = {0.75, 0.80, 0.90, 1.0}
    bad = np.zeros(len(I), dtype=bool)
    for i, r in enumerate(I.itertuples(index=False)):
        cd = r.conducted_date
        if pd.isna(cd):
            bad[i] = (r.hazard_multiplier != 1.0) or pd.notna(r.engagement_delta) or r.outcome_category != "Not_Applicable" or pd.notna(r.left_within_2_quarters)
            continue
        bad[i] |= round(float(r.hazard_multiplier), 4) not in allowed
        d, sc = groups.get(r.employee_id, (np.array([], dtype="datetime64[D]"), np.array([])))
        pos = int(np.searchsorted(d, np.datetime64(cd.date(), "D"), side="right"))
        delta = sc[pos:pos + 2].mean() - sc[pos - 1] if 0 < pos < len(d) else np.nan
        if np.isnan(delta):
            bad[i] |= pd.notna(r.engagement_delta) or r.outcome_category != "Not_Applicable"
        else:
            cat = "Improved" if delta >= 5 else "Declined" if delta <= -5 else "No_Change"
            bad[i] |= pd.isna(r.engagement_delta) or abs(delta - r.engagement_delta) > 0.006 or r.outcome_category != cat
        term = c.out["termination_date"].get(r.employee_id, pd.NaT)
        vol = c.out["final_status"].get(r.employee_id) == "Exited_Voluntary"
        left = bool(vol and pd.notna(term) and cd < term <= cd + pd.Timedelta(days=182))
        bad[i] |= pd.isna(r.left_within_2_quarters) or bool(r.left_within_2_quarters) != left
    return I.loc[bad, "intervention_id"].tolist(), len(I)


RULE_IDS = [r.rule_id for r in RULES]
assert len(RULE_IDS) == len(set(RULE_IDS)), "duplicate rule ids"