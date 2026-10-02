"""Create a source delivery archive from an explicit allowlist."""

import hashlib
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    "README.md",
    "AGENTS.md",
    "pyproject.toml",
    "uv.lock",
    ".env.example",
    ".gitignore",
    ".gitattributes",
    "CHANGELOG.md",
    "app.py",
    "cli.py",
    "start.sh",
    "start.bat",
    "THIRD_PARTY_NOTICES.md",
}
DIRECTORIES = {"src", "data", "examples", "tests", "scripts", "docs"}


def main():
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    output = ROOT / "dist" / f"chem-agent-demo-{version}.zip"
    output.parent.mkdir(exist_ok=True)
    included = []
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(ROOT.rglob("*")):
            relative = path.relative_to(ROOT)
            if not path.is_file() or path.is_symlink():
                continue
            if relative.parts[0] not in DIRECTORIES and str(relative) not in FILES:
                continue
            if any(
                part in {"__pycache__", ".pytest_cache", ".DS_Store", ".env"}
                for part in relative.parts
            ):
                continue
            if path.suffix in {".pyc", ".tmp"}:
                continue
            archive.write(path, str(Path("chem-agent-demo") / relative))
            included.append(str(relative))
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".zip.sha256").write_text(f"{digest}  {output.name}\n", encoding="utf-8")
    print(f"Created {output.name}: {len(included)} files, {output.stat().st_size} bytes")
    print(f"SHA256: {digest}")


if __name__ == "__main__":
    main()
