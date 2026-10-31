"""CLI:  python -m yottaflex.model --data data/full --out data/full/model --report docs/model_report.md"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from ..io import read_tables
from .pipeline import run
from .report import render


def _jsonable(o):
    if isinstance(o, pd.DataFrame):
        return o.round(6).to_dict(orient="records")
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if hasattr(o, "item"):
        return o.item()
    return o


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Train the explainable model, audit it, and write supportive signals.")
    ap.add_argument("--data", default="data/full")
    ap.add_argument("--out", default="data/full/model")
    ap.add_argument("--report", help="write the markdown model report here")
    ap.add_argument("--no-baseline", action="store_true", help="skip regenerating the clean baseline for the leak ladder")
    a = ap.parse_args(argv)

    raw = read_tables(a.data)
    raw.pop("ground_truth", None)                      # the model side never sees the ground truth
    meta_path = Path(a.data, "generation_report.json")
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else None
    clean = None
    if meta and not a.no_baseline:
        from ..generate import generate_dataset
        clean = generate_dataset(meta["n_employees"], meta["seed"], inject_anomalies=False).tables
    R = run(raw, clean)

    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    R["signals"].to_csv(out / "retention_signals.csv", index=False, lineterminator="\n")
    R["coefficients"].round(6).to_csv(out / "coefficients.csv", index=False, lineterminator="\n")
    R["subgroups"].round(6).to_csv(out / "subgroup_audit.csv", index=False, lineterminator="\n")
    drop = {"signals", "model", "test_frame", "test_prob"}
    (out / "model_metrics.json").write_text(json.dumps(_jsonable({k: v for k, v in R.items() if k not in drop}), indent=2, sort_keys=True, default=str) + "\n")
    if a.report:
        Path(a.report).parent.mkdir(parents=True, exist_ok=True)
        Path(a.report).write_text(render(R, meta["n_employees"] if meta else len(raw["employee"]), meta["seed"] if meta else 0) + "\n", encoding="utf-8")
    t = R["test"]
    print(f"test: ROC-AUC {t['roc_auc']:.3f}  PR-AUC {t['pr_auc']:.3f} (base {t['base_rate']:.3f})  recall@5% {t['recall_at_5pct']:.1%}  lift@5% {t['lift_at_5pct']:.1f}x")
    print(f"signals: {len(R['signals'])} rows -> {out / 'retention_signals.csv'}")
    print("production audit:", "PASS" if R["audit"]["production"]["passed"] else "FAIL")
    return 0 if R["audit"]["production"]["passed"] and R["audit"]["split"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
