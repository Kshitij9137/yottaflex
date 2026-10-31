"""Run all rules, then score the four anomaly detectors against the ground truth."""
from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from .rules import RULES, Ctx
from .schema import GROUND_TRUTH, coerce

PREFIX_ENTITY = {"EMP": "employee", "SNAP": "tenure_snapshot", "SURV": "engagement_survey", "WKL": "workload_snapshot",
                 "INT": "intervention", "OUT": "attrition_outcome", "ROLE": "role", "TEAM": "team",
                 "BAND": "compensation_band", "PRM": "promotion_history", "ASG": "employee_team_assignment"}
INJECTED_TYPES = ("future_information_leak", "missing_survey_as_negative",
                  "label_termination_mismatch", "unreviewed_individual_score")


def entity_of(record_id, default):
    return PREFIX_ENTITY.get(str(record_id).split("-", 1)[0], default)


@dataclass
class RuleResult:
    rule_id: str
    category: str
    entity: str
    description: str
    n_checked: int
    n_violations: int
    sample: list
    maps_to: str | None


def run_rules(raw: dict[str, pd.DataFrame]):
    """-> (ctx, [RuleResult], {rule_id: {(entity, record_id)}})."""
    ctx = Ctx(raw)
    results, flagged = [], {}
    for r in RULES:
        ids_, n = r.fn(ctx)
        recs = {(entity_of(i, r.entity), i) for i in ids_}
        flagged[r.rule_id] = recs
        results.append(RuleResult(r.rule_id, r.category, r.entity, r.description, int(n), len(recs),
                                  sorted(i for _, i in recs)[:3], r.maps_to))
    return ctx, results, flagged


def load_ground_truth(raw_gt: pd.DataFrame) -> pd.DataFrame:
    typed, bad, problems = coerce(raw_gt, GROUND_TRUTH)
    if bad or problems:
        raise ValueError(f"ground truth is malformed: bad rows={bad[:5]} problems={problems}")
    return typed


def _prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


# Rules a naive analyst would write. They are NOT detectors; they show why decoys exist.
def naive_hits(ctx: Ctx) -> dict[str, tuple[str, set]]:
    W, A, V = ctx.T["workload_snapshot"], ctx.T["employee_team_assignment"], ctx.T["engagement_survey"]
    return {
        "NAIVE: high workload = attrition risk": ("benign_high_workload", {("workload_snapshot", i) for i in W.loc[W["high_load_flag"].fillna(False).astype(bool), "workload_id"]}),
        "NAIVE: assignment ended = employee left": ("benign_internal_transfer", {("employee_team_assignment", i) for i in A.loc[A["effective_to"].notna(), "assignment_id"]}),
        "NAIVE: missing survey = disengaged": ("benign_missing_survey", {("engagement_survey", i) for i in V.loc[V["response_status"] == "Skipped", "survey_id"]}),
    }


def evaluate(ctx: Ctx, results: list[RuleResult], flagged: dict, gt: pd.DataFrame | None) -> dict:
    out: dict = {"n_rules": len(results), "rules_with_violations": [r.rule_id for r in results if r.n_violations]}
    all_flagged = set().union(*flagged.values()) if flagged else set()
    out["total_flagged_records"] = len(all_flagged)
    if gt is None:
        out["has_ground_truth"] = False
        return out
    out["has_ground_truth"] = True
    gt = gt.copy()
    gt["key"] = list(zip(gt["entity"], gt["record_id"]))
    injected = gt[gt["is_injected"].astype(bool)]
    decoys = gt[~gt["is_injected"].astype(bool)]
    inj_keys, dec_keys = set(injected["key"]), set(decoys["key"])

    pk_sets = {e: set(ctx.T[e][ctx.T[e].columns[0]]) for e in gt["entity"].unique()}
    out["gt_records_missing_from_tables"] = int(sum(rid not in pk_sets[e] for e, rid in zip(gt["entity"], gt["record_id"])))

    det_rules = {}
    for r in RULES:
        if r.maps_to:
            det_rules.setdefault(r.maps_to, []).append(r.rule_id)
    rows, subrows = [], []
    for issue in INJECTED_TYPES:
        flag = set().union(*[flagged[rid] for rid in det_rules.get(issue, [])]) if det_rules.get(issue) else set()
        truth = set(injected.loc[injected["issue_type"] == issue, "key"])
        tp, fp, fn = len(flag & truth), len(flag - truth), len(truth - flag)
        p, r_, f1 = _prf(tp, fp, fn)
        rows.append({"issue_type": issue, "rules": det_rules.get(issue, []), "truth": len(truth), "flagged": len(flag),
                     "tp": tp, "fp": fp, "fn": fn, "precision": round(p, 4), "recall": round(r_, 4), "f1": round(f1, 4),
                     "fp_on_decoys": len((flag - truth) & dec_keys), "fp_on_other_anomalies": len((flag - truth) & inj_keys)})
        for sub, g in injected[injected["issue_type"] == issue].groupby("issue_subtype"):
            ks = set(g["key"])
            subrows.append({"issue_type": issue, "issue_subtype": sub, "truth": len(ks), "found": len(ks & flag),
                            "recall": round(len(ks & flag) / len(ks), 4)})
    out["detectors"], out["subtypes"] = rows, subrows

    det_all = set().union(*[flagged[rid] for ids_ in det_rules.values() for rid in ids_])
    out["decoys_total"] = len(dec_keys)
    out["decoys_flagged_by_detectors"] = len(dec_keys & det_all)
    out["decoys_flagged_by_any_rule"] = len(dec_keys & all_flagged)

    unexpl = {}
    for rid, recs in flagged.items():
        bad = recs - inj_keys
        if bad:
            unexpl[rid] = len(bad)
    out["unexplained_violations_by_rule"] = unexpl
    out["unexplained_violations"] = int(sum(unexpl.values()))
    out["violating_records_total"] = len(all_flagged)
    out["violating_records_explained"] = len(all_flagged & inj_keys)
    out["injected_records_not_flagged_by_any_rule"] = len(inj_keys - all_flagged)

    naive = []
    for name, (decoy_type, hits) in naive_hits(ctx).items():
        dk = set(decoys.loc[decoys["issue_type"] == decoy_type, "key"])
        naive.append({"rule": name, "decoy_type": decoy_type, "flags_in_dataset": len(hits),
                      "decoys": len(dk), "decoys_wrongly_flagged": len(hits & dk),
                      "share_of_decoys_wrongly_flagged": round(len(hits & dk) / len(dk), 4) if dk else 0.0,
                      "our_detectors_flag_these_decoys": len(dk & det_all)})
    out["naive_rules"] = naive
    return out


def passed(baseline_failures: list | None, ev: dict) -> bool:
    if baseline_failures:
        return False
    if not ev.get("has_ground_truth"):
        return not ev["rules_with_violations"]
    return (ev["unexplained_violations"] == 0 and ev["decoys_flagged_by_any_rule"] == 0
            and ev["gt_records_missing_from_tables"] == 0 and ev["injected_records_not_flagged_by_any_rule"] == 0
            and all(d["precision"] == 1.0 and d["recall"] == 1.0 for d in ev["detectors"]))


def results_as_dicts(results):
    return [asdict(r) for r in results]