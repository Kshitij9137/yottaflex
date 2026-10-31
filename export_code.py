from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = PROJECT_DIR / "project_code.txt"

INCLUDE_EXTENSIONS = {".py", ".md", ".toml", ".ini", ".cfg", ".yml", ".yaml"}
INCLUDE_NAMES = {"LICENSE", "Makefile"}
EXCLUDE_DIRS = {
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "build",
    "data",
    "dist",
    "env",
    "venv",
    "yottaflex.egg-info",
}


def included_files() -> list[Path]:
    files = []
    for path in PROJECT_DIR.rglob("*"):
        relative_path = path.relative_to(PROJECT_DIR)
        if not path.is_file() or EXCLUDE_DIRS.intersection(relative_path.parts):
            continue
        if path.suffix.lower() not in INCLUDE_EXTENSIONS:
            if path.name not in {"requirements.txt", "requirements-lock.txt"} | INCLUDE_NAMES:
                continue
        if ".min." in path.name or path == OUTPUT_FILE:
            continue
        files.append(path)
    return sorted(files, key=lambda path: path.relative_to(PROJECT_DIR).as_posix().lower())


def read_text(path: Path) -> str:
    content = path.read_bytes()
    encoding = "utf-16" if content.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8"
    return content.decode(encoding)


def main() -> None:
    files = included_files()
    total_lines = 0

    with OUTPUT_FILE.open("w", encoding="utf-8", newline="\n") as outfile:
        outfile.write("PROJECT CODE CONTEXT\n")
        outfile.write("Paths are relative to the project root.\n")
        outfile.write(f"Files included: {len(files)}\n")
        outfile.write("\nIncluded files:\n")
        for path in files:
            outfile.write(f"- {path.relative_to(PROJECT_DIR).as_posix()}\n")

        for path in files:
            content = read_text(path)
            outfile.write("\n" + "=" * 70 + "\n")
            outfile.write(f"FILE: {path.relative_to(PROJECT_DIR).as_posix()}\n")
            outfile.write("=" * 70 + "\n")
            outfile.write(content)
            if content and not content.endswith("\n"):
                outfile.write("\n")
            total_lines += len(content.splitlines())

    print(f"Exported {len(files)} files and {total_lines} lines to {OUTPUT_FILE.name}.")


if __name__ == "__main__":
    main()
