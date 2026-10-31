"""Phase 6: prove that the same seed gives byte-identical output.

What it does (all through the documented CLIs, in temporary directories):
  1. python -m yottaflex.generate  --seed S   -> run A
  2. python -m yottaflex.generate  --seed S   -> run B
  3. python -m yottaflex.generate  --seed S+1 -> negative control (must DIFFER, else the check proves nothing)
  4. python -m yottaflex.export    on A and B (JSON + SQL seed), optionally python -m yottaflex.model too
  5. compares row counts (CSV) and SHA-256 (every file) between A and B
Writes docs/reproducibility_<label>.json and .md and exits 1 on any mismatch.

Usage:
  python scripts/repro_check.py --n-employees 500   --label starter
  python scripts/repro_check.py --n-employees 10000 --label full --compare-committed data/full
  python scripts/repro_check.py --n-employees 500 --label starter --with-model
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_SEED = 20261022


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def csv_rows(p: Path) -> int | None:
    if p.suffix != ".csv":
        return None
    with p.open(newline="", encoding="utf-8") as f:
        return max(sum(1 for _ in csv.reader(f)) - 1, 0)


def snapshot(d: Path) -> dict[str, dict]:
    return {p.relative_to(d).as_posix(): {"rows": csv_rows(p), "sha256": sha256(p)}
            for p in sorted(d.rglob("*")) if p.is_file()}


def diff(a: dict, b: dict) -> list[str]:
    out = []
    for k in sorted(set(a) | set(b)):
        if k not in a or k not in b:
            out.append(f"{k}: present in only one run")
        elif a[k] != b[k]:
            out.append(f"{k}: rows {a[k]['rows']} vs {b[k]['rows']}; sha256 {a[k]['sha256'][:12]} vs {b[k]['sha256'][:12]}")
    return out


def diff_expected_files(expected: dict, actual: dict) -> list[str]:
    """Compare every expected file while allowing unrelated files in the target directory."""
    actual_expected = {name: actual[name] for name in expected if name in actual}
    return diff(expected, actual_expected)


def run(*args: str) -> None:
    subprocess.run([sys.executable, "-m", *args], check=True, stdout=subprocess.DEVNULL)


def build(out: Path, n: int, seed: int, with_model: bool) -> dict:
    run("yottaflex.generate", "--n-employees", str(n), "--seed", str(seed), "--out", str(out))
    run("yottaflex.export", "--data", str(out))
    if with_model:
        run("yottaflex.model", "--data", str(out), "--out", str(out / "model"))
    return snapshot(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n-employees", type=int, default=10_000)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--label", default="full")
    ap.add_argument("--with-model", action="store_true", help="also train the model in both runs and compare its outputs")
    ap.add_argument("--no-control", action="store_true", help="skip the different-seed negative control")
    ap.add_argument("--compare-committed", type=Path, help="also compare run A with this committed data directory")
    ap.add_argument("--docs-dir", type=Path, default=Path("docs"))
    a = ap.parse_args()

    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        A = build(t / "run_a", a.n_employees, a.seed, a.with_model)
        B = build(t / "run_b", a.n_employees, a.seed, a.with_model)
        C = None if a.no_control else build(t / "control", a.n_employees, a.seed + 1, a.with_model)

    same_seed = diff(A, B)
    control = None if C is None else diff(A, C)
    committed = None
    if a.compare_committed:
        cm = snapshot(a.compare_committed)
        committed = diff_expected_files(A, cm)

    result = {
        "label": a.label, "seed": a.seed, "n_employees": a.n_employees,
        "generator_command": f"python -m yottaflex.generate --n-employees {a.n_employees} --seed {a.seed} --out <dir>",
        "python": platform.python_version(), "platform": platform.platform(),
        "files_compared": len(A),
        "run_a_equals_run_b": not same_seed, "mismatches": same_seed,
        "negative_control_differs": None if control is None else bool(control),
        "equals_committed": None if committed is None else not committed, "committed_mismatches": committed,
        "files": A,
    }
    a.docs_dir.mkdir(parents=True, exist_ok=True)
    (a.docs_dir / f"reproducibility_{a.label}.json").write_bytes(
        (json.dumps(result, indent=2, sort_keys=True) + "\n").encode("utf-8"))

    md = [f"# Reproducibility proof: {a.label}", "",
          f"- Command: `{result['generator_command']}`",
          f"- Seed {a.seed}, {a.n_employees} employees, Python {result['python']} on {result['platform']}",
          f"- Files compared: {len(A)} (CSV tables, ground truth, generation report, JSON and SQL exports"
          + (", model outputs" if a.with_model else "") + ")",
          f"- **Run A == Run B (row counts and SHA-256): {result['run_a_equals_run_b']}**",
          f"- Negative control (seed {a.seed + 1}) differs: {result['negative_control_differs']}"]
    if committed is not None:
        md.append(f"- Matches committed `{a.compare_committed}`: {result['equals_committed']}")
    md += ["", "| file | rows | sha256 |", "|---|---:|---|"]
    md += [f"| {k} | {'' if v['rows'] is None else v['rows']} | `{v['sha256']}` |" for k, v in A.items()]
    (a.docs_dir / f"reproducibility_{a.label}.md").write_bytes(("\n".join(md) + "\n").encode("utf-8"))

    print(json.dumps({k: v for k, v in result.items() if k != "files"}, indent=2))
    ok = not same_seed and (control is None or bool(control)) and not committed
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())