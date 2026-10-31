"""Phase 6: export generated tables as JSON and SQL seed data, then verify the SQL.

CLI:  python -m yottaflex.export --data data/full

Reads <data>/*.csv (written by `python -m yottaflex.generate`) and writes, under <data>/export/:
  schema.sql          CREATE TABLE with PK, FK, NOT NULL (parent tables first)
  seed.sql            INSERT statements in primary-key order (deterministic)
  json/<table>.json   one JSON array per table, one record per line, typed values
  export_report.json  row counts, SHA-256 of every export file, load-check results

Design notes
  * Tables, column order, types, required flags and foreign keys come from
    yottaflex.validate.schema.SCHEMA, so the SQL cannot drift from the data dictionary.
  * ground_truth is NOT part of the SQL seed. It stays in ground_truth.csv/.json, so the
    "database a model sees" never contains labels about injected anomalies.
  * Injected anomalies are kept as they are (they are labelled in ground_truth). They are
    designed to stay join-valid, so the load check below must still pass on the injected data.
  * Output bytes are fixed: UTF-8, "\\n" line endings, no timestamps. Same CSV in = same bytes out.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd

from .io import read_tables
from .validate.schema import SCHEMA, Col

SQL_TYPE = {"str": "TEXT", "int": "INTEGER", "float": "REAL", "bool": "INTEGER",
            "date": "TEXT", "datetime": "TEXT"}

INSERT_BATCH = 200   # rows per INSERT (SQLite allows up to 500 in one VALUES list)

# Documented 1:1 relationships (data_dictionary.md) plus the natural keys of the snapshot tables.
# Enforced only with --strict-cardinality, because an injected duplicate would (correctly) refuse to load.
UNIQUES = {
    "tenure_snapshot": [("employee_id", "snapshot_quarter")],
    "engagement_survey": [("snapshot_id",)],
    "workload_snapshot": [("snapshot_id",)],
    "attrition_outcome": [("employee_id",)],
}


def _q(name: str) -> str:
    return '"' + name + '"'


def schema_sql(strict: bool) -> str:
    stmts = []
    for table, cols in SCHEMA.items():
        lines = []
        for i, c in enumerate(cols):
            parts = [_q(c.name), SQL_TYPE[c.typ]]
            if i == 0:
                parts.append("PRIMARY KEY")
            elif c.req:
                parts.append("NOT NULL")
            lines.append("  " + " ".join(parts))
        for c in cols:
            if c.fk:
                lines.append(f"  FOREIGN KEY ({_q(c.name)}) REFERENCES {_q(c.fk[0])} ({_q(c.fk[1])})")
        if strict:
            for u in UNIQUES.get(table, []):
                lines.append("  UNIQUE (" + ", ".join(_q(x) for x in u) + ")")
        stmts.append(f"CREATE TABLE {_q(table)} (\n" + ",\n".join(lines) + "\n);\n")
    return "\n".join(stmts)


def _sql_value(v, c: Col) -> str:
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return "NULL"
    if c.typ == "bool":
        return "1" if v in ("True", "true", True) else "0"
    if c.typ in ("int", "float"):
        return str(v)                      # keep the exact text written in the CSV
    return "'" + str(v).replace("'", "''") + "'"


def _json_value(v, c: Col):
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    if c.typ == "bool":
        return v in ("True", "true", True)
    if c.typ == "int":
        return int(v)
    if c.typ == "float":
        return float(v)
    return str(v)


def _records(df: pd.DataFrame, cols: list[Col]):
    names = [c.name for c in cols]
    if list(df.columns) != names:
        raise SystemExit(f"column mismatch for table: CSV has {list(df.columns)}, schema expects {names}")
    for row in df.itertuples(index=False, name=None):
        yield row


def _write(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8")
    path.write_bytes(data)                 # bytes: no platform newline translation
    return hashlib.sha256(data).hexdigest()


def export(data_dir: str | Path, strict: bool = False) -> dict:
    d = Path(data_dir)
    out = d / "export"
    raw = read_tables(d)
    raw.pop("ground_truth", None)          # never part of the seed
    missing = [t for t in SCHEMA if t not in raw]
    if missing:
        raise SystemExit(f"missing tables in {d}: {missing}")

    sums: dict[str, str] = {}
    counts: dict[str, int] = {}
    seed = ["BEGIN;"]
    for table, cols in SCHEMA.items():
        df = raw[table]
        counts[table] = len(df)
        names = ", ".join(_q(c.name) for c in cols)
        json_lines, tuples = [], []
        for row in _records(df, cols):
            tuples.append("(" + ", ".join(_sql_value(v, c) for v, c in zip(row, cols)) + ")")
            rec = {c.name: _json_value(v, c) for v, c in zip(row, cols)}
            json_lines.append(json.dumps(rec, ensure_ascii=False, separators=(", ", ": ")))
        for i in range(0, len(tuples), INSERT_BATCH):     # multi-row INSERTs keep the file ~3x smaller
            seed.append(f"INSERT INTO {_q(table)} ({names}) VALUES\n  "
                        + ",\n  ".join(tuples[i:i + INSERT_BATCH]) + ";")
        seed.append("")
        body = "[\n" + ",\n".join(json_lines) + "\n]\n" if json_lines else "[]\n"
        sums[f"json/{table}.json"] = _write(out / "json" / f"{table}.json", body)
    seed.append("COMMIT;")
    sums["schema.sql"] = _write(out / "schema.sql", schema_sql(strict))
    sums["seed.sql"] = _write(out / "seed.sql", "\n".join(seed) + "\n")

    check = verify_sql(out, counts)
    report = {"strict_cardinality": strict, "row_counts": counts,
              "sha256": dict(sorted(sums.items())), "sql_load_check": check}
    _write(out / "export_report.json", json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def verify_sql(out: Path, counts: dict[str, int]) -> dict:
    """Load the exported SQL into in-memory SQLite with foreign keys ON and compare to the CSV counts."""
    con = sqlite3.connect(":memory:")
    con.execute("PRAGMA foreign_keys = ON")
    result: dict = {"loaded": False, "row_count_mismatches": {}, "foreign_key_violations": None}
    try:
        con.executescript((out / "schema.sql").read_text(encoding="utf-8"))
        con.executescript((out / "seed.sql").read_text(encoding="utf-8"))
        result["loaded"] = True
    except sqlite3.Error as e:             # report instead of hiding: this is a real data finding
        result["error"] = f"{type(e).__name__}: {e}"
        return result
    for table, n in counts.items():
        got = con.execute(f"SELECT COUNT(*) FROM {_q(table)}").fetchone()[0]
        if got != n:
            result["row_count_mismatches"][table] = {"csv": n, "sql": got}
    result["foreign_key_violations"] = len(con.execute("PRAGMA foreign_key_check").fetchall())
    return result


def passed(report: dict) -> bool:
    c = report["sql_load_check"]
    return bool(c["loaded"] and not c["row_count_mismatches"] and c["foreign_key_violations"] == 0)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Export JSON + SQL seed files and verify the SQL.")
    ap.add_argument("--data", default="data/full", help="directory with the generated CSVs")
    ap.add_argument("--strict-cardinality", action="store_true",
                    help="add UNIQUE constraints for the documented 1:1 relationships")
    a = ap.parse_args(argv)
    rep = export(a.data, a.strict_cardinality)
    for t, n in rep["row_counts"].items():
        print(f"  {t:<26}{n:>8}")
    c = rep["sql_load_check"]
    print(f"SQL load: {'ok' if c['loaded'] else 'FAILED ' + c.get('error', '')}   "
          f"row-count mismatches: {len(c['row_count_mismatches'])}   FK violations: {c['foreign_key_violations']}")
    ok = passed(rep)
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())