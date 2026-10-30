"""The single place where the attrition label is defined.

Labels for every cutoff (train, validation, test) come from termination facts via
this one function, so a stored label can always be re-derived and checked.
"""
from __future__ import annotations

import pandas as pd


def derive_label(final_status: pd.Series, termination_date: pd.Series, eligible: pd.Series,
                 cutoff, horizon_end) -> pd.Series:
    """1 = voluntary exit in (cutoff, horizon_end]; 0 = stayed; <NA> = not scorable.

    Not scorable: no snapshot at the cutoff (already gone or not yet hired), or an
    involuntary exit inside the horizon (competing event, excluded from evaluation).
    """
    cutoff, horizon_end = pd.Timestamp(cutoff), pd.Timestamp(horizon_end)
    in_h = (termination_date > cutoff) & (termination_date <= horizon_end)
    vol = (final_status == "Exited_Voluntary") & in_h
    invol = (final_status == "Exited_Involuntary") & in_h
    out = pd.Series(0, index=final_status.index, dtype="Int64")
    out[vol.to_numpy()] = 1
    out[(~eligible | invol).to_numpy()] = pd.NA
    return out


def labels_for_cutoff(outcomes: pd.DataFrame, snapshots: pd.DataFrame, cutoff, horizon_end) -> pd.Series:
    """Label per employee_id for any cutoff; eligibility = has a snapshot on the cutoff date."""
    have = set(snapshots.loc[snapshots["snapshot_date"] == pd.Timestamp(cutoff), "employee_id"])
    o = outcomes.set_index("employee_id")
    eligible = o.index.to_series().isin(have)
    return derive_label(o["final_status"], o["termination_date"], eligible, cutoff, horizon_end)