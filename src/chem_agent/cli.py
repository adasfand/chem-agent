"""Reproducible command-line entry points."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from chem_agent.agent import run_task
from chem_agent.config import Settings
from chem_agent.knowledge import KnowledgeBase
from chem_agent.retrieval import HybridRetriever, build_index


def main() -> int:
    parser = argparse.ArgumentParser(description="化工知识增强与工具调用")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="项目根目录")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="检查本机环境和配置，不发起模型请求")
    commands.add_parser("index", help="从知识卡重建检索索引并输出资料清单")
    commands.add_parser("rag-index", help="使用 LightRAG 构建持久图谱与向量索引（调用模型）")
    commands.add_parser("rag-status", help="检查 LightRAG 索引是否与当前资料一致")
    search = commands.add_parser("search", help="离线检索知识卡")
    search.add_argument("query")
    run = commands.add_parser("run", help="调用实际模型处理任务（消耗 API 额度）")
    run.add_argument("question")
    run.add_argument("--follow-up", help="延续 runs/ 中指定 run_id 的上下文")
    commands.add_parser("ui", help="启动本机界面")
    args = parser.parse_args()
    try:
        settings = Settings.load(args.root)
        if args.command == "ui":
            from chem_agent.ui import launch

            launch(settings)
            return 0
        if args.command in {"doctor", "index", "search", "rag-index", "rag-status"}:
            knowledge = KnowledgeBase(settings.knowledge_dir)
            if args.command == "doctor":
                import platform

                result = {
                    "python": platform.python_version(),
                    "knowledge_cards": len(knowledge.inventory()),
                    "knowledge_version": knowledge.version,
                    "model": settings.model,
                    "credentials_configured": bool(settings.api_key),
                    "rag_index": HybridRetriever(settings).index_status,
                    "mode": "configuration_check_only",
                }
            elif args.command == "index":
                result = {"version": knowledge.version, "documents": knowledge.inventory()}
                output = settings.root / "build" / "knowledge_manifest.json"
                output.parent.mkdir(exist_ok=True)
                output.write_text(
                    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            elif args.command == "rag-index":
                result = build_index(settings)
            elif args.command == "rag-status":
                result = HybridRetriever(settings).index_status
            else:
                result = knowledge.search(args.query)
        else:
            history = []
            if args.follow_up:
                if not re.fullmatch(r"\d{8}T\d{6}-[a-f0-9]{10}", args.follow_up):
                    raise ValueError("无效的 run_id。")
                previous = json.loads(
                    (settings.runs_dir / f"{args.follow_up}.json").read_text(encoding="utf-8")
                )
                history = previous.get("history", []) + [
                    {"role": "user", "content": previous["question"]},
                    {"role": "assistant", "content": previous["answer"]},
                ]
            result = run_task(args.question, settings, history=history)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get("status") == "failed" else 0
    except ValueError as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    except OSError:
        print(
            json.dumps(
                {"status": "failed", "error": "文件操作失败，请检查项目文件或权限。"},
                ensure_ascii=False,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
