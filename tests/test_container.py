"""Check delivery inputs using Docker's actual build-context filtering."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_container_context_retains_supported_cards_and_excludes_private_files(tmp_path):
    docker = shutil.which("docker")
    if not docker:
        pytest.skip("Docker is unavailable; this check uses its actual ignore semantics.")
    try:
        available = subprocess.run(
            [docker, "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        pytest.skip("The Docker daemon is unavailable.")
    if available.returncode:
        pytest.skip("The Docker daemon is unavailable.")

    context = tmp_path / "context"
    context.mkdir()
    shutil.copyfile(ROOT / ".dockerignore", context / ".dockerignore")
    # scratch and a local output need neither a registry image nor network access.
    (context / "Dockerfile").write_text("FROM scratch\nCOPY . /\n", encoding="utf-8")
    public = {
        "data/knowledge/root.md",
        "data/knowledge/upper.MD",
        "data/knowledge/source.txt",
        "data/knowledge/upper_source.TXT",
        "data/knowledge/section/nested.md",
        "data/knowledge/section/deeper/nested.TxT",
        "src/chem_agent/example.py",
    }
    private = {
        ".env",
        "runs/private.json",
        "build/private.md",
        "data/knowledge/unsupported.json",
        "data/knowledge/section/.env.production",
        "data/knowledge/section/.local/private.txt",
        "data/knowledge/section/runs/private.md",
        "data/knowledge/section/.venv/private.py",
        "data/knowledge/section/build/private.md",
        "data/knowledge/section/dist/private.txt",
        "data/knowledge/section/__pycache__/private.pyc",
        "data/knowledge/section/.pytest_cache/private.txt",
        "data/knowledge/section/.ruff_cache/private.md",
        "data/knowledge/section/.git/private.txt",
        "src/chem_agent/.env.production",
        "src/chem_agent/.local/private.txt",
        "src/chem_agent/runs/private.json",
        "src/chem_agent/__pycache__/private.pyc",
    }
    for name in public | private:
        path = context / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture content\n", encoding="utf-8")

    output = tmp_path / "output"
    completed = subprocess.run(
        [
            docker,
            "build",
            "--network=none",
            "--output",
            f"type=local,dest={output}",
            str(context),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    included = {path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()}
    assert public <= included
    assert private.isdisjoint(included)
