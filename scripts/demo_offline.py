"""Run an explicit fixed tool workflow without credentials, downloads or a model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from chem_agent.config import Settings
from chem_agent.execution import Execution
from chem_agent.knowledge import KnowledgeBase
from chem_agent.report import render_report
from chem_agent.tools import make_tools
from chem_agent.trace import RunTrace

ROOT = Path(__file__).resolve().parents[1]


def run_demo(
    settings: Settings, flow_kg_h: float = 1000, specific_heat: float = 4.18, delta_t: float = 40
) -> dict:
    """Exercise real retrieval, registry, calculation, references and persistence.

    This fixed offline workflow does not test model planning or LightRAG quality.
    All physical parameters come from this function's explicit caller inputs.
    """
    knowledge = KnowledgeBase(settings.knowledge_dir)
    trace = RunTrace(
        settings.runs_dir,
        f"显热演示：流量 {flow_kg_h} kg/h，比热 {specific_heat} kJ/(kg·K)，温差 {delta_t} K。",
        {"model": "not_used", "workflow": "fixed_offline_demo"},
        knowledge.version,
        mode="offline_demo",
    )
    tools = {tool.name: tool for tool in make_tools(Execution(knowledge, trace))}
    try:
        tools["set_plan"](
            steps=[
                {"step_id": "s1", "goal": "检索公式和边界", "tool_name": "search_knowledge"},
                {"step_id": "s2", "goal": "换算质量流量", "tool_name": "convert_units"},
                {
                    "step_id": "s3",
                    "goal": "使用真实换算结果计算显热",
                    "tool_name": "calc_heat_duty",
                    "depends_on": ["s1", "s2"],
                },
            ]
        )
        found = tools["search_knowledge"](
            step_id="s1", arguments={"query": "显热热负荷公式适用条件", "top_k": 3}
        )["output"]
        if not found["hits"]:
            tools["final_answer"](
                answer="当前资料没有显热依据。", status="no_evidence", citations=[]
            )
            return trace.result()
        tools["convert_units"](
            step_id="s2", arguments={"value": flow_kg_h, "from_unit": "kg/h", "to_unit": "kg/s"}
        )
        heat = tools["calc_heat_duty"](
            step_id="s3",
            arguments={
                "mass_flow_kg_s": {"$ref": "s2.value"},
                "specific_heat_kj_kg_k": specific_heat,
                "delta_t_k": delta_t,
            },
        )["output"]
        tools["final_answer"](
            answer=f"工具计算热负荷为 {heat['heat_duty_kw']:.12g} kW。"
            "按稳态、恒比热、无相变、无反应热及无热损失计算。",
            status="completed",
            citations=[hit["chunk_id"] for hit in found["hits"]],
        )
    except ValueError as exc:
        trace.finish("failed", f"离线演示输入或执行校验失败：{exc}")
    return trace.result()


def main() -> int:
    parser = argparse.ArgumentParser(description="离线固定流程演示；不调用模型或下载索引")
    parser.add_argument("--flow", type=float, default=1000, help="质量流量 kg/h")
    parser.add_argument("--cp", type=float, default=4.18, help="用户给定比热 kJ/(kg·K)")
    parser.add_argument("--delta-t", type=float, default=40, help="温差 K")
    args = parser.parse_args()
    # Do not load .env or keys: this path always uses the local lexical retriever.
    result = run_demo(Settings(root=ROOT), args.flow, args.cp, args.delta_t)
    report = ROOT / "runs" / f"{result['run_id']}.md"
    report.write_text(render_report(result), encoding="utf-8")
    report.chmod(0o600)
    print(
        json.dumps(
            {
                "mode": result["mode"],
                "status": result["status"],
                "answer": result["answer"],
                "trace": result["trace_path"],
                "report": str(report),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
