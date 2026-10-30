"""Solve the intercept b0 so cumulative voluntary attrition hits the documented target."""
from __future__ import annotations

from .. import config
from .rng import streams
from .simulate import simulate


def calibrate_b0(wf, band_mid, p, seed, target=config.TARGET_VOLUNTARY_ATTRITION,
                 tol=0.0008, max_iter=26):
    lo, hi = -12.0, 2.0
    best_b0, best_gap, best_rate = lo, 1.0, 0.0
    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        rate = simulate(wf, band_mid, p, mid, streams(seed)["dynamics"], collect=False).vol_rate
        gap = abs(rate - target)
        if gap < best_gap:
            best_b0, best_gap, best_rate = mid, gap, rate
        if gap < tol:
            break
        if rate > target:
            hi = mid
        else:
            lo = mid
    return best_b0, best_rate