"""Temporal datasets: one row per (cutoff, employee). Labels come from termination facts via the single label function."""
from __future__ import annotations

import pandas as pd

from .. import config
from ..labels import labels_for_cutoff
from .features import features_at

SPLITS = ("train", "validation", "test")


def build_split(P, T, split: str, **kw) -> pd.DataFrame:
    C, H = config.CUTOFFS[split], config.HORIZON_ENDS[split]
    F = features_at(P, T["intervention"], C, **kw)
    y = labels_for_cutoff(T["attrition_outcome"], T["tenure_snapshot"], C, H).reindex(F.index)
    F.insert(0, "y", y)
    F.insert(0, "cutoff", pd.Timestamp(C))
    F = F[F["y"].notna()].copy()                 # not scorable: left before the cutoff, or involuntary exit in the horizon
    F["y"] = F["y"].astype(int)
    return F


def build_all(P, T, **kw) -> dict[str, pd.DataFrame]:
    return {s: build_split(P, T, s, **kw) for s in SPLITS}
