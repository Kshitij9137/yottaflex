"""Phase 6/7 tests: JSON and SQL exports are complete, join-valid, deterministic and free of ground truth."""
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from yottaflex import config
from yottaflex.export import export, passed, schema_sql
from yottaflex.generate.__main__ import main as generate_main
from yottaflex.io import read_tables
from yottaflex.validate.schema import SCHEMA

N = 500


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("data")
    assert generate_main(["--n-employees", str(N), "--seed", str(config.SEED), "--out", str(d)]) == 0
    return d


@pytest.fixture(scope="module")
def report(data_dir):
    return export(data_dir)


@pytest.fixture(scope="module")
def db(data_dir, report):
    con = sqlite3.connect(":memory:")
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript((data_dir / "export" / "schema.sql").read_text(encoding="utf-8"))
    con.executescript((data_dir / "export" / "seed.sql").read_text(encoding="utf-8"))
    return con


def test_export_loads_and_reconciles_with_the_csvs(report):
    assert passed(report)
    check = report["sql_load_check"]
    assert check["loaded"] and check["row_count_mismatches"] == {} and check["foreign_key_violations"] == 0
    assert set(report["row_counts"]) == set(SCHEMA)


def test_row_counts_match_csv_json_and_sql(data_dir, report, db):
    csv_tables = read_tables(data_dir)
    for table in SCHEMA:
        n = len(csv_tables[table])
        assert report["row_counts"][table] == n
        assert db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] == n
        assert len(json.loads((data_dir / "export" / "json" / f"{table}.json").read_text(encoding="utf-8"))) == n


def test_strict_cardinality_also_loads(data_dir):
    copy = data_dir.parent / "strict_copy"
    shutil.copytree(data_dir, copy, dirs_exist_ok=True)
    assert passed(export(copy, strict=True))
    assert "UNIQUE" in (copy / "export" / "schema.sql").read_text(encoding="utf-8")


def test_every_schema_foreign_key_becomes_a_sql_constraint():
    expected = sum(1 for cols in SCHEMA.values() for c in cols if c.fk)
    assert schema_sql(strict=False).count("FOREIGN KEY") == expected > 10


def test_constraints_are_live_not_decorative(db):
    with pytest.raises(sqlite3.IntegrityError):               # orphan parent
        db.execute("INSERT INTO tenure_snapshot (snapshot_id, employee_id) VALUES ('SNAP-X', 'EMP-999999')")
    db.rollback()
    first = db.execute("SELECT employee_id FROM employee LIMIT 1").fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError):               # duplicate primary key
        db.execute('INSERT INTO employee (employee_id) VALUES (?)', (first,))
    db.rollback()


def test_ground_truth_never_enters_the_database_files(data_dir, report):
    assert "ground_truth" not in SCHEMA
    for name in ("schema.sql", "seed.sql"):
        text = (data_dir / "export" / name).read_text(encoding="utf-8").lower()
        assert "ground_truth" not in text and "issue_type" not in text and "is_injected" not in text
    assert not (data_dir / "export" / "json" / "ground_truth.json").exists()
    assert (data_dir / "ground_truth.json").exists()          # kept separately, as the brief requires


def test_json_values_are_typed_and_nulls_are_real(data_dir):
    emp = json.loads((data_dir / "export" / "json" / "employee.json").read_text(encoding="utf-8"))
    assert list(emp[0]) == [c.name for c in SCHEMA["employee"]]
    assert isinstance(emp[0]["hire_date"], str) and len(emp[0]["hire_date"]) == 10
    role = json.loads((data_dir / "export" / "json" / "role.json").read_text(encoding="utf-8"))
    assert isinstance(role[0]["level"], int) and isinstance(role[0]["is_people_manager_track"], bool)
    sv = json.loads((data_dir / "export" / "json" / "engagement_survey.json").read_text(encoding="utf-8"))
    gt = read_tables(data_dir)["ground_truth"]
    injected = set(gt.loc[gt["issue_subtype"] == "skipped_scored_zero", "record_id"])      # labelled anomaly
    skipped = [r for r in sv if r["response_status"] == "Skipped"]
    assert skipped and injected
    for r in skipped:
        if r["survey_id"] in injected:
            assert r["engagement_score"] == 0.0                   # the anomaly survives export, still labelled
        else:
            assert r["engagement_score"] is None and r["q_intent_to_stay"] is None


def test_no_sensitive_column_in_exported_schema(data_dir):
    text = (data_dir / "export" / "schema.sql").read_text(encoding="utf-8").lower()
    for banned in ("gender", "ethnicity", "religion", "caste", "nationality", "disability", "pin_code", "age"):
        assert f'"{banned}"' not in text


def test_export_bytes_are_deterministic_and_use_lf_only(data_dir, report):
    first = dict(report["sha256"])
    second = export(data_dir)["sha256"]
    assert first == second
    for rel in first:
        raw = (data_dir / "export" / rel).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == first[rel]
        assert b"\r" not in raw, rel
