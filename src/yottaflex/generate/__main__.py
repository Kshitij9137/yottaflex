"""CLI:  python -m yottaflex.generate --n-employees 10000 --seed 20261022 --out data/full"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .. import config
from ..io import write_csv_tables, write_ground_truth
from .pipeline import generate_dataset


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Generate the synthetic workforce dataset.")
    ap.add_argument("--n-employees", type=int, default=10_000, help="scale (>= 500)")
    ap.add_argument("--seed", type=int, default=config.SEED)
    ap.add_argument("--out", default="data/full", help="output directory")
    ap.add_argument("--no-inject", action="store_true", help="write the clean baseline (no anomalies, no ground truth)")
    a = ap.parse_args(argv)
    t0 = time.time()
    ds = generate_dataset(a.n_employees, a.seed, inject_anomalies=not a.no_inject)
    sums = write_csv_tables(ds.tables, a.out)
    if ds.ground_truth is not None:
        sums.update(write_ground_truth(ds.ground_truth, a.out))
    meta = {**ds.meta, "sha256": sums, "generator_command":
            f"python -m yottaflex.generate --n-employees {a.n_employees} --seed {a.seed}"
            + (" --no-inject" if a.no_inject else "") + " --out <dir>"}
    Path(a.out, "generation_report.json").write_bytes((json.dumps(meta, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    print(json.dumps({k: meta[k] for k in ("n_employees", "seed", "voluntary_attrition_rate",
                                           "involuntary_attrition_rate", "rule_score_auc_next_quarter",
                                           "row_counts", "ground_truth_counts")
                      if k in meta}, indent=2))
    print(f"done in {time.time() - t0:.1f}s -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())