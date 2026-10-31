"""Submission hygiene: no placeholder text, required documents present, commands in the README are real."""
import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDERS = ("(to be filled)", "One-paragraph summary", "Work in progress", "[CONFIRM", "[FILL", "TODO")
REQUIRED = ["README.md", "LICENSE", "docs/data_dictionary.md", "docs/design_decisions.md",
            "docs/source_manifest.md", "docs/validation_summary.md", "docs/model_report.md", "docs/ai_usage.md"]


@pytest.mark.parametrize("rel", REQUIRED)
def test_required_documents_exist_and_are_not_empty(rel):
    p = ROOT / rel
    assert p.exists() and len(p.read_text(encoding="utf-8").strip()) > 200, rel


@pytest.mark.parametrize("rel", ["README.md", "docs/source_manifest.md", "docs/ai_usage.md"])
def test_no_placeholder_text_left(rel):
    text = (ROOT / rel).read_text(encoding="utf-8")
    assert not [p for p in PLACEHOLDERS if p in text], rel


def test_source_manifest_states_no_external_data():
    assert "No external data was used" in (ROOT / "docs/source_manifest.md").read_text(encoding="utf-8")


def test_dependency_lockfile_is_portable_utf8_with_exact_pins():
    raw = (ROOT / "requirements-lock.txt").read_bytes()
    text = raw.decode("utf-8")
    assert not raw.startswith(b"\xef\xbb\xbf")
    requirements = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    assert requirements and all("==" in requirement for requirement in requirements)


def test_readme_commands_point_at_real_modules_and_files():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for mod in set(re.findall(r"python -m (yottaflex[\w.]*)", text)):
        assert importlib.util.find_spec(mod) is not None, mod
    for script in set(re.findall(r"python (scripts/[\w./-]+\.py)", text)):
        assert (ROOT / script).exists(), script
    for link in set(re.findall(r"\]\((docs/[\w./-]+)\)", text)):
        assert (ROOT / link).exists(), link


def test_single_pytest_config_and_tests_live_in_tests_dir():
    assert (ROOT / "pytest.ini").exists() and not (ROOT / "src" / "Pytest.ini").exists()
    assert not list((ROOT / "src").rglob("test_*.py"))
