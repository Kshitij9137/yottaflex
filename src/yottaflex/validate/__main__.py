"""CLI:  python -m yottaflex.validate --data data/full --report docs/validation_summary.md"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..io import read_tables
from .evaluate import evaluate, load_ground_truth, passed, results_as_dicts, run_rules
from .report import GENERATED, render
from .rules import RULES


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Validate an exported dataset and score the anomaly detectors.")
    ap.add_argument("--data", default="data/full")
    ap.add_argument("--report", help="write the markdown summary here")
    ap.add_argument("--json", help="write the full machine-readable results here")
    ap.add_argument("--no-baseline", action="store_true", help="skip regenerating the clean baseline")
    a = ap.parse_args(argv)

    raw = read_tables(a.data)
    gt_raw = raw.pop("ground_truth", None)
    meta_path = Path(a.data, "generation_report.json")
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else None

    ctx, results, flagged = run_rules(raw)
    gt = load_ground_truth(gt_raw) if gt_raw is not None else None
    ev = evaluate(ctx, results, flagged, gt)

    base_results, base_fail = None, None
    if meta and not a.no_baseline and gt is not None:
        from ..generate import generate_dataset
        clean = generate_dataset(meta["n_employees"], meta["seed"], inject_anomalies=False)
        _, base_results, _ = run_rules(clean.tables)
        base_fail = [r.rule_id for r in base_results if r.n_violations]

    ok = passed(base_fail, ev)
    docs = [RULES_i for RULES_i in RULES if not r_is_generated(RULES_i.rule_id)]
    if a.report:
        Path(a.report).parent.mkdir(parents=True, exist_ok=True)
        Path(a.report).write_text(render(meta, results, ev, base_results, ok, docs) + "\n", encoding="utf-8")
    if a.json:
        Path(a.json).write_text(json.dumps({"passed": ok, "evaluation": ev, "rules": results_as_dicts(results),
                                             "baseline_rules_with_violations": base_fail}, indent=2, sort_keys=True, default=str) + "\n")
    print(f"rules: {ev['n_rules']}  records flagged: {ev['total_flagged_records']}")
    if ev.get("has_ground_truth"):
        for d in ev["detectors"]:
            print(f"  {d['issue_type']:<32} precision {d['precision']:.2f}  recall {d['recall']:.2f}  (TP {d['tp']}, FP {d['fp']}, FN {d['fn']})")
        print(f"  unexplained violations: {ev['unexplained_violations']}   decoys flagged: {ev['decoys_flagged_by_any_rule']}/{ev['decoys_total']}")
    if base_fail is not None:
        print(f"  clean baseline: {len(base_fail)} rules with violations")
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def r_is_generated(rule_id: str) -> bool:
    return rule_id.startswith(GENERATED)


if __name__ == "__main__":
    raise SystemExit(main())