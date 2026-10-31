"""Apply the Phase 7 changes to your repository.

Run from the repository root:   python phase7/apply_phase7.py
It is idempotent (safe to run twice) and prints every change it makes. Review with `git diff` afterwards.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FILES = HERE / "files"
ROOT = Path.cwd()

# (file, exact old text, new text). Matching tolerates CRLF files (Windows checkouts).
EDITS = [
    ("src/yottaflex/labels.py",
     "    eligible = o.index.to_series().isin(have)\n",
     "    # employed at the cutoff: has a snapshot there AND had not already left (a post-exit snapshot must not count)\n"
     "    employed = o[\"termination_date\"].isna() | (o[\"termination_date\"] > pd.Timestamp(cutoff))\n"
     "    eligible = o.index.to_series().isin(have) & employed\n"),
    ("src/yottaflex/validate/rules.py",
     "    m = pd.Series(np.asarray(mask, dtype=object), index=df.index).fillna(False).astype(bool)\n",
     "    m = pd.Series(np.asarray(mask, dtype=object), index=df.index)\n"
     "    m = m.where(m.notna(), False).astype(bool)          # NA counts as \"no violation\" (no FutureWarning downcast)\n"),
    ("tests/test_generate.py",
     "            assert not row.field\n",
     "            assert pd.isna(row.field) or row.field == \"\"     # empty cell reads back as \"\" or NaN depending on pandas\n"),
]
DELETE = ["src/yottaflex/model/labels.py", "src/Pytest.ini"]
MOVE = [("src/yottaflex/model/test_model.py", "tests/test_model.py"),
        ("src/yottaflex/01_planning.md", "docs/01_planning.md")]
GITIGNORE = ["project_code*.txt", "*.egg-info/", ".pytest_cache/", ".venv/", "__pycache__/"]


def edit(rel: str, old: str, new: str) -> None:
    p = ROOT / rel
    if not p.exists():
        sys.exit(f"missing {rel}: run this from the repository root")
    text = p.read_bytes().decode("utf-8")
    crlf = "\r\n" in text
    o, n = (old.replace("\n", "\r\n"), new.replace("\n", "\r\n")) if crlf else (old, new)
    if n in text:
        print(f"  already applied  {rel}")
    elif o in text:
        p.write_bytes(text.replace(o, n, 1).encode("utf-8"))
        print(f"  edited           {rel}")
    else:
        sys.exit(f"cannot find the expected text in {rel}; make this edit by hand")


def main() -> None:
    if not (ROOT / "src" / "yottaflex").is_dir():
        sys.exit("run from the repository root (the folder that contains src/yottaflex)")
    print("edits")
    for rel, old, new in EDITS:
        edit(rel, old, new)

    print("moves and deletes")
    for src, dst in MOVE:
        s, d = ROOT / src, ROOT / dst
        if s.exists():
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(s), str(d))
            print(f"  moved            {src} -> {dst}")
        else:
            print(f"  already moved    {src}")
    for rel in DELETE:
        p = ROOT / rel
        if p.exists():
            p.unlink()
            print(f"  deleted          {rel}")

    print("new and replaced files")
    for f in sorted(FILES.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(FILES)
        dst = ROOT / rel
        if dst.exists() and dst.read_bytes() == f.read_bytes():
            continue
        if (rel.as_posix() == "docs/ai_usage.md" and dst.exists() and dst.stat().st_size > 500
                and "[FILL" not in dst.read_text(encoding="utf-8")):
            print(f"  kept your        {rel} (no [FILL] markers left)")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(f, dst)
        print(f"  wrote            {rel.as_posix()}")

    gi = ROOT / ".gitignore"
    have = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
    add = [line for line in GITIGNORE if line not in have]
    if add:
        with gi.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(("\n" if have and have[-1] != "" else "") + "\n".join(add) + "\n")
        print(f"  .gitignore       added {', '.join(add)}")

    print("\nDone. Next: python -m pytest   (test_docs fails until every [FILL ...] in docs/ai_usage.md is replaced)")


if __name__ == "__main__":
    main()
