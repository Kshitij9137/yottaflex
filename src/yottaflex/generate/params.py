"""All tunable generator parameters in one place (mirrors docs/design_decisions.md)."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# Order of families follows config.JOB_FAMILIES:
# Engineering, Product, Sales, Customer_Support, Operations, IT_Ops, People_HR
FAMILY_WEIGHTS = (0.35, 0.08, 0.15, 0.17, 0.12, 0.08, 0.05)
FAMILY_PAY_FACTOR = (1.15, 1.15, 1.00, 0.80, 0.90, 0.95, 1.00)
FAMILY_ONCALL_BASE = (4.0, 1.0, 1.0, 6.0, 5.0, 8.0, 1.0)
BASE_MID_BY_LEVEL = {1: 900_000, 2: 1_080_000, 3: 1_300_000, 4: 1_560_000, 5: 1_870_000}
BAND_FY_GROWTH = 1.04
STAGNATION_GRACE_MONTHS = 36   # no stagnation penalty before this many months without promotion
PEAK_BOOST_HOURS = (4.0, 10.0)  # planned-peak extra weekly hours (low, high)
FY_STARTS = (2024, 2025, 2026)
P_LEVEL_PRE = (0.44, 0.33, 0.16, 0.06, 0.01)
P_LEVEL_NEW = (0.45, 0.35, 0.15, 0.04, 0.01)

# Order matters: column order of the contribution matrix.
FACTOR_NAMES = (
    "low_engagement", "engagement_decline", "promotion_stagnation",
    "below_band_pay", "sustained_overload", "early_tenure",
)


@dataclass(frozen=True)
class RiskCoefficients:
    eng_gap: float = 0.90
    eng_drop: float = 0.40
    stagnation: float = 0.60
    pay_gap: float = 0.70
    overload: float = 0.80
    early_tenure: float = 0.50
    frailty_sd: float = 0.60  # unobservable per-employee noise

    def as_array(self) -> np.ndarray:
        return np.array([self.eng_gap, self.eng_drop, self.stagnation,
                         self.pay_gap, self.overload, self.early_tenure])


@dataclass(frozen=True)
class SimParams:
    team_size: int = 25
    pre_window_share: float = 0.85
    fixed_term_share: float = 0.10
    invol_hazard: float = 0.003      # per quarter, independent of risk factors
    max_hazard: float = 0.50         # cap on quarterly voluntary hazard
    transfer_prob: float = 0.008     # per quarter
    lateral_prob: float = 0.004      # per quarter (always comes with a transfer)
    reorg_share: float = 0.10
    ep_start_prob: float = 0.07      # start of a non-peak overload episode
    nonresp_base: float = 0.12
    nonresp_slope: float = 0.0045    # per workload-index point above 35
    partial_prob: float = 0.05
    signal_top_frac: float = 0.015
    signal_uptake: float = 0.60
    signal_decline: float = 0.10
    final_q_pending: float = 0.15
    mgr_drop_points: float = 20.0
    mgr_prob: float = 0.20
    hr_prob: float = 0.0005
    cooldown_quarters: int = 2
    # hazard multiplier by intervention type
    # (Stay_Conversation, Workload_Rebalance, Career_Path_Discussion, Compensation_Review)
    type_multiplier: tuple = (0.90, 0.80, 0.80, 0.75)
    risk: RiskCoefficients = field(default_factory=RiskCoefficients)