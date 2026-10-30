"""Vectorised date helpers shared by the generator and the validators.

Using one implementation for both means "derived value recomputes exactly" is a
real check, not two copies of the same bug.
"""
from __future__ import annotations

from datetime import date

import numpy as np

D1 = np.timedelta64(1, "D")


def d64(x) -> np.datetime64:
    return np.datetime64(x, "D")


def months_between(start, end) -> np.ndarray:
    """Whole calendar months from `start` to `end` (day-of-month aware)."""
    s = np.asarray(start, dtype="datetime64[D]")
    e = np.asarray(end, dtype="datetime64[D]")
    sm = s.astype("datetime64[M]")
    em = e.astype("datetime64[M]")
    months = em.astype(np.int64) - sm.astype(np.int64)
    s_day = (s - sm.astype("datetime64[D]")).astype(np.int64)
    e_day = (e - em.astype("datetime64[D]")).astype(np.int64)
    return months - (e_day < s_day).astype(np.int64)


def fiscal_year_start(d) -> np.ndarray:
    """Indian fiscal year (Apr-Mar): returns the calendar year in which the FY starts."""
    d = np.asarray(d, dtype="datetime64[D]")
    year = d.astype("datetime64[Y]").astype(np.int64) + 1970
    month = d.astype("datetime64[M]").astype(np.int64) % 12 + 1
    return year - (month < 4).astype(np.int64)


def quarter_end_of(d) -> np.ndarray:
    """Last day of the calendar quarter containing each date."""
    d = np.asarray(d, dtype="datetime64[D]")
    m = d.astype("datetime64[M]").astype(np.int64)
    end_m = (m // 3) * 3 + 3  # first month after the quarter
    return end_m.astype("datetime64[M]").astype("datetime64[D]") - D1


def aprils_between(d1, d2) -> int:
    """Number of 1 April dates in the interval (d1, d2]."""
    a = d1.astype(object) if isinstance(d1, np.datetime64) else d1
    b = d2.astype(object) if isinstance(d2, np.datetime64) else d2
    return sum(1 for y in range(a.year, b.year + 1) if a < date(y, 4, 1) <= b)