"""Phase 7 tests: the CLI contract, byte-stable outputs, and the reproducibility proof script itself."""
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

from yottaflex import config
from yottaflex.generate.__main__ import main as generate_main

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def repro():
    spec = importlib.util.spec_from_file_location("repro_check", ROOT / "scripts" / "repro_check.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cli_writes_all_tables_and_a_truthful_report(tmp_path):
    assert generate_main(["--n-employees", "500", "--seed", str(config.SEED), "--out", str(tmp_path)]) == 0
    rep = json.loads((tmp_path / "generation_report.json").read_text(encoding="utf-8"))
    assert rep["seed"] == config.SEED and rep["n_employees"] == 500
    assert rep["generator_command"].endswith("--out <dir>") and "--seed 20261022" in rep["generator_command"]
    for name, digest in rep["sha256"].items():                      # every recorded checksum is the real one
        assert hashlib.sha256((tmp_path / name).read_bytes()).hexdigest() == digest, name
    assert {"ground_truth.csv", "ground_truth.json"} <= set(rep["sha256"])
    assert len([f for f in rep["sha256"] if f.endswith(".csv")]) == 12     # 11 tables + ground truth


def test_no_inject_writes_a_clean_dataset_without_ground_truth(tmp_path):
    assert generate_main(["--n-employees", "500", "--no-inject", "--out", str(tmp_path)]) == 0
    assert not (tmp_path / "ground_truth.csv").exists() and not (tmp_path / "ground_truth.json").exists()
    assert "--no-inject" in json.loads((tmp_path / "generation_report.json").read_text(encoding="utf-8"))["generator_command"]


def test_generated_files_use_lf_line_endings_on_every_platform(tmp_path):
    generate_main(["--n-employees", "500", "--out", str(tmp_path)])
    for f in tmp_path.iterdir():
        assert b"\r" not in f.read_bytes(), f.name


def test_scale_is_parameterised_with_one_code_path(tmp_path):
    generate_main(["--n-employees", "500", "--out", str(tmp_path / "s")])
    generate_main(["--n-employees", "700", "--out", str(tmp_path / "m")])
    small = json.loads((tmp_path / "s" / "generation_report.json").read_text(encoding="utf-8"))["row_counts"]
    mid = json.loads((tmp_path / "m" / "generation_report.json").read_text(encoding="utf-8"))["row_counts"]
    assert small["employee"] == 500 and mid["employee"] == 700 and small["role"] == mid["role"] == 35


# ------------------------------------------------------------------ the proof script
def test_diff_reports_changed_missing_and_extra_files(repro):
    a = {"x.csv": {"rows": 2, "sha256": "aa"}, "y.csv": {"rows": 3, "sha256": "bb"}}
    assert repro.diff(a, dict(a)) == []
    changed = {**a, "y.csv": {"rows": 3, "sha256": "cc"}}
    assert any("y.csv" in m for m in repro.diff(a, changed))
    assert any("only one run" in m for m in repro.diff(a, {"x.csv": a["x.csv"]}))
    assert any("z.csv" in m for m in repro.diff(a, {**a, "z.csv": a["x.csv"]}))


def test_snapshot_counts_csv_rows_including_quoted_newlines(repro, tmp_path):
    (tmp_path / "t.csv").write_bytes(b'id,note\n1,"two\nlines"\n2,plain\n')
    (tmp_path / "t.json").write_bytes(b"[]\n")
    snap = repro.snapshot(tmp_path)
    assert snap["t.csv"]["rows"] == 2 and snap["t.json"]["rows"] is None
    assert snap["t.csv"]["sha256"] == hashlib.sha256((tmp_path / "t.csv").read_bytes()).hexdigest()


def test_repro_script_end_to_end_passes_and_writes_proof(repro, tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(ROOT / "src") + os.pathsep + os.environ.get("PYTHONPATH", ""))
    monkeypatch.setattr(sys, "argv", ["repro_check.py", "--n-employees", "500", "--label", "t",
                                      "--no-control", "--docs-dir", str(tmp_path)])
    assert repro.main() == 0
    proof = json.loads((tmp_path / "reproducibility_t.json").read_text(encoding="utf-8"))
    assert proof["run_a_equals_run_b"] is True and proof["mismatches"] == []
    assert proof["files_compared"] >= 25 and proof["seed"] == config.SEED
    assert (tmp_path / "reproducibility_t.md").read_text(encoding="utf-8").count("`") > 50   # table of hashes


def test_repro_script_fails_when_runs_differ(repro, tmp_path, monkeypatch):
    seeds = iter([config.SEED, config.SEED + 7])          # sabotage: run B uses another seed
    real = repro.build
    monkeypatch.setattr(repro, "build", lambda out, n, seed, wm: real(out, n, next(seeds), wm))
    monkeypatch.setenv("PYTHONPATH", str(ROOT / "src"))
    monkeypatch.setattr(sys, "argv", ["repro_check.py", "--n-employees", "500", "--label", "bad",
                                      "--no-control", "--docs-dir", str(tmp_path)])
    assert repro.main() == 1
