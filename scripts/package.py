"""Create a source delivery archive from an explicit allowlist."""

import hashlib
import os
import tomllib
import zipfile
from collections.abc import Iterator
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
WEB = Path("src/chem_agent/web")
WEB_FILES = {
    "package.json",
    "package-lock.json",
    "index.html",
    "vite.config.ts",
    "vitest.config.ts",
    "tsconfig.json",
    "tsconfig.app.json",
    "tsconfig.node.json",
    "eslint.config.js",
    "eslint.config.mjs",
    ".prettierrc.json",
    ".prettierignore",
    ".npmrc",
    ".gitignore",
}
WEB_DIRECTORIES = {"src", "public", "dist", "tests", "scripts"}
EXCLUDED_DIRECTORIES = {
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".vite",
    ".vite-temp",
    ".cache",
    ".git",
    ".idea",
    ".venv",
    ".local",
    "coverage",
    "test-results",
    "playwright-report",
}


def source_files(root: Path) -> Iterator[Path]:
    """Walk only approved directories, pruning installed dependencies before traversal."""
    for directory, subdirectories, filenames in os.walk(root, followlinks=False):
        current = Path(directory)
        relative = current.relative_to(root)
        subdirectories[:] = sorted(
            name
            for name in subdirectories
            if name not in EXCLUDED_DIRECTORIES
            and not (current / name).is_symlink()
            and (relative != Path(".") or name in DIRECTORIES)
            and (relative != WEB or name in WEB_DIRECTORIES)
        )
        for name in sorted(filenames):
            path = current / name
            if path.is_symlink() or not path.is_file():
                continue
            if relative == Path(".") and name not in FILES:
                continue
            if relative == WEB and name not in WEB_FILES:
                continue
            if name.startswith(".env") and name != ".env.example":
                continue
            if name == ".DS_Store" or path.suffix in {".pyc", ".tmp", ".tsbuildinfo"}:
                continue
            yield path


def main() -> None:
    required = [ROOT / WEB / "package.json", ROOT / WEB / "package-lock.json"]
    if any(not path.is_file() for path in required):
        raise SystemExit(
            "Frontend package.json and package-lock.json are required for source delivery"
        )
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    output = ROOT / "dist" / f"chem-agent-demo-{version}.zip"
    output.parent.mkdir(exist_ok=True)
    included = []
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in source_files(ROOT):
            relative = path.relative_to(ROOT)
            archive.write(path, str(Path("chem-agent-demo") / relative))
            included.append(str(relative))
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".zip.sha256").write_text(f"{digest}  {output.name}\n", encoding="utf-8")
    print(f"Created {output.name}: {len(included)} files, {output.stat().st_size} bytes")
    print(f"SHA256: {digest}")


if __name__ == "__main__":
    main()
