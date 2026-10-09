"""Offline delivery checks observe business output and archive boundaries."""

import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from chem_agent.config import Settings
from chem_agent.report import render_report
from scripts import package
from scripts.demo_offline import run_demo

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("flow, expected", [(1000, 46.44444444444444), (2000, 92.88888888888889)])
def test_offline_demo_uses_real_evidence_and_changed_inputs(tmp_path, flow, expected):
    shutil.copytree(ROOT / "data", tmp_path / "data")
    result = run_demo(Settings(root=tmp_path), flow_kg_h=flow)
    assert result["mode"] == "offline_demo"
    assert result["status"] == "completed"
    assert result["model_requests"] == []
    assert "运行模式" in render_report(result) and "offline_demo" in render_report(result)
    assert result["citations"] and result["evidence"]
    call = result["calls"][-1]
    assert call["output"]["heat_duty_kw"] == pytest.approx(expected)
    assert call["input_refs"][0]["ref"] == "s2.value"
    persisted = json.loads(Path(result["trace_path"]).read_text())
    assert persisted["mode"] == "offline_demo"
    assert persisted["latency_ms"] >= 0


def test_package_excludes_private_nested_files_and_cache(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text('[project]\nversion="test"\n')
    (tmp_path / ".env.example").write_text("DEEPSEEK_API_KEY=\n")
    for name in (
        "src/public.py",
        "src/.env.production",
        "src/.local/key.txt",
        "docs/runs/private.json",
        "scripts/.venv/private.py",
        "tests/test_ok.py",
        "docs/ARCHITECTURE.md",
        "Dockerfile",
        "compose.yaml",
        ".dockerignore",
        "化工知识增强与工具调用_代码交付初步方案.md",
    ):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("example")
    outside = tmp_path / "private.txt"
    outside.write_text("private")
    (tmp_path / "src" / "linked.txt").symlink_to(outside)
    monkeypatch.setattr(package, "ROOT", tmp_path)
    package.main()
    with zipfile.ZipFile(tmp_path / "dist" / "chem-agent-demo-test.zip") as archive:
        names = set(archive.namelist())
    assert "chem-agent-demo/src/public.py" in names
    assert "chem-agent-demo/.env.example" in names
    assert "chem-agent-demo/Dockerfile" in names
    assert "chem-agent-demo/compose.yaml" in names
    assert "chem-agent-demo/.dockerignore" in names
    assert "chem-agent-demo/化工知识增强与工具调用_代码交付初步方案.md" in names
    assert not any(
        "private" in name or "linked" in name or ".env.production" in name for name in names
    )


@pytest.mark.parametrize("directory", ["data", "docs"])
def test_package_excludes_symlinked_allowlist_roots(tmp_path, monkeypatch, directory):
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text('[project]\nversion="test"\n')
    private = tmp_path / "private"
    private.mkdir()
    (private / "private-record.txt").write_text("private sample content")
    (project / directory).symlink_to(private, target_is_directory=True)
    (project / "src").mkdir()
    (project / "src" / "public.py").write_text("example")
    monkeypatch.setattr(package, "ROOT", project)
    package.main()
    with zipfile.ZipFile(project / "dist" / "chem-agent-demo-test.zip") as archive:
        names = set(archive.namelist())
    assert "chem-agent-demo/src/public.py" in names
    assert not any(name.startswith(f"chem-agent-demo/{directory}/") for name in names)
    assert not any("private" in name for name in names)


@pytest.mark.parametrize("arguments", [{"flow_kg_h": -1}, {"specific_heat": 0}])
def test_offline_demo_validation_failure_finishes_the_trace(tmp_path, arguments):
    shutil.copytree(ROOT / "data", tmp_path / "data")
    result = run_demo(Settings(root=tmp_path), **arguments)
    assert result["status"] == "failed"
    assert result["mode"] == "offline_demo"
    assert result["model_requests"] == []
    assert result["calls"][-1]["status"] == "failed"
    assert "output" not in result["calls"][-1]
    assert result["finished_at"] and result["latency_ms"] >= 0
    persisted = json.loads(Path(result["trace_path"]).read_text())
    assert persisted["status"] == "failed"
    assert "执行未完成" in render_report(result)


def test_offline_demo_cli_exports_failure_report_and_returns_nonzero(tmp_path):
    shutil.copytree(ROOT / "data", tmp_path / "data")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copyfile(ROOT / "scripts" / "demo_offline.py", scripts / "demo_offline.py")
    environment = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    completed = subprocess.run(
        [sys.executable, str(scripts / "demo_offline.py"), "--cp", "0"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 1
    assert "Traceback" not in completed.stderr
    summary = json.loads(completed.stdout)
    assert summary["status"] == "failed" and summary["mode"] == "offline_demo"
    assert json.loads(Path(summary["trace"]).read_text())["status"] == "failed"
    assert "执行未完成" in Path(summary["report"]).read_text()
