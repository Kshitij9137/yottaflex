"""Deterministic CSV export (fixed encoding, line endings, column order, number formats)."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd


def write_csv_tables(tables: dict[str, pd.DataFrame], out_dir) -> dict[str, str]:
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    sums = {}
    for name, df in tables.items():
        path = out / f"{name}.csv"
        df.to_csv(path, index=False, encoding="utf-8", lineterminator="\n",
                  date_format="%Y-%m-%d", float_format="%.10g")
        sums[f"{name}.csv"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return sums


def write_ground_truth(gt: pd.DataFrame, out_dir) -> dict[str, str]:
    """ground_truth.csv and ground_truth.json (identical content, two formats)."""
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    gt.to_csv(out / "ground_truth.csv", index=False, encoding="utf-8", lineterminator="\n")
    (out / "ground_truth.json").write_bytes((gt.to_json(orient="records", indent=2) + "\n").encode("utf-8"))  # bytes: no CRLF translation on Windows
    return {f: hashlib.sha256((out / f).read_bytes()).hexdigest() for f in ("ground_truth.csv", "ground_truth.json")}


def read_tables(data_dir) -> dict[str, pd.DataFrame]:
    """Read exported CSVs as raw strings (typing and validation happen in yottaflex.validate)."""
    d = Path(data_dir)
    out = {}
    for f in sorted(d.glob("*.csv")):
        out[f.stem] = pd.read_csv(f, dtype=str, keep_default_na=False, na_values=[""])
    return out