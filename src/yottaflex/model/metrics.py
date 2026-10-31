"""Evaluation metrics for rare-event ranking: PR-AUC, precision/recall/lift at top-k, calibration, bootstrap CIs."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

TOP_FRACTIONS = (0.01, 0.05, 0.10)


def top_k_stats(y: np.ndarray, score: np.ndarray, frac: float) -> dict:
    k = max(1, int(round(frac * len(y))))
    order = np.argsort(-score, kind="stable")[:k]
    hits = int(y[order].sum())
    base = y.mean()
    return {"k": k, "precision": hits / k, "recall": hits / max(1, int(y.sum())),
            "lift": (hits / k) / base if base > 0 else float("nan"), "hits": hits}


def calibration_table(y: np.ndarray, p: np.ndarray, bins: int = 10) -> pd.DataFrame:
    q = pd.qcut(pd.Series(p).rank(method="first"), bins, labels=False)
    df = pd.DataFrame({"bin": q, "p": p, "y": y}).groupby("bin").agg(n=("y", "size"), mean_predicted=("p", "mean"),
                                                                    observed_rate=("y", "mean")).reset_index()
    return df


def expected_calibration_error(y, p, bins: int = 10) -> float:
    t = calibration_table(y, p, bins)
    return float((t["n"] * (t["mean_predicted"] - t["observed_rate"]).abs()).sum() / t["n"].sum())


def evaluate_scores(y, score, prob=None) -> dict:
    y, score = np.asarray(y, dtype=int), np.asarray(score, dtype=float)
    out = {"n": int(len(y)), "positives": int(y.sum()), "base_rate": float(y.mean()),
           "roc_auc": float(roc_auc_score(y, score)), "pr_auc": float(average_precision_score(y, score))}
    for f in TOP_FRACTIONS:
        s = top_k_stats(y, score, f)
        out[f"precision_at_{int(f * 100)}pct"], out[f"recall_at_{int(f * 100)}pct"], out[f"lift_at_{int(f * 100)}pct"] = s["precision"], s["recall"], s["lift"]
    if prob is not None:
        prob = np.asarray(prob, dtype=float)
        out["brier"], out["ece"] = float(brier_score_loss(y, prob)), expected_calibration_error(y, prob)
        out["mean_predicted"] = float(prob.mean())
    return out


def bootstrap_ci(y, score, seed: int, n_boot: int = 400) -> dict:
    """95% percentile intervals for ROC-AUC, PR-AUC and recall@5%, resampling employees."""
    y, score = np.asarray(y, dtype=int), np.asarray(score, dtype=float)
    rng = np.random.default_rng(seed)
    vals = {"roc_auc": [], "pr_auc": [], "recall_at_5pct": []}
    for _ in range(n_boot):
        i = rng.integers(0, len(y), len(y))
        if y[i].sum() == 0:
            continue
        vals["roc_auc"].append(roc_auc_score(y[i], score[i]))
        vals["pr_auc"].append(average_precision_score(y[i], score[i]))
        vals["recall_at_5pct"].append(top_k_stats(y[i], score[i], 0.05)["recall"])
    return {k: [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))] for k, v in vals.items()}
