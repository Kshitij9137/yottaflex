"""Inject documented data-quality anomalies and benign ground-truth examples."""
from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .. import config, ids


@dataclass(frozen=True)
class AnomalyRates:
    late_recorded_row: float = 0.006
    snapshot_after_exit: float = 0.004
    skipped_scored_zero: float = 0.03
    label_mismatch: float = 0.005
    unreviewed_individual_score: float = 0.10
    benign_decoy: float = 0.03


def _count(rate: float, base: int) -> int:
    return max(1, round(rate * base)) if rate > 0 else 0


def _sample(values, count: int, rng: np.random.Generator, excluded=(), label="records",
            exclude_first=False):
    excluded = set(excluded)
    candidates = list(dict.fromkeys(
        value for value in values
        if (value[0] if exclude_first and isinstance(value, tuple) else value) not in excluded
    ))
    if len(candidates) < count:
        raise RuntimeError(f"not enough {label}: need {count}, found {len(candidates)}")
    if count == 0:
        return []
    selected = rng.choice(len(candidates), size=count, replace=False)
    return [candidates[int(i)] for i in selected]


def _serializable(value):
    if value is None or value is pd.NA or pd.isna(value):
        return None
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        return str(pd.Timestamp(value).date())
    if isinstance(value, np.generic):
        return value.item()
    return value


def _record(records, issue_type, subtype, entity, record_id, fields=(),
            original=None, injected=True, description=""):
    records.append({
        "issue_type": issue_type,
        "issue_subtype": subtype,
        "entity": entity,
        "record_id": record_id,
        "field": ", ".join(fields) if fields else "",
        "original_value": json.dumps(
            {key: _serializable(value) for key, value in (original or {}).items()},
            sort_keys=True,
        ) if original is not None else None,
        "expected_decision": "flag" if injected else "do_not_flag",
        "is_injected": injected,
        "description": description,
    })


def _stamp(value) -> pd.Timestamp:
    return pd.Timestamp(value).tz_localize(None) if pd.Timestamp(value).tzinfo else pd.Timestamp(value)


def _append_row(frame: pd.DataFrame, row: pd.Series) -> pd.DataFrame:
    addition = pd.DataFrame([row.to_dict()])
    addition = addition.loc[:, ~addition.isna().all()]
    return pd.concat([frame, addition], ignore_index=True)


def _employee_outcomes(tables):
    return tables["attrition_outcome"].set_index("employee_id")


def _inject_late_rows(tables, rng, records, used, rate):
    outcomes = _employee_outcomes(tables)
    snapshots = tables["tenure_snapshot"]
    candidates = []
    for name in ("test", "validation", "train"):
        cutoff = pd.Timestamp(config.CUTOFFS[name])
        horizon_end = pd.Timestamp(config.HORIZON_ENDS[name])
        cutoff_snapshots = snapshots.loc[snapshots["snapshot_date"] == cutoff]
        for row in cutoff_snapshots.itertuples(index=False):
            outcome = outcomes.loc[row.employee_id]
            termination = outcome["termination_date"]
            if outcome["final_status"] != "Exited_Voluntary" or pd.isna(termination):
                continue
            termination = _stamp(termination)
            if cutoff + pd.Timedelta(days=1) < termination <= horizon_end:
                candidates.append((row.employee_id, row.snapshot_id, termination))
    candidates = list({employee: (employee, snapshot, term)
                       for employee, snapshot, term in candidates}.values())
    count = _count(rate, len(outcomes))
    selected = _sample(candidates, count, rng, label="eligible leavers for late-recorded rows",
                       exclude_first=True)
    workload = tables["workload_snapshot"]
    surveys = tables["engagement_survey"]
    for employee, snapshot_id, termination in selected:
        used.add(employee)
        late_time = termination - pd.Timedelta(days=1) + pd.Timedelta(hours=18)
        if rng.random() < 0.5:
            row_index = workload.index[workload["snapshot_id"] == snapshot_id][0]
            row = workload.loc[row_index]
            fields = ("avg_weekly_hours", "overtime_hours_quarter", "workload_index",
                      "high_load_flag", "recorded_at")
            original = {field: row[field] for field in fields}
            hours = float(rng.integers(60, 66))
            workload.at[row_index, "avg_weekly_hours"] = hours
            workload.at[row_index, "overtime_hours_quarter"] = round(max(0, hours - 40) * 13, 1)
            index = 100 * (0.55 * (hours - 35) / 20
                           + 0.30 * row["active_project_count"] / 8
                           + 0.15 * row["on_call_days"] / 20)
            workload.at[row_index, "workload_index"] = round(float(np.clip(index, 0, 100)), 1)
            workload.at[row_index, "high_load_flag"] = workload.at[row_index, "workload_index"] >= 65
            workload.at[row_index, "recorded_at"] = late_time.strftime("%Y-%m-%dT%H:%M:%SZ")
            entity, record_id = "workload_snapshot", row["workload_id"]
        else:
            row_index = surveys.index[surveys["snapshot_id"] == snapshot_id][0]
            row = surveys.loc[row_index]
            item_fields = ("q_manager_support", "q_growth_opportunity", "q_workload_sustainable",
                           "q_recognition", "q_intent_to_stay")
            fields = (*item_fields, "engagement_score", "recorded_at")
            original = {field: row[field] for field in fields}
            values = rng.integers(1, 3, size=len(item_fields))
            for field, value in zip(item_fields, values):
                surveys.at[row_index, field] = int(value)
            surveys.at[row_index, "engagement_score"] = round(
                100 * (float(values.mean()) - 1) / 4, 1)
            surveys.at[row_index, "recorded_at"] = late_time.strftime("%Y-%m-%dT%H:%M:%SZ")
            entity, record_id = "engagement_survey", row["survey_id"]
        _record(records, "future_information_leak", "late_recorded_row", entity, record_id,
                fields, original, description="Snapshot data was revised after its prediction cutoff.")


def _inject_post_exit_snapshots(tables, rng, records, used, rate):
    outcomes = _employee_outcomes(tables)
    snapshots = tables["tenure_snapshot"]
    candidates = []
    for quarter in config.QUARTERS:
        quarter_end = pd.Timestamp(ids.quarter_end(quarter))
        quarter_start = quarter_end - pd.DateOffset(months=3) + pd.Timedelta(days=1)
        exited = outcomes.loc[
            outcomes["final_status"].isin(("Exited_Voluntary", "Exited_Involuntary"))
            & outcomes["termination_date"].notna()
        ]
        existing = set(snapshots.loc[
            snapshots["snapshot_quarter"] == quarter, "employee_id"])
        for employee, outcome in exited.iterrows():
            term = _stamp(outcome["termination_date"])
            if quarter_start <= term < quarter_end and employee not in existing:
                candidates.append((employee, quarter, quarter_end, term))
    count = _count(rate, len(outcomes))
    selected = _sample(candidates, count, rng, excluded=used,
                       label="employees eligible for post-exit snapshots", exclude_first=True)
    for employee, quarter, quarter_end, termination in selected:
        used.add(employee)
        prior = snapshots.loc[snapshots["employee_id"] == employee].sort_values("snapshot_date").iloc[-1]
        snapshot_id = ids.snapshot_id(employee, quarter)
        snapshot = prior.copy()
        snapshot.update({
            "snapshot_id": snapshot_id,
            "snapshot_quarter": quarter,
            "snapshot_date": quarter_end,
            "recorded_at": quarter_end.strftime("%Y-%m-%dT19:00:00Z"),
        })
        tables["tenure_snapshot"] = _append_row(tables["tenure_snapshot"], snapshot)
        _record(records, "future_information_leak", "snapshot_after_exit",
                "tenure_snapshot", snapshot_id, ("(inserted row)",),
                description=f"Snapshot was inserted after termination on {termination.date()}.")

        prior_workload = tables["workload_snapshot"].loc[
            tables["workload_snapshot"]["snapshot_id"] == prior["snapshot_id"]].iloc[0]
        workload_id = ids.workload_id(employee, quarter)
        workload = prior_workload.copy()
        workload.update({
            "workload_id": workload_id,
            "snapshot_id": snapshot_id,
            "recorded_at": quarter_end.strftime("%Y-%m-%dT19:00:00Z"),
        })
        tables["workload_snapshot"] = _append_row(tables["workload_snapshot"], workload)
        _record(records, "future_information_leak", "snapshot_after_exit",
                "workload_snapshot", workload_id, ("(inserted row)",),
                description="Workload row accompanies a post-exit snapshot.")

        prior_survey = tables["engagement_survey"].loc[
            tables["engagement_survey"]["snapshot_id"] == prior["snapshot_id"]].iloc[0]
        year = quarter_end.year
        prefix = f"SURV-{year}-"
        counters = tables["engagement_survey"]["survey_id"].loc[
            tables["engagement_survey"]["survey_id"].str.startswith(prefix)]
        next_counter = max((int(value.rsplit("-", 1)[1]) for value in counters), default=0) + 1
        survey_id = ids.survey_id(year, next_counter)
        survey = prior_survey.copy()
        survey.update({
            "survey_id": survey_id,
            "snapshot_id": snapshot_id,
            "survey_date": quarter_end - pd.Timedelta(days=7),
            "response_status": "Skipped",
            "items_answered": 0,
            "engagement_score": pd.NA,
            "recorded_at": quarter_end.strftime("%Y-%m-%dT19:00:00Z"),
        })
        for field in ("q_manager_support", "q_growth_opportunity", "q_workload_sustainable",
                      "q_recognition", "q_intent_to_stay"):
            survey[field] = pd.NA
        tables["engagement_survey"] = _append_row(tables["engagement_survey"], survey)
        _record(records, "future_information_leak", "snapshot_after_exit",
                "engagement_survey", survey_id, ("(inserted row)",),
                description="Skipped survey row accompanies a post-exit snapshot.")


def _inject_skipped_surveys(tables, rng, records, used, rate):
    surveys = tables["engagement_survey"]
    skipped = surveys.loc[surveys["response_status"] == "Skipped"]
    count = _count(rate, len(skipped))
    candidates = [(row.employee_id, index) for index, row in skipped.iterrows()]
    selected = _sample(candidates, count, rng, excluded=used,
                       label="untouched skipped surveys", exclude_first=True)
    for employee, index in selected:
        used.add(employee)
        row = surveys.loc[index]
        original = {"engagement_score": row["engagement_score"]}
        surveys.at[index, "engagement_score"] = 0.0
        _record(records, "missing_survey_as_negative", "skipped_scored_zero",
                "engagement_survey", row["survey_id"], ("engagement_score",), original,
                description="A skipped survey was assigned a zero engagement score.")


def _inject_label_mismatches(tables, rng, records, used, rate):
    outcomes = tables["attrition_outcome"]
    total = _count(rate, len(outcomes))
    counts = (round(total * 0.4), round(total * 0.4), total - round(total * 0.4) * 2)
    subsets = (
        ("label_missing_exit", outcomes.loc[
            (outcomes["final_status"] == "Exited_Voluntary")
            & (outcomes["voluntary_attrition_label"] == 1)]),
        ("label_without_exit", outcomes.loc[
            (outcomes["final_status"] == "Active")
            & (outcomes["voluntary_attrition_label"] == 0)]),
        ("label_outside_horizon", outcomes.loc[
            (outcomes["final_status"] == "Exited_Voluntary")
            & (outcomes["termination_date"] <= pd.Timestamp(config.CUTOFFS["test"]))
            & ~outcomes["eligible_at_cutoff"]]),
    )
    for (subtype, pool), count in zip(subsets, counts):
        selected = _sample(list(zip(pool["employee_id"], pool.index)), count, rng,
                           excluded=used, label=f"outcomes for {subtype}",
                           exclude_first=True)
        for employee, index in selected:
            used.add(employee)
            row = outcomes.loc[index]
            original = {"voluntary_attrition_label": row["voluntary_attrition_label"]}
            outcomes.at[index, "voluntary_attrition_label"] = 1 if subtype != "label_missing_exit" else 0
            _record(records, "label_termination_mismatch", subtype, "attrition_outcome",
                    row["outcome_id"], ("voluntary_attrition_label",), original,
                    description="Stored label does not match the termination facts.")


def _inject_unreviewed_scores(tables, rng, records, used, rate):
    interventions = tables["intervention"]
    signal_flagged = interventions["trigger_source"] == "Signal_Flagged"
    eligible = interventions.loc[
        signal_flagged
        & interventions["status"].isin(("Conducted", "Closed"))]
    count = _count(rate, int(signal_flagged.sum()))
    selected = _sample(list(eligible.index), count, rng,
                       label="conducted signal-flagged interventions")
    subtypes = ("no_explanation", "no_human_review", "no_explanation_no_review")
    assignments = [subtypes[index % len(subtypes)] for index in range(count)]
    rng.shuffle(assignments)
    for index, subtype in zip(selected, assignments):
        row = interventions.loc[index]
        fields = ["signal_top_factors"]
        original = {"signal_top_factors": row["signal_top_factors"]}
        interventions.at[index, "signal_top_factors"] = None
        if subtype in ("no_human_review", "no_explanation_no_review"):
            fields.extend(("reviewed_by_employee_id", "reviewed_date", "review_status"))
            original.update({field: row[field] for field in fields[1:]})
            interventions.at[index, "reviewed_by_employee_id"] = None
            interventions.at[index, "reviewed_date"] = pd.NaT
            interventions.at[index, "review_status"] = "Pending"
        _record(records, "unreviewed_individual_score", subtype, "intervention",
                row["intervention_id"], fields, original,
                description="Conducted individual risk score is missing explanation or human review.")


def _add_decoys(tables, rng, records, rate):
    employees = tables["employee"]["employee_id"]
    count = _count(rate, len(employees))
    workload = tables["workload_snapshot"]
    surveys = tables["engagement_survey"]
    injected_ids = {}
    for record in records:
        if record["is_injected"]:
            injected_ids.setdefault(record["entity"], set()).add(record["record_id"])
    scores = surveys.set_index("snapshot_id")["engagement_score"]
    high = workload.loc[
        workload["planned_peak_flag"].astype(bool)
        & (workload["snapshot_id"].map(scores) >= 70)
        & ~workload["workload_id"].isin(injected_ids.get("workload_snapshot", set()))]
    selected = _sample(
        list(high.index), count, rng,
        label="planned-peak high-workload decoys")
    for index in selected:
        row = workload.loc[index]
        _record(records, "benign_high_workload", "planned_peak_healthy_engagement",
                "workload_snapshot", row["workload_id"], injected=False,
                description="Planned peak workload coincides with healthy engagement.")

    assignments = tables["employee_team_assignment"].merge(
        tables["attrition_outcome"][["employee_id", "termination_date"]],
        on="employee_id", how="left")
    assignments = assignments.sort_values(["employee_id", "effective_from"], kind="stable")
    assignments["next_reason"] = assignments.groupby("employee_id")["change_reason"].shift(-1)
    assignments["next_effective_from"] = assignments.groupby("employee_id")["effective_from"].shift(-1)
    observed_end = assignments["termination_date"].fillna(pd.Timestamp(config.WINDOW_END))
    transfer = assignments.loc[
        (assignments["next_reason"] == "Internal_Transfer")
        & assignments["effective_to"].notna()
        & assignments["next_effective_from"].notna()
        & (observed_end > assignments["next_effective_from"] + pd.Timedelta(days=180))]
    selected = _sample(
        list(transfer["assignment_id"]), count, rng,
        label="long-lived internal transfer decoys")
    for record_id in selected:
        _record(records, "benign_internal_transfer", "assignment_closed_by_transfer",
                "employee_team_assignment", record_id, injected=False,
                description="Assignment ended due to a transfer; the employee remained employed.")

    skipped = surveys.loc[(surveys["response_status"] == "Skipped")
                          & surveys["engagement_score"].isna()
                          & ~surveys["survey_id"].isin(
                              injected_ids.get("engagement_survey", set()))]
    selected = _sample(
        list(skipped.index), count, rng,
        label="untouched skipped-survey decoys")
    for index in selected:
        row = surveys.loc[index]
        _record(records, "benign_missing_survey", "skipped_null_score", "engagement_survey",
                row["survey_id"], injected=False,
                description="Skipped survey correctly has no engagement score.")


def inject(tables, n_employees, rng, rates=None):
    rates = rates or AnomalyRates()
    result = {name: frame.copy(deep=True) for name, frame in tables.items()}
    records = []
    used = set()
    _inject_late_rows(result, rng, records, used, rates.late_recorded_row)
    _inject_post_exit_snapshots(result, rng, records, used, rates.snapshot_after_exit)
    _inject_skipped_surveys(result, rng, records, used, rates.skipped_scored_zero)
    _inject_label_mismatches(result, rng, records, used, rates.label_mismatch)
    _inject_unreviewed_scores(result, rng, records, used, rates.unreviewed_individual_score)
    _add_decoys(result, rng, records, rates.benign_decoy)

    ground_truth = pd.DataFrame(records)
    ground_truth = ground_truth.sort_values(
        ["issue_type", "entity", "record_id"], kind="stable").reset_index(drop=True)
    ground_truth.insert(0, "gt_id", [ids.ground_truth_id(i + 1) for i in range(len(ground_truth))])
    return result, ground_truth
