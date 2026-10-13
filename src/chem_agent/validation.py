"""Source identity and labels used by optional developer validation scripts."""

import hashlib
import os
from pathlib import Path

CASE_TITLES = {
    "knowledge": "专业知识检索与增强问答",
    "heat": "显热计算及真实结果回用",
    "heat_changed_input": "修改流量后重新计算",
    "balance": "混合物料衡算",
    "units": "压力单位换算",
    "missing_parameter": "缺少比热时请求补充",
    "follow_up": "同一对话补充参数",
    "incompatible_units": "不兼容量纲处理",
    "mixed_heat": "混合、换算与加热组合任务",
    "temperature_explanation": "温度换算与概念解释",
}


def source_identity(root: Path) -> dict:
    """Hash runtime sources, frontend, knowledge, example and delivery configuration."""
    paths = {
        root / name
        for name in (
            "pyproject.toml",
            "uv.lock",
            ".env.example",
            "README.md",
            "AGENTS.md",
            "app.py",
            "cli.py",
            "start.bat",
            "start.sh",
            "Dockerfile",
            "compose.yaml",
            ".dockerignore",
            ".gitignore",
        )
    }
    for directory, subdirectories, files in os.walk(root / "src", followlinks=False):
        subdirectories[:] = [
            name
            for name in subdirectories
            if name not in {"node_modules", "__pycache__", ".venv", "dist", "build"}
        ]
        paths.update(Path(directory) / name for name in files if name.endswith(".py"))
    paths.update((root / "scripts").glob("*.py"))
    for directory in (
        "data/knowledge",
        "examples",
        "src/chem_agent/web/src",
        "src/chem_agent/web/client",
    ):
        paths.update(path for path in (root / directory).rglob("*") if path.is_file())
    for name in (
        "package.json",
        "package-lock.json",
        "vite.config.ts",
        "tsconfig.json",
        ".npmrc",
        ".gitignore",
        "eslint.config.js",
    ):
        paths.add(root / "src/chem_agent/web" / name)
    digest = hashlib.sha256()
    count = 0
    for path in sorted(paths):
        if not path.is_file() or path.is_symlink() or "__pycache__" in path.parts:
            continue
        for part in (path.relative_to(root).as_posix().encode(), path.read_bytes()):
            digest.update(len(part).to_bytes(8, "big"))
            digest.update(part)
        count += 1
    return {"source_sha256": digest.hexdigest(), "files": count}
