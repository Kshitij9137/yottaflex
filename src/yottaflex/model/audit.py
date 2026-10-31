"""Leak, label, split and sensitive-attribute audits. These run on the feature table, never on the ground truth."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from .. import config, labels
from .features import cutoff_end

SENSITIVE_TOKENS = {"age", "dob", "birth", "gender", "sex", "ethnicity", "race", "religion", "caste", "nationality",
                    "disability", "health", "marital", "family", "pregnancy", "maternity", "home", "pin", "zip",
                    "location", "address", "name", "photo"}
SUSPICIOUS_AUC = 0.90


def provenance_audit(F: pd.DataFrame, cutoff) -> dict:
    """Does any row used by a feature post-date the cutoff, or was it recorded after the cutoff?"""
    late_rec = int((F["src_max_recorded_at"] > cutoff_end(cutoff)).sum())
    late_date = int((F["src_max_date"] > pd.Timestamp(cutoff)).sum())
    return {"rows": int(len(F)), "recorded_after_cutoff": late_rec, "dated_after_cutoff": late_date,
            "violations": int(((F["src_max_recorded_at"] > cutoff_end(cutoff)) | (F["src_max_date"] > pd.Timestamp(cutoff))).sum())}


def forbidden_audit(cols: list[str]) -> dict:
    forbidden = sorted(set(cols) & config.FORBIDDEN_FEATURE_COLUMNS)
    sensitive = sorted(c for c in cols if set(c.lower().split("_")) & SENSITIVE_TOKENS)
    return {"forbidden_columns": forbidden, "sensitive_name_matches": sensitive, "ok": not forbidden and not sensitive}


def univariate_audit(X: pd.DataFrame, y: pd.Series, cols: list[str], threshold: float = SUSPICIOUS_AUC) -> dict:
    """A single feature that separates the outcome almost perfectly is a leak until proven otherwise."""
    auc = {c: float(roc_auc_score(y, X[c])) for c in cols if X[c].nunique() > 1}
    strength = {c: max(a, 1 - a) for c, a in auc.items()}
    flagged = {c: round(v, 4) for c, v in strength.items() if v >= threshold}
    top = sorted(strength.items(), key=lambda kv: -kv[1])[:3]
    return {"threshold": threshold, "flagged": flagged, "strongest": [(c, round(v, 4)) for c, v in top], "ok": not flagged}


def label_audit(T: dict, split: str = "test") -> dict:
    """Stored label vs the label recomputed from termination facts (the model only ever uses the recomputed one)."""
    C, H = config.CUTOFFS[split], config.HORIZON_ENDS[split]
    again = labels.labels_for_cutoff(T["attrition_outcome"], T["tenure_snapshot"], C, H)
    stored = T["attrition_outcome"].set_index("employee_id")["voluntary_attrition_label"].astype("Int64")
    same = (again == stored).fillna(False).astype(bool) | (again.isna() & stored.isna())
    return {"employees": int(len(same)), "stored_vs_recomputed_mismatches": int((~same).sum())}


def split_audit() -> dict:
    order = ["train", "validation", "test"]
    ok = all(config.HORIZON_ENDS[a] <= config.CUTOFFS[b] and config.CUTOFFS[a] < config.CUTOFFS[b]
             for a, b in zip(order, order[1:]))
    return {"ok": ok and config.HORIZON_ENDS["test"] <= config.WINDOW_END,
            "rule": "each horizon ends on or before the next cutoff, so training labels are observed before the test cutoff"}


def run_audit(F: pd.DataFrame, cols: list[str], cutoff) -> dict:
    prov, forb = provenance_audit(F, cutoff), forbidden_audit(cols)
    uni = univariate_audit(F, F["y"], cols)
    return {"provenance": prov, "forbidden": forb, "univariate": uni,
            "passed": prov["violations"] == 0 and forb["ok"] and uni["ok"]}
