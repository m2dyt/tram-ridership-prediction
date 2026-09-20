"""Check local Markdown links and per-directory documentation for maintained files."""

import re
import subprocess
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]


def main():
    listed = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT, text=True
    )
    files = sorted({Path(name) for name in listed.splitlines() if (ROOT / name).is_file()})
    errors = []
    for path in files:
        if path.name != "README.md":
            readme = ROOT / path.parent / "README.md"
            if not readme.is_file() or path.name not in readme.read_text(encoding="utf-8"):
                errors.append(f"Undocumented file: {path.as_posix()}")
        if path.suffix == ".md":
            text = (ROOT / path).read_text(encoding="utf-8")
            for target in re.findall(r"\]\(([^)]+)\)", text):
                if target.startswith(("http:", "https:", "#", "mailto:")):
                    continue
                local = unquote(target.split("#", 1)[0].strip("<>"))
                if local and not (ROOT / path.parent / local).exists():
                    errors.append(f"Broken link: {path.as_posix()} -> {target}")
    for error in errors:
        print(error)
    if not errors:
        print(f"Documentation verified: {len(files)} maintained files")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
