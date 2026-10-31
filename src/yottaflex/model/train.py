"""Interpretable baseline (logistic regression) plus a gradient-boosting comparison."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import average_precision_score

from .. import config

C_GRID = (0.01, 0.1, 1.0)


def make_lr(C: float):
    return make_pipeline(StandardScaler(), LogisticRegression(C=C, max_iter=5000))


def make_gb():
    return HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200, random_state=config.SEED)


def select_C(train: pd.DataFrame, val: pd.DataFrame, cols: list[str]) -> tuple[float, dict]:
    """Pick the regularisation on the validation cutoff (labels observed before the test cutoff)."""
    scores = {}
    for C in C_GRID:
        m = make_lr(C).fit(train[cols], train["y"])
        scores[C] = float(average_precision_score(val["y"], m.predict_proba(val[cols])[:, 1]))
    return max(scores, key=scores.get), scores


def fit_final(train: pd.DataFrame, val: pd.DataFrame, cols: list[str], C: float):
    both = pd.concat([train, val])               # validation labels are fully observed by the test cutoff
    return make_lr(C).fit(both[cols], both["y"])


def coefficient_table(model, cols: list[str]) -> pd.DataFrame:
    lr = model.named_steps["logisticregression"]
    t = pd.DataFrame({"feature": cols, "coefficient": lr.coef_[0]})
    t["odds_ratio_per_sd"] = np.exp(t["coefficient"])
    return t.reindex(t["coefficient"].abs().sort_values(ascending=False).index).reset_index(drop=True)
