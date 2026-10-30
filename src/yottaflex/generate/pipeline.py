"""End-to-end generation: masters -> calibrate -> simulate -> tables."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .. import config
from . import masters as M
from .anomalies import AnomalyRates, inject
from .calibrate import calibrate_b0
from .params import SimParams
from .rng import streams
from .simulate import simulate
from .tables import build_tables


@dataclass
class Dataset:
    tables: dict[str, pd.DataFrame]      # what a candidate model/validator sees
    meta: dict
    ground_truth: pd.DataFrame | None = None   # separate file; never a feature source
    baseline: dict | None = None          # clean tables before injection (for tests/evaluation)


def _auc(score: np.ndarray, y: np.ndarray) -> float:
    r = pd.Series(score).rank().to_numpy()
    n1, n0 = y.sum(), (~y).sum()
    return float((r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def _sort_by_pk(tables):
    return {name: df.sort_values(df.columns[0], kind="stable").reset_index(drop=True) for name, df in tables.items()}


def generate_dataset(n_employees: int = 10_000, seed: int = config.SEED,
                     params: SimParams | None = None, inject_anomalies: bool = True,
                     rates: AnomalyRates | None = None) -> Dataset:
    p = params or SimParams()
    rngs = streams(seed)
    roles = M.build_roles()
    bands, band_mid = M.build_bands(roles)
    wf = M.build_workforce(n_employees, band_mid, rngs["masters"], p)
    b0, _ = calibrate_b0(wf, band_mid, p, seed)
    sim = simulate(wf, band_mid, p, b0, streams(seed)["dynamics"], collect=True)
    total = sim.vol_rate + sim.invol_rate
    lo, hi = config.TOTAL_ATTRITION_BOUNDS
    if not lo <= total <= hi:
        raise RuntimeError(f"total attrition {total:.3f} outside documented bounds {lo}-{hi}")
    tables = build_tables(wf, roles, bands, sim, p, rngs["post"])
    tables = _sort_by_pk(tables)             # canonical order: by primary key
    baseline = {k: v.copy() for k, v in tables.items()}
    gt = None
    if inject_anomalies:
        tables, gt = inject(tables, n_employees, rngs["anomalies"], rates or AnomalyRates())
        tables = _sort_by_pk(tables)

    # sanity diagnostic: how well does the transparent rule rank next-quarter exits?
    s = np.concatenate([d[0][d[1]] for d in sim.diag]); y = np.concatenate([d[2][d[1]] for d in sim.diag])
    meta = {
        "seed": seed, "n_employees": n_employees, "b0": round(b0, 6),
        "voluntary_attrition_rate": round(sim.vol_rate, 5), "involuntary_attrition_rate": round(sim.invol_rate, 5),
        "rule_score_auc_next_quarter": round(_auc(s, y), 4),
        "row_counts": {k: int(len(v)) for k, v in tables.items()},
    }
    if gt is not None:
        meta["ground_truth_counts"] = {f"{r.issue_type}/{r.is_injected}": int(r.n) for r in
                                       gt.groupby(["issue_type", "is_injected"]).size().rename("n").reset_index().itertuples()}
    return Dataset(tables, meta, gt, baseline)