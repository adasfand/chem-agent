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
    "Dockerfile",
    "compose.yaml",
    ".dockerignore",
    "化工知识增强与工具调用_代码交付初步方案.md",
}
DIRECTORIES = {"src", "data", "examples", "tests", "scripts", "docs"}
EXCLUDED_PARTS = {
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".DS_Store",
    ".env",
    ".venv",
    ".local",
    ".git",
    "runs",
    "build",
    "dist",
    "node_modules",
    ".vite",
    "coverage",
    ".idea",
}


def main():
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    output = ROOT / "dist" / f"chem-agent-demo-{version}.zip"
    output.parent.mkdir(exist_ok=True)
    resolved_root = ROOT.resolve()
    included = []
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        candidates = [ROOT / name for name in FILES]
        for name in DIRECTORIES:
            directory = ROOT / name
            if not directory.is_symlink():
                candidates.extend(directory.rglob("*"))
        for path in sorted(candidates):
            relative = path.relative_to(ROOT)
            if (
                not path.is_file()
                or path.is_symlink()
                or not path.resolve().is_relative_to(resolved_root)
            ):
                continue
            if relative.parts[0] not in DIRECTORIES and str(relative) not in FILES:
                continue
            if (
                any(part in EXCLUDED_PARTS or part.startswith(".env.") for part in relative.parts)
                and str(relative) != ".env.example"
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
