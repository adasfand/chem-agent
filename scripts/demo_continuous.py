"""Execute the delivery's continuous-blending example through real offline tools."""

from __future__ import annotations

import json
from pathlib import Path

from chem_agent.config import Settings
from chem_agent.execution import Execution
from chem_agent.knowledge import KnowledgeBase
from chem_agent.tools import make_tools
from chem_agent.trace import RunTrace

ROOT = Path(__file__).resolve().parents[1]


def run_continuous_demo(settings: Settings) -> dict:
    question = json.loads((ROOT / "examples/tasks.json").read_text(encoding="utf-8"))[0]["question"]
    knowledge = KnowledgeBase(settings.knowledge_dir)
    trace = RunTrace(
        settings.runs_dir,
        question,
        {"model": "not_used", "workflow": "continuous_blending_offline"},
        knowledge.version,
        mode="offline_demo",
    )
    execution = Execution(knowledge, trace, [question], require_retrieval=True)
    tools = {tool.name: tool for tool in make_tools(execution)}
    actions = [
        (
            "search_knowledge",
            "检索混合与加热依据",
            [],
            {"query": "质量衡算 质量分数 显热热负荷 变比热 温差 体积流量", "top_k": 5},
        ),
        (
            "calc_mass_balance",
            "混合总量与溶质衡算",
            ["s1"],
            {
                "streams": [
                    {"flow_kg_h": 1000, "mass_fraction": 0.12},
                    {"flow_kg_h": 2000, "mass_fraction": 0.03},
                ]
            },
        ),
        (
            "calc_temperature_change",
            "第一级温差",
            [],
            {"inlet_temperature_c": 25, "outlet_temperature_c": 55},
        ),
        (
            "calc_temperature_change",
            "第二级温差",
            [],
            {"inlet_temperature_c": 55, "outlet_temperature_c": 75},
        ),
        (
            "calc_temperature_change",
            "总温差",
            [],
            {"inlet_temperature_c": 25, "outlet_temperature_c": 75},
        ),
        (
            "convert_units",
            "质量流量换算",
            ["s2"],
            {"value": {"$ref": "s2.total_flow_kg_h"}, "from_unit": "kg/h", "to_unit": "kg/s"},
        ),
        (
            "calc_heat_duty",
            "第一级热负荷",
            ["s1", "s3", "s6"],
            {
                "mass_flow_kg_s": {"$ref": "s6.value"},
                "specific_heat_kj_kg_k": 3.8,
                "delta_t_k": {"$ref": "s3.delta_t_k"},
            },
        ),
        (
            "calc_heat_duty",
            "第二级热负荷",
            ["s1", "s4", "s6"],
            {
                "mass_flow_kg_s": {"$ref": "s6.value"},
                "specific_heat_kj_kg_k": 3.8,
                "delta_t_k": {"$ref": "s4.delta_t_k"},
            },
        ),
        (
            "calc_heat_duty",
            "两级总热负荷",
            ["s1", "s5", "s6"],
            {
                "mass_flow_kg_s": {"$ref": "s6.value"},
                "specific_heat_kj_kg_k": 3.8,
                "delta_t_k": {"$ref": "s5.delta_t_k"},
            },
        ),
        (
            "calc_volume_flow",
            "缓冲罐工况体积流量",
            ["s2"],
            {"mass_flow_kg_h": {"$ref": "s2.total_flow_kg_h"}, "density_kg_m3": 1050},
        ),
        (
            "calc_residence_time",
            "平均停留时间",
            ["s10"],
            {"vessel_volume_m3": 1.5, "volume_flow_m3_h": {"$ref": "s10.volume_flow_m3_h"}},
        ),
    ]
    try:
        tools["set_plan"](
            steps=[
                {"step_id": f"s{i}", "tool_name": tool, "goal": goal, "depends_on": dependencies}
                for i, (tool, goal, dependencies, _) in enumerate(actions, 1)
            ]
        )
        for i, (tool, _, _, arguments) in enumerate(actions, 1):
            tools[tool](step_id=f"s{i}", arguments=arguments)
        tools["final_answer"](
            answer="连续配料综合题的十一个步骤已完成。",
            status="completed",
            citations=[item["chunk_id"] for item in trace.data["evidence"]],
            explanation=(
                "质量分数以溶液质量为基准，质量浓度以溶液体积为基准，二者通过同工况密度联系。"
                "热量表示累计能量，热负荷表示单位时间的传热功率。"
                "摄氏温度与热力学温度具有固定偏移，两种温标的温差数值相同。"
                "恒比热显热公式用于稳态单相且比热恒定的过程；"
                "相变计算补充压力、相态和相变焓，变比热计算采用适用温区内的热容积分。"
            ),
        )
    except ValueError as exc:
        trace.finish("failed", str(exc))
    return trace.result()
