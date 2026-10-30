"""Step 1 of the workflow: master data (Role, CompensationBand, Employee, Team).

Everything here is generated before any transaction/event table so that every
foreign key created later is valid by construction.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from .. import config, ids
from ..dates import D1, aprils_between, fiscal_year_start
from . import params as P

N_FAM = len(config.JOB_FAMILIES)
N_ROLES = N_FAM * len(config.LEVELS)
HR_FAMILY = config.JOB_FAMILIES.index("People_HR")
MIN_EMPLOYEES = 500  # below this, some family may have no eligible manager


def role_index(fam, level):
    """Role index 0..34 from family index and level 1..5."""
    return np.asarray(fam) * 5 + np.asarray(level) - 1


def round100(x):
    return np.round(np.asarray(x, dtype=float) / 100.0) * 100.0


# --------------------------------------------------------------------------
# Role and CompensationBand
# --------------------------------------------------------------------------
def build_roles() -> pd.DataFrame:
    rows = []
    for f, fam in enumerate(config.JOB_FAMILIES):
        for lvl in config.LEVELS:
            rows.append({
                "role_id": ids.role_id(int(role_index(f, lvl)) + 1),
                "role_title": f"{fam} L{lvl}",
                "job_family": fam,
                "level": lvl,
                "is_people_manager_track": lvl >= 4,
            })
    return pd.DataFrame(rows)


def build_bands(roles: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    """Three effective-dated versions per role (FY2024, FY2025, FY2026)."""
    rows = []
    mid = np.zeros((N_ROLES, len(P.FY_STARTS)), dtype=np.int64)
    for f in range(N_FAM):
        for lvl in config.LEVELS:
            r = int(role_index(f, lvl))
            role_id = roles.loc[r, "role_id"]
            for k, fy in enumerate(P.FY_STARTS):
                m = P.BASE_MID_BY_LEVEL[lvl] * P.FAMILY_PAY_FACTOR[f] * P.BAND_FY_GROWTH ** k
                lo = int(round(m * 0.8 / 1000) * 1000)
                hi = int(round(m * 1.2 / 1000) * 1000)
                md = (lo + hi) // 2
                mid[r, k] = md
                rows.append({
                    "band_id": ids.band_id(role_id, fy),
                    "role_id": role_id,
                    "effective_from": date(fy, 4, 1),
                    "effective_to": date(fy + 1, 3, 31) if k < len(P.FY_STARTS) - 1 else None,
                    "currency": "INR",
                    "annual_min": lo,
                    "annual_mid": md,
                    "annual_max": hi,
                })
    df = pd.DataFrame(rows)
    df["effective_from"] = pd.to_datetime(df["effective_from"])
    df["effective_to"] = pd.to_datetime(df["effective_to"])
    return df, mid


# --------------------------------------------------------------------------
# Workforce (Employee + initial state for the simulation)
# --------------------------------------------------------------------------
@dataclass
class Workforce:
    n: int
    hire: np.ndarray            # datetime64[D]
    is_pre: np.ndarray          # hired before the window
    family: np.ndarray          # family index (constant until a lateral move)
    init_level: np.ndarray      # level at hire
    level: np.ndarray           # level at start of simulation (after pre-window promotions)
    salary: np.ndarray          # annual INR at the start of the simulation
    last_promo: np.ndarray      # date of last promotion (hire date if none)
    team: np.ndarray            # initial team index
    is_manager: np.ndarray
    merit: np.ndarray
    trait_eng: np.ndarray
    trait_load: np.ndarray
    frailty: np.ndarray
    employment_type: np.ndarray
    rec_minutes: np.ndarray
    pre_events: dict
    fam_offset: np.ndarray
    fam_nteams: np.ndarray
    team_family: np.ndarray
    team_peak_q: np.ndarray
    team_manager: np.ndarray
    team_created: np.ndarray
    pay_factor: np.ndarray = field(default_factory=lambda: np.array(P.FAMILY_PAY_FACTOR))


def build_workforce(n: int, band_mid: np.ndarray, rng: np.random.Generator,
                    p: P.SimParams) -> Workforce:
    if n < MIN_EMPLOYEES:
        raise ValueError(f"n_employees must be >= {MIN_EMPLOYEES} (got {n})")
    ws = np.datetime64(config.WINDOW_START, "D")

    # --- hire dates (sorted so EMP ids are chronological) -------------------
    is_pre = rng.random(n) < p.pre_window_share
    tenure_days = np.clip(np.floor(rng.gamma(1.6, 800.0, n)), 1, 3196).astype(np.int64)
    new_off = np.floor(rng.random(n) * 637).astype(np.int64)  # hires up to 2026-06-30
    hire = np.where(is_pre,
                    ws - tenure_days.astype("timedelta64[D]"),
                    ws + new_off.astype("timedelta64[D]"))
    order = np.argsort(hire, kind="stable")
    hire, is_pre = hire[order], is_pre[order]
    ten0 = (ws - hire).astype(np.int64)  # days from hire to window start (<=0 for new hires)

    # --- role family and entry level ---------------------------------------
    family = rng.choice(N_FAM, size=n, p=P.FAMILY_WEIGHTS)
    lvl_pre = rng.choice(5, size=n, p=P.P_LEVEL_PRE) + 1
    lvl_new = rng.choice(5, size=n, p=P.P_LEVEL_NEW) + 1
    init_level = np.where(is_pre, lvl_pre, lvl_new)

    # --- pre-window promotion history --------------------------------------
    level = init_level.copy()
    last_promo = hire.copy()
    ev_dates: dict[int, list] = {}
    for i in np.flatnonzero(is_pre):
        k = min(int(rng.poisson(ten0[i] / 365.25 / 4.0)), 5 - int(init_level[i]))
        span = int(ten0[i]) - 300      # room between hire+270d and window start-30d
        k = 0 if span < 0 else min(k, span // 270 + 1)
        if k > 0:
            slack = span - (k - 1) * 270
            offs = np.sort(rng.random(k)) * slack
            dts = [hire[i] + np.timedelta64(270 + int(offs[j]) + 270 * j, "D") for j in range(k)]
            ev_dates[int(i)] = dts
            level[i] = init_level[i] + k
            last_promo[i] = dts[-1]

    # --- salary at the start of the simulation -----------------------------
    compa_pre = np.clip(rng.normal(1.00, 0.09, n), 0.80, 1.25)
    compa_new = np.clip(rng.normal(0.97, 0.08, n), 0.82, 1.20)
    fy_hire = np.clip(fiscal_year_start(hire) - 2024, 0, 2)
    r_start = role_index(family, level)
    r_init = role_index(family, init_level)
    salary = np.where(is_pre,
                      round100(compa_pre * band_mid[r_start, 0]),
                      round100(compa_new * band_mid[r_init, fy_hire])).astype(np.int64)

    # Walk each pre-window career backwards from the salary at window start so the
    # PromotionHistory rows reconcile: new = prior * (1 + pct), with 5% merit per April.
    ev_emp, ev_date, ev_from, ev_to, ev_prior, ev_new = [], [], [], [], [], []
    for i, dts in ev_dates.items():
        s_end, d_end = float(salary[i]), ws
        for j in range(len(dts) - 1, -1, -1):
            new_j = float(round100(s_end / 1.05 ** aprils_between(dts[j], d_end)))
            pct = 0.08 + 0.10 * rng.random()
            prior_j = float(round100(new_j / (1 + pct)))
            ev_emp.append(i); ev_date.append(dts[j])
            ev_from.append(int(role_index(family[i], init_level[i] + j)))
            ev_to.append(int(role_index(family[i], init_level[i] + j + 1)))
            ev_prior.append(int(prior_j)); ev_new.append(int(new_j))
            s_end, d_end = prior_j, dts[j]
    pre_events = {
        "emp": np.array(ev_emp, dtype=np.int64),
        "date": np.array(ev_date, dtype="datetime64[D]"),
        "from_role": np.array(ev_from, dtype=np.int64),
        "to_role": np.array(ev_to, dtype=np.int64),
        "prior": np.array(ev_prior, dtype=np.int64),
        "new": np.array(ev_new, dtype=np.int64),
    }

    # --- unobservable and behavioural traits -------------------------------
    merit = np.clip(rng.normal(0.05, 0.015, n), 0.0, 0.10)
    trait_eng = rng.standard_normal(n)
    trait_load = rng.standard_normal(n)
    frailty = rng.normal(0.0, p.risk.frailty_sd, n)
    emp_type = np.where(rng.random(n) < p.fixed_term_share, "Fixed_Term", "Full_Time")
    rec_minutes = rng.integers(0, 600, n)

    # --- teams: managers first, then members --------------------------------
    team = np.full(n, -1, dtype=np.int64)
    is_manager = np.zeros(n, dtype=bool)
    fam_offset = np.zeros(N_FAM, dtype=np.int64)
    fam_nteams = np.zeros(N_FAM, dtype=np.int64)
    team_family, team_manager = [], []
    off = 0
    for f in range(N_FAM):
        members = np.flatnonzero(family == f)
        t_f = max(1, int(round(len(members) / p.team_size)))
        cands = members[is_pre[members] & (level[members] >= 4)]
        if len(cands) == 0:
            raise ValueError(f"no manager candidates in family {config.JOB_FAMILIES[f]}; raise n_employees")
        t_f = min(t_f, len(cands))
        mgrs = rng.permutation(cands)[:t_f]
        is_manager[mgrs] = True
        team[mgrs] = off + np.arange(t_f)
        others = members[~is_manager[members]]
        team[others] = off + rng.integers(0, t_f, len(others))
        fam_offset[f], fam_nteams[f] = off, t_f
        team_family += [f] * t_f
        team_manager += [int(m) for m in mgrs]
        off += t_f
    n_teams = off
    team_peak_q = rng.integers(1, 5, n_teams)
    team_created = np.datetime64("2016-01-01", "D") + rng.integers(0, 3100, n_teams).astype("timedelta64[D]")

    return Workforce(
        n=n, hire=hire, is_pre=is_pre, family=family, init_level=init_level, level=level,
        salary=salary, last_promo=last_promo, team=team, is_manager=is_manager, merit=merit,
        trait_eng=trait_eng, trait_load=trait_load, frailty=frailty, employment_type=emp_type,
        rec_minutes=rec_minutes, pre_events=pre_events, fam_offset=fam_offset,
        fam_nteams=fam_nteams, team_family=np.array(team_family), team_peak_q=team_peak_q,
        team_manager=np.array(team_manager), team_created=team_created,
    )


def build_teams(wf: Workforce, emp_ids: np.ndarray) -> pd.DataFrame:
    rows = []
    for t in range(len(wf.team_family)):
        f = int(wf.team_family[t])
        pos = t - int(wf.fam_offset[f])
        rows.append({
            "team_id": ids.team_id(t + 1),
            "team_name": f"{config.JOB_FAMILIES[f]} Team {pos + 1}",
            "job_family": config.JOB_FAMILIES[f],
            "manager_employee_id": emp_ids[wf.team_manager[t]],
            "planned_peak_quarter": int(wf.team_peak_q[t]),
            "created_date": pd.Timestamp(wf.team_created[t]),
        })
    return pd.DataFrame(rows)