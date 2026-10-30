"""Steps 2-3 of the workflow: the quarter-by-quarter simulation.

Order inside each quarter t (see docs/design_decisions.md section 6):
  A. exits for quarter t, drawn from the hazard computed with data recorded by end of t-1
  B. events: merit (April), promotions, internal transfers, lateral moves
  C. snapshots: tenure, workload, engagement survey; then the rule-based risk terms
  D. interventions triggered from those snapshots (they affect quarters t+1 and t+2)

Common random numbers: every random array is drawn at full size in a fixed order,
so changing the calibration intercept b0 never shifts any other random draw.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np

from .. import config, ids
from ..dates import D1, fiscal_year_start, months_between
from .masters import N_FAM, Workforce, round100
from .params import FAMILY_ONCALL_BASE, PEAK_BOOST_HOURS, STAGNATION_GRACE_MONTHS, SimParams

T = len(config.QUARTERS)
NAT = np.datetime64("NaT", "D")
FACTOR_TO_TYPE = np.array([0, 0, 2, 3, 1, 0])    # index into config.INTERVENTION_TYPES
FACTOR_TO_REASON = np.array([0, 0, 1, 2, 3, 4])  # index into config.TERMINATION_REASONS
_DRAW_UNIFORM = (
    "u_v", "u_i", "u_xf", "u_promo", "u_pdate", "u_ppct", "u_tr", "u_tdate", "u_tteam",
    "u_treason", "u_lfam", "u_lteam", "u_lpct", "u_ep", "u_epd", "u_epb", "u_peak",
    "u_resp", "u_part", "u_na", "u_sd", "u_up", "u_mgr", "u_hr", "u_rev", "u_pend",
    "u_d1", "u_d2", "u_d3", "u_d4",
)


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def _draw(rng: np.random.Generator, n: int) -> dict:
    d = {name: rng.random(n) for name in _DRAW_UNIFORM}
    for name in ("n_shock", "n_hours", "n_proj", "n_dev"):
        d[name] = rng.standard_normal(n)
    d["g_on"] = rng.gamma(2.0, 0.5, n)
    d["n_items"] = rng.standard_normal((n, 5))
    d["r_items"] = rng.random((n, 5))
    return d


def _qbounds():
    out = []
    for lab in config.QUARTERS:
        y, q = int(lab[:4]), int(lab[-1])
        out.append((np.datetime64(date(y, 3 * q - 2, 1), "D"),
                    np.datetime64(ids.quarter_end(lab), "D"), q, y))
    return out


def _td(x) -> np.ndarray:
    return np.asarray(x).astype(np.int64).astype("timedelta64[D]")


@dataclass
class SimResult:
    b0: float
    n: int
    snaps: list = field(default_factory=list)
    promo: list = field(default_factory=list)      # per-quarter dicts
    assign: list = field(default_factory=list)
    iv: list = field(default_factory=list)
    diag: list = field(default_factory=list)
    exit_date: np.ndarray | None = None
    exit_type: np.ndarray | None = None            # 0 active, 1 voluntary, 2 involuntary
    exit_reason: np.ndarray | None = None
    vol_rate: float = 0.0
    invol_rate: float = 0.0


def simulate(wf: Workforce, band_mid: np.ndarray, p: SimParams, b0: float,
             rng: np.random.Generator, collect: bool = True) -> SimResult:
    n, c = wf.n, p.risk
    coef = c.as_array()
    qb = _qbounds()
    pay_factor = wf.pay_factor

    fam = wf.family.copy()
    level = wf.level.copy()
    salary = wf.salary.astype(float).copy()
    last_promo = wf.last_promo.copy()
    team = wf.team.copy()
    team_start = wf.hire.copy()
    dev = np.zeros(n); shock = np.zeros(n)
    ep_left = np.zeros(n, dtype=np.int64); ep_boost = np.zeros(n)
    last_eng = np.full(n, np.nan); prev_eng = np.full(n, np.nan)
    cnt = np.zeros(n, dtype=np.int64)
    exited = np.zeros(n, dtype=bool)
    exit_date = np.full(n, NAT, dtype="datetime64[D]")
    exit_type = np.zeros(n, dtype=np.int8)
    exit_reason = np.full(n, -1, dtype=np.int8)
    has_prev = np.zeros(n, dtype=bool)
    terms_sum = np.zeros(n); contrib = np.zeros((n, 6))
    mult_left = np.zeros(n, dtype=np.int64); mult_val = np.ones(n)
    rec_left = np.zeros(n, dtype=np.int64)
    last_int_t = np.full(n, -99, dtype=np.int64)
    int_lb = np.full(n, NAT, dtype="datetime64[D]")

    res = SimResult(b0=b0, n=n)
    # lateral-move eligibility by pay factor; People_HR is excluded so reviewers stay HR
    ratio = pay_factor[:, None] / pay_factor[None, :]
    fam_ok = (ratio >= 0.9) & (ratio <= 1.1) & ~np.eye(N_FAM, dtype=bool)
    fam_ok[N_FAM - 1, :] = False
    fam_ok[:, N_FAM - 1] = False

    for t, (qs, qe, qn, yr) in enumerate(qb):
        d = _draw(rng, n)
        span = int((qe - qs).astype(np.int64)) + 1

        # ---------------- A. exits during quarter t -------------------------
        if t >= 1:
            mult = np.where(mult_left > 0, mult_val, 1.0)
            h = np.minimum(sigmoid(b0 + terms_sum + wf.frailty) * mult, p.max_hazard)
            elig = has_prev & ~exited
            vex = elig & (d["u_v"] < h)
            iex = elig & ~vex & (d["u_i"] < p.invol_hazard)
            newx = vex | iex
            lb = np.where(np.isnat(int_lb), qs - D1, np.maximum(int_lb, qs - D1))
            days = (qe - lb).astype(np.int64)
            xdate = lb + (1 + np.floor(d["u_xf"] * days).astype(np.int64)).astype("timedelta64[D]")
            exit_date = np.where(newx, xdate, exit_date)
            exit_type = np.where(vex, 1, np.where(iex, 2, exit_type)).astype(np.int8)
            dom = np.argmax(contrib, axis=1)
            reason = np.where(contrib.max(axis=1) > 0, FACTOR_TO_REASON[dom], 4)
            exit_reason = np.where(vex, reason, exit_reason).astype(np.int8)
            exited |= newx
            if collect:
                res.diag.append((terms_sum.copy(), elig.copy(), vex.copy()))
            mult_left = np.maximum(mult_left - 1, 0)
            int_lb[:] = NAT

        # ---------------- B. events ------------------------------------------
        active_mid = (wf.hire <= qe) & ~exited
        cont = active_mid & (wf.hire < qs)
        if qn == 2:  # April merit step for everyone hired before 1 April
            apr1 = np.datetime64(date(yr, 4, 1), "D")
            m = cont & (wf.hire < apr1)
            salary = np.where(m, round100(salary * (1 + wf.merit)), salary)

        msp0 = months_between(last_promo, qs)
        ten0 = months_between(wf.hire, qs)
        p_pr = 0.015 + 0.04 * np.clip((msp0 - 12) / 24, 0, 1)
        pdate = qs + np.floor(d["u_pdate"] * span).astype(np.int64).astype("timedelta64[D]")
        promoted = (cont & (level < 5) & (ten0 >= 9) & (d["u_promo"] < p_pr)
                    & ((pdate - last_promo).astype(np.int64) >= 270))
        pidx = np.flatnonzero(promoted)
        q_promo = {"emp": [], "date": [], "type": [], "from_role": [], "to_role": [], "prior": [], "new": []}
        if pidx.size:
            prior = salary[pidx]
            new = round100(prior * (1 + 0.08 + 0.10 * d["u_ppct"][pidx]))
            q_promo = {"emp": pidx, "date": pdate[pidx], "type": np.full(pidx.size, "Promotion"),
                       "from_role": fam[pidx] * 5 + level[pidx] - 1,
                       "to_role": fam[pidx] * 5 + level[pidx],
                       "prior": prior.astype(np.int64), "new": new.astype(np.int64)}
            salary[pidx] = new
            level[pidx] += 1
            last_promo[pidx] = pdate[pidx]

        cand2 = cont & ~wf.is_manager & ~promoted
        tdate = qs + np.floor(d["u_tdate"] * span).astype(np.int64).astype("timedelta64[D]")
        feas = (tdate - team_start).astype(np.int64) >= 30
        nteams_f = wf.fam_nteams[fam]
        is_tr = cand2 & feas & (d["u_tr"] < p.transfer_prob) & (nteams_f >= 2)
        elig_mat = fam_ok[fam]
        cnt_l = elig_mat.sum(axis=1)
        is_lat = (cand2 & feas & (d["u_tr"] >= p.transfer_prob)
                  & (d["u_tr"] < p.transfer_prob + p.lateral_prob) & (cnt_l > 0))
        tr_flag = is_tr | is_lat
        # same-family transfer: pick any other team of the family
        cur_pos = team - wf.fam_offset[fam]
        r = np.floor(d["u_tteam"] * np.maximum(nteams_f - 1, 1)).astype(np.int64)
        new_team_tr = wf.fam_offset[fam] + np.where(r < cur_pos, r, r + 1)
        # lateral move: pick the k-th eligible target family, then any team in it
        k = np.minimum(np.floor(d["u_lfam"] * np.maximum(cnt_l, 1)).astype(np.int64),
                       np.maximum(cnt_l, 1) - 1)
        cs = np.cumsum(elig_mat, axis=1)
        tgt = np.argmax(elig_mat & (cs == (k + 1)[:, None]), axis=1)
        new_team_lat = wf.fam_offset[tgt] + np.floor(d["u_lteam"] * wf.fam_nteams[tgt]).astype(np.int64)

        tidx = np.flatnonzero(is_tr); lidx = np.flatnonzero(is_lat)
        reorg = d["u_treason"] < p.reorg_share
        q_assign = {
            "emp": np.concatenate([tidx, lidx]),
            "date": np.concatenate([tdate[tidx], tdate[lidx]]),
            "team": np.concatenate([new_team_tr[tidx], new_team_lat[lidx]]),
            "reason": np.concatenate([np.where(reorg[tidx], "Reorg", "Internal_Transfer"),
                                      np.full(lidx.size, "Internal_Transfer")]),
        }
        if lidx.size:
            prior = salary[lidx]
            new = round100(prior * (1 + 0.05 * d["u_lpct"][lidx]))
            lat = {"emp": lidx, "date": tdate[lidx], "type": np.full(lidx.size, "Lateral_Move"),
                   "from_role": fam[lidx] * 5 + level[lidx] - 1,
                   "to_role": tgt[lidx] * 5 + level[lidx] - 1,
                   "prior": prior.astype(np.int64), "new": new.astype(np.int64)}
            q_promo = {kk: np.concatenate([np.asarray(q_promo[kk]), lat[kk]]) for kk in lat}
            salary[lidx] = new
            fam[lidx] = tgt[lidx]
        team[tidx] = new_team_tr[tidx]; team[lidx] = new_team_lat[lidx]
        team_start[tidx] = tdate[tidx]; team_start[lidx] = tdate[lidx]
        if collect:
            res.promo.append(q_promo); res.assign.append(q_assign)

        # ---------------- C. snapshots ---------------------------------------
        act = (wf.hire <= qe) & ~exited
        fy_idx = int(np.asarray(fiscal_year_start(qe)).item()) - 2024
        role_idx = fam * 5 + level - 1
        compa = salary / band_mid[role_idx, fy_idx]
        msp = months_between(last_promo, qe)
        ten = months_between(wf.hire, qe)
        mit = months_between(team_start, qe)

        # workload: base + AR(1) shock + planned peak (benign) + non-peak overload episodes
        ep_start = (ep_left == 0) & (d["u_ep"] < p.ep_start_prob)
        ep_left = np.where(ep_start, 1 + np.floor(d["u_epd"] * 4).astype(np.int64), ep_left)
        ep_boost = np.where(ep_start, 9.0 + 5.0 * d["u_epb"], ep_boost)
        in_ep = ep_left > 0
        peak = wf.team_peak_q[team] == qn
        shock = 0.6 * shock + 1.8 * d["n_shock"]
        base = 41.0 + 2.0 * wf.trait_load + 0.5 * (level - 3)
        hours = (base + shock + peak * (PEAK_BOOST_HOURS[0] + (PEAK_BOOST_HOURS[1] - PEAK_BOOST_HOURS[0]) * d["u_peak"]) + in_ep * ep_boost + 1.2 * d["n_hours"])
        hours = np.clip(np.round(hours, 1), 30.0, 65.0)
        ep_left = np.maximum(ep_left - 1, 0)
        projects = np.clip(np.rint(3.5 + 0.12 * (hours - 41.0) + 1.2 * d["n_proj"]), 0, 12).astype(np.int64)
        oncall = np.clip(np.rint(np.array(FAMILY_ONCALL_BASE)[fam] * d["g_on"]
                                 + 0.4 * np.maximum(0.0, hours - 45.0)), 0, 30).astype(np.int64)
        widx = np.round(np.clip(100.0 * (0.55 * (hours - 35.0) / 20.0 + 0.30 * projects / 8.0
                                         + 0.15 * oncall / 20.0), 0.0, 100.0), 1)
        high = widx >= 65.0
        overload_now = high & ~peak
        cnt = np.where(overload_now, cnt + 1, np.where(high & peak, cnt, 0))

        # engagement: latent state driven by non-peak overload, stagnation, pay gap, transfers
        stagn = np.clip((msp - STAGNATION_GRACE_MONTHS) / 12.0, 0, 2) * (level < 5)
        pay = np.clip((0.95 - compa) / 0.10, 0, 2)
        drive = 5.0 * overload_now + 2.0 * stagn + 2.5 * pay + 3.0 * tr_flag - 4.0 * (rec_left > 0)
        dev = 0.5 * dev - 1.0 * drive + 3.5 * d["n_dev"]
        rec_left = np.maximum(rec_left - 1, 0)
        latent = np.clip(70.0 + 9.0 * wf.trait_eng + dev, 5.0, 98.0)
        items = np.clip(np.rint(1.0 + 4.0 * (latent[:, None] + 10.0 * d["n_items"]) / 100.0), 1, 5)

        # survey missingness is MAR: depends on workload, never on intent to leave
        p_non = np.clip(p.nonresp_base + p.nonresp_slope * np.maximum(0.0, widx - 35.0), 0.0, 0.40)
        skipped = d["u_resp"] < p_non
        partial = ~skipped & (d["u_part"] < p.partial_prob)
        n_ask = np.where(partial, 3 + (d["u_na"] > 0.5).astype(np.int64), 5)
        ranks = np.argsort(np.argsort(d["r_items"], axis=1), axis=1)
        ans = (ranks < n_ask[:, None]) & ~skipped[:, None]
        n_ans = ans.sum(axis=1)
        mean_ans = np.where(n_ans > 0, (items * ans).sum(axis=1) / np.maximum(n_ans, 1), np.nan)
        score = np.round(100.0 * (mean_ans - 1.0) / 4.0, 1)
        sd_off = np.minimum(np.floor(d["u_sd"] * 21).astype(np.int64), (qe - wf.hire).astype(np.int64))
        survey_date = qe - sd_off.astype("timedelta64[D]")

        resp = act & (n_ans > 0)
        prev_eng = np.where(resp, last_eng, prev_eng)
        last_eng = np.where(resp, score, last_eng)

        # rule-based risk terms (documented in design_decisions.md section 7)
        eng_gap = np.where(np.isnan(last_eng), 0.0, np.clip((60.0 - last_eng) / 20.0, -1.5, 2.5))
        eng_drop = np.where(np.isnan(prev_eng) | np.isnan(last_eng), 0.0,
                            np.maximum(0.0, prev_eng - last_eng) / 20.0)
        moderator = np.where(np.isnan(last_eng), 1.0, np.where(last_eng >= 70.0, 0.3, 1.0))
        overload_eff = np.minimum(cnt, 4) / 2.0 * moderator
        early = (ten < 12).astype(float)
        contrib = np.stack([eng_gap, eng_drop, stagn, pay, overload_eff, early], axis=1) * coef
        terms_sum = contrib.sum(axis=1)
        has_prev = act.copy()

        if collect:
            idx = np.flatnonzero(act)
            res.snaps.append({
                "t": t, "emp": idx, "role_idx": role_idx[idx], "team": team[idx],
                "tenure": ten[idx], "msp": msp[idx], "mit": mit[idx],
                "salary": salary[idx].astype(np.int64), "compa": compa[idx],
                "tr": tr_flag[idx], "promo": promoted[idx],
                "hours": hours[idx], "projects": projects[idx], "oncall": oncall[idx],
                "peak": peak[idx], "widx": widx[idx], "high": high[idx],
                "items": np.where(ans[idx], items[idx], np.nan), "n_ans": n_ans[idx],
                "partial": partial[idx], "skipped": skipped[idx], "score": score[idx],
                "survey_date": survey_date[idx],
            })

        # ---------------- D. interventions ----------------------------------
        iv = None
        if t <= T - 2:
            rule_p = sigmoid(b0 + terms_sum)  # same rule, without the unobservable noise
            elig_i = act & ((t - last_int_t) > p.cooldown_quarters)
            thr = np.quantile(rule_p[act], 1 - p.signal_top_frac) if act.any() else 2.0
            flag = elig_i & (rule_p >= thr) & (d["u_up"] < p.signal_uptake)
            drop = np.nan_to_num(prev_eng - last_eng, nan=0.0)
            mgr = elig_i & ~flag & resp & (drop >= p.mgr_drop_points) & (d["u_mgr"] < p.mgr_prob)
            hr = elig_i & ~flag & ~mgr & (d["u_hr"] < p.hr_prob)
            sel = np.flatnonzero(flag | mgr | hr)
            if sel.size:
                src = np.where(flag[sel], 0, np.where(mgr[sel], 1, 2))
                cb = contrib[sel]
                dom = np.argmax(cb, axis=1)
                anyp = cb.max(axis=1) > 0
                ity = np.where(anyp, FACTOR_TO_TYPE[dom], 0)
                # type effect applies only if its driving factor is present
                need_col = np.array([-1, 4, 2, 3])[ity]
                relevant = (ity == 0) | (cb[np.arange(sel.size), np.maximum(need_col, 0)] > 0)
                mult_t = np.where(relevant, np.array(p.type_multiplier)[ity], 1.0)
                u = lambda name: d[name][sel]
                declined = (src == 0) & (u("u_rev") < p.signal_decline)
                pending = (src == 0) & ~declined & (t == T - 2) & (u("u_pend") < p.final_q_pending)
                proposed = qe + (1 + np.floor(u("u_d1") * 14).astype(np.int64)).astype("timedelta64[D]")
                reviewed = np.where(src == 0,
                                    proposed + (1 + np.floor(u("u_d2") * 7).astype(np.int64)).astype("timedelta64[D]"),
                                    NAT)
                reviewed = np.where(pending, NAT, reviewed)
                base_d = np.where(np.isnat(reviewed), proposed, reviewed)
                not_yet = (src == 0) & ~declined & ~pending & (t == T - 2) & (u("u_d3") < 0.2)
                conducted_ok = ~declined & ~pending & ~not_yet
                conducted = np.where(conducted_ok,
                                     base_d + (3 + np.floor(u("u_d3") * 12).astype(np.int64)).astype("timedelta64[D]"),
                                     NAT)
                closed = np.where(conducted_ok & (u("u_d4") < 0.7),
                                  conducted + (7 + np.floor(u("u_d4") / 0.7 * 24).astype(np.int64)).astype("timedelta64[D]"),
                                  NAT)
                closed = np.where(closed > np.datetime64(config.WINDOW_END, "D"), NAT, closed)
                lb_d = np.where(~np.isnat(conducted), conducted, np.where(~np.isnat(reviewed), reviewed, proposed))
                int_lb[sel] = lb_d
                last_int_t[sel] = t
                did = sel[conducted_ok]
                mult_left[did] = 2; mult_val[did] = mult_t[conducted_ok]; rec_left[did] = 2
                review_status = np.select([src != 0, declined, pending], ["Not_Required", "Declined", "Pending"], "Approved")
                status = np.select([declined, pending, not_yet, ~np.isnat(closed), conducted_ok],
                                   ["Declined", "Proposed", "Approved", "Closed", "Conducted"], "Conducted")
                if collect:
                    iv = {"emp": sel, "t": np.full(sel.size, t), "src": src, "ity": ity,
                          "score": np.where(src == 0, rule_p[sel], np.nan), "contrib": cb,
                          "review_status": review_status, "status": status,
                          "proposed": proposed, "reviewed": reviewed, "conducted": conducted,
                          "closed": closed, "mult": np.where(conducted_ok, mult_t, 1.0)}
        if collect and iv is not None:
            res.iv.append(iv)

    res.exit_date, res.exit_type, res.exit_reason = exit_date, exit_type, exit_reason
    res.vol_rate = float((exit_type == 1).sum()) / n
    res.invol_rate = float((exit_type == 2).sum()) / n
    return res