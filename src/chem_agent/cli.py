import argparse
import json
from pathlib import Path

from .config import Settings
from .knowledge import KnowledgeIndex
from .trace import redact


def main():
    parser = argparse.ArgumentParser(description="化工知识增强与工具调用")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("build-index")
    search = commands.add_parser("search")
    search.add_argument("question")
    for name in ("ask", "task"):
        commands.add_parser(name).add_argument("question")
    example = commands.add_parser("example")
    example.add_argument("case_id", choices=["A", "B", "C"])
    args = parser.parse_args()
    settings = Settings.load(args.root)
    try:
        if args.command == "build-index":
            index = KnowledgeIndex.build(settings.knowledge_dir, settings.index_dir)
            result = {"documents": len(index.snapshot["documents"]), "chunks": len(index.chunks),
                      "corpus_sha256": index.snapshot["corpus_sha256"]}
        elif args.command == "search":
            index = KnowledgeIndex.load(settings.index_dir, settings.knowledge_dir)
            result = index.search(args.question, settings.top_k, settings.min_score)
        else:
            from .service import run_task
            question, mode = getattr(args, "question", ""), args.command
            if args.command == "example":
                cases = json.loads((settings.root / "examples/tasks.json").read_text(encoding="utf-8"))
                case = next(c for c in cases if c["id"] == args.case_id)
                question, mode = case["question"], case["mode"]
            result = run_task(settings, question, mode)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get("status") == "failed" else 0
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": redact(str(exc), (settings.api_key, settings.api_base))}, ensure_ascii=False))
        return 1
